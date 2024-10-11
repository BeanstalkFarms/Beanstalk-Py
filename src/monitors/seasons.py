from abc import abstractmethod

from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class SeasonsMonitor(Monitor):
    def __init__(
        self, message_function, short_msgs=False, channel_to_wallets=None, prod=False, dry_run=None
    ):
        super().__init__(
            "Seasons", message_function, SUNRISE_CHECK_PERIOD, prod=prod, dry_run=dry_run
        )
        # Toggle shorter messages (must fit into <280 character safely).
        self.short_msgs = short_msgs
        # Read-only access to self.channel_to_wallets, which may be modified by other threads.
        self.channel_to_wallets = channel_to_wallets
        self._eth_event_client = EthEventsClient(EventClientType.SEASON)
        self.beanstalk_graph_client = BeanstalkGraphClient()
        self.bean_client = BeanClient()
        self.beanstalk_client = BeanstalkClient()
        # Most recent season processed. Do not initialize.
        self.current_season_id = None

    def _monitor_method(self):
        while self._thread_active:
            # Wait until the eligible for a sunrise.
            self._wait_until_expected_sunrise()
            # Once the sunrise is complete, get the season stats.
            current_season_stats, last_season_stats = self._block_and_get_seasons_stats()
            # A new season has begun.
            if current_season_stats:
                # Get the txn hash for this sunrise call
                incentive = self._eth_event_client.get_log_range(current_season_stats.sunrise_block)
                if len(incentive) > 0:
                    current_season_stats.sunrise_hash = incentive[0].txn_hash.hex()

                # Report season summary to users.
                self.message_function(
                    self.season_summary_string(
                        last_season_stats, current_season_stats, short_str=self.short_msgs
                    )
                )

    def _wait_until_expected_sunrise(self):
        """Wait until beanstalk is eligible for a sunrise call.

        Assumes sunrise timing cycle beings with Unix Epoch (1/1/1970 00:00:00 UTC).
        This is not exact since we do not bother with syncing local and graph time.
        """
        if self._dry_run == ["seasons"]:
            time.sleep(1)
            return

        seconds_until_next_sunrise = SEASON_DURATION - time.time() % SEASON_DURATION
        sunrise_ready_timestamp = time.time() + seconds_until_next_sunrise
        loop_count = 0
        while self._thread_active and time.time() < sunrise_ready_timestamp:
            if loop_count % 60 == 0:
                logging.info(
                    f"Blindly waiting {int((sunrise_ready_timestamp - time.time())/60)} "
                    "more minutes until expected sunrise."
                )
            loop_count += 1
            time.sleep(1)

    def _block_and_get_seasons_stats(self):
        """Blocks until sunrise is complete, then returns stats of current and previous season.

        Repeatedly makes graph calls to check sunrise status.
        """
        while self._thread_active:
            current_season_stats, last_season_stats = self.beanstalk_graph_client.seasons_stats()
            # If a new season is detected and sunrise was sufficiently recent.
            if (
                self.current_season_id != current_season_stats.season
                and int(current_season_stats.created_at) > time.time() - SEASON_DURATION / 2
            ) or self._dry_run:
                self.current_season_id = current_season_stats.season
                logging.info(f"New season detected with id {self.current_season_id}")
                return current_season_stats, last_season_stats
            time.sleep(self.query_rate)
        return None, None

    def season_summary_string(self, last_season_stats, current_season_stats, short_str=False):
        eth_price = self.beanstalk_client.get_token_usd_twap(WRAPPED_ETH, 3600)
        wsteth_price = self.beanstalk_client.get_token_usd_twap(WSTETH, 3600)
        wsteth_eth_price = wsteth_price / eth_price

        # new_farmable_beans = float(current_season_stats.silo_hourly_bean_mints)
        reward_beans = current_season_stats.reward_beans
        incentive_beans = current_season_stats.incentive_beans
        pod_rate = current_season_stats.pod_rate * 100
        price = current_season_stats.price
        delta_b = current_season_stats.delta_b
        issued_soil = current_season_stats.issued_soil
        last_weather = last_season_stats.temperature
        sown_beans = last_season_stats.sown_beans

        fertilizer_bought = self.beanstalk_graph_client.get_fertilizer_bought()
        percent_recap = self.beanstalk_client.get_recap_funded_percent()

        # Silo asset balances.
        current_silo_bdv = current_season_stats.deposited_bdv
        silo_assets_changes = self.beanstalk_graph_client.silo_assets_seasonal_changes(
            current_season_stats.pre_assets, last_season_stats.pre_assets
        )
        logging.info([a.final_season_asset for a in silo_assets_changes])
        silo_assets_changes.sort(
            key=lambda a: int(a.final_season_asset["depositedBDV"]), reverse=True
        )

        # Current state.
        ret_string = f"⏱ Season {last_season_stats.season + 1} has started!"
        ret_string += f"\n💵 Bean price is ${round_num(price, 4)}"

        # Well info.
        wells_info = []
        for well_addr in WHITELISTED_WELLS:
            wells_info.append(self.bean_client.get_pool_info(well_addr))

        # Sort highest liquidity wells first
        wells_info = sorted(wells_info, key=lambda x: x['liquidity'], reverse=True)

        ret_string += f'\n⚖️ {"+" if delta_b > 0 else ""}{round_num(delta_b, 0)} TWA deltaB'

        # Full string message.
        if not short_str:
            ret_string += f"\n🪙 TWA ETH price is ${round_num(eth_price, 2)}"
            ret_string += f"\n🪙 TWA wstETH price is ${round_num(wsteth_price, 2)} (1 wstETH = {round_num(wsteth_eth_price, 4)} ETH)"
            # Bean Supply stats.
            ret_string += f"\n\n**Supply**"
            ret_string += f"\n🌱 {round_num(reward_beans, 0, avoid_zero=True)} Beans minted"
            ret_string += f"\n☀️ {round_num(incentive_beans, 0)} Beans gm reward"
            ret_string += f"\n🚜 {round_num(sown_beans, 0, avoid_zero=True)} Beans Sown"

            # Liquidity stats.
            ret_string += f"\n\n**Liquidity**"

            for well_info in wells_info:
                ret_string += f"\n🌊 {SILO_TOKENS_MAP[well_info['pool'].lower()]}: ${round_num(token_to_float(well_info['liquidity'], 6), 0)} - "
                ret_string += (
                    f"_deltaB [{round_num(token_to_float(well_info['delta_b'], 6), 0)}], "
                )
                ret_string += f"price [${round_num(token_to_float(well_info['price'], 6), 4)}]_"

            # Silo balance stats.
            ret_string += f"\n\n**Silo**"
            ret_string += f"\n🏦 {round_num(current_silo_bdv, 0)} BDV in Silo"

            # Gets current and previous season seeds for each asset
            """
            TODO: Disabled this entire section until a fix for season block can be implemented
            This is preferable so the seasons can log in the meantime

            season_block = self.beanstalk_client.get_season_block()
            parallelized = []
            for asset_changes in silo_assets_changes:
                parallelized.append(lambda token=asset_changes.token: self.beanstalk_client.get_seeds(token))
                parallelized.append(lambda token=asset_changes.token, block=season_block - 1: self.beanstalk_client.get_seeds(token, block))

            seed_results = execute_lambdas(*parallelized)

            for i in range(len(silo_assets_changes)):

                asset_changes = silo_assets_changes[i]
                seeds_now = seed_results[2*i]
                seeds_prev = seed_results[2*i + 1]

                ret_string += f"\n"
                _, _, token_symbol, decimals = get_erc20_info(
                    asset_changes.token, web3=self._web3
                ).parse()
                delta_asset = token_to_float(asset_changes.delta_asset, decimals)
                delta_seeds = seeds_now - seeds_prev
                # Asset BDV at final season end, deduced from subgraph data.
                asset_bdv = bean_to_float(
                    asset_changes.final_season_asset["depositedBDV"]
                ) / token_to_float(asset_changes.final_season_asset["depositedAmount"], decimals)
                # asset_bdv = bean_to_float(asset_changes.final_season_bdv)
                current_bdv = asset_changes.final_season_asset["depositedBDV"]

                ret_string += f"{token_symbol}:"

                # BDV
                if delta_asset < 0:
                    ret_string += f"\n\t📉 BDV: {round_num(abs(delta_asset * asset_bdv), 0)}"
                elif delta_asset == 0:
                    ret_string += f"\n\t📊 BDV: No change"
                else:
                    ret_string += f"\n\t📈 BDV: {round_num(abs(delta_asset * asset_bdv), 0)}"

                # Seeds
                if delta_seeds < 0:
                    ret_string += f"\n\t📉 Seeds: {round_num(abs(delta_seeds), 3, avoid_zero=True)}"
                elif delta_seeds == 0:
                    ret_string += f"\n\t📊 Seeds: No change"
                else:
                    ret_string += f"\n\t📈 Seeds: {round_num(abs(delta_seeds), 3, avoid_zero=True)}"

                # ret_string += f' — {token_symbol}  ({round_num(bean_to_float(current_bdv)/current_silo_bdv*100, 1)}% of Silo)'
                ret_string += f"\n\t📊 Totals: {round_num_auto(bean_to_float(current_bdv), sig_fig_min=2, abbreviate=True)} BDV, {round_num(seeds_now, 3)} Seeds, {round_num(bean_to_float(current_bdv)/current_silo_bdv*100, 1)}% of Silo"
            """

            # Field.
            ret_string += f"\n\n**Field**"
            ret_string += f"\n🌾 {round_num(sown_beans * (1 + last_weather/100), 0, avoid_zero=True)} Pods minted"
            ret_string += f"\n🏞 "
            if issued_soil == 0:
                ret_string += f"No"
            else:
                ret_string += f"{round_num(issued_soil, 0, avoid_zero=True)}"
            ret_string += f" Soil in Field"
            ret_string += f"\n🌡 {round_num(current_season_stats.temperature, 0)}% Temperature"
            ret_string += f"\n🧮 {round_num(pod_rate, 0)}% Pod Rate"

            # Barn.
            ret_string += f"\n\n**Barn**"
            ret_string += f"\n{percent_to_moon_emoji(percent_recap)} {round_num(fertilizer_bought, 0)} Fertilizer sold ({round_num(percent_recap*100, 2)}% recapitalized)"

            # Txn hash of sunrise/gm call.
            if hasattr(current_season_stats, 'sunrise_hash'):
                ret_string += f"\n\n<https://arbiscan.io/tx/{current_season_stats.sunrise_hash}>"
                ret_string += "\n_ _"  # Empty line that does not get stripped.

        # Short string version (for Twitter).
        else:
            # Display total liquidity only
            total_liquidity = 0
            for well_info in wells_info:
                total_liquidity += token_to_float(well_info['liquidity'], 6)
            total_liquidity = round_num(total_liquidity, 0)
            ret_string += f"\n\n🌊 Total Liquidity: ${total_liquidity}"

            ret_string += f"\n"
            if reward_beans > 0:
                ret_string += f"\n🌱 {round_num(reward_beans, 0, avoid_zero=True)} Beans Minted"
            if sown_beans > 0:
                ret_string += f"\n🚜 {round_num(sown_beans, 0, avoid_zero=True)} Beans Sown for {round_num(sown_beans * (1 + last_weather/100), 0, avoid_zero=True)} Pods"

            ret_string += f"\n🌡 {round_num(current_season_stats.temperature, 0)}% Temperature"
            ret_string += f"\n🧮 {round_num(pod_rate, 0)}% Pod Rate"
        return ret_string

    @abstractmethod
    def silo_balance_str(name, deposits=None, bdv=None):
        """Return string representing the total deposited amount of a token."""
        ret_string = f"\n"
        if deposits is not None:
            ret_string += f"🏦 {round_num(deposits, 0)} {name} in Silo"
        elif bdv is not None:
            ret_string += f"🏦 {round_num(bdv, 0)} BDV worth of {name} in Silo"
        else:
            raise ValueError("Must specify either delta_deposits or bdv (Bean denominated value)")
        return ret_string

from abc import abstractmethod
import asyncio.exceptions
from datetime import datetime, timedelta
import discord
from discord.ext import tasks, commands
from enum import Enum
import re
import logging
from opensea import OpenseaAPI
import os
import subprocess
import sys
import threading
import time
import websockets

from constants.addresses import *
from data_access.graphs import (
    BeanSqlClient,
    BeanstalkSqlClient,
    BasinSqlClient,
    SnapshotClient,
    DAO_SNAPSHOT_NAME,
)
from data_access.eth_chain import *
from data_access.etherscan import get_gas_base_fee
from data_access.coin_gecko import get_token_price
from data_access.chainlink import get_eth_price
from tools.util import get_txn_receipt_or_wait

# Strongly encourage Python 3.8+.
# If not 3.8+ uncaught exceptions on threads will not be logged.
MIN_PYTHON = (3, 8)
if sys.version_info < MIN_PYTHON:
    logging.critical(
        "Python %s.%s or later is required for proper exception logging.\n" % MIN_PYTHON
    )
LOGGING_FORMAT_STR_SUFFIX = "%(levelname)s : %(asctime)s : %(message)s"
LOGGING_FORMATTER = logging.Formatter(LOGGING_FORMAT_STR_SUFFIX)

TIMESTAMP_KEY = "timestamp"
# Discord server guild ID.
# BEANSTALK_GUILD_ID = 880413392916054098
ID_KEY = "id"
# The duration of a season. Assumes that seasons align with Unix epoch.
SEASON_DURATION = 3600  # seconds
# How long to wait between discord preview bot updates.
PREVIEW_CHECK_PERIOD = 4  # seconds
# For all check periods there is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds).
APPROX_BLOCK_TIME = 12  # seconds
# How long to wait between peg checks.
PEG_CHECK_PERIOD = APPROX_BLOCK_TIME  # seconds
# How long to wait between checks for a sunrise when we expect a new season to begin.
SUNRISE_CHECK_PERIOD = APPROX_BLOCK_TIME  # seconds
# Rate at which to check chain for new Uniswap V2 pool interactions.
POOL_CHECK_RATE = APPROX_BLOCK_TIME  # seconds
# Rate at which to check for events on the Beanstalk contract.
BEANSTALK_CHECK_RATE = APPROX_BLOCK_TIME  # seconds
# How long to wait between checks for fert purchases.
BARN_RAISE_CHECK_RATE = APPROX_BLOCK_TIME  # seconds
# Bytes in 100 megabytes.
ONE_HUNDRED_MEGABYTES = 100 * 1000000
# Initial time to wait before reseting dead monitor.
RESET_MONITOR_DELAY_INIT = 15  # seconds
# Timestamp for start of Barn Raise.
BARN_RAISE_START_TIME = 1652112000  # seconds
# # Governance quorum percentages.
# BIP_QUORUM_RATIO = 0.5
# BOP_QUORUM_RATIO = 0.35
# SUNRISE_TIME_PRE_EXPLOIT = 1650196819
# SUNRISE_TIME_POST_EXPLOIT = 1659762014
# Timestamp for deployment of Basin.
BASIN_DEPLOY_EPOCH = 1692814103

DISCORD_NICKNAME_LIMIT = 32

GENESIS_SLUG = "beanft-genesis"
WINTER_SLUG = "beanft-winter"
BARN_RAISE_SLUG = "beanft-barn-raise"


class PegCrossType(Enum):
    NO_CROSS = 0
    CROSS_ABOVE = 1
    CROSS_BELOW = 2


class Monitor:
    """Base class for monitors. Do not use directly.

    Args:
        name: simple human readable name string to use for logging.
        message_function: fun(str) style function to send application messages.
        query_rate: int representing rate monitored data should be queried (in seconds).
        prod: bool indicating if this is a production instance or not.
    """

    def __init__(self, name, message_function, query_rate, prod=False, dry_run=False):
        self.name = name
        self.message_function = message_function
        self.query_rate = query_rate
        self.prod = prod
        self._dry_run = dry_run
        # Time to wait before restarting monitor after an unhandled exception. Exponential backoff.
        self.monitor_reset_delay = RESET_MONITOR_DELAY_INIT
        self._thread_active = False
        self._thread_wrapper = threading.Thread(target=self._thread_wrapper_method)
        self._web3 = get_web3_instance()

    @abstractmethod
    def _monitor_method(self):
        pass

    def start(self):
        logging.info(f"Starting {self.name} monitoring thread...")
        if self._dry_run:
            self.message_function(f"{self.name} monitoring started (with simulated data).")
        elif not self.prod:
            self.message_function(f"{self.name} monitoring started.")
        self._thread_active = True
        self._thread_wrapper.start()

    def stop(self):
        logging.info(f"Stopping {self.name} monitoring thread...")
        if not self.prod:
            self.message_function(f"{self.name} monitoring stopped.")
        self._thread_active = False
        self._thread_wrapper.join(3 * self.query_rate)

    def _thread_wrapper_method(self):
        """
        If an unhandled exception occurs in the monitor and it is killed, log the exception here
        and restart the monitor.

        The most common failures are web3 calls, which can fail arbitrarily on external access.
        """
        retry_time = 0
        while self._thread_active:
            if time.time() < retry_time:
                logging.info(
                    f"Waiting {retry_time - time.time()} more seconds before restarting "
                    f" monitor on {self.name} thread."
                )
                time.sleep(1)
                continue
            logging.info(f"Starting monitor on {self.name} thread.")
            self._web3 = get_web3_instance()
            try:
                self._monitor_method()
            # Websocket disconnects are expected occasionally.
            except websockets.exceptions.ConnectionClosedError as e:
                logging.error(f"Websocket connection closed error\n{e}\n**restarting the monitor**")
                logging.warning(e, exc_info=True)
            # Timeouts on data access are expected occasionally.
            except asyncio.exceptions.TimeoutError as e:
                logging.error(f"Asyncio timeout error:\n{e}\n**restarting the monitor**")
                logging.warning(e, exc_info=True)
            except Exception as e:
                logging.error(
                    f"Unhandled exception in the {self.name} thread."
                    f"\n**restarting the monitor**."
                )
                logging.warning(e, exc_info=True)
            # Reset the restart delay after a stretch of successful running.
            if time.time() > retry_time + 3600:
                self.monitor_reset_delay = RESET_MONITOR_DELAY_INIT
            else:
                self.monitor_reset_delay *= 2
            retry_time = time.time() + self.monitor_reset_delay
        logging.warning("Thread wrapper returned.")


class PegCrossMonitor(Monitor):
    """Monitor bean graph for peg crosses and send out messages on detection."""

    def __init__(self, message_function, prod=False):
        super().__init__("Peg", message_function, PEG_CHECK_PERIOD, prod=prod, dry_run=False)
        self.bean_graph_client = BeanSqlClient()
        self.last_known_cross = None

    def _monitor_method(self):
        """Continuously monitor for BEAN price crossing the peg.

        Note that this assumes that block time > period of graph checks.
        """
        # Delay startup to protect against crash loops.
        min_update_time = time.time() + 1
        while self._thread_active:
            # Attempt to check as quickly as the graph allows, but no faster than set frequency.
            if not time.time() > min_update_time:
                time.sleep(1)
                continue
            min_update_time = time.time() + PEG_CHECK_PERIOD

            try:
                cross_types = self._check_for_peg_crosses()
            # Will get index error before there is data in the subgraph.
            except IndexError:
                continue
            for cross_type in cross_types:
                if cross_type != PegCrossType.NO_CROSS:
                    output_str = PegCrossMonitor.peg_cross_string(cross_type)
                    self.message_function(output_str)

    def _check_for_peg_crosses(self):
        """
        Check to see if the peg has been crossed since the last known timestamp of the caller.
        Assumes that block time > period of graph checks.

        Returns:
            [PegCrossType]
        """
        # Get latest data from graph.
        last_cross = self.bean_graph_client.last_cross()

        # # For testing.
        # import random
        # self.last_known_cross = {'timestamp': 1, 'id': int(last_cross['id']) - 2}
        # logging.info(f'TESTING: Last cross was above? {last_cross["above"]}')
        # price = random.uniform(0.5, 1.5)

        # If the last known cross has not been set yet, initialize it.
        if not self.last_known_cross:
            logging.info(
                "Peg cross timestamp initialized with last peg cross = "
                f"{last_cross[TIMESTAMP_KEY]}"
            )
            self.last_known_cross = last_cross
            return [PegCrossType.NO_CROSS]

        # If the cross is not newer than the last known cross or id is not greater, return.
        # These checks are necessary due to unpredictable variations in the graph.
        if last_cross[TIMESTAMP_KEY] <= self.last_known_cross[TIMESTAMP_KEY] or int(
            last_cross[ID_KEY]
        ) <= int(self.last_known_cross[ID_KEY]):
            return [PegCrossType.NO_CROSS]

        # If multiple crosses have occurred since last known cross.
        last_cross_id = int(last_cross["id"])
        last_known_cross_id = int(self.last_known_cross["id"])
        number_of_new_crosses = last_cross_id - last_known_cross_id

        if number_of_new_crosses > 1:
            # Returns n crosses ordered most recent -> least recent.
            new_cross_list = self.bean_graph_client.get_last_crosses(n=number_of_new_crosses)
        else:
            new_cross_list = [last_cross]

        # We cannot rely on very recent data of the subgraph to be accurate/consistent. So double
        # check the id and try again later if it is wrong.
        if int(new_cross_list[0]["id"]) != last_known_cross_id + number_of_new_crosses:
            logging.warning(
                f"Subgraph data discrepency on latest peg crosses. Latest cross id "
                f'is {new_cross_list[0]["id"]} but expected id of {last_cross_id}. '
                "Trying again later."
            )
            return [PegCrossType.NO_CROSS]

        # Set the last known cross to be the latest new cross.
        self.last_known_cross = last_cross

        # At least one new cross has been detected.
        # Determine the cross types and return list in ascending order.
        cross_types = []
        for cross in reversed(new_cross_list):
            if cross["above"]:
                logging.info("Price crossed above peg.")
                cross_types.append(PegCrossType.CROSS_ABOVE)
            else:
                logging.info("Price crossed below peg.")
                cross_types.append(PegCrossType.CROSS_BELOW)
        return cross_types

    @abstractmethod
    def peg_cross_string(cross_type):
        """Return peg cross string used for bot messages."""
        # NOTE(funderberker): Have to compare enum values here because method of import of caller
        # can change the enum id.
        if cross_type.value == PegCrossType.CROSS_ABOVE.value:
            return "🟩↗ BEAN crossed above peg!"
        elif cross_type.value == PegCrossType.CROSS_BELOW.value:
            return "🟥↘ BEAN crossed below peg!"
        else:
            return "Peg not crossed."


class SeasonsMonitor(Monitor):
    def __init__(
        self, message_function, short_msgs=False, channel_to_wallets=None, prod=False, dry_run=False
    ):
        super().__init__(
            "Seasons", message_function, SUNRISE_CHECK_PERIOD, prod=prod, dry_run=dry_run
        )
        # Toggle shorter messages (must fit into <280 character safely).
        self.short_msgs = short_msgs
        # Read-only access to self.channel_to_wallets, which may be modified by other threads.
        self.channel_to_wallets = channel_to_wallets
        self.beanstalk_graph_client = BeanstalkSqlClient()
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
                # Report season summary to users.
                self.message_function(
                    self.season_summary_string(
                        last_season_stats, current_season_stats, short_str=self.short_msgs
                    )
                )

            # if self.channel_to_wallets:
            #     self.update_all_wallet_watchers()

            # # For testing.
            # # Note that this will not handle deltas correctly.
            # current_season_stats, last_season_stats = self.beanstalk_graph_client.seasons_stats()
            # self.message_function(self.season_summary_string(last_season_stats, current_season_stats, short_str=self.short_msgs))
            # time.sleep(10)

    def _wait_until_expected_sunrise(self):
        """Wait until beanstalk is eligible for a sunrise call.

        Assumes sunrise timing cycle beings with Unix Epoch (1/1/1970 00:00:00 UTC).
        This is not exact since we do not bother with syncing local and graph time.
        """
        if self._dry_run:
            time.sleep(5)
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
        # TODO(funderberker): Put in max number of checks here before giving up and wait for
        # next sunrise.
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
            time.sleep(SUNRISE_CHECK_PERIOD)
        return None, None

    def season_summary_string(self, last_season_stats, current_season_stats, short_str=False):
        # new_farmable_beans = float(current_season_stats.silo_hourly_bean_mints)
        reward_beans = current_season_stats.reward_beans
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
        ret_string = f"⏱ Season {last_season_stats.season} is complete!"
        ret_string += f"\n💵 Current price is ${round_num(price, 6)}"

        # Pool info.
        bean_eth_well_pi = self.bean_client.well_bean_eth_pool_info()
        curve_pool_pi = self.bean_client.curve_bean_3crv_pool_info()

        # Full string message.
        if not short_str:
            ret_string += (
                f'\n⚖ {"+" if delta_b > 0 else ""}{round_num(delta_b, 0)} time-weighted deltaB'
            )
            # Bean Supply stats.
            ret_string += f"\n\n**Supply**"
            ret_string += f"\n🌱 {round_num(reward_beans, 0, avoid_zero=True)} Beans minted"
            ret_string += f"\n🚜 {round_num(sown_beans, 0, avoid_zero=True)} Beans Sown"

            # Liquidity stats.
            ret_string += f"\n\n**Liquidity**"
            ret_string += (
                f"\n🌊 BEANETH: ${round_num(token_to_float(bean_eth_well_pi['liquidity'], 6), 0)} - "
            )
            ret_string += (
                f"_deltaB [{round_num(token_to_float(bean_eth_well_pi['delta_b'], 6), 0)}], "
            )
            ret_string += f"price [${round_num(token_to_float(bean_eth_well_pi['price'], 6), 4)}]_"
            ret_string += (
                f"\n🔸 BEAN3CRV: ${round_num(token_to_float(curve_pool_pi['liquidity'], 6), 0)} - "
            )
            ret_string += f"_deltaB [{round_num(token_to_float(curve_pool_pi['delta_b'], 6), 0)}], "
            ret_string += f"price [${round_num(token_to_float(curve_pool_pi['price'], 6), 4)}]_"

            # Silo balance stats.
            ret_string += f"\n\n**Silo**"
            ret_string += f"\n🏦 {round_num(current_silo_bdv, 0)} BDV in Silo"
            asset_rank = 0
            for asset_changes in silo_assets_changes:
                asset_rank += 1
                # silo_asset_str = ''
                ret_string += f"\n"
                _, _, token_symbol, decimals = get_erc20_info(
                    asset_changes.token, web3=self._web3
                ).parse()
                delta_asset = token_to_float(asset_changes.delta_asset, decimals)
                # Asset BDV at final season end, deduced from subgraph data.
                asset_bdv = bean_to_float(
                    asset_changes.final_season_asset["depositedBDV"]
                ) / token_to_float(asset_changes.final_season_asset["depositedAmount"], decimals)
                # asset_bdv = bean_to_float(asset_changes.final_season_bdv)
                current_bdv = asset_changes.final_season_asset["depositedBDV"]

                # VERSION 1
                if delta_asset < 0:
                    ret_string += f"📉 {round_num(abs(delta_asset * asset_bdv), 0)} BDV"
                elif delta_asset == 0:
                    ret_string += f"🧾 No change"
                else:
                    ret_string += f"📈 {round_num(abs(delta_asset * asset_bdv), 0)} BDV"
                # ret_string += f' — {token_symbol}  ({round_num(bean_to_float(current_bdv)/current_silo_bdv*100, 1)}% of Silo)'
                ret_string += f" — {token_symbol}  ({round_num_auto(bean_to_float(current_bdv)/1000000, sig_fig_min=2)}M BDV)"

            # Field.
            ret_string += f"\n\n**Field**"
            ret_string += f"\n🌾 {round_num(sown_beans * (1 + last_weather/100), 0, avoid_zero=True)} Pods minted"
            ret_string += f"\n🏞 "
            if issued_soil == 0:
                ret_string += f"No"
            else:
                ret_string += f"{round_num(issued_soil, 0, avoid_zero=True)}"
            ret_string += f" Soil in Field"
            ret_string += f"\n🌤 {round_num(current_season_stats.temperature, 0)}% Temperature"
            ret_string += f"\n🧮 {round_num(pod_rate, 0)}% Pod Rate"

            # Barn.
            ret_string += f"\n\n**Barn**"
            ret_string += f"\n{percent_to_moon_emoji(percent_recap)} {round_num(fertilizer_bought, 0)} Fertilizer sold ({round_num(percent_recap*100, 2)}%)"
            ret_string += "\n_ _"  # Empty line that does not get stripped.

        # Short string version (for Twitter).
        else:
            ret_string += f"\n"
            ret_string += f"\n🌱 {round_num(reward_beans, 0, avoid_zero=True)} Beans Minted"
            # ret_string += f'\n🪴 ${round_num(fertilizer_bought, 0)} Fertilizer sold'

            # silo_bdv = 0
            # for asset in current_season_stats.pre_assets:
            #     token = self._web3.toChecksumAddress(asset['token'])
            #     _,_, token_symbol, decimals = get_erc20_info(token, web3=self._web3).parse()
            #     silo_bdv += bean_to_float(asset['depositedBDV'])
            # ret_string += f'\n{SeasonsMonitor.silo_balance_str("assets", bdv=silo_bdv)}'
            ret_string += f"\n🚜 {round_num(sown_beans, 0, avoid_zero=True)} Beans Sown for {round_num(sown_beans * (1 + last_weather/100), 0, avoid_zero=True)} Pods"
            ret_string += f"\n🌤 {round_num(current_season_stats.temperature, 0)}% Temperature"
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


class BasinPeriodicMonitor(Monitor):
    """Periodically summarized and report Basin status."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(f"basin", message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_type = EventClientType.AQUIFER
        self._eth_event_client = EthEventsClient(self.pool_type, AQUIFER_ADDR)
        self.well_client = WellClient(BEAN_ETH_WELL_ADDR)
        self.update_period = 60 * 60 * 24
        self.update_ref_time = int(
            0.5 * 60 * 60
        )  # 15 * 60 * 60 # timestamp to check period against (11:00 EST)
        # updated_secs_ago = time.time() - (time.time() % self.update_period) - self.update_ref_time
        self.last_update = time.time()  # arbitrary init
        self.basin_graph_client = BasinSqlClient()

    def _monitor_method(self):
        while True:
            self._wait_until_update_time()
            if not self._thread_active:
                return
            self.message_function(self.period_string())

    def _wait_until_update_time(self):
        if self._dry_run:
            time.sleep(5)
            return

        # Avoid double updates.
        if self.last_update > time.time() - 30:
            time.sleep(30)

        clock_epoch_now = time.time() % self.update_period
        if self.update_ref_time > clock_epoch_now:
            secs_until_update = self.update_ref_time - clock_epoch_now
        else:
            secs_until_update = (
                self.update_period - time.time() % self.update_period + self.update_ref_time
            )
        timestamp_next_update = time.time() + secs_until_update
        loop_count = 0
        while self._thread_active and time.time() < timestamp_next_update:
            if loop_count % 60 == 0:
                logging.info(
                    f"Blindly waiting {int((timestamp_next_update - time.time())/60)} "
                    "more minutes until expected update."
                )
            loop_count += 1
            time.sleep(10)
        self.last_update = time.time()

    def period_string(self):
        days_of_basin = int((datetime.utcnow() - datetime.fromtimestamp(BASIN_DEPLOY_EPOCH)).days)
        ret_str = f"🪣 Basin Daily Report #{days_of_basin}\n"
        # ret_str = f'🪣 {(datetime.now() - timedelta(days=1)).strftime("%b %d %Y")}\n'

        total_liquidity = 0
        daily_volume = 0
        weekly_volume = 0
        wells = self.basin_graph_client.get_latest_well_snapshots(7)

        per_well_str = ""
        for well in wells:
            per_well_str += "\n- 🌱 " if well["id"] == BEAN_ETH_WELL_ADDR.lower() else "\n💦 "
            per_well_str += f'{TOKEN_SYMBOL_MAP.get(well["id"])} Liquidity: ${round_num_auto(float(well["dailySnapshots"][0]["totalLiquidityUSD"])/1000000, sig_fig_min=2)}m'
            total_liquidity += float(well["dailySnapshots"][0]["totalLiquidityUSD"])
            daily_volume += float(well["dailySnapshots"][0]["deltaVolumeUSD"])
            for snapshot in well["dailySnapshots"]:
                weekly_volume += float(snapshot["deltaVolumeUSD"])

        ret_str += (
            f"\n🌊 Total Liquidity: ${round_num_auto(total_liquidity/1000000, sig_fig_min=2)}m"
        )
        ret_str += f"\n📊 24H Volume: ${round_num_auto(daily_volume/1000, sig_fig_min=2)}k"
        ret_str += f"\n🗓 7D Volume: ${round_num_auto(weekly_volume/1000, sig_fig_min=2)}k"

        ret_str += f"\n\n**Wells**"
        ret_str += per_well_str

        return ret_str

    @abstractmethod
    def get_well_name(bore_well_log):
        """Return string representing the name of a well."""
        name = ""
        tokens = bore_well_log.args.get("tokens")
        for i in range(0, len(tokens)):
            addr = tokens[i]
            (_, _, symbol, decimals) = get_erc20_info(addr).parse()
            if i > 0:
                name += ":"
            name += symbol


# NOTE arguments for doing 1 monitor for all wells and 1 monitor per well. In first pass wells will each get their
#      own discord channel, which will require human intervention in this code anyway, so going to go for 1 channel
#      per well for now.
class WellMonitor(Monitor):
    """Monitor Wells for events.

    This provides events in Beanstalk exchange channel as well as Basin per-well channels.

    NOTE assumption that all wells contain Bean. Valuation is done in BDV using the bean side of the trade to
         directly determine value.
    ^^ make this assumption less strict, instead only skip valuation if no BDV
    """

    def __init__(self, message_function, address, bean_reporting=False, prod=False, dry_run=False):
        super().__init__(f"wells", message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_type = EventClientType.WELL
        self._eth_event_client = EthEventsClient(self.pool_type, address)
        self.well_client = WellClient(address)
        self.bean_client = BeanClient()
        self.basin_graph_client = BasinSqlClient()
        self.bean_reporting = bean_reporting

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + POOL_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the well event logs for a single txn."""
        # Sometimes ignore Silo Convert txns, which will be handled by the Beanstalk monitor.
        if self.bean_reporting is True and event_sig_in_txn(
            BEANSTALK_EVENT_MAP["Convert"], txn_hash
        ):
            logging.info("Ignoring well txn, reporting as convert instead.")
            return

        for event_log in event_logs:
            event_str = self.any_event_str(event_log)
            if event_str:
                self.message_function(event_str)

    def any_event_str(self, event_log):
        bdv = value = None
        event_str = ""
        bean_well_value = self.bean_client.well_bean_eth_bean_price()
        # Parse possible values of interest from the event log. Not all will be populated.
        fromToken = event_log.args.get("fromToken")
        toToken = event_log.args.get("toToken")
        amountIn = event_log.args.get("amountIn")
        amountOut = event_log.args.get("amountOut")
        # recipient = event_log.args.get('recipient')
        tokenAmountsIn = event_log.args.get("tokenAmountsIn")  # int[]
        lpAmountOut = event_log.args.get("lpAmountOut")  # int
        lpAmountIn = event_log.args.get("lpAmountIn")
        tokenOut = event_log.args.get("tokenOut")
        tokenAmountOut = event_log.args.get("tokenAmountOut")
        tokenAmountsOut = event_log.args.get("tokenAmountsOut")
        #  = event_log.args.get('reserves')
        lpAmountOut = event_log.args.get("lpAmountOut")

        tokens = self.well_client.tokens()
        logging.info(f"well tokens: {tokens}")

        is_swapish = False
        is_lpish = False

        if event_log.event == "AddLiquidity":
            is_lpish = True
            event_str += f"📥 LP added - "
            lp_amount = lpAmountOut
            for i in range(len(tokens)):
                erc20_info = get_erc20_info(tokens[i])
                event_str += f"{round_token(tokenAmountsIn[i], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}"
                if i < len(tokens) - 1:
                    event_str += " and"
                event_str += f" "
            bdv = token_to_float(lpAmountOut, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(
                BEAN_ETH_WELL_ADDR, web3=self._web3
            )
        elif event_log.event == "Sync":
            is_lpish = True
            event_str += f"📥 LP added - "
            # subgraph may be down, providing no deposit data.
            deposit = self.basin_graph_client.try_get_well_deposit_info(
                event_log.transactionHash, event_log.logIndex
            )
            if deposit:
                for i in range(len(tokens)):
                    erc20_info = get_erc20_info(deposit["tokens"][i]["id"])
                    event_str += f'{round_token(deposit["reserves"][i], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}'
                    if i < len(tokens) - 1:
                        event_str += " and"
                    event_str += f" "
                value = float(deposit["amountUSD"])
            else:
                bdv = token_to_float(
                    lpAmountOut, WELL_LP_DECIMALS
                ) * get_constant_product_well_lp_bdv(BEAN_ETH_WELL_ADDR, web3=self._web3)
        elif event_log.event == "RemoveLiquidity" or event_log.event == "RemoveLiquidityOneToken":
            is_lpish = True
            event_str += f"📤 LP removed - "
            for i in range(len(tokens)):
                erc20_info = get_erc20_info(tokens[i])
                if event_log.event == "RemoveLiquidityOneToken":
                    if tokenOut == tokens[i]:
                        out_amount = tokenAmountOut
                    else:
                        out_amount = 0
                else:
                    out_amount = tokenAmountsOut[i]
                event_str += f"{round_token(out_amount, erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}"

                if i < len(tokens) - 1:
                    event_str += f" and"
                event_str += f" "
            bdv = token_to_float(lpAmountIn, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(
                BEAN_ETH_WELL_ADDR, web3=self._web3
            )
        elif event_log.event == "Swap":
            is_swapish = True
            # value = lpAmountIn * lp_value
            erc20_info_in = get_erc20_info(fromToken)
            erc20_info_out = get_erc20_info(toToken)
            amount_in = amountIn
            amount_in_str = round_token(amount_in, erc20_info_in.decimals, erc20_info_in.addr)
            amount_out = amountOut
            amount_out_str = round_token(amount_out, erc20_info_out.decimals, erc20_info_out.addr)
            if fromToken == BEAN_ADDR:
                bdv = bean_to_float(amountIn)
            elif toToken == BEAN_ADDR:
                bdv = bean_to_float(amountOut)
        elif event_log.event == "Shift":
            erc20_info_out = get_erc20_info(toToken)

            amount_in = None
            if event_log.address == BEAN_ETH_WELL_ADDR and toToken == BEAN_ADDR:
                bdv = bean_to_float(amountOut)
                erc20_info_in = get_erc20_info(WRAPPED_ETH)
                amount_in = get_eth_sent(event_log.transactionHash, self._web3)
                amount_in_str = round_token(amount_in, erc20_info_in.decimals, erc20_info_in.addr)
            elif event_log.address == BEAN_ETH_WELL_ADDR and toToken == WRAPPED_ETH:
                value = token_to_float(amountOut, erc20_info_out.decimals) * get_eth_price(
                    self._web3
                )
                erc20_info_in = get_erc20_info(BEAN_ADDR)
                amount_in = self.well_client.get_beans_sent(event_log.transactionHash)
                if amount_in:
                    bdv = bean_to_float(amount_in)
                    amount_in_str = round_token(
                        amount_in, erc20_info_in.decimals, erc20_info_in.addr
                    )
            amount_out = amountOut
            amount_out_str = round_token(amount_out, erc20_info_out.decimals, erc20_info_out.addr)
            if (
                amount_in is not None and amount_in > 0
            ):  # not None and not 0, then it is a pseudo swap
                is_swapish = True
            else:  # one sided shift
                event_str += f"🔀 {amount_out_str} {erc20_info_out.symbol} shifted out "
        else:
            logging.warning(f"Unexpected event log seen in Well ({event_log.event}). Ignoring.")
            return ""

        if bdv is not None:
            value = bdv * self.bean_client.avg_bean_price()

        if is_swapish:
            if self.bean_reporting and erc20_info_out.symbol == "BEAN":
                event_str += f"📗 {amount_out_str} {erc20_info_out.symbol} bought for {amount_in_str} {erc20_info_in.symbol} @ ${round_num(value/bean_to_float(amount_out), 4)} "
            elif self.bean_reporting and erc20_info_in.symbol == "BEAN":
                event_str += f"📕 {amount_in_str} {erc20_info_in.symbol} sold for {amount_out_str} {erc20_info_out.symbol} @ ${round_num(value/bean_to_float(amount_in), 4)} "
            else:
                event_str += (
                    f"🔁 {amount_in_str} {erc20_info_in.symbol} swapped "
                    f"for {amount_out_str} {erc20_info_out.symbol} "
                )

        if value is not None:
            event_str += f"({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            if (is_swapish or is_lpish) and self.bean_reporting:
                event_str += f"\n_{latest_pool_price_str(self.bean_client, BEAN_ETH_WELL_ADDR)}_ "
            if is_lpish and not self.bean_reporting:
                event_str += f"\n_{latest_well_lp_str(self.bean_client, BEAN_ETH_WELL_ADDR)}_ "
            event_str += f"\n{value_to_emojis(value)}"

        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str


class CurvePoolMonitor(Monitor):
    """Monitor a Curve pool for events."""

    def __init__(self, message_function, pool_type, prod=False, dry_run=False):
        if pool_type is EventClientType.CURVE_BEAN_3CRV_POOL:
            name = "Bean:3CRV Curve Pool"
        else:
            raise ValueError("Curve pool must be set to a supported pool.")
        super().__init__(name, message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_type = pool_type
        self._eth_event_client = EthEventsClient(self.pool_type)
        self.bean_client = BeanClient()
        self.three_pool_client = CurveClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + POOL_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the curve pool event logs for a single txn.

        Assumes that there are no non-Bean:3CRV TokenExchangeUnderlying events in logs.
        Note that Event Log Object is not the same as Event object.
        """
        # NOTE(funderberker): Using txn function to determine what is happening no longer works
        # because nearly everything is embedded into farm(bytes[] data) calls.
        # Ignore Silo Convert txns, which will be handled by the Beanstalk monitor.
        if event_sig_in_txn(BEANSTALK_EVENT_MAP["Convert"], txn_hash):
            logging.info("Ignoring pool txn, reporting as convert instead.")
            return

        if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
            bean_price = self.bean_client.curve_bean_3crv_bean_price()
        # No default since each pool must have support manually built in.
        for event_log in event_logs:
            event_str = self.any_event_str(event_log, bean_price)
            if event_str:
                self.message_function(event_str)

    def any_event_str(self, event_log, bean_price):
        event_str = ""
        # Parse possible values of interest from the event log. Not all will be populated.
        sold_id = event_log.args.get("sold_id")
        tokens_sold = event_log.args.get("tokens_sold")
        bought_id = event_log.args.get("bought_id")
        tokens_bought = event_log.args.get("tokens_bought")
        token_amounts = event_log.args.get("token_amounts")
        # Coin is a single ERC20 token, token is the pool token. So Coin can be Bean or 3CRV.
        token_amount = event_log.args.get("token_amount")
        coin_amount = event_log.args.get("coin_amount")

        value = None
        if token_amounts is not None:
            bean_amount = bean_to_float(token_amounts[FACTORY_3CRV_INDEX_BEAN])
            if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
                crv_amount = crv_to_float(token_amounts[FACTORY_3CRV_INDEX_3CRV])
                token_name = "3CRV"
                crv_value = self.three_pool_client.get_3crv_price()
            value = bean_amount * bean_price + crv_amount * crv_value
        # RemoveLiquidityOne.
        if coin_amount is not None:
            if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
                lp_value = self.bean_client.curve_bean_3crv_lp_value()
                lp_amount = token_to_float(token_amount, CRV_DECIMALS)
            value = lp_amount * lp_value

        if event_log.event == "TokenExchangeUnderlying" or event_log.event == "TokenExchange":
            # Set the variables of quantity and direction of exchange.
            bean_out = stable_in = bean_in = stable_out = None
            if bought_id in [FACTORY_3CRV_UNDERLYING_INDEX_BEAN]:
                bean_out = bean_to_float(tokens_bought)
                stable_in = tokens_sold
                stable_id = sold_id
            elif sold_id in [FACTORY_3CRV_UNDERLYING_INDEX_BEAN]:
                bean_in = bean_to_float(tokens_sold)
                stable_out = tokens_bought
                stable_id = bought_id
            else:
                logging.warning("Exchange detected between two non-Bean tokens. Ignoring.")
                return ""

            # Set the stable name string and convert value to float.
            if event_log.event == "TokenExchange":
                stable_name = "3CRV"
                stable_in = crv_to_float(stable_in)
                stable_out = crv_to_float(stable_out)
                stable_price = self.three_pool_client.get_3crv_price()
            elif stable_id == FACTORY_3CRV_UNDERLYING_INDEX_DAI:
                stable_name = "DAI"
                stable_in = dai_to_float(stable_in)
                stable_out = dai_to_float(stable_out)
                stable_price = get_token_price(DAI)
            elif stable_id == FACTORY_3CRV_UNDERLYING_INDEX_USDC:
                stable_name = "USDC"
                stable_in = usdc_to_float(stable_in)
                stable_out = usdc_to_float(stable_out)
                stable_price = get_token_price(USDC)
            elif stable_id == FACTORY_3CRV_UNDERLYING_INDEX_USDT:
                stable_name = "USDT"
                stable_in = usdt_to_float(stable_in)
                stable_out = usdt_to_float(stable_out)
                stable_price = get_token_price(USDT)
            else:
                logging.error(f"Unexpected stable_id seen ({stable_id}) in exchange. Ignoring.")
                return ""

            event_str += self.exchange_event_str(
                stable_name,
                stable_price,
                bean_out=bean_out,
                bean_in=bean_in,
                stable_in=stable_in,
                stable_out=stable_out,
            )
        elif event_log.event == "AddLiquidity":
            event_str += f"📥 LP added - {round_num(bean_amount, 0)} Beans and {round_num(crv_amount, 0)} {token_name} ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        elif event_log.event == "RemoveLiquidity" or event_log.event == "RemoveLiquidityImbalance":
            event_str += f"📤 LP removed - {round_num(bean_amount, 0)} Beans and {round_num(crv_amount, 0)} {token_name} ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        elif event_log.event == "RemoveLiquidityOne":
            event_str += f"📤 LP removed - "
            if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
                # If 6 decimal then it must be Bean that was withdrawn. 18 decimal is 3CRV.
                if is_6_not_18_decimal_token_amount(coin_amount):
                    event_str += f"{round_num(bean_to_float(coin_amount), 0)} Beans"
                else:
                    event_str += f"{round_num(crv_to_float(coin_amount), 0)} 3CRV"
            event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        else:
            logging.warning(
                f"Unexpected event log seen in Curve Pool ({event_log.event}). Ignoring."
            )
            return ""

        if value is not None:
            event_str += f"\n{value_to_emojis(value)}"
        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def exchange_event_str(
        self,
        stable_name,
        stable_price,
        stable_in=None,
        bean_in=None,
        stable_out=None,
        bean_out=None,
    ):
        """Generate a standard token exchange string."""
        event_str = ""
        if (not stable_in and not bean_in) or (not stable_out and not bean_out):
            logging.error("Must set at least one input and one output of swap.")
            return ""
        if (stable_in and bean_in) or (stable_out and bean_out):
            logging.error("Cannot set two inputs or two outputs of swap.")
            return ""
        if stable_in:
            event_str += f"📗 {round_num(bean_out, 0)} {get_erc20_info(BEAN_ADDR).symbol} bought for {round_num(stable_in, 0)} {stable_name}"
            swap_value = stable_in * stable_price
            swap_price = swap_value / bean_out
        elif bean_in:
            event_str += f"📕 {round_num(bean_in, 0)} {get_erc20_info(BEAN_ADDR).symbol} sold for {round_num(stable_out, 0)} {stable_name}"
            # If this is a sale of Beans for a fertilizer purchase.
            swap_value = stable_out * stable_price
            swap_price = swap_value / bean_in
        event_str += f" @ ${round_num(swap_price, 4)} ({round_num(swap_value, 0, avoid_zero=True, incl_dollar=True)})"
        event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        event_str += f"\n{value_to_emojis(swap_value)}"
        return event_str


class BeanstalkMonitor(Monitor):
    """Monitor the Beanstalk contract for events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(
            "Beanstalk", message_function, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self._eth_event_client = EthEventsClient(EventClientType.BEANSTALK)
        self.bean_client = BeanClient()
        self.beanstalk_client = BeanstalkClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + BEANSTALK_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        # logging.warning(f'handling {txn_hash} logs...')
        # Prune *plant* deposit logs. They are uninteresting clutter.
        # Prune *pick* deposit logs. They are uninteresting clutter.
        # For each earn (plant/pick) event log remove a corresponding AddDeposit log.
        # for earn_event_log in get_logs_by_names(['Plant'], event_logs):
        for earn_event_log in get_logs_by_names(["Plant", "Pick"], event_logs):
            for deposit_event_log in get_logs_by_names("AddDeposit", event_logs):
                if deposit_event_log.args.get("token") == (
                    earn_event_log.args.get("token") or BEAN_ADDR
                ) and deposit_event_log.args.get("amount") == (
                    earn_event_log.args.get("beans") or earn_event_log.args.get("amount")
                ):
                    # Remove event log from event logs
                    event_logs.remove(deposit_event_log)
                    # At most allow 1 match.
                    logging.info(
                        f"Ignoring a {earn_event_log.event} AddDeposit event {txn_hash.hex()}"
                    )
                    break
        # Prune *transfer* deposit logs. They are uninteresting clutter.
        # Note that this assumes that a transfer event never includes a novel deposit.
        remove_event_logs = get_logs_by_names(["RemoveDeposit", "RemoveDeposits"], event_logs)
        deposit_event_logs = get_logs_by_names("AddDeposit", event_logs)
        for remove_event_log in remove_event_logs:
            for deposit_event_log in deposit_event_logs:
                if deposit_event_log.args.get("token") == remove_event_log.args.get("token"):
                    # and deposit_event_log.args.get('amount') == \
                    # (remove_event_log.args.get('amount'))):
                    # Remove event log from event logs
                    try:
                        event_logs.remove(remove_event_log)
                    except ValueError:
                        pass
                    event_logs.remove(deposit_event_log)
                    logging.info(
                        f"Ignoring a AddDeposit RemoveDeposit(s) pair {txn_hash.hex()}, possible transfer or silo migration"
                    )

        if event_in_logs("ClaimFertilizer", event_logs):
            event_str = self.rinse_str(event_logs)
            if event_str:
                self.message_function(event_str)
            remove_events_from_logs_by_name("ClaimFertilizer", event_logs)

        # Process conversion logs as a batch.
        if event_in_logs("Convert", event_logs):
            self.message_function(self.silo_conversion_str(event_logs))
        # Handle txn logs individually using default strings.
        else:
            for event_log in event_logs:
                event_str = self.single_event_str(event_log)
                if event_str:
                    self.message_function(event_str)

    def single_event_str(self, event_log):
        """Create a string representing a single event log.

        Events that are from a convert call should not be passed into this function as they
        should be processed in batch.
        """

        event_str = ""
        bean_price = self.bean_client.avg_bean_price()

        # Ignore these events. They are uninteresting clutter.
        if event_log.event in ["RemoveWithdrawal", "RemoveWithdrawals" "Plant", "Pick"]:
            return ""

        # Deposit & Withdraw events.
        elif event_log.event in ["AddDeposit", "RemoveDeposit", "RemoveDeposits"]:
            # Pull args from the event log.
            token_address = event_log.args.get("token")
            token_amount_long = event_log.args.get("amount")  # AddDeposit, AddWithdrawal
            bdv = None
            if event_log.args.get("bdvs") is not None:
                bdv = bean_to_float(sum(event_log.args.get("bdvs")))
            else:
                bdv = bean_to_float(event_log.args.get("bdv"))

            _, _, token_symbol, decimals = get_erc20_info(token_address, web3=self._web3).parse()
            amount = token_to_float(token_amount_long, decimals)

            value = None
            if bdv > 0:
                value = bdv * bean_price

            if event_log.event in ["AddDeposit"]:
                event_str += f"📥 Silo Deposit"
            elif event_log.event in ["RemoveDeposit", "RemoveDeposits"]:
                event_str += f"📭 Silo Withdrawal"
            else:
                return ""

            event_str += f" - {round_num_auto(amount, min_precision=0)} {token_symbol}"
            # Some legacy events may not set BDV, skip valuation. Also do not value unripe assets.
            if value is not None and not token_address.startswith(UNRIPE_TOKEN_PREFIX):
                event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
                event_str += f"\n{value_to_emojis(value)}"

        # Sow event.
        elif event_log.event in ["Sow", "Harvest"]:
            # Pull args from the event log.
            beans_amount = bean_to_float(event_log.args.get("beans"))
            beans_value = beans_amount * bean_price
            pods_amount = bean_to_float(event_log.args.get("pods"))

            if event_log.event == "Sow":
                event_str += (
                    f"🚜 {round_num(beans_amount, 0, avoid_zero=True)} Beans Sown for "
                    f"{round_num(pods_amount, 0, avoid_zero=True)} Pods ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                )
                event_str += f"\n{value_to_emojis(beans_value)}"
            elif event_log.event == "Harvest":
                event_str += f"👩‍🌾 {round_num(beans_amount, 0, avoid_zero=True)} Pods Harvested for Beans ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                event_str += f"\n{value_to_emojis(beans_value)}"

        # Chop event.
        elif event_log.event in ["Chop"]:
            token = event_log.args.get("token")
            underlying = self.beanstalk_client.get_underlying_token(token)
            _, _, chopped_symbol, chopped_decimals = get_erc20_info(token, self._web3).parse()
            chopped_amount = token_to_float(event_log.args.get("amount"), chopped_decimals)
            _, _, underlying_symbol, underlying_decimals = get_erc20_info(
                underlying, self._web3
            ).parse()
            underlying_amount = token_to_float(
                event_log.args.get("underlying"), underlying_decimals
            )
            if underlying == BEAN_ADDR:
                underlying_token_value = bean_price
            # If underlying assets are Bean-based LP represented in price aggregator.
            # If not in aggregator, will return none and not display value.
            else:
                underlying_token_value = self.bean_client.get_curve_lp_token_value(
                    underlying, underlying_decimals
                )
            event_str += f"⚰ {round_num(chopped_amount, 0)} {chopped_symbol} Chopped for {round_num(underlying_amount, 0, avoid_zero=True)} {underlying_symbol}"
            if underlying_token_value is not None:
                underlying_value = underlying_amount * underlying_token_value
                event_str += (
                    f" ({round_num(underlying_value, 0, avoid_zero=True, incl_dollar=True)})"
                )
                event_str += f"\n{value_to_emojis(underlying_value)}"

        # Unknown event type.
        else:
            logging.warning(
                f"Unexpected event log from Beanstalk contract ({event_log}). Ignoring."
            )
            return ""

        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def silo_conversion_str(self, event_logs):
        """Create a human-readable string representing a silo position conversion.

        Assumes that there are no non-Bean swaps contained in the event logs.
        Assumes event_logs is not empty.
        Assumes embedded AddDeposit logs have been removed from logs.
        Uses events from Beanstalk contract.
        """
        bean_price = self.bean_client.avg_bean_price()
        # Find the relevant logs, should contain one RemoveDeposit and one AddDeposit.
        # print(event_logs)
        # in silo v3 AddDeposit event will always be present and these will always get set
        bdv_float = 0
        value = 0
        for event_log in event_logs:
            if event_log.event == "AddDeposit":
                bdv_float = bean_to_float(event_log.args.get("bdv"))
                value = bdv_float * bean_price
            elif event_log.event == "Convert":
                remove_token_addr = event_log.args.get("fromToken")
                _, _, remove_token_symbol, remove_decimals = get_erc20_info(
                    remove_token_addr, web3=self._web3
                ).parse()
                add_token_addr = event_log.args.get("toToken")
                _, _, add_token_symbol, add_decimals = get_erc20_info(
                    add_token_addr, web3=self._web3
                ).parse()
                remove_float = token_to_float(event_log.args.get("fromAmount"), remove_decimals)
                add_float = token_to_float(event_log.args.get("toAmount"), add_decimals)

        pool_token = BEAN_ADDR
        if remove_token_addr == CURVE_BEAN_3CRV_ADDR or add_token_addr == CURVE_BEAN_3CRV_ADDR:
            pool_token = CURVE_BEAN_3CRV_ADDR
        elif remove_token_addr in [BEAN_ETH_WELL_ADDR, UNRIPE_3CRV_ADDR] or add_token_addr in [
            BEAN_ETH_WELL_ADDR,
            UNRIPE_3CRV_ADDR,
        ]:
            pool_token = BEAN_ETH_WELL_ADDR

        event_str = (
            f"🔄 {round_num_auto(remove_float, min_precision=0)} Deposited {remove_token_symbol} "
            f"Converted to {round_num_auto(add_float, min_precision=0)} Deposited {add_token_symbol} "
        )
        # if (not remove_token_addr.startswith(UNRIPE_TOKEN_PREFIX)):
        event_str += f"({round_num(bdv_float, 0)} BDV)"
        pool_type_str = f""
        event_str += f"\n_{latest_pool_price_str(self.bean_client, pool_token)}_ "
        if not remove_token_addr.startswith(UNRIPE_TOKEN_PREFIX):
            event_str += f"\n{value_to_emojis(value)}"
        event_str += f"\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def rinse_str(self, event_logs):
        bean_amount = 0.0
        for event_log in event_logs:
            if event_log.event == "ClaimFertilizer":
                bean_amount += bean_to_float(event_log.args.beans)
        # Ignore rinses with essentially no beans bc they are clutter, especially on transfers.
        if bean_amount < 1:
            return ""
        bean_price = self.bean_client.avg_bean_price()
        event_str = f"💦 Sprouts Rinsed - {round_num(bean_amount,0)} Sprouts ({round_num(bean_amount * bean_price, 0, avoid_zero=True, incl_dollar=True)})"
        event_str += f"\n{value_to_emojis(bean_amount * bean_price)}"
        event_str += f"\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>"
        return event_str


class MarketMonitor(Monitor):
    """Monitor the Beanstalk contract for market events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(
            "Market", message_function, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self._eth_event_client = EthEventsClient(EventClientType.MARKET)
        self.bean_client = BeanClient(self._web3)
        self.bean_contract = get_bean_contract(self._web3)
        self.beanstalk_contract = get_beanstalk_contract(self._web3)
        self.beanstalk_graph_client = BeanstalkSqlClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + BEANSTALK_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        # Match the txn invoked method. Matching is done on the first 10 characters of the hash.
        transaction_receipt = tools.util.get_txn_receipt_or_wait(self._web3, txn_hash)

        # Handle txn logs individually using default strings.
        for event_log in event_logs:
            event_str = self.farmers_market_str(event_log, transaction_receipt)
            # Ignore second+ events for a single multi-event transaction.
            if not event_str:
                continue
            event_str += f"\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>"
            # Empty line that does not get stripped.
            event_str += "\n_ _"
            self.message_function(event_str)

    def farmers_market_str(self, event_log, transaction_receipt):
        """Create a human-readable string representing an event related to the farmer's market.

        Assumes event_log is an event of one of the types implemented below.
        Uses events from Beanstalk contract.
        """
        event_str = ""
        bean_amount = 0
        pod_amount = 0

        cost_in_beans = bean_to_float(event_log.args.get("costInBeans"))

        if cost_in_beans or event_log.event == "PodListingCreated":
            pod_amount = pods_to_float(event_log.args.get("amount"))
        else:
            bean_amount = bean_to_float(event_log.args.get("amount"))

        price_per_pod = pods_to_float(event_log.args.get("pricePerPod"))
        if cost_in_beans:
            bean_amount = cost_in_beans

        if not bean_amount:
            bean_amount = pod_amount * price_per_pod
        if not pod_amount and price_per_pod:
            pod_amount = bean_amount / price_per_pod
        if not price_per_pod and pod_amount:
            price_per_pod = bean_amount / pod_amount

        # Index of the plot (place in line of first pod of the plot).
        plot_index = pods_to_float(event_log.args.get("index"))
        # ID of the order.
        order_id = event_log.args.get("id")
        if order_id:
            # order_id = order_id.decode('utf8')
            # order_id = self._web3.keccak(text=order_id).hex()
            order_id = order_id.hex()
        # Index of earliest pod to list, relative to start of plot.
        relative_start_index = pods_to_float(event_log.args.get("start"))
        # Absolute index of the first pod to list.
        start_index = plot_index + relative_start_index
        # Current index at start of pod line (number of pods ever harvested).
        pods_harvested = pods_to_float(
            call_contract_function_with_retry(self.beanstalk_contract.functions.harvestableIndex())
        )
        # Lowest place in line of a listing.
        start_place_in_line = start_index - pods_harvested
        # Highest place in line an order will purchase.
        order_max_place_in_line = pods_to_float(event_log.args.get("maxPlaceInLine"))

        bean_price = self.bean_client.avg_bean_price()
        start_place_in_line_str = round_num(start_place_in_line, 0)
        order_max_place_in_line_str = round_num(order_max_place_in_line, 0)

        # If this was a pure cancel (not relist or reorder).
        if (
            event_log.event == "PodListingCancelled"
            and not self.beanstalk_contract.events["PodListingCreated"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
            and not self.beanstalk_contract.events["PodOrderFilled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
        ) or (
            event_log.event == "PodOrderCancelled"
            and not self.beanstalk_contract.events["PodOrderCreated"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
            and not self.beanstalk_contract.events["PodListingFilled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            )
        ):
            if event_log.event == "PodListingCancelled":
                listing_graph_id = (
                    event_log.args.get("account").lower() + "-" + str(event_log.args.get("index"))
                )
                pod_listing = self.beanstalk_graph_client.get_pod_listing(listing_graph_id)
                # If this listing did not exist, ignore cancellation.
                if pod_listing is None:
                    logging.info(
                        f"Ignoring null listing cancel with graph id {listing_graph_id} and txn hash {event_log.transactionHash.hex()}"
                    )
                    return ""
                pod_amount_str = round_num(pods_to_float(int(pod_listing["amount"])), 0)
                start_place_in_line_str = round_num(
                    pods_to_float(int(pod_listing["index"]) + int(pod_listing["start"]))
                    - pods_harvested,
                    0,
                )
                price_per_pod_str = round_num(bean_to_float(pod_listing["pricePerPod"]), 3)
                event_str += f"❌ Pod Listing Cancelled"
                event_str += f" - {pod_amount_str} Pods Listed at {start_place_in_line_str} @ {price_per_pod_str} Beans/Pod"
            else:
                pod_order = self.beanstalk_graph_client.get_pod_order(order_id)
                # If this order did not exist, ignore cancellation.
                if pod_order is None:
                    logging.info(
                        f"Ignoring null order cancel with graph id {order_id} and txn hash {event_log.transactionHash.hex()}"
                    )
                    return ""
                pod_amount = pods_to_float(
                    int(pod_order["podAmount"]) - int(pod_order["podAmountFilled"])
                )
                max_place = pods_to_float(pod_order["maxPlaceInLine"])
                price_per_pod = bean_to_float(pod_order["pricePerPod"])
                event_str += f"❌ Pod Order Cancelled"
                event_str += f" - {round_num(pod_amount,0)} Pods Ordered before {round_num(max_place,0)} @ {round_num(price_per_pod,3)} Beans/Pod"
        # If a new listing or relisting.
        elif event_log.event == "PodListingCreated":
            # Check if this was a relist, if so send relist message.
            if self.beanstalk_contract.events["PodListingCancelled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            ):
                event_str += f"♻ Pods re-Listed"
            else:
                event_str += f"✏ Pods Listed"
            event_str += f" - {round_num(pod_amount, 0)} Pods Listed at {start_place_in_line_str} @ {round_num(price_per_pod, 3)} Beans/Pod ({round_num(pod_amount * bean_price * price_per_pod, avoid_zero=True, incl_dollar=True)})"
        # If a new order or reorder.
        elif event_log.event == "PodOrderCreated":
            # Check if this was a relist.
            if self.beanstalk_contract.events["PodOrderCancelled"]().processReceipt(
                transaction_receipt, errors=DISCARD
            ):
                event_str += f"♻ Pods re-Ordered"
            else:
                event_str += f"🖌 Pods Ordered"
            event_str += f" - {round_num(pod_amount, 0)} Pods Ordered before {order_max_place_in_line_str} @ {round_num(price_per_pod, 3)} Beans/Pod ({round_num(pod_amount * bean_price * price_per_pod, avoid_zero=True, incl_dollar=True)})"
        # If a fill.
        elif event_log.event in ["PodListingFilled", "PodOrderFilled"]:
            event_str += f"💰 Pods Exchanged - "
            # Pull the Bean Transfer log to find cost.
            if event_log.event == "PodListingFilled":
                event_str += f"{round_num(pod_amount, 0)} Pods Listed at {start_place_in_line_str} in Line Filled"
                if price_per_pod:
                    event_str += f" @ {round_num(price_per_pod, 3)} Beans/Pod ({round_num(bean_price * bean_amount, avoid_zero=True, incl_dollar=True)})"
                    event_str += f"\n{value_to_emojis(bean_price * bean_amount)}"
            elif event_log.event == "PodOrderFilled":
                event_str += (
                    f"{round_num(pod_amount, 0)} Pods Ordered at "
                    f"{start_place_in_line_str} in Line Filled @ {round_num(price_per_pod, 3)} "
                    f"Beans/Pod ({round_num(bean_price * bean_amount, avoid_zero=True, incl_dollar=True)})"
                )
                event_str += f"\n{value_to_emojis(bean_price * bean_amount)}"
        return event_str


class BarnRaiseMonitor(Monitor):
    def __init__(
        self,
        message_function,
        report_events=True,
        report_summaries=False,
        prod=False,
        dry_run=False,
    ):
        super().__init__(
            "BarnRaise", message_function, BARN_RAISE_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        # Used for special init cases
        # self.SUMMARY_BLOCK_RANGE = self._web3.eth.get_block('latest').number - 14918083
        self.SUMMARY_BLOCK_RANGE = 1430  # ~ 6 hours
        # self.SUMMARY_BLOCK_RANGE = 5720 + 1192 # ~ 24 hours, offset by 5 hours
        self.EMOJI_RANKS = ["🥇", "🥈", "🥉"]
        self.report_events = report_events
        self.report_summaries = report_summaries
        self.bean_client = BeanClient()
        self.barn_raise_client = BarnRaiseClient()
        self._eth_event_client = EthEventsClient(EventClientType.BARN_RAISE)
        self.beanstalk_graph_client = BeanstalkSqlClient()
        self.last_total_bought = self.beanstalk_graph_client.get_fertilizer_bought()

    def _monitor_method(self):
        last_check_time = 0

        while self._thread_active:
            # Wait until check rate time has passed.
            if time.time() < last_check_time + BARN_RAISE_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()

            # If reporting summaries and a 6 hour block has passed.
            if self.report_summaries:
                current_block = safe_get_block(self._web3, "latest")
                if (current_block.number - 14915799) % self.SUMMARY_BLOCK_RANGE == 0:
                    # if True:
                    from_block = safe_get_block(
                        self._web3, current_block.number - self.SUMMARY_BLOCK_RANGE
                    )
                    time_range = current_block.timestamp - from_block.timestamp
                    all_events_in_time_range = []
                    for txn_pair in self._eth_event_client.get_log_range(
                        from_block=from_block.number, to_block=current_block.number
                    ):
                        event_logs = txn_pair.logs
                        all_events_in_time_range.extend(event_logs)
                    # Do not report a summary if nothing happened.
                    if len(all_events_in_time_range) == 0:
                        logging.info("No events detected to summarize. Skipping summary.")
                        continue
                    # Sort events based on size.
                    all_events_in_time_range = sorted(
                        all_events_in_time_range,
                        key=lambda event: event.args.get("value") or sum(event.args.get("values")),
                        reverse=True,
                    )
                    # all_events_in_time_range = sorted(all_events_in_time_range, lambda(event: int(event.args.value)))
                    total_raised = 0
                    for event in all_events_in_time_range:
                        usdc_amount = int(event.args.value)
                        total_raised += usdc_amount
                    msg_str = f"🚛 In the past {round_num(time_range/3600, 1)} hours ${round_num(total_raised, 0)} was raised from {len(all_events_in_time_range)} txns"
                    remaining = self.barn_raise_client.remaining()
                    msg_str += f"\n🪴 {round_num(remaining, 0)} Fertilizer remaining"
                    msg_str += f"\n"
                    for i in range(3):
                        try:
                            event = all_events_in_time_range[i]
                        # There may not be 3 events in a time block.
                        except IndexError:
                            break
                        # msg_str += f'\n{self.EMOJI_RANKS[i]} ${round_num(event.args.value, 0)} ({event.args["to"]})' # {event.transactionHash.hex()}
                        msg_str += f"\n{self.EMOJI_RANKS[i]} ${round_num(event.args.value, 0)} (https://etherscan.io/tx/{event.transactionHash.hex()})"

                    self.message_function(msg_str)

            # If reporting events.
            if self.report_events:
                # Check for new Bids, Bid updates, and Sows.
                all_events = []
                for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                    all_events.extend(txn_pair.logs)
                for event_log in all_events:
                    self._handle_event_log(event_log)

    def _handle_event_log(self, event_log):
        """Process a single event log for the Barn Raise."""
        # Mint single.
        if (
            event_log.event in ["TransferSingle", "TransferBatch"]
            and event_log.args["from"] == NULL_ADDR
        ):
            if event_log.event == "TransferSingle":
                amount = int(event_log.args.value)
            # Mint batch.   <- is this even possible???
            elif event_log.event == "TransferBatch":
                amount = sum([int(value) for value in event_log.args.values])

            weth_amount = token_to_float(
                get_eth_sent(event_log.transactionHash, web3=self._web3), 18
            )

            event_str = f"🚛 Fertilizer Purchased - {round_num(amount, 0)} Fert for {round_num(weth_amount, 3)} WETH @ {round_num(self.barn_raise_client.get_humidity(), 1)}% Humidity"
            total_bought = self.beanstalk_graph_client.get_fertilizer_bought()

            # The subgraph is slower to update, so may need to calculate total bought here.
            if total_bought <= self.last_total_bought + 1:
                self.last_total_bought = total_bought + amount
            else:
                self.last_total_bought = total_bought

            event_str += f" - Total sold: {round_num(self.last_total_bought, 0)}"
            # event_str += f' ({round_num(self.barn_raise_client.remaining(), 0)} Available Fertilizer)'
            event_str += f"\n{value_to_emojis(amount)}"
        # Transfer or some other uninteresting transaction.
        else:
            return

        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        self.message_function(event_str)


class RootMonitor(Monitor):
    """Monitor Root token contract."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(
            "RootMonitor", message_function, APPROX_BLOCK_TIME, prod=prod, dry_run=dry_run
        )
        self._eth_event_client = EthEventsClient(EventClientType.ROOT_TOKEN)
        self.root_client = RootClient()
        self.bean_client = BeanClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + APPROX_BLOCK_TIME:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the root token event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        root_bdv = self.root_client.get_root_token_bdv()
        for event_log in event_logs:
            event_str = self.any_event_str(event_log, root_bdv)
            if event_str:
                self.message_function(event_str)

    def any_event_str(self, event_log, root_bdv):
        event_str = ""
        if event_log.address != ROOT_ADDR:
            logging.warning(
                f"Ignoring non-Root token events (i.e. transfers of other tokens). {event_log.address}"
            )
            return ""
        # # Parse possible values of interest from the event log.
        # account = event_log.args.get('account')
        # deposits = event_log.args.get('deposits')
        # bdv = bean_to_float(event_log.args.get('bdv'))
        # stalk = stalk_to_float(event_log.args.get('stalk'))
        # seeds = seeds_to_float(event_log.args.get('seeds'))
        # shares = root_to_float(event_log.args.get('shares'))
        # value_bdv = root_bdv * shares # is this always the same as event arg 'bdv' ?
        bean_usd = self.bean_client.avg_bean_price()

        if event_log.event == "Transfer":
            amount = root_to_float(event_log.args.value)
            value_bdv = root_bdv * amount  # is this always the same as event arg 'bdv' ?
            value_usd = value_bdv * bean_usd

            # if event_log.event == 'Mint':
            #     event_str += f'🌳 {round_num(shares, 2)} Root minted from {round_num(bdv, 2)} BDV'
            # elif event_log.event == 'Redeem':
            #     event_str += f'🪓 {round_num(shares, 2)} Root redeemed for {round_num(bdv, 2)} BDV'
            if event_log.args.get("from") == NULL_ADDR:
                event_str += f"🌳 {round_num(amount, 2)} Root minted ({round_num(value_usd, 2, avoid_zero=True, incl_dollar=True)})"
            elif event_log.args.get("to") == NULL_ADDR:
                event_str += f"🪓 {round_num(amount, 2)} Root redeemed ({round_num(value_usd, 2, avoid_zero=True, incl_dollar=True)})"
            else:
                logging.info(f"Transfer of Root tokens, not mint or redeem. Ignoring.")
                return ""
        elif event_log.event == "Plant":
            beans = root_to_float(event_log.args.beans)
            value_usd = beans * bean_usd
            event_str += f" Roots Earned {beans} Beans (${value_usd})"
        else:
            logging.warning(
                f"Unexpected event log seen in {self.name} Monitor ({event_log.event}). Ignoring."
            )
            return ""

        event_str += f"\n{value_to_emojis_root(value_usd)}"
        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str


class RootUniswapMonitor(Monitor):
    """Monitor the Root:Bean Uniswap V3 pool for events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(
            "Root:Bean Uniswap V3 Pool",
            message_function,
            POOL_CHECK_RATE,
            prod=prod,
            dry_run=dry_run,
        )
        self._eth_event_client = EthEventsClient(EventClientType.UNI_V3_ROOT_BEAN_POOL)
        self.uniswap_client = UniswapV3Client(UNI_V3_ROOT_BEAN_ADDR, ROOT_DECIMALS, BEAN_DECIMALS)
        self.bean_client = BeanClient()
        self.root_client = RootClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + POOL_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the pool event logs for a single txn."""
        # Prune any swaps or logs not in the Root:Bean Uni V3 pool.
        pool_only_event_logs = []
        for event_log in event_logs:
            if event_log.address == UNI_V3_ROOT_BEAN_ADDR:
                pool_only_event_logs.append(event_log)
        event_logs = pool_only_event_logs

        for event_log in event_logs:
            event_str = self.any_event_str(event_log)
            if event_str:
                self.message_function(event_str)

    def any_event_str(self, event_log):
        event_str = ""
        # Parse possible values of interest from the event log. Not all will be populated.
        root_amount = eth_to_float(event_log.args.get("amount0"))
        bean_amount = bean_to_float(event_log.args.get("amount1"))
        pool_amount = bean_to_float(event_log.args.get("amount"))

        root_buy = True if root_amount < 0 else False
        root_amount = abs(root_amount)
        bean_amount = abs(bean_amount)

        bean_price = self.bean_client.avg_bean_price()

        if event_log.event in ["Mint", "Burn"]:
            if event_log.event == "Mint":
                event_str += f"📥 LP added - {round_num(root_amount, 0)} Roots and {round_num(bean_amount, 0)} Beans"
            if event_log.event == "Burn":
                event_str += f"📤 LP removed - {round_num(root_amount, 0)} Roots and {round_num(bean_amount, 0)} Beans"
            root_bean_equivalent = root_amount * self.root_client.get_root_token_bdv()
            lp_value = (root_bean_equivalent + bean_amount) * bean_price
            event_str += f" ({round_num(lp_value, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n{value_to_emojis(lp_value)}"
        elif event_log.event == "Swap":
            swap_value = bean_amount * bean_price
            if root_buy:  # Root leaving pool
                event_str += f"📘 {round_num(root_amount, 0)} ROOT bought for {round_num(bean_amount, 0)} {get_erc20_info(BEAN_ADDR).symbol} "
            else:  # Bean leaving pool
                event_str += f"📙 {round_num(root_amount, 0)} ROOT sold for {round_num(bean_amount, 0)} {get_erc20_info(BEAN_ADDR).symbol} "

            event_str += f" @ {round_num(bean_amount/root_amount, 4)} BDV"
            event_str += f"  -  Current Root BDV in pool is ${round_num(self.uniswap_client.price_ratio(), 4)}"
            event_str += f"\n{value_to_emojis(swap_value)}"

        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    @abstractmethod
    def swap_event_str(
        eth_price, bean_price, eth_in=None, bean_in=None, eth_out=None, bean_out=None
    ):
        event_str = ""
        if (not eth_in and not bean_in) or (not eth_out and not bean_out):
            logging.error("Must set at least one input and one output of swap.")
            return ""
        if (eth_in and bean_in) or (eth_out and bean_out):
            logging.error("Cannot set two inputs or two outputs of swap.")
            return ""
        if eth_in:
            event_str += f"📘 {round_num(bean_out)} {get_erc20_info(BEAN_ADDR).symbol} bought for {round_num(eth_in, 4)} ETH"
            swap_price = avg_eth_to_bean_swap_price(eth_in, bean_out, eth_price)
            swap_value = swap_price * bean_out
        elif bean_in:
            event_str += f"📙 {round_num(bean_in)} {get_erc20_info(BEAN_ADDR).symbol} sold for {round_num(eth_out, 4)} ETH"
            swap_price = avg_bean_to_eth_swap_price(bean_in, eth_out, eth_price)
            swap_value = swap_price * bean_in
        event_str += f" @ ${round_num(swap_price, 4)} ({round_num(swap_value, avoid_zero=True, incl_dollar=True)})"
        event_str += f"  -  Latest pool block price is ${round_num(bean_price, 4)}"
        event_str += f"\n{value_to_emojis(swap_value)}"
        return event_str


class BettingMonitor(Monitor):
    """Monitor the Root Betting contract(s)."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(
            "Betting", message_function, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self.pool_check_time = APPROX_BLOCK_TIME * 4
        self._eth_event_client = EthEventsClient(EventClientType.BETTING)
        self.root_client = RootClient(self._web3)
        self.betting_client = BettingClient(self._web3)
        self.pool_status_thread = threading.Thread(target=self._pool_status_thread_method)

    def start(self):
        super().start()
        self.pool_status_thread.start()

    def stop(self):
        super().stop()
        self.pool_status_thread.join(2 * self.pool_check_time)

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + BEANSTALK_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _pool_status_thread_method(self):
        """Send messages when pool status changes without associated event."""
        end_time_range = time.time()
        while True:
            start_time_range = end_time_range
            time.sleep(self.pool_check_time)
            pools = self.betting_client.get_all_pools()
            end_time_range = time.time()
            for pool in pools:
                if pool["status"] == 1:  # Betting phase or currently playing
                    # If pool has started since last check (no more betting).
                    if pool["startTime"] >= start_time_range and pool["startTime"] < end_time_range:
                        self.message_function(f'📣 Pool Started - {pool["eventName"]}')

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the root event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        root_bdv = self.root_client.get_root_token_bdv()
        for event_log in event_logs:
            self.message_function(self.any_event_str(event_log, root_bdv))

    def any_event_str(self, event_log, root_bdv):
        event_str = ""

        # Parse possible values of interest from the event log.
        pool_id = event_log.args.get("poolId")

        number_of_teams = event_log.args.get("numberOfTeams")
        start_time = event_log.args.get("startTime")

        player = event_log.args.get("player")
        team_id = event_log.args.get("teamId")

        winner_ids = event_log.args.get("winnerId")
        amount = root_to_float(event_log.args.get("amount")) or 0

        pool = self.betting_client.get_pool(pool_id)
        value_bdv = root_bdv * amount

        if event_log.event == "BetPlaced":
            event_str += f"🎲 Bet Placed - {round_num(amount, 0)} Roots"
            if pool["numberOfTeams"] > 0:
                team = self.betting_client.get_pool_team(pool_id, team_id)
                event_str += f' on {team["name"]}'
                american_odds = get_american_odds(pool["totalAmount"], team["totalAmount"])
                if american_odds:
                    event_str += f" ({american_odds})"
            event_str += f' for {pool["eventName"]}'
        elif event_log.event == "PoolCreated":
            # (start: <t:{start_time}>)
            event_str += f'🪧 Pool Created - {pool["eventName"]}'
        # elif event_log.event == 'PoolStarted':
        #     event_str += f'📣 Pool Started - {pool["eventName"]}'
        elif event_log.event == "PoolGraded":
            winner_str = ""
            for winner_id in winner_ids:
                team = self.betting_client.get_pool_team(pool_id, winner_id)
                winner_str += f' {team["name"]}'
            event_str += f'🏁 Pool Graded - {pool["eventName"]}: {winner_str}'
        elif event_log.event == "WinningsClaimed":
            event_str += (
                f'💰 Winnings Claimed - {round_num(amount, 0)} Root from {pool["eventName"]}'
            )
        else:
            logging.warning(
                f"Unexpected event log seen in {self.name} Monitor ({event_log.event}). Ignoring."
            )

        if value_bdv:
            event_str += f"\n{value_to_emojis_root(value_bdv)}"
        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str


class DiscordSidebarClient(discord.ext.commands.Bot):
    def __init__(self, monitor, prod=False):
        super().__init__(command_prefix=commands.when_mentioned_or("!"))

        self.nickname = ""
        self.last_nickname = ""
        self.status_text = ""

        # Try to avoid hitting Discord API rate limit when all bots starting together.
        time.sleep(1.1)

        # subclass of util.Monitor
        self.monitor = monitor(self.set_nickname, self.set_status)
        self.monitor.start()

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        # Ignore base class, because we always want to reconnect.
        # https://discordpy.readthedocs.io/en/latest/api.html#discord.ClientUser.edit
        # https://discordpy.readthedocs.io/en/latest/api.html#exceptions
        self._update_naming.add_exception_type(discord.DiscordException)

        # Start the price display task in the background.
        self._update_naming.start()

    def stop(self):
        self.monitor.stop()

    def set_nickname(self, text):
        """Set bot server nickname."""
        self.nickname = text

    def set_status(self, text):
        """Set bot custom status text."""
        self.status_text = text

    async def on_ready(self):
        # Log the commit of this run.
        logging.info(
            "Git commit is "
            + subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(os.path.realpath(__file__)),
            )
            .decode("ascii")
            .strip()
        )

        self.user_id = self.user.id
        # self.beanstalk_guild = self.get_guild(BEANSTALK_GUILD_ID)
        # Guild IDs for all servers this bot is in.
        self.current_guilds = []
        for guild in self.guilds:
            self.current_guilds.append(guild)
            logging.info(f"Guild found: {guild.id}")

    @tasks.loop(seconds=1, reconnect=True)
    async def _update_naming(self):
        if self.nickname:
            await update_discord_bot_name(self.nickname, self)
        self.nickname = ""
        if self.status_text:
            await self.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name=self.status_text)
            )
            logging.info(f"Bot status changed to {self.status_text}")
            self.status_text = ""

    @_update_naming.before_loop
    async def before__update_naming_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()


async def update_discord_bot_name(name, bot):
    emoji_accent = holiday_emoji()
    next_name = emoji_accent + name + emoji_accent
    # Discord character limit
    if len(next_name) > DISCORD_NICKNAME_LIMIT:
        pruned_name = next_name[: DISCORD_NICKNAME_LIMIT - 3] + "..."
        logging.info(f"Pruning nickname from {next_name} to {pruned_name}")
        next_name = pruned_name
    # Note(funderberker): Is this rate limited?s
    for guild in bot.current_guilds:
        logging.info(f"Attempting to set nickname in guild with id {guild.id}")
        await guild.me.edit(nick=next_name)
        logging.info(f"Bot nickname changed to {next_name} in guild with id {guild.id}")
    return next_name


class PreviewMonitor(Monitor):
    """Base class for Discord Sidebar monitors. Do not use directly.

    Discord bot applications permissions needed: Change Nickname
    """

    def __init__(
        self,
        name,
        name_function,
        status_function,
        display_count=0,
        check_period=PREVIEW_CHECK_PERIOD,
    ):
        super().__init__(name, lambda s: None, check_period, prod=True)
        self.name = name
        # can be changed on the fly by subclass.
        self.display_count = display_count
        self.name_function = name_function
        self.status_function = status_function
        self.check_period = check_period
        self.display_index = 0
        # Delay startup to protect against crash loops.
        self.min_update_time = time.time() + 1

    def wait_for_next_cycle(self):
        """Attempt to check as quickly as the graph allows, but no faster than set period."""
        while True:
            if not time.time() > self.min_update_time:
                time.sleep(1)
                continue
            self.min_update_time = time.time() + self.check_period
            break

    def iterate_display_index(self):
        """Iterate the display index by one, looping at max display count."""
        if self.display_count != 0:
            self.display_index = (self.display_index + 1) % self.display_count


class PricePreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into current Bean status and update bot name/status."""

    def __init__(self, name_function, status_function):
        super().__init__("Price", name_function, status_function, 4)
        self.HOURS = 24
        self.last_name = ""
        self.bean_client = None
        self.beanstalk_graph_client = None

    def _monitor_method(self):
        self.bean_client = BeanClient()
        self.beanstalk_graph_client = BeanstalkSqlClient()
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            price_info = self.bean_client.get_price_info()
            bean_price = self.bean_client.avg_bean_price(price_info=price_info)
            delta_b = self.bean_client.total_delta_b(price_info=price_info)
            name_str = f"{holiday_emoji()}BEAN: ${round_num(bean_price, 4)}"
            if name_str != self.last_name:
                self.name_function(name_str)
                self.last_name = name_str

            # Rotate data and update status.
            if self.display_index in [0, 1, 2]:
                seasons = self.beanstalk_graph_client.seasons_stats(
                    self.HOURS, seasons=True, siloHourlySnapshots=False, fieldHourlySnapshots=False
                )
                prices = [season.price for season in seasons]
                rewards = [season.reward_beans for season in seasons]
                if self.display_index == 0:
                    self.status_function(
                        f"${round_num(sum(prices) / self.HOURS, 4)} Avg Price - {self.HOURS}hr"
                    )
                if self.display_index == 1:
                    self.status_function(
                        f"{round_num(sum(rewards) / self.HOURS, 0)} Avg Minted - {self.HOURS}hr"
                    )
                if self.display_index == 2:
                    self.status_function(f"{round_num(sum(rewards), 0)} Minted - {self.HOURS}hr")
            elif self.display_index == 3:
                status_str = ""
                if delta_b > 0:
                    status_str += "+"
                elif delta_b < 0:
                    status_str += "-"
                status_str += round_num(abs(delta_b), 0)
                self.status_function(f"{status_str} deltaB")


class BarnRaisePreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into current Barn Raise status."""

    def __init__(self, name_function, status_function):
        super().__init__("Barn Raise Preview", name_function, status_function, 2)
        self.last_name = ""
        self.beanstalk_client = None
        self.beanstalk_graph_client = None
        # self.snapshot_sql_client = SnapshotSqlClient()

    def _monitor_method(self):
        self.beanstalk_client = BeanstalkClient()
        self.beanstalk_graph_client = BeanstalkSqlClient()
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            percent_funded = self.beanstalk_client.get_recap_funded_percent()
            fertilizer_bought = self.beanstalk_graph_client.get_fertilizer_bought()

            name_str = f"{holiday_emoji()}Sold: ${round_num(fertilizer_bought, 0)}"
            if name_str != self.last_name:
                self.name_function(name_str)
                self.last_name = name_str

            # Rotate data and update status.
            if self.display_index == 0:
                self.status_function(
                    f"Humidity: {round_num(self.beanstalk_client.get_humidity(), 1)}%"
                )
            elif self.display_index == 1:
                self.status_function(f"{round_num(percent_funded*100, 2)}% Fertilizer Sold")


class NFTPreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into BeaNFT collections."""

    def __init__(self, name_function, status_function):
        super().__init__("NFT", name_function, status_function, check_period=8)
        self.opensea_api = None

    def _monitor_method(self):
        api_key = os.environ["OPEN_SEA_KEY"]
        self.opensea_api = OpenseaAPI(apikey=api_key)
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            # Rotate data and update status.
            name_str = ""
            status_str = ""

            # Set collection slug and name.
            if self.display_index == 0:
                slug = GENESIS_SLUG
                name = "Genesis BeaNFT"
            elif self.display_index == 1:
                slug = WINTER_SLUG
                name = "Winter BeaNFT"
            elif self.display_index == 2:
                slug = BARN_RAISE_SLUG
                name = "Barn Raise BeaNFT"
            else:
                logging.exception("Invalid status index for NFT Preview Bot.")
                continue

            # Set bot name and status.
            # Floor price preview.
            if self.display_index in [0, 1, 2]:
                logging.info(f"Retrieving OpenSea data for {slug} slug...")
                collection = self.opensea_api.collection_stats(collection_slug=slug)
                logging.info(f"OpenSea data for {slug} slug:\n{collection}")
                collection_stats = collection["stats"]
                name_str = f'{holiday_emoji()}Floor: {collection_stats["floor_price"]}Ξ'
                status_str = f"{name}"

            self.name_function(name_str)
            self.status_function(status_str)


class EthPreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into Eth mainnet."""

    def __init__(self, name_function, status_function):
        super().__init__("ETH", name_function, status_function, check_period=APPROX_BLOCK_TIME)
        self._web3 = get_web3_instance()

    def _monitor_method(self):
        while self._thread_active:
            self.wait_for_next_cycle()
            gas_base_fee = get_gas_base_fee()
            eth_price = self.eth_price()
            self.name_function(f"{holiday_emoji()}{round_num(gas_base_fee, 1)} Gwei")
            self.status_function(f"ETH: ${round_num(eth_price)}")

    def eth_price(self):
        return get_eth_price(self._web3)


class RootValuePreviewMonitor(PreviewMonitor):
    """Monitor data that offers view into current Root token status via discord nickname/status."""

    def __init__(self, name_function, status_function):
        super().__init__("RootValue", name_function, status_function, 1)
        self.last_name = ""
        self.root_client = None

    def _monitor_method(self):
        self.root_client = RootClient()
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            root_bdv = self.root_client.get_root_token_bdv()
            name_str = f"ROOT: {round_num(root_bdv, 3)} BDV"
            if name_str != self.last_name:
                self.name_function(name_str)
                self.last_name = name_str

            # Rotate data and update status.
            if self.display_index == 0:
                self.status_function(f"Supply: {round_num(self.root_client.get_total_supply(), 0)}")


class BasinStatusPreviewMonitor(PreviewMonitor):
    """Monitor data that offers view into current Basin token status via discord nickname/status.

    Note that this was implemented in a generalized fashion, then switched to specifically ETH:BEAN. I expect
    it to return to an all-well implementation in the future.
    """

    def __init__(self, name_function, status_function):
        super().__init__("BasinStatus", name_function, status_function, 1)
        self.last_name = ""
        self.basin_graph_client = BasinSqlClient()

    def _monitor_method(self):
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            bean_eth_liquidity = 0
            bean_eth_volume = 0
            wells = self.basin_graph_client.get_wells_stats()

            for well in wells:
                if well["id"].lower() == BEAN_ETH_WELL_ADDR.lower():
                    bean_eth_liquidity += float(well["totalLiquidityUSD"])
                    bean_eth_volume += float(well["cumulativeVolumeUSD"])

            if bean_eth_liquidity == 0:
                logging.warning(
                    "Missing BEAN:ETH well liquidity data in subgraph query result. Skipping update..."
                )
                continue

            # root_bdv = self.root_client.get_root_token_bdv()
            name_str = f"Liq: ${round_num(bean_eth_liquidity, 0)}"
            if name_str != self.last_name:
                self.name_function(name_str)
                self.last_name = name_str

            # Rotate data and update status.
            if self.display_index == 0:
                # self.status_function(f"Cumul Vol: ${round_num(bean_eth_volume/1000, 0)}k")
                self.status_function(f"BEANETH")


class ParadoxPoolsPreviewMonitor(PreviewMonitor):
    """Monitor data that offers view into live Paradox Pools via discord nickname/status."""

    def __init__(self, name_function, status_function):
        super().__init__(
            "Betting", name_function, status_function, 2, check_period=PREVIEW_CHECK_PERIOD
        )
        self.last_name = ""
        self.betting_client = None
        self.active_pool_index = 0

    def _monitor_method(self):
        self.betting_client = BettingClient()
        while self._thread_active:
            self.iterate_display_index()

            active_pools = self.betting_client.get_active_pools()

            if len(active_pools) == 0:
                self.name_function("No active Pools")
                self.status_function("")
                time.sleep(60)
                continue
            self.active_pool_index = (self.active_pool_index + 1) % len(active_pools)
            pool = active_pools[self.active_pool_index]

            # Rotate data and update status.
            self.status_function(f'{pool["eventName"]}')

            # Rotate data and update status.
            # Pot Size.
            if self.display_index == 0:
                self.name_function(f'Pot: {round_num(pool["totalAmount"], 0)} Roots')
                self.wait_for_next_cycle()
            # Single outcome odds.
            elif self.display_index == 1:
                for team_id in range(pool["numberOfTeams"]):
                    team = self.betting_client.get_pool_team(pool["id"], team_id)
                    name_str = f'{team["name"]}'
                    american_odds = get_american_odds(pool["totalAmount"], team["totalAmount"])
                    if american_odds:
                        name_str += f": {american_odds}"
                    self.name_function(name_str)
                    self.wait_for_next_cycle()


class SnapshotPreviewMonitor(PreviewMonitor):
    """Monitor active Snapshots and display via discord nickname/status."""

    def __init__(self, name_function, status_function):
        super().__init__(
            "Snapshot", name_function, status_function, 1, check_period=PREVIEW_CHECK_PERIOD
        )
        self.last_name = ""
        self.last_status = ""

    def _monitor_method(self):
        self.snapshot_client = SnapshotClient()
        self.beanstalk_graph_client = BeanstalkSqlClient()
        while self._thread_active:
            active_proposals = self.snapshot_client.get_active_proposals()
            if len(active_proposals) == 0:
                self.name_function("DAO: 0 active")
                self.status_function(f"snapshot.org/#/" + DAO_SNAPSHOT_NAME)
                time.sleep(60)
                continue

            # Rotate data and update status.
            for proposal in active_proposals:
                votable_stalk = stalk_to_float(
                    self.beanstalk_graph_client.get_start_stalk_by_season(
                        self.beanstalk_graph_client.get_season_id_by_timestamp(proposal["start"])
                    )
                )
                logging.info(f"votable_stalk = {votable_stalk}")

                # self.status_function(proposal['title'])

                self.name_function(f'DAO: {proposal["title"]}')
                self.status_function(f'Votes: {round_num(proposal["scores_total"], 0)}')
                self.wait_for_next_cycle()
                for i in range(len(proposal["choices"])):
                    try:
                        self.status_function(
                            f'{round_num(100 * proposal["scores"][i] / votable_stalk,2)}% - {proposal["choices"][i]}'
                        )
                    except IndexError:
                        # Unkown if Snapshot guarantees parity between these arrays.
                        break
                    self.wait_for_next_cycle()


class MsgHandler(logging.Handler):
    """A handler class which sends a message on a text channel."""

    def __init__(self, message_function):
        """
        Initialize the handler.
        """
        logging.Handler.__init__(self)
        self.message_function = message_function

    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        """
        try:
            msg = self.format(record)
            self.message_function(msg)
        except Exception:
            self.handleError(record)

    def __repr__(self):
        level = getLevelName(self.level)
        return "<%s %s (%s)>" % (self.__class__.__name__, self.baseFilename, level)


def event_in_logs(name, event_logs):
    """Return True if an event with given name is in the set of logs. Else return False."""
    for event_log in event_logs:
        if event_log.event == name:
            return True
    return False


def remove_events_from_logs_by_name(name, event_logs):
    for event_log in event_logs:
        if event_log.event == name:
            event_logs.remove(event_log)


def event_sig_in_txn(event_sig, txn_hash, web3=None):
    """Return True if an event signature appears in any logs from a txn. Else return False."""
    if not web3:
        web3 = get_web3_instance()
    receipt = tools.util.get_txn_receipt_or_wait(web3, txn_hash)
    for log in receipt.logs:
        try:
            if log.topics[0].hex() == event_sig:
                return True
        # Ignore anonymous events (logs without topics).
        except IndexError:
            pass
    return False


def get_logs_by_names(names, event_logs):
    if type(names) == str:
        names = [names]
    events = []
    for event_log in event_logs:
        if event_log.event in names:
            events.append(event_log)
    return events


def sig_compare(signature, signatures):
    """Compare a signature to one or many signatures and return if there are any matches.

    Comparison is made based on 10 character prefix.
    """
    if type(signatures) is str:
        signatures = [signatures]

    for sig in signatures:
        if signature[:9] == sig[:9]:
            return True
    return False


def round_num(number, precision=2, avoid_zero=False, incl_dollar=False):
    """Round a string or float to requested precision and return as a string."""
    if avoid_zero and number > 0 and number < 1:
        return "< $1" if incl_dollar else "<1"
    ret_string = "$" if incl_dollar else ""
    ret_string += f"{float(number):,.{precision}f}"
    return ret_string


def round_num_auto(number, sig_fig_min=3, min_precision=2):
    """Round a string or float and return as a string.

    Caller specifies the minimum significant figures and precision that that very large and very
    small numbers can both be handled.
    """
    if number > 1:
        return round_num(number, min_precision)
    return "%s" % float(f"%.{sig_fig_min}g" % float(number))


def round_token(number, decimals, addr):
    if addr.lower() == WRAPPED_ETH.lower():
        precision = 2
    else:
        precision = 0
    return round_num(token_to_float(number, decimals), precision)


def value_to_emojis(value):
    """Convert a rounded dollar value to a string of emojis."""
    value = int(value)
    if value < 0:
        return ""
    value = round(value, -3)
    if value < 10000:
        return "🐟" * (value // 1000) or "🐟"
    value = round(value, -4)
    if value < 100000:
        return "🦈" * (value // 10000)
    value = round(value, -5)
    return "🐳" * (value // 100000)


def latest_pool_price_str(bean_client, addr):
    pool_info = bean_client.get_pool_info(addr)
    if addr == BEAN_ADDR:
        type_str = " Bean"
    elif addr == CURVE_BEAN_3CRV_ADDR:
        type_str = " pool"
    else:
        type_str = " Well"
    price = token_to_float(pool_info["price"], BEAN_DECIMALS)
    delta_b = token_to_float(pool_info["delta_b"], BEAN_DECIMALS)
    # liquidity = pool_info['liquidity']
    return (
        f"Latest{type_str} data: deltaB [{round_num(delta_b, 0)}], price [${round_num(price, 4)}]"
    )


def latest_well_lp_str(bean_client, addr):
    pool_info = bean_client.get_pool_info(addr)
    # lp_price = token_to_float(pool_info['lp_usd'], BEAN_DECIMALS)
    liquidity = token_to_float(pool_info["liquidity"], BEAN_DECIMALS)
    return f"Latest Well liquidity: ${round_num(liquidity, 0)}"


def value_to_emojis_root(value):
    """Convert a rounded dollar value to a string of emojis. Smaller values for betting."""
    return value_to_emojis(value * 10)


def number_to_emoji(n):
    """Take an int as a string or int and return the corresponding # emoji. Above 10 returns '#'."""
    n = int(n)
    if n == 0:
        return "🏆"
    elif n == 1:
        return "🥇"
    elif n == 2:
        return "🥈"
    elif n == 3:
        return "🥉"
    else:
        return "🏅"


def percent_to_moon_emoji(percent):
    """Convert a float percent (e.g. .34) to a gradient moon emoji."""
    percent = float(percent)
    if percent < 0:
        return ""
    elif percent < 0.20:
        return "🌑"
    elif percent < 0.40:
        return "🌘"
    elif percent < 0.70:
        return "🌗"
    elif percent < 0.99999999:  # safety for rounding/float imperfections
        return "🌖"
    else:
        return "🌕"


PDT_OFFSET = 7 * 60 * 60
holiday_schedule = [
    # Mid Autumn Festival, UTC+9 9:00 - UTC-7 24:00
    (1662768000, 1662854400 + PDT_OFFSET, "🏮"),
    (1666681200, 1667296800, "🎃"),  # Halloween, Oct 24 - Nov 1
    (1669287600, 1669374000, "🦃"),  # US Thanksgiving, Nov 24 - Nov 25
]


def holiday_emoji():
    """Returns an emoji with appropriate festive spirit."""
    utc_now = time.time()
    for start_time, end_time, emoji in holiday_schedule:
        if start_time < utc_now and utc_now < end_time:
            return emoji
    return ""


def get_implied_odds(pool_amount, team_amount):
    """Calculate implied odds from pool and team amounts (float)."""
    return team_amount / pool_amount


def get_american_odds(pool_amount, team_amount):
    """Calculate American odds (str)."""
    implied_odds = get_implied_odds(pool_amount, team_amount)
    if implied_odds < 0 or implied_odds > 1:
        raise ValueError("Implied odds must be normalized between 0-1")
    # Occurs when this team has no bets but other teams do
    if implied_odds == 0:
        return ""
    # Occurs when only this team has bets.
    elif implied_odds == 1:
        return ""

    # payout = 1 / implied_odds
    profit = 1 / implied_odds * (1 - implied_odds)
    if profit >= 1:
        return f"+{round_num(profit*100, 0)}"
    else:
        return f"-{round_num(100/profit, 0)}"


def msg_includes_embedded_links(msg):
    """Attempt to detect if there are embedded links in this message. Not an exact system."""
    if msg.count("]("):
        return True


def strip_custom_discord_emojis(text):
    """Remove custom discord emojis using regex."""
    # <:beanstalker:1004908839394615347>
    stripped_type_0 = re.sub(r"<:[Z-z]+:[0-9]+>", " ", text)
    # :PU_PeepoPumpkin:
    # Unclear if this second type will come in normal workflow.
    stripped_type_1 = re.sub(r":[0-z]+:", " ", text)
    return stripped_type_1


def handle_sigterm(signal_number, stack_frame):
    """Process a sigterm with a python exception for clean exiting."""
    logging.warning("Handling SIGTERM. Exiting.")
    raise SystemExit


# Configure uncaught exception handling for threads.


def log_thread_exceptions(args):
    """Log uncaught exceptions for threads."""
    logging.critical(
        "Uncaught exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )


threading.excepthook = log_thread_exceptions


def log_exceptions(exc_type, exc_value, exc_traceback):
    """Log uncaught exceptions for main thread."""
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


def configure_main_thread_exception_logging():
    sys.excepthook = log_exceptions


if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    sunrise_monitor = SeasonsMonitor(print)
    sunrise_monitor.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    sunrise_monitor.stop()

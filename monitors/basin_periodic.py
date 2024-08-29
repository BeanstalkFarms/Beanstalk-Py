from datetime import datetime, timedelta

from bots.util import *
from monitors.monitor import Monitor
from data_access.eth_chain import *
from data_access.subgraphs.basin import BasinGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class BasinPeriodicMonitor(Monitor):
    """Periodically summarized and report Basin status."""

    def __init__(self, message_function, prod=False, dry_run=None):
        super().__init__(f"basin", message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.update_period = 60 * 60 * 24
        self.update_ref_time = int(
            # 9:05am PST/12:05pm EST. Subgraph takes daily snapshot in tandem with the sunrise,
            # for now recommend waiting 5 extra minutes for that reason
            16 * 60 * 60 + 5*60
        )  # 15 * 60 * 60 # timestamp to check period against (11:00 EST)
        # updated_secs_ago = time.time() - (time.time() % self.update_period) - self.update_ref_time
        self.last_update = time.time()  # arbitrary init
        self.basin_graph_client = BasinGraphClient()

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

        whitelisted_wells_str = ""
        other_wells_liquidity = 0
        for well in wells:
            if well["id"] in {token.lower() for token in {BEAN_ETH_WELL_ADDR, BEAN_WSTETH_WELL_ADDR}}:
                whitelisted_wells_str += f'\n- 🌱 {TOKEN_SYMBOL_MAP.get(well["id"])} Liquidity: ${round_num_auto(float(well["dailySnapshots"][0]["totalLiquidityUSD"]), sig_fig_min=2, abbreviate=True)}'
            else:
                other_wells_liquidity += float(well["dailySnapshots"][0]["totalLiquidityUSD"]);
            total_liquidity += float(well["dailySnapshots"][0]["totalLiquidityUSD"])
            daily_volume += float(well["dailySnapshots"][0]["deltaTradeVolumeUSD"])
            for snapshot in well["dailySnapshots"]:
                weekly_volume += float(snapshot["deltaTradeVolumeUSD"])

        ret_str += f"\n🌊 Total Liquidity: ${round_num_auto(total_liquidity, sig_fig_min=2, abbreviate=True)}"
        ret_str += (
            f"\n📊 24H Volume: ${round_num_auto(daily_volume, sig_fig_min=2, abbreviate=True)}"
        )
        ret_str += (
            f"\n🗓 7D Volume: ${round_num_auto(weekly_volume, sig_fig_min=2, abbreviate=True)}"
        )

        ret_str += f"\n\n**Wells**"
        ret_str += whitelisted_wells_str
        if other_wells_liquidity > 0:
            ret_str += f"\n- 💦 Other Wells' Liquidity: ${round_num_auto(other_wells_liquidity, sig_fig_min=2, abbreviate=True)}"

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

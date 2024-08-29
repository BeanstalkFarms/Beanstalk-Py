from data_access.etherscan import get_gas_base_fee
from data_access.contracts.eth_usd_oracle import get_twa_eth_price

from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.eth_chain import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

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
        return get_twa_eth_price(self._web3, 0)

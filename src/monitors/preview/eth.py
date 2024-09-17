from constants.chain import Chain
from data_access.etherscan import get_gas_base_fee

from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.contracts.util import *
from data_access.contracts.beanstalk import BeanstalkClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class EthPreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into Eth mainnet."""

    def __init__(self, name_function, status_function):
        super().__init__("ETH", name_function, status_function)
        self.beanstalk_client = BeanstalkClient()

    def _monitor_method(self):
        while self._thread_active:
            self.wait_for_next_cycle()
            gas_base_fee = get_gas_base_fee(Chain.ETH)
            eth_price = self.eth_price()
            self.name_function(f"{holiday_emoji()}{round_num(gas_base_fee, 1)} Gwei")
            self.status_function(f"ETH: ${round_num(eth_price)}")

    def eth_price(self):
        return self.beanstalk_client.get_token_usd_price(WRAPPED_ETH)

from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.contracts.util import *
from data_access.contracts.bean import BeanClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

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
        self.beanstalk_graph_client = BeanstalkGraphClient()
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

from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.graphs import *

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
                self.status_function(f"{round_num(percent_funded*100, 2)}% Recapitalized")

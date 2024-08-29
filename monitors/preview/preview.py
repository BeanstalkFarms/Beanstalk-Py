from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

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

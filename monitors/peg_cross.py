from enum import Enum
from abc import abstractmethod

from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.subgraphs.bean import BeanGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class PegCrossType(Enum):
    NO_CROSS = 0
    CROSS_ABOVE = 1
    CROSS_BELOW = 2

class PegCrossMonitor(Monitor):
    """Monitor bean graph for peg crosses and send out messages on detection."""

    def __init__(self, message_function, prod=False):
        super().__init__("Peg", message_function, PEG_CHECK_PERIOD, prod=prod, dry_run=None)
        self.bean_graph_client = BeanGraphClient()
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
                f"{last_cross['timestamp']}"
            )
            self.last_known_cross = last_cross
            return [PegCrossType.NO_CROSS]

        # If the cross is not newer than the last known cross or id is not greater, return.
        # These checks are necessary due to unpredictable variations in the graph.
        if last_cross["timestamp"] <= self.last_known_cross["timestamp"] or int(
            last_cross["id"]
        ) <= int(self.last_known_cross["id"]):
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

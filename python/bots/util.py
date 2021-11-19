from abc import abstractmethod
import asyncio
from enum import Enum
import logging
import threading
import time

from subgraphs.bean_subgraph import (
    BeanSqlClient, PRICE_FIELD, LAST_PEG_CROSS_FIELD)
from subgraphs.beanstalk_subgraph import BeanstalkSqlClient, TIMESTAMP_FIELD

# There is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds), so frequency should not be set too low.
PEG_UPDATE_FREQUENCY = 0.1  # hz

SEASON_DURATION = 3600 # seconds

# How long to wait between checks for a sunrise when we expect a new season to begin.
SUNRISE_CHECK_PERIOD = 5

class PegCrossType(Enum):
    NO_CROSS = 0
    CROSS_ABOVE = 1
    CROSS_BELOW = 2

# NOTE(funderberker): Fidelity can be improved by reading through list of crosses and taking
# all since the last known cross. Return list of cross types.
class PegCrossMonitor():
    """Monitor bean subgraph for peg crosses and send out messages on detection."""
    def __init__(self, message_function):
        self.message_function = message_function
        self.bean_subgraph_client = BeanSqlClient()
        self.last_known_cross = 0
        self._threads_active = False
        self._crossing_thread = threading.Thread(target=self._monitor_for_cross)

    def start(self):
        logging.info('Starting peg monitoring thread...')
        self._threads_active = True
        self._crossing_thread.start()
        self.message_function('Peg monitoring started.')

    def stop(self):
        logging.info('Stopping peg monitoring thread...')
        self._threads_active = False
        self._crossing_thread.join(1 / PEG_UPDATE_FREQUENCY * 10)
        self.message_function('Peg monitoring stopped.')

    # NOTE(funderberker): subgraph implementation of cross data will change soon.
    def _monitor_for_cross(self):
        """Continuously monitor for BEAN price crossing the peg.

        Note that this assumes that block time > period of subgraph checks.
        """
        min_update_time = 0
        while self._threads_active:
            # Attempt to check as quickly as the graph allows, but no faster than set frequency.
            if not time.time() > min_update_time:
                time.sleep(1)
                continue
            min_update_time = time.time() + 1 / PEG_UPDATE_FREQUENCY
            
            cross_type = self._check_for_peg_cross()
            if cross_type != PegCrossType.NO_CROSS:
                output_str = PegCrossMonitor.peg_cross_string(cross_type)
                self.message_function(output_str)
                logging.info(output_str)


    def _check_for_peg_cross(self):
        """
        Check to see if the peg has been crossed since the last known timestamp of the caller.
        Assumes that block time > period of subgraph checks.

        Note that this call can take over 10 seconds due to graph access delays. If an access
        takes longer than two blocks it is possible to miss a cross (only the latest cross)
        will be reported.

        Returns:
            PegCrossType
        """
        cross_type = PegCrossType.NO_CROSS

        # Get latest data from subgraph. May take 10+ seconds.
        result = self.bean_subgraph_client.get_bean_fields([LAST_PEG_CROSS_FIELD, PRICE_FIELD])
        last_cross = int(result[LAST_PEG_CROSS_FIELD])
        price = float(result[PRICE_FIELD])

        # # For testing.
        # import random
        # self.last_known_cross = 1
        # price = random.uniform(0.5, 1.5)

        if not self.last_known_cross:
            logging.info('Peg cross timestamp initialized with last peg cross = '
                         f'{last_cross}')
        else:
            if last_cross > self.last_known_cross:
                if price >= 1.0:
                    logging.info('Price crossed above peg.')
                    cross_type = PegCrossType.CROSS_ABOVE
                else:
                    logging.info('Price crossed below peg.')
                    cross_type = PegCrossType.CROSS_BELOW
        self.last_known_cross = last_cross
        return cross_type

    @abstractmethod
    def peg_cross_string(cross_type):
        """Return peg cross string used for bot messages."""
        # NOTE(funderberker): Have to compare enum values here because method of import of caller
        # can change the enum id.
        if cross_type.value == PegCrossType.CROSS_ABOVE.value:
            return 'BEAN crossed above peg! 🟩↗'
        elif cross_type.value == PegCrossType.CROSS_BELOW.value:
            return 'BEAN crossed below peg! 🟥↘'
        else:
            return 'Peg not crossed.'




class SunriseMonitor():
    def __init__(self, message_function):
        self.message_function = message_function
        self.beanstalk_subgraph_client = BeanstalkSqlClient()

        # Initialize season ID to last completed season.
        self.last_season_id = self.beanstalk_subgraph_client.last_season_stat('id')

        self._threads_active = False
        self._sunrise_thread = threading.Thread(target=self._monitor_for_sunrise)

    def start(self):
        logging.info('Starting sunrise monitoring thread...')
        self._threads_active = True
        self._sunrise_thread.start()
        self.message_function('Sunrise monitoring started.')

    def stop(self):
        logging.info('Stopping sunrise monitoring thread...')
        self._threads_active = False
        self._sunrise_thread.join(SUNRISE_CHECK_PERIOD * 3)
        self.message_function('Sunrise monitoring stopped.')

    def _monitor_for_sunrise(self):
        while self._threads_active:
            # Wait until the eligible for a sunrise.
            self._wait_until_expected_sunrise()
            # Once the sunrise is complete, get the season stats.
            season_stats = self._block_and_get_season_stats()
            # Report season summary to users.
            if self._threads_active:
                self.message_function(self.season_summary_string(season_stats))
            
            # # For testing.
            # season_stats = self.beanstalk_subgraph_client.last_season_stats()
            # print(self.season_summary_string(season_stats))
            # time.sleep(5)

    def _wait_until_expected_sunrise(self):
        """Wait until beanstalk is eligible for a sunrise call.
        
        Assumes sunrise timing cycle beings with Unix Epoch (1/1/1970 00:00:00 UTC).
        This is not exact since we do not bother with syncing local and graph time.
        """
        expected_sunrise_ready = time.time() + time.time() % SEASON_DURATION
        while self._threads_active and time.time() < expected_sunrise_ready:
            time.sleep(0.5)

    def _block_and_get_season_stats(self):
        """Blocks until sunrise is complete, then returns stats of completed season.

        Repeatedly makes graph calls to check sunrise status.
        """
        while self._threads_active:
            season_stats = self.beanstalk_subgraph_client.last_season_stats()
            if self.last_season_id != season_stats['id']:
                self.last_season_id = season_stats['id']
                return season_stats
            time.sleep(SUNRISE_CHECK_PERIOD)


    def season_summary_string(self, season_stats):
        return (
            f'One more season complete!\n'
            f'The *price* is {season_stats["price"]}\n'
            f'The *weather* is {season_stats["weather"]}\n'
            # f'There is {season_stats[""]} *soil* available\n'
            f'\n'
            # f'{season_stats[""]} beans were *minted*\n'
            f'{season_stats["newFarmableBeans"]} beans are newly *farmable*\n'
            f'{season_stats["newHarvestablePods"]} pods are newly *harvestable*\n'
            f'\n'
            f'{season_stats["newDepositedBeans"]} beans were deposited into the silo\n' # Field appears to be unpopulated
            f'{season_stats["newWithdrawnBeans"]} beans were withdrawn from the silo\n' # Field appears to be unpopulated
            f'{season_stats["newDepositedLP"]} LP was deposited into the silo\n' # Field appears to be unpopulated
            f'{season_stats["newWithdrawnLP"]} LP was withdrawn from the silo\n' # Field appears to be unpopulated
            f'{season_stats[""]} pods were sowed' # newPods fields is not what I expected
        )

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    sunrise_monitor = SunriseMonitor(print)
    sunrise_monitor.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    sunrise_monitor.stop()

from abc import abstractmethod
from enum import Enum
import logging
import threading
import time

from data_access.graphs import (
    BeanSqlClient, BeanstalkSqlClient, LAST_PEG_CROSS_FIELD, PRICE_FIELD)
# from data_access.eth_chain import get_pair_contract_filter

# There is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds), so frequency should not be set too low.
PEG_UPDATE_FREQUENCY = 0.1  # hz
# The duration of a season. Assumes that seasons align with Unix epoch.
SEASON_DURATION = 3600 # seconds
# Amount of time to wait after detecting a cross before checking for next cross.
CROSS_COOLDOWN = 120 # seconds
# How long to wait between checks for a sunrise when we expect a new season to begin.
SUNRISE_CHECK_PERIOD = 10
# Frequency to check chain for new Uniswap V2 pool interactions.
EVENT_POLL_FREQUENCY = 0.1

class PegCrossType(Enum):
    NO_CROSS = 0
    CROSS_ABOVE = 1
    CROSS_BELOW = 2

# NOTE(funderberker): Fidelity can be improved by reading through list of crosses and taking
# all since the last known cross. Return list of cross types.
class PegCrossMonitor():
    """Monitor bean graph for peg crosses and send out messages on detection."""
    def __init__(self, message_function):
        self.message_function = message_function
        self.bean_graph_client = BeanSqlClient()
        self.last_known_cross = 0
        self._thread_active = False
        self._crossing_thread = threading.Thread(target=self._monitor_for_cross)

    def start(self):
        logging.info('Starting peg monitoring thread...')
        self._thread_active = True
        self._crossing_thread.start()
        self.message_function('Peg monitoring started.')

    def stop(self):
        logging.info('Stopping peg monitoring thread...')
        self._thread_active = False
        self._crossing_thread.join(10 / PEG_UPDATE_FREQUENCY)
        self.message_function('Peg monitoring stopped.')

    # NOTE(funderberker): graph implementation of cross data will change soon.
    def _monitor_for_cross(self):
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
            min_update_time = time.time() + 1 / PEG_UPDATE_FREQUENCY
            
            cross_type = self._check_for_peg_cross()
            if cross_type != PegCrossType.NO_CROSS:
                output_str = PegCrossMonitor.peg_cross_string(cross_type)
                self.message_function(output_str)
                logging.info(output_str)

                # Delay additional checks for crosses by some amount of time. Due to the long
                # graph access times we cannot reliably catch all crosses in this implementation.
                # Soon the implementation of crosses in the graph will be updated such that
                # processing all crosses is trivial, for now we accept that we have limited
                # fidelity and do not attempt to convey all of the very rapid crosses that may
                # occur when price is holding near peg.
                logging.info(
                    f'Pausing peg checks for {CROSS_COOLDOWN} seconds to prevent imperfect spam.')
                time.sleep(CROSS_COOLDOWN)


    def _check_for_peg_cross(self):
        """
        Check to see if the peg has been crossed since the last known timestamp of the caller.
        Assumes that block time > period of graph checks.

        Note that this call can take over 10 seconds due to graph access delays. If an access
        takes longer than two blocks it is possible to miss a cross (only the latest cross)
        will be reported.

        Returns:
            PegCrossType
        """
        cross_type = PegCrossType.NO_CROSS

        # Get latest data from graph. May take 10+ seconds.
        result = self.bean_graph_client.get_bean_fields([LAST_PEG_CROSS_FIELD, PRICE_FIELD])
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
        self.beanstalk_graph_client = BeanstalkSqlClient()

        # Most recent season processed. Do not initialize.
        self.current_season_id = None

        self._thread_active = False
        self._sunrise_thread = threading.Thread(target=self._monitor_for_sunrise)

    def start(self):
        logging.info('Starting sunrise monitoring thread...')
        self._thread_active = True
        self._sunrise_thread.start()
        self.message_function('Sunrise monitoring started.')

    def stop(self):
        logging.info('Stopping sunrise monitoring thread...')
        self._thread_active = False
        self._sunrise_thread.join(SUNRISE_CHECK_PERIOD * 3)
        self.message_function('Sunrise monitoring stopped.')

    def _monitor_for_sunrise(self):
        while self._thread_active:
            # Wait until the eligible for a sunrise.
            self._wait_until_expected_sunrise()
            # Once the sunrise is complete, get the season stats.
            current_season_stats, last_season_stats = self._block_and_get_seasons_stats()
            # Report season summary to users.
            if current_season_stats:
                self.message_function(self.season_summary_string(
                    last_season_stats, current_season_stats))

            # # For testing.
            # current_season_stats, last_season_stats = self.beanstalk_graph_client.seasons_stats()
            # self.message_function(self.season_summary_string(last_season_stats, current_season_stats))
            # time.sleep(5)

    def _wait_until_expected_sunrise(self):
        """Wait until beanstalk is eligible for a sunrise call.
        
        Assumes sunrise timing cycle beings with Unix Epoch (1/1/1970 00:00:00 UTC).
        This is not exact since we do not bother with syncing local and graph time.
        """
        seconds_until_next_sunrise = SEASON_DURATION - time.time() % SEASON_DURATION
        sunrise_ready_timestamp = time.time() + seconds_until_next_sunrise
        loop_count = 0
        while self._thread_active and time.time() < sunrise_ready_timestamp:
            if loop_count % 60 == 0:
                logging.info(f'Blindly waiting {int((sunrise_ready_timestamp - time.time())/60)} '
                             'more minutes until expected sunrise.')
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
            if (self.current_season_id != current_season_stats['id'] and 
                int(current_season_stats['timestamp']) > time.time() - SEASON_DURATION / 2):
                self.current_season_id = current_season_stats['id']
                logging.info(f'New season detected with id {self.current_season_id}')
                return current_season_stats, last_season_stats
            time.sleep(SUNRISE_CHECK_PERIOD)
        return None, None

    def season_summary_string(self, last_season_stats, current_season_stats):
        new_farmable_beans = float(current_season_stats['newFarmableBeans'])
        new_harvestable_pods = float(current_season_stats['newHarvestablePods'])
        newMintedBeans = new_farmable_beans + new_harvestable_pods
        # newSoil = float(current_season_stats['newSoil'])
        new_deposited_lp = float(last_season_stats["newDepositedLP"])
        new_withdrawn_lp = float(last_season_stats["newWithdrawnLP"])
        pooled_beans = float(current_season_stats['pooledBeans'])
        pooled_eth = float(current_season_stats['pooledEth'])
        total_lp = float(current_season_stats['lp'])
        bean_pool_ratio = pooled_beans / total_lp
        eth_pool_ratio = pooled_eth / total_lp
        deposited_bean_lp = round_str(new_deposited_lp * bean_pool_ratio)
        deposited_eth_lp = round_str(new_deposited_lp * eth_pool_ratio)
        withdrawn_bean_lp = round_str(new_withdrawn_lp * bean_pool_ratio)
        withdrawn_eth_lp = round_str(new_withdrawn_lp * eth_pool_ratio)
        last_weather = float(last_season_stats['weather'])
        newPods = float(last_season_stats['newPods'])
        
        ret_string = f'⏱ Season {last_season_stats["id"]} is complete!'
        ret_string += f'\n💵 The TWAP last season was ${round_str(current_season_stats["price"], 3)}'
        ret_string += f'\n🌤 The weather is {current_season_stats["weather"]}%'
        # ret_string += f'\nThere is {current_season_stats["soil"]} soil available' # Coming in graph version 1.1.10
        if newMintedBeans:
            ret_string += f'\n\n🌱 {round_str(newMintedBeans)} beans were minted'
            ret_string += f'\n👩‍🌾 {round_str(new_farmable_beans)} beans are newly farmable'
            ret_string += f'\n👨‍🌾 {round_str(new_harvestable_pods)} pods are newly harvestable'
        else:
            ret_string += f'\n\n🌱 No new beans were minted.'
        # if newSoil:
        #     ret_string += f'\n\n{round_str(newSoil)} soil was added'
        ret_string += f'\n\n👉 {round_str(last_season_stats["newDepositedBeans"])} beans deposited'
        ret_string += f'\n👉 {deposited_bean_lp} beans and {deposited_eth_lp} ETH of LP deposited'
        ret_string += f'\n👈 {round_str(last_season_stats["newWithdrawnBeans"])} beans withdrawn'
        ret_string += f'\n👈 {withdrawn_bean_lp} beans and {withdrawn_eth_lp} ETH of LP withdrawn'
        ret_string += f'\n🚜 {round_str(newPods / (1 + last_weather/100))} beans sown'
        ret_string += f'\n🌾 {round_str(newPods)} pods minted'
        return ret_string

def round_str(string, precision=2):
    """Round a string float to requested precision."""
    return f'{float(string):,.{precision}f}'

'''
class PoolMonitor():
    """Monitor the ETH:BEAN Uniswap V2 pool for events."""
    def __init__(self, message_function):
        self.message_function = message_function
        self._pair_contract_filter = get_pair_contract_filter()
        self._thread_active = False
        self._pool_thread = threading.Thread(target=self._monitor_pool_events)

    def start(self):
        logging.info('Starting pool monitoring thread...')
        self._thread_active = True
        self._pool_thread.start()
        self.message_function('Pool monitoring started.')

    def stop(self):
        logging.info('Stopping pool monitoring thread...')
        self._thread_active = False
        self._pool_thread.join(3 / EVENT_POLL_FREQUENCY)
        self.message_function('Pool monitoring stopped.')

    def _monitor_pool_events(self):
        while self._thread_active:
            for event in self._pair_contract_filter.get_new_entries():
                self._handle_pair_event(event)
            time.sleep(1/EVENT_POLL_FREQUENCY)

    def _handle_pair_event(self, event):
        logging.info(event)
        self.message_function(self._event_to_message(event))
    
    def _event_to_message(self, event):
        return f'ETH:BEAN pool interaction occurred with txn hash {event["transactionHash"]}'
'''

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

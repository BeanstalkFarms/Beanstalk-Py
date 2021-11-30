from abc import abstractmethod
from enum import Enum
import logging
import threading
import time

from web3 import eth

from data_access.graphs import (
    BeanSqlClient, BeanstalkSqlClient, LAST_PEG_CROSS_FIELD, PRICE_FIELD)
from data_access import eth_chain

# There is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds), so frequency should not be set too low.
PEG_UPDATE_FREQUENCY = 0.1  # hz
# The duration of a season. Assumes that seasons align with Unix epoch.
SEASON_DURATION = 3600 # seconds
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
    def __init__(self, message_function, prod=False):
        self.message_function = message_function
        self.prod = prod
        self.bean_graph_client = BeanSqlClient()
        self.last_known_cross = 0
        self._thread_active = False
        self._crossing_thread = threading.Thread(target=self._monitor_for_cross)

    def start(self):
        if not self.prod:
            logging.info('Starting peg monitoring thread...')
        self._thread_active = True
        self._crossing_thread.start()
        self.message_function('Peg monitoring started.')

    def stop(self):
        if not self.prod:
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


    def _check_for_peg_cross(self):
        """
        Check to see if the peg has been crossed since the last known timestamp of the caller.
        Assumes that block time > period of graph checks.

        Returns:
            PegCrossType
        """
        cross_type = PegCrossType.NO_CROSS

        # Get latest data from graph.
        result = self.bean_graph_client.last_cross()
        last_cross = int(result['timestamp'])
        cross_above = float(result['above'])

        # # For testing.
        # import random
        # self.last_known_cross = 1
        # price = random.uniform(0.5, 1.5)

        if not self.last_known_cross:
            logging.info('Peg cross timestamp initialized with last peg cross = '
                         f'{last_cross}')
        elif self.last_known_cross < last_cross:
            if cross_above:
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
    def __init__(self, message_function, prod=False):
        self.message_function = message_function
        self.prod = prod
        self.beanstalk_graph_client = BeanstalkSqlClient()

        # Most recent season processed. Do not initialize.
        self.current_season_id = None

        self._thread_active = False
        self._sunrise_thread = threading.Thread(target=self._monitor_for_sunrise)

    def start(self):
        if not self.prod:
            logging.info('Starting sunrise monitoring thread...')
        self._thread_active = True
        self._sunrise_thread.start()
        self.message_function('Sunrise monitoring started.')

    def stop(self):
        if not self.prod:
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
        deposited_bean_lp = round_num(new_deposited_lp * bean_pool_ratio)
        deposited_eth_lp = round_num(new_deposited_lp * eth_pool_ratio)
        withdrawn_bean_lp = round_num(new_withdrawn_lp * bean_pool_ratio)
        withdrawn_eth_lp = round_num(new_withdrawn_lp * eth_pool_ratio)
        last_weather = float(last_season_stats['weather'])
        newPods = float(last_season_stats['newPods'])
        
        ret_string = f'⏱ Season {last_season_stats["id"]} is complete!'
        ret_string += f'\n💵 The TWAP last season was ${round_num(current_season_stats["price"], 3)}'
        ret_string += f'\n🌤 The weather is {current_season_stats["weather"]}%'
        # ret_string += f'\nThere is {current_season_stats["soil"]} soil available' # Coming in graph version 1.1.10
        if newMintedBeans:
            ret_string += f'\n\n🌱 {round_num(newMintedBeans)} Beans were minted'
            ret_string += f'\n👩‍🌾 {round_num(new_farmable_beans)} Beans are newly farmable'
            ret_string += f'\n👨‍🌾 {round_num(new_harvestable_pods)} Pods are newly harvestable'
        else:
            ret_string += f'\n\n🌱 No new Beans were minted.'
        # if newSoil:
        #     ret_string += f'\n\n{round_num(newSoil)} soil was added'
        ret_string += f'\n\n👉 {round_num(last_season_stats["newDepositedBeans"])} Beans deposited'
        ret_string += f'\n👉 {deposited_bean_lp} Beans and {deposited_eth_lp} ETH of LP deposited'
        ret_string += f'\n👈 {round_num(last_season_stats["newWithdrawnBeans"])} Beans withdrawn'
        ret_string += f'\n👈 {withdrawn_bean_lp} Beans and {withdrawn_eth_lp} ETH of LP withdrawn'
        ret_string += f'\n🚜 {round_num(newPods / (1 + last_weather/100))} Beans sown'
        ret_string += f'\n🌾 {round_num(newPods)} Pods minted'
        return ret_string


class PoolMonitor():
    """Monitor the ETH:BEAN Uniswap V2 pool for events."""
    def __init__(self, message_function, prod=False):
        self.message_function = message_function
        self.prod = prod
        self._eth_event_client = eth_chain.EthEventClient()
        self._eth_event_client.set_event_log_filters_pool_contract()
        # self._pool_contract_filter = eth_chain.get_pool_contract_filter()
        self._thread_active = False
        self._pool_thread = threading.Thread(target=self._monitor_pool_events)

    def start(self):
        if not self.prod:
            logging.info('Starting pool monitoring...')
        self._thread_active = True
        self._pool_thread.start()
        self.message_function('Pool monitoring started.')

    def stop(self):
        if not self.prod:
            logging.info('Stopping pool monitoring...')
        self._thread_active = False
        self._pool_thread.join(3 / EVENT_POLL_FREQUENCY)
        self.message_function('Pool monitoring stopped.')

    def _monitor_pool_events(self):
        while self._thread_active:
            for event_log in self._eth_event_client.get_new_log_entries():
                self._handle_pool_event_log(event_log)
            time.sleep(1/EVENT_POLL_FREQUENCY)

    def _handle_pool_event_log(self, event_log):
        """Process the pool event log.

        Note that Event Log Object is not the same as Event object. *sideeyes web3.py developers.*
        """
        event_str = ''
        # Parse possible values of interest from the event log. Not all will be populated.
        eth_amount = eth_chain.eth_to_float(event_log.args.get('amount0'))
        bean_amount = eth_chain.bean_to_float(event_log.args.get('amount1'))
        eth_in = eth_chain.eth_to_float(event_log.args.get('amount0In'))
        eth_out = eth_chain.eth_to_float(event_log.args.get('amount0Out'))
        bean_in = eth_chain.bean_to_float(event_log.args.get('amount1In'))
        bean_out = eth_chain.bean_to_float(event_log.args.get('amount1Out'))
        if event_log.event == 'Mint':
            event_str = f'👉 LP added - {round_num(bean_amount)} Beans and {round_num(eth_amount, 3)} ETH'
        elif event_log.event == 'Burn':
            eth_out = eth_chain.eth_to_float(event_log.args.amount0)
            bean_out = eth_chain.bean_to_float(event_log.args.amount1)
            event_str = f'👈 LP removed - {round_num(bean_amount)} Beans and {round_num(eth_amount, 3)} ETH'
        elif event_log.event == 'Swap':
            if eth_in > 0:
                event_str = f'🤝 {round_num(eth_in, 3)} ETH swapped for {round_num(bean_out)} Beans'
            elif bean_in > 0:
                event_str = f'🤝 {round_num(bean_in)} Beans swapped for {round_num(eth_out, 3)} ETH'
            else:
                logging.warning('Unexpected Swap args detected.')

        logging.info(event_str)
        self.message_function(event_str)
        return

    
def round_num(number, precision=2):
    """Round a string or float to requested precision and return as a string."""
    return f'{float(number):,.{precision}f}'

def handle_sigterm():
    """Process a sigterm with a python exception for clean exiting."""
    logging.warning("Handling SIGTERM.")
    raise SystemExit

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

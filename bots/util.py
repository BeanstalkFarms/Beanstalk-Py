from abc import abstractmethod
import asyncio.exceptions
from collections import OrderedDict
import discord
from discord.ext import tasks, commands
from enum import Enum, IntEnum
import logging
import os
import subprocess
import sys
import threading
import time
import websockets

from web3 import eth

from constants.addresses import *
from data_access.graphs import (
    BeanSqlClient, BeanstalkSqlClient, LAST_PEG_CROSS_FIELD, PRICE_FIELD)
from data_access import eth_chain

# Strongly encourage Python 3.8+.
# If not 3.8+ uncaught exceptions on threads will not be logged.
MIN_PYTHON = (3, 8)
if sys.version_info < MIN_PYTHON:
    logging.critical(
        "Python %s.%s or later is required for proper exception logging.\n" % MIN_PYTHON)
LOGGING_FORMAT_STR_SUFFIX = '%(levelname)s : %(asctime)s : %(message)s'
LOGGING_FORMATTER = logging.Formatter(LOGGING_FORMAT_STR_SUFFIX)

TIMESTAMP_KEY = 'timestamp'
# Discord server guild ID.
BEANSTALK_GUILD_ID = 880413392916054098
ID_KEY = 'id'
# The duration of a season. Assumes that seasons align with Unix epoch.
SEASON_DURATION = 3600  # seconds
# For all check periods there is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds).
# How long to wait between peg checks.
PEG_CHECK_PERIOD = 12  # seconds
# How long to wait between price updates.
PRICE_CHECK_PERIOD = 12  # seconds
# How long to wait between checks for a sunrise when we expect a new season to begin.
SUNRISE_CHECK_PERIOD = 12  # seconds
# Rate at which to check chain for new Uniswap V2 pool interactions.
POOL_CHECK_RATE = 12  # seconds
# Rate at which to check for events on the Beanstalk contract.
BEANSTALK_CHECK_RATE = 12  # seconds
# How long to wait between checks for new bids and sows.
BARN_RAISE_CHECK_RATE = 6  # seconds
# Bytes in 50 megabytes.
ONE_HUNDRED_MEGABYTES = 100**6
# Initial time to wait before reseting dead monitor.
RESET_MONITOR_DELAY_INIT = 5  # seconds
# Timestamp for start of Barn Raise.
BARN_RAISE_START_TIME = 1652112000 # seconds
# Initial goal USDC of Barn Raise.
BARN_RAISE_USDC_TARGET = 77000000


class PegCrossType(Enum):
    NO_CROSS = 0
    CROSS_ABOVE = 1
    CROSS_BELOW = 2


class Monitor():
    """Base class for monitors. Do not use directly.

    Args:
        name: simple human readable name string to use for logging.
        message_function: fun(str) style function to send application messages.
        query_rate: int representing rate monitored data should be queried (in seconds).
        prod: bool indicating if this is a production instance or not.
    """

    def __init__(self, name, message_function, query_rate, prod=False, dry_run=False):
        self.name = name
        self.message_function = message_function
        self.query_rate = query_rate
        self.prod = prod
        self._dry_run = dry_run
        # Time to wait before restarting monitor after an unhandled exception. Exponential backoff.
        self.monitor_reset_delay = RESET_MONITOR_DELAY_INIT
        self._thread_active = False
        self._thread_wrapper = threading.Thread(
            target=self._thread_wrapper_method)

    @abstractmethod
    def _monitor_method(self):
        pass

    def start(self):
        logging.info(f'Starting {self.name} monitoring thread...')
        if self._dry_run:
            self.message_function(
                f'{self.name} monitoring started (with simulated data).')
        elif not self.prod:
            self.message_function(f'{self.name} monitoring started.')
        self._thread_active = True
        self._thread_wrapper.start()

    def stop(self):
        logging.info(f'Stopping {self.name} monitoring thread...')
        if not self.prod:
            self.message_function(f'{self.name} monitoring stopped.')
        self._thread_active = False
        self._thread_wrapper.join(3 * self.query_rate)

    def _thread_wrapper_method(self):
        """
        If an unhandled exception occurs in the monitor and it is killed, log the exception here
        and restart the monitor.

        The most common failures are web3 calls, which can fail arbitrarily on external access.
        """
        retry_time = 0
        while self._thread_active:
            if time.time() < retry_time:
                time.sleep(0.5)
                continue
            try:
                self._monitor_method()
            # Websocket disconnects are expected occasionally.
            except websockets.exceptions.ConnectionClosedError as e:
                logging.error(
                    f'Websocket connection closed error\n{e}\n**restarting the monitor**')
                logging.warning(e, exc_info=True)
            # Timeouts on data access are expected occasionally.
            except asyncio.exceptions.TimeoutError as e:
                logging.error(
                    f'Asyncio timeout error:\n{e}\n**restarting the monitor**')
                logging.warning(e, exc_info=True)
            except Exception as e:
                logging.exception(e)
                logging.error(f'Unhandled exception in the {self.name} thread.'
                              f'\nLogging and **restarting the monitor**.')
            # Reset the restart delay after a stretch of successful running.
            if time.time() > retry_time + 3600:
                self.monitor_reset_delay = RESET_MONITOR_DELAY_INIT
            else:
                self.monitor_reset_delay *= 2
            retry_time = time.time() + self.monitor_reset_delay


class PegCrossMonitor(Monitor):
    """Monitor bean graph for peg crosses and send out messages on detection."""

    def __init__(self, message_function, prod=False):
        super().__init__('Peg', message_function, PEG_CHECK_PERIOD, prod=prod, dry_run=False)
        self.bean_graph_client = BeanSqlClient()
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

            cross_types = self._check_for_peg_crosses()
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
            logging.info('Peg cross timestamp initialized with last peg cross = '
                         f'{last_cross[TIMESTAMP_KEY]}')
            self.last_known_cross = last_cross
            return [PegCrossType.NO_CROSS]

        # If the cross is not newer than the last known cross or id is not greater, return.
        # These checks are necessary due to unpredictable variations in the graph.
        if (last_cross[TIMESTAMP_KEY] <= self.last_known_cross[TIMESTAMP_KEY] or
                int(last_cross[ID_KEY]) <= int(self.last_known_cross[ID_KEY])):
            return [PegCrossType.NO_CROSS]

        # If multiple crosses have occurred since last known cross.
        last_cross_id = int(last_cross['id'])
        last_known_cross_id = int(self.last_known_cross['id'])
        number_of_new_crosses = last_cross_id - last_known_cross_id
        if number_of_new_crosses > 1:
            # Returns n crosses ordered most recent -> least recent.
            new_cross_list = self.bean_graph_client.get_last_crosses(
                n=number_of_new_crosses)
        else:
            new_cross_list = [last_cross]

        # We cannot rely on very recent data of the subgraph to be accurate/consistent. So double
        # check the id and try again later if it is wrong.
        if int(new_cross_list[0]['id']) != last_known_cross_id + number_of_new_crosses:
            logging.warning(f'Subgraph data discrepency on latest peg crosses. Latest cross id '
                            f'is {new_cross_list[0]["id"]} but expected id of {last_cross_id}. '
                            'Trying again later.')
            return [PegCrossType.NO_CROSS]

        # Set the last known cross to be the latest new cross.
        self.last_known_cross = last_cross

        # At least one new cross has been detected.
        # Determine the cross types and return list in ascending order.
        cross_types = []
        for cross in reversed(new_cross_list):
            if cross['above']:
                logging.info('Price crossed above peg.')
                cross_types.append(PegCrossType.CROSS_ABOVE)
            else:
                logging.info('Price crossed below peg.')
                cross_types.append(PegCrossType.CROSS_BELOW)
        return cross_types

    @abstractmethod
    def peg_cross_string(cross_type):
        """Return peg cross string used for bot messages."""
        # NOTE(funderberker): Have to compare enum values here because method of import of caller
        # can change the enum id.
        if cross_type.value == PegCrossType.CROSS_ABOVE.value:
            return '🟩↗ BEAN crossed above peg!'
        elif cross_type.value == PegCrossType.CROSS_BELOW.value:
            return '🟥↘ BEAN crossed below peg!'
        else:
            return 'Peg not crossed.'


class PricePreviewMonitor(Monitor):
    """Monitor data that offers a view into current Bean status and update bot name/status."""

    def __init__(self, name_function, status_function):
        super().__init__('Price', status_function,
                         PRICE_CHECK_PERIOD, prod=True, dry_run=False)
        self.STATUS_DISPLAYS_COUNT = 3
        self.HOURS = 24
        self.bean_client = eth_chain.BeanClient()
        self.beanstalk_graph_client = BeanstalkSqlClient()
        self.last_status = ''
        self.status_display_index = 0
        self.name_function = name_function
        self.status_function = status_function

    def _monitor_method(self):
        # Delay startup to protect against crash loops.
        min_update_time = time.time() + 1
        while self._thread_active:
            # Attempt to check as quickly as the graph allows, but no faster than set period.
            if not time.time() > min_update_time:
                time.sleep(1)
                continue
            min_update_time = time.time() + PRICE_CHECK_PERIOD

            bean_price = self.bean_client.avg_bean_price()
            status_str = f'BEAN: ${round_num(bean_price, 4)}'
            if status_str != self.last_status:
                self.name_function(status_str)
                self.last_status = status_str

            # Rotate data and update status.
            self.status_display_index = (
                self.status_display_index + 1) % self.STATUS_DISPLAYS_COUNT
            if self.status_display_index == 0:
                seasons = self.beanstalk_graph_client.seasons_stats(
                    list(range(self.HOURS)), fields=['price'])
                prices = [float(season['price']) for season in seasons]
                self.status_function(
                    f'${round_num(sum(prices) / self.HOURS, 4)} Avg Price - {self.HOURS}hr')
            elif self.status_display_index in [1, 2]:
                seasons = self.beanstalk_graph_client.seasons_stats(
                    list(range(self.HOURS)), fields=['newFarmableBeans', 'newHarvestablePods'])
                mints = [float(season['newFarmableBeans']) +
                         float(season['newHarvestablePods']) for season in seasons]
                if self.status_display_index == 1:
                    self.status_function(
                        f'{round_num(sum(mints)/self.HOURS, 0)} Avg Minted - {self.HOURS}hr')
                if self.status_display_index == 2:
                    self.status_function(
                        f'{round_num(sum(mints), 0)} Minted - {self.HOURS}hr')


class BarnRaisePreviewMonitor(Monitor):
    """Monitor data that offers a view into current Barn Raise status."""

    def __init__(self, name_function, status_function):
        super().__init__('Barn Raise Preview', status_function,
                         PRICE_CHECK_PERIOD, prod=True, dry_run=False)
        self.STATUS_DISPLAYS_COUNT = 3
        self.barn_raise_client = eth_chain.BarnRaiseClient()
        self.last_name = ''
        self.status_display_index = 0
        self.name_function = name_function
        self.status_function = status_function

    def _monitor_method(self):
        # Delay startup to protect against crash loops.
        min_update_time = time.time() + 1
        while self._thread_active:
            # Attempt to check as quickly as the graph allows, but no faster than set period.
            if not time.time() > min_update_time:
                time.sleep(1)
                continue
            min_update_time = time.time() + PRICE_CHECK_PERIOD

            remaining = self.barn_raise_client.remaining()
            total_raised = BARN_RAISE_USDC_TARGET - remaining
            name_str = f'Sold: ${round_num(total_raised, 0)}'
            if name_str != self.last_name:
                self.name_function(name_str)
                self.last_name = name_str

            # Rotate data and update status.
            self.status_display_index = (
                self.status_display_index + 1) % self.STATUS_DISPLAYS_COUNT
            if self.status_display_index == 0:
                self.status_function(
                    f'Avail: ${round_num(remaining, 0)}')
            elif self.status_display_index == 1:
                self.status_function(
                    f'Humidity: {round_num(self.barn_raise_client.humidity(), 1)}%')
            elif self.status_display_index == 2:
                self.status_function(
                    f'{round_num(total_raised/BARN_RAISE_USDC_TARGET*100, 2)}% raised')


class SunriseMonitor(Monitor):
    def __init__(self, message_function, short_msgs=False, channel_to_wallets=None, prod=False):
        super().__init__('Sunrise', message_function,
                         SUNRISE_CHECK_PERIOD, prod=prod, dry_run=False)
        # Toggle shorter messages (must fit into <280 character safely).
        self.short_msgs = short_msgs
        # Read-only access to self.channel_to_wallets, which may be modified by other threads.
        self.channel_to_wallets = channel_to_wallets
        self.beanstalk_graph_client = BeanstalkSqlClient()
        self.bean_client = eth_chain.BeanClient()
        self.beanstalk_client = eth_chain.BeanstalkClient()
        # Most recent season processed. Do not initialize.
        self.current_season_id = None

        # Dict of LP tokens and relevant info.
        # Init LP values that are not supported by the subgraph.
        # NOTE(funderberker): Will need to reboot bot on new silo token to get it to appear.
        self.token_infos = OrderedDict(
            self.bean_client.get_price_info()['pool_infos'])
        self.token_infos = OrderedDict(
            reversed(list(self.token_infos.items())))
        for pool_info in self.token_infos.values():
            name, symbol, decimals = eth_chain.get_erc20_info(
                pool_info['pool'])
            # Use human-defined clean name if set, otherwise fallback to contract defined name.
            pool_info['name'] = eth_chain.HARDCODE_ADDRESS_TO_NAME.get(
                pool_info['pool'], name)
            pool_info['symbol'] = symbol
            pool_info['decimals'] = decimals
        self.set_silo_deltas()

    def _monitor_method(self):
        while self._thread_active:
            # Wait until the eligible for a sunrise.
            self._wait_until_expected_sunrise()
            # Once the sunrise is complete, get the season stats.
            current_season_stats, last_season_stats = self._block_and_get_seasons_stats()
            # A new season has begun.
            if current_season_stats:
                # Update silo totals once at the beginning of a new season.
                self.set_silo_deltas()
                # Report season summary to users.
                self.message_function(self.season_summary_string(
                    last_season_stats, current_season_stats, short_str=self.short_msgs))

            if self.channel_to_wallets:
                self.update_all_wallet_watchers()

            # # For testing.
            # # Note that this will not handle deltas correctly.
            # current_season_stats, last_season_stats = self.beanstalk_graph_client.seasons_stats()
            # self.message_function(self.season_summary_string(last_season_stats, current_season_stats, short_str=self.short_msgs))
            # time.sleep(10)

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
                logging.info(
                    f'New season detected with id {self.current_season_id}')
                return current_season_stats, last_season_stats
            time.sleep(SUNRISE_CHECK_PERIOD)
        return None, None

    def season_summary_string(self, last_season_stats, current_season_stats, short_str=False):
        new_farmable_beans = float(current_season_stats['newFarmableBeans'])
        new_harvestable_pods = float(
            current_season_stats['newHarvestablePods'])
        newMintedBeans = new_farmable_beans + new_harvestable_pods
        pod_rate = float(
            current_season_stats['pods']) / float(current_season_stats['beans']) * 100
        twap = float(current_season_stats["price"])
        newSoil = float(self.beanstalk_client.get_season_start_soil())

        last_weather = float(last_season_stats['weather'])
        newPods = float(last_season_stats['newPods'])

        # Current state.
        ret_string = f'⏱ Season {last_season_stats["id"]} is complete!'
        ret_string += f'\n💵 The TWAP last season was ${round_num(twap, 3)}'

        # Full string message.
        if not short_str:
            # Bean Supply stats.
            ret_string += f'\n\n**Supply**'
            ret_string += f'\n🌱 {round_num(newMintedBeans, 0)} Beans minted'
            ret_string += f'\n🚜 {round_num(newPods / (1 + last_weather/100), 0)} Beans sown'
            ret_string += f'\n🌾 {round_num(newPods, 0)} Pods minted'

            # Silo balance stats.
            ret_string += f'\n\n**Silo**'
            for pool_info in self.token_infos.values():
                # Different wording for Beans.
                if pool_info['pool'] == BEAN_ADDR or pool_info['deposited_delta_bdv'] == 0:
                    ret_string += SunriseMonitor.silo_balance_change_str(
                        pool_info['name'], delta_deposits=pool_info['deposited_delta'])
                else:
                    ret_string += SunriseMonitor.silo_balance_change_str(
                        pool_info['name'], delta_bdv=pool_info['deposited_delta_bdv'])
                # If not a complete season of data, show a warning.
                if pool_info['delta_seconds'] < 0.95 * SEASON_DURATION:
                    ret_string += f' (partial data: {round_num(pool_info["delta_seconds"]/60, 0)} minutes)'

            # Field.
            ret_string += f'\n\n**Field**'
            ret_string += f'\n🧮 {round_num(pod_rate)}% Pod Rate'
            ret_string += f'\n🏞 {round_num(newSoil, 0)} Soil in the Field' if newSoil else f'\nNo soil in the Field'
            ret_string += f'\n🌤 {current_season_stats["weather"]}% Weather'
            ret_string += '\n_ _'  # Empty line that does not get stripped.

        # Short string version (for Twitter).
        else:
            ret_string += f'\n🌤 The weather is {current_season_stats["weather"]}%'
            ret_string += f'\n'
            ret_string += f'\n🌱 {round_num(newMintedBeans, 0)} Beans minted'
            delta_silo_bdv = sum([pool_info['deposited_delta_bdv']
                                 for pool_info in self.token_infos.values()])
            # Only show delta sum if all deltas are complete sets of season data.
            if all([time.time() - pool_info['delta_seconds'] >= 0.95 * SEASON_DURATION for pool_info in self.token_infos.values()]):
                if delta_silo_bdv == 0:
                    ret_string += f'🗒 No change in Silo BDV'
                else:
                    ret_string += f'\n{SunriseMonitor.silo_balance_change_str("Silo assets", delta_bdv=delta_silo_bdv)}'
            ret_string += f'\n🚜 {round_num(newPods / (1 + last_weather/100), 0)} Beans sown for {round_num(newPods, 0)} Pods'
        return ret_string


# ⏱ Season 5739 is complete!
# 💵 TWAP last  Season $1.009

# Supply
# 🌱 39,352.08 Beans minted
# 🚜 215.62 Beans sown
# 🌾 14,166.56 Pods minted

# Silo
# 📈 18,957 increase in Bean
# 📈 879 BDV increase in Uniswap V2 BEAN:ETH LP
# 📈 2,608 BDV increase in Curve BEAN:3CRV LP

# Field
# 🧮 1,409.53% Pod Rate
# 🏞 299.62 Soil in the Field
# 🌤️ 6467% Weather


# ⏱ Season 5749 is complete!
# 💵 The TWAP last season was $1.004
# 🌤️ The weather is 6448%

# 🌱 18,032.05 Beans minted
# 📈 72,394 BDV increase in Silo
# 🚜 136.72 Beans sown for 8,956.45 Pods


    @abstractmethod
    def silo_balance_change_str(name, delta_deposits=None, delta_bdv=None):
        """Return string representing the change in total deposited amount of a token."""
        if delta_deposits is not None:
            delta = delta_deposits
        elif delta_bdv is not None:
            delta = delta_bdv
        else:
            raise ValueError(
                'Must specify either delta_deposits or bdv (Bean denominated value)')
        ret_string = f'\n'
        if abs(delta) < 1.0:
            ret_string += f'🗒 No change in {name}'
        else:
            ret_string += f'📉' if delta < 0 else f'📈'
            # Use with the token directly or its Bean value equivalent.
            if delta_deposits:
                ret_string += f' {round_num(abs(delta), 0)}'
                ret_string += f' decrease' if delta < 0 else f' increase'
                ret_string += f' in {name}'
            else:
                ret_string += f' {round_num(abs(delta), 0)} BDV'
                ret_string += f' decrease' if delta < 0 else f' increase'
                ret_string += f' in {name}'
        return ret_string

    def set_silo_deltas(self, price_info=None):
        """Set the silo asset deposit amount changes, relative to previous call of this method."""
        # Pull LP token infos for current LP pricing and liquidity.
        price_info = self.bean_client.get_price_info()

        # Generalized pools.
        for address, pool_info in self.token_infos.items():
            now = time.time()
            pool_info['delta_seconds'] = now - \
                pool_info.get('last_timestamp', now)
            pool_info['last_timestamp'] = now
            # Bean and LP not in the price oracle.
            if address not in price_info['pool_infos']:
                if address == BEAN_ADDR:
                    current_deposit_amount = self.beanstalk_client.get_total_deposited_beans()
                    token_bdv = 1.0  # 1 Bean == 1 Bean
                else:
                    current_deposit_amount = self.beanstalk_client.get_total_deposited(
                        address, pool_info['decimals'])
                    token_bdv = 0.0  # Unknown value
            # LP.
            else:
                current_token_info = price_info['pool_infos'][address]
                token_value = self.bean_client.get_lp_token_value(
                    address, pool_info['decimals'], liquidity_long=current_token_info['liquidity'])
                token_bdv = token_value / \
                    eth_chain.token_to_float(
                        current_token_info['price'], 6)  # Bean / LP
                current_deposit_amount = self.beanstalk_client.get_total_deposited(
                    address, pool_info['decimals'])

            # If this is the first, init last deposit amount == current deposit amount.
            pool_info['deposited_amount_last'] = pool_info.get(
                'deposited_amount_last', current_deposit_amount)
            # Calculate and set deltas.
            pool_info['deposited_delta'] = current_deposit_amount - \
                pool_info['deposited_amount_last']
            pool_info['deposited_delta_bdv'] = pool_info['deposited_delta'] * token_bdv
            logging.info(
                f"name: {pool_info['name']} - last deposits: {pool_info['deposited_amount_last']} - current_deposits: {current_deposit_amount} - delta deposits: {pool_info['deposited_delta']}")
            pool_info['deposited_amount_last'] = current_deposit_amount

    def update_all_wallet_watchers(self):
        current_season_stats = self.beanstalk_graph_client.current_season_stats()
        bean_price = self.bean_client.avg_bean_price()
        for channel_id, wallets in self.channel_to_wallets.items():
            # Ignore users with empty watch lists.
            if not wallets:
                continue
            self.message_function(self.wallets_str(
                wallets, current_season_stats, bean_price), channel_id)

    def wallets_str(self, wallets, current_season_stats, bean_price):
        ret_str = ''
        account_id_to_addr = {str.lower(addr): addr for addr in wallets}
        accounts_status = self.beanstalk_graph_client.wallets_stats(
            list(account_id_to_addr.keys()))
        for account_status in accounts_status:
            ret_str += self.wallet_str(
                account_id_to_addr[account_status['id']], account_status, current_season_stats, bean_price)
            ret_str += '\n'
        return ret_str

    def wallet_str(self, address, account_status, current_season_stats, bean_price):
        """Create a standard string representing a wallet status.

        address is a string of the wallet address (with standard capitalization).
        account_stats is a map of data about an account from the subgraph.
        """
        deposited_beans = float(account_status["depositedBeans"])
        lp_eth, lp_beans = lp_eq_values(
            float(account_status["depositedLP"]),
            total_lp=float(current_season_stats['lp']),
            pooled_eth=float(current_season_stats['pooledEth']),
            pooled_beans=float(current_season_stats['pooledBeans']),
        )

        ret_string = f'📜 `{address}`\n'
        # wallet_str += f'Circulating Beans: {account_stats[""]}'
        ret_string += f'🌱 Deposited Beans: {round_num(deposited_beans)}  (${round_num(deposited_beans*bean_price)})\n'
        ret_string += f'🌿 Deposited LP: {round_num(lp_eth, 4)} ETH and {round_num(lp_beans)} Beans  (${round_num(2*lp_beans*bean_price)})\n'
        ret_string += f'🌾 Pods: {round_num(account_status["pods"])}\n'
        return ret_string

#### DEPRECATED. WILL NEED REFRESHER BEFORE USING AGAIN.
'''
class UniswapPoolMonitor(Monitor):
    """Monitor the ETH:BEAN Uniswap V2 pool for events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__('Uniswap Pool', message_function,
                         POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self._eth_event_client = eth_chain.EthEventsClient(
            eth_chain.EventClientType.UNISWAP_POOL)
        self.uniswap_client = eth_chain.UniswapClient()
        self.bean_client = eth_chain.BeanClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + POOL_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_hash, event_logs in self._eth_event_client.get_new_logs(dry_run=self._dry_run).items():
                self._handle_txn_logs(txn_hash, event_logs)

            # # For testing purposes, track the price on each check.
            # if not self.prod:
            #     self.uniswap_client.current_eth_and_bean_price()

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the pool event logs for a single txn.

        Assumes that there are not non-Bean swaps in logs (e.g. ETH:USDC).
        Note that Event Log Object is not the same as Event object. *sideeyes web3.py developers.*
        """
        # Match the txn invoked method. Matching is done on the first 10 characters of the hash.
        transaction = self.uniswap_client._web3.eth.get_transaction(txn_hash)
        txn_method_sig_prefix = transaction['input'][:9]

        # Process the txn logs based on the method.
        # Ignore silo conversion events. They will be handled by the beanstalk class.
        if event_in_logs('Convert', event_logs):
            return

        # Each txn of interest should only include one ETH:BEAN swap.
        if len(event_logs) > 1:
            logging.warning(
                f'Multiple swaps of interest seen in a single txn ({str(event_logs)}).')
        for event_log in event_logs:
            event_str = UniswapPoolMonitor.any_event_str(
                event_log, self.uniswap_client.current_eth_price(),
                self.bean_client.uniswap_v2_bean_price())
            if event_str:
                self.message_function(event_str)

    @abstractmethod
    def any_event_str(event_log, eth_price, bean_price):
        event_str = ''
        # Parse possible values of interest from the event log. Not all will be populated.
        eth_amount = eth_chain.eth_to_float(event_log.args.get('amount0'))
        bean_amount = eth_chain.bean_to_float(event_log.args.get('amount1'))
        eth_in = eth_chain.eth_to_float(event_log.args.get('amount0In'))
        eth_out = eth_chain.eth_to_float(event_log.args.get('amount0Out'))
        bean_in = eth_chain.bean_to_float(event_log.args.get('amount1In'))
        bean_out = eth_chain.bean_to_float(event_log.args.get('amount1Out'))

        if event_log.event in ['Mint', 'Burn']:
            if event_log.event == 'Mint':
                event_str += f'📥 LP added - {round_num(bean_amount)} Beans and {round_num(eth_amount, 4)} ETH'
            if event_log.event == 'Burn':
                event_str += f'📤 LP removed - {round_num(bean_amount)} Beans and {round_num(eth_amount, 4)} ETH'
            # LP add/remove always takes equal value of both assets.
            lp_value = bean_amount * bean_price * 2
            event_str += f' (${round_num(lp_value)})'
            event_str += f'\n{value_to_emojis(lp_value)}'
        elif event_log.event == 'Swap':
            if eth_in:
                event_str += UniswapPoolMonitor.swap_event_str(
                    eth_price, bean_price, eth_in=eth_in, bean_out=bean_out)
            elif bean_in:
                event_str += UniswapPoolMonitor.swap_event_str(
                    eth_price, bean_price, bean_in=bean_in, eth_out=eth_out)

        event_str += f'\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>'
        # Empty line that does not get stripped.
        event_str += '\n_ _'
        return event_str

    @abstractmethod
    def swap_event_str(eth_price, bean_price, eth_in=None, bean_in=None, eth_out=None, bean_out=None):
        event_str = ''
        if ((not eth_in and not bean_in) or (not eth_out and not bean_out)):
            logging.error(
                'Must set at least one input and one output of swap.')
            return ''
        if ((eth_in and bean_in) or (eth_out and bean_out)):
            logging.error('Cannot set two inputs or two outputs of swap.')
            return ''
        if eth_in:
            event_str += f'📗 {round_num(bean_out)} Beans bought for {round_num(eth_in, 4)} ETH'
            swap_price = eth_chain.avg_eth_to_bean_swap_price(
                eth_in, bean_out, eth_price)
            swap_value = swap_price * bean_out
        elif bean_in:
            event_str += f'📕 {round_num(bean_in)} Beans sold for {round_num(eth_out, 4)} ETH'
            swap_price = eth_chain.avg_bean_to_eth_swap_price(
                bean_in, eth_out, eth_price)
            swap_value = swap_price * bean_in
        event_str += f' @ ${round_num(swap_price, 4)} (${round_num(swap_value)})'
        event_str += f'  -  Latest pool block price is ${round_num(bean_price, 4)}'
        event_str += f'\n{value_to_emojis(swap_value)}'
        return event_str
'''

class CurvePoolMonitor(Monitor):
    """Monitor a Curve pool for events."""

    def __init__(self, message_function, pool_type, prod=False, dry_run=False):
        if pool_type is eth_chain.EventClientType.CURVE_BEAN_3CRV_POOL:
            name = 'Bean:3CRV Curve Pool'
        else:
            raise ValueError('Curve pool must be set to a supported pool.')
        super().__init__(name, message_function,
                         POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_type = pool_type
        self._eth_event_client = eth_chain.EthEventsClient(
            self.pool_type)
        self.bean_client = eth_chain.BeanClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + POOL_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_hash, event_logs in self._eth_event_client.get_new_logs(dry_run=self._dry_run).items():
                self._handle_txn_logs(txn_hash, event_logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the curve pool event logs for a single txn.

        Assumes that there are no non-Bean:3CRV TokenExchangeUnderlying events in logs.
        Note that Event Log Object is not the same as Event object.
        """
        # Ignore Silo Convert txns, which will be handled by the Beanstalk monitor.
        transaction = self._eth_event_client._web3.eth.get_transaction(txn_hash)
        txn_method_sig_prefix = transaction['input'][:9]
        if sig_compare(txn_method_sig_prefix, eth_chain.convert_sigs.values()):
            return
        
        if self.pool_type == eth_chain.EventClientType.CURVE_BEAN_3CRV_POOL:
            bean_price = self.bean_client.curve_bean_3crv_bean_price()
        # No default since each pool must have support manually built in.
        for event_log in event_logs:
            event_str = self.any_event_str(
                event_log, bean_price)
            if event_str:
                self.message_function(event_str)

    def any_event_str(self, event_log, bean_price):
        event_str = ''
        # Parse possible values of interest from the event log. Not all will be populated.
        sold_id = event_log.args.get('sold_id')
        tokens_sold = event_log.args.get('tokens_sold')
        bought_id = event_log.args.get('bought_id')
        tokens_bought = event_log.args.get('tokens_bought')
        token_amounts = event_log.args.get('token_amounts')
        # Coin is a single ERC20 token, token is the pool token. So Coin can be Bean or 3CRV.
        token_amount = event_log.args.get('token_amount')
        coin_amount = event_log.args.get('coin_amount')

        if token_amounts is not None:
            bean_lp_amount = eth_chain.bean_to_float(
                token_amounts[eth_chain.FACTORY_3CRV_INDEX_BEAN])
            if (self.pool_type == eth_chain.EventClientType.CURVE_BEAN_3CRV_POOL):
                token_lp_amount = eth_chain.crv_to_float(
                    token_amounts[eth_chain.FACTORY_3CRV_INDEX_3CRV])
                token_lp_name = '3CRV'
                token_value = self.bean_client.curve_bean_3crv_token_value()
            value = bean_lp_amount * bean_price + token_lp_amount * token_value
        # RemoveLiquidityOne.
        if coin_amount is not None:
            if (self.pool_type == eth_chain.EventClientType.CURVE_BEAN_3CRV_POOL):
                token_value = self.bean_client.curve_bean_3crv_token_value()
            value = token_amount * token_value

        if event_log.event == 'TokenExchangeUnderlying' or event_log.event == 'TokenExchange':
            # Set the variables of quantity and direction of exchange.
            bean_out = stable_in = bean_in = stable_out = None
            if bought_id in [eth_chain.FACTORY_3CRV_UNDERLYING_INDEX_BEAN]:
                bean_out = eth_chain.bean_to_float(tokens_bought)
                stable_in = tokens_sold
                stable_id = sold_id
            elif sold_id in [eth_chain.FACTORY_3CRV_UNDERLYING_INDEX_BEAN]:
                bean_in = eth_chain.bean_to_float(tokens_sold)
                stable_out = tokens_bought
                stable_id = bought_id
            else:
                logging.warning(
                    'Exchange detected between two non-Bean tokens. Ignoring.')
                return ''

            # Set the stable name string and convert value to float.
            if event_log.event == 'TokenExchange':
                stable_name = '3CRV'
                stable_in = eth_chain.crv_to_float(stable_in)
                stable_out = eth_chain.crv_to_float(stable_out)
            elif stable_id == eth_chain.FACTORY_3CRV_UNDERLYING_INDEX_DAI:
                stable_name = 'DAI'
                stable_in = eth_chain.dai_to_float(stable_in)
                stable_out = eth_chain.dai_to_float(stable_out)
            elif stable_id == eth_chain.FACTORY_3CRV_UNDERLYING_INDEX_USDC:
                stable_name = 'USDC'
                stable_in = eth_chain.usdc_to_float(stable_in)
                stable_out = eth_chain.usdc_to_float(stable_out)
            elif stable_id == eth_chain.FACTORY_3CRV_UNDERLYING_INDEX_USDT:
                stable_name = 'USDT'
                stable_in = eth_chain.usdt_to_float(stable_in)
                stable_out = eth_chain.usdt_to_float(stable_out)
            else:
                logging.error(
                    f'Unexpected stable_id seen ({stable_id}) in exchange. Ignoring.')
                return ''

            event_str += self.exchange_event_str(bean_price, stable_name,
                                                 bean_out=bean_out, bean_in=bean_in,
                                                 stable_in=stable_in, stable_out=stable_out)
        elif event_log.event == 'AddLiquidity':
            event_str += f'📥 LP added - {round_num(bean_lp_amount, 0)} Beans and {round_num(token_lp_amount, 0)} {token_lp_name} (${round_num(value, 0)})'
        elif event_log.event == 'RemoveLiquidity' or event_log.event == 'RemoveLiquidityImbalance':
            event_str += f'📤 LP removed - {round_num(bean_lp_amount, 0)} Beans and {round_num(token_lp_amount, 0)} {token_lp_name} (${round_num(value, 0)})'
        elif event_log.event == 'RemoveLiquidityOne':
            event_str += f'📤 LP removed - ${round_num(value, 0)}'
        else:
            logging.warning(
                f'Unexpected event log seen in Curve Pool ({event_log.event}). Ignoring.')
            return ''

        event_str += f'\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>'
        # Empty line that does not get stripped.
        event_str += '\n_ _'
        return event_str

    def exchange_event_str(self, bean_price, stable_name, stable_in=None, bean_in=None, stable_out=None, bean_out=None):
        """Generate a standard token exchange string.

        Note that we assume all tokens in 3CRV have a value of $1.
        """
        event_str = ''
        if ((not stable_in and not bean_in) or (not stable_out and not bean_out)):
            logging.error(
                'Must set at least one input and one output of swap.')
            return ''
        if ((stable_in and bean_in) or (stable_out and bean_out)):
            logging.error('Cannot set two inputs or two outputs of swap.')
            return ''
        if stable_in:
            event_str += f'📗 {round_num(bean_out, 0)} Beans bought for {round_num(stable_in, 0)} {stable_name}'
            swap_price = stable_in / bean_out
            swap_value = stable_in
        elif bean_in:
            event_str += f'📕 {round_num(bean_in, 0)} Beans sold for {round_num(stable_out, 0)} {stable_name}'
            swap_price = stable_out / bean_in
            swap_value = stable_out
        event_str += f' @ ${round_num(swap_price, 4)} (${round_num(swap_value, 0)})'
        event_str += f'  -  Latest pool block price is ${round_num(bean_price, 4)}'
        event_str += f'\n{value_to_emojis(swap_value)}'
        return event_str


class BeanstalkMonitor(Monitor):
    """Monitor the Beanstalk contract for events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__('Beanstalk', message_function,
                         BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run)
        self._web3 = eth_chain.get_web3_instance()
        self._eth_event_client = eth_chain.EthEventsClient(
            eth_chain.EventClientType.BEANSTALK)
        self.beanstalk_graph_client = BeanstalkSqlClient()
        self.bean_client = eth_chain.BeanClient()
        self.beanstalk_client = eth_chain.BeanstalkClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + BEANSTALK_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_hash, event_logs in self._eth_event_client.get_new_logs(dry_run=self._dry_run).items():
                self._handle_txn_logs(txn_hash, event_logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        # Prune *plant* deposit logs. They are uninteresting clutter.
        # Prune *pick* deposit logs. They are uninteresting clutter.
        # For each event log remove a corresponding AddDeposit log.
        # event_logs_to_remove = []
        # for earn_event_log in get_logs_by_names(['Plant'], event_logs):
        for earn_event_log in get_logs_by_names(['Plant', 'Pick'], event_logs):
            for deposit_event_log in get_logs_by_names('AddDeposit', event_logs):
                if (deposit_event_log.args.get('token') == \
                    (earn_event_log.args.get('token') or BEAN_ADDR) and
                    deposit_event_log.args.get('amount') == \
                    (earn_event_log.args.get('beans') or earn_event_log.args.get('amount'))):
                    # event_logs_to_remove.append(deposit_event_log)
                    # Remove event log from event logs
                    event_logs.remove(deposit_event_log)
                    # At most allow 1 match.
                    logging.info(f'Ignoring a {earn_event_log.event} AddDeposit event')
                    break

        # for event_log in event_logs_to_remove:
        #     event_logs.remove(event_log)

        # Process conversion logs as a batch.
        if event_in_logs('Convert', event_logs):
            self.message_function(self.silo_conversion_str(
                event_logs, self.beanstalk_graph_client))
        # Handle txn logs individually using default strings.
        else:
            for event_log in event_logs:
                event_str = self.single_event_str(event_log,
                                                    self.beanstalk_graph_client)
                if event_str:
                    self.message_function(event_str)

    def single_event_str(self, event_log, beanstalk_graph_client):
        """Create a string representing a single event log.
        
        Events that are from a convert call should not be passed into this function as they
        should be processed in batch.
        """
        # Ignore deposits and withdrawals of unripe assets. Not interesting.
        if (event_log.event in ['AddDeposit', 'RemoveWithdrawal', 'RemoveWithdrawals']
           and event_log.args.get('token').startswith(UNRIPE_TOKEN_PREFIX)):
            return ''

        event_str = ''
        bean_price = self.bean_client.avg_bean_price()

        # Ignore these events. They are uninteresting clutter.
        if event_log.event in ['RemoveWithdrawal', 'RemoveWithdrawals', 'RemoveDeposit', 'RemoveDeposits', 'Plant', 'Pick']:
            return ''

        # Deposit & Withdraw events.
        elif event_log.event in ['AddDeposit', 'AddWithdrawal']:
            # Pull args from the event log.
            token_address = event_log.args.get('token')
            token_amount_long = event_log.args.get('amount') # AddDeposit, AddWithdrawal
            bdv = eth_chain.bean_to_float(event_log.args.get('bdv'))
            
            token_name, token_symbol, decimals = eth_chain.get_erc20_info(
                token_address, web3=self._web3)
            amount = eth_chain.token_to_float(
                token_amount_long, decimals)
                
            if bdv:
                value = bdv * bean_price
            elif token_address == BEAN_ADDR:
                value = amount * bean_price
            # Value is not known for withdrawals, so it must be calculated here.
            else:
                token_value = self.bean_client.get_lp_token_value(token_address, decimals)
                if token_value is not None:
                    value = amount * token_value
                else:
                    value = None

            if event_log.event in ['AddDeposit']:
                event_str += f'📥 Silo Deposit'
            elif event_log.event in ['AddWithdrawal']:
                event_str += f'📭 Silo Withdrawal'
            event_str += f' - {round_num_auto(amount, min_precision=0)} {token_symbol}'
            if value:
                event_str += f' (${round_num(value, 0)})'
                event_str += f'\n{value_to_emojis(value)}'
        
        # Sow event.
        elif event_log.event in ['Sow', 'Harvest']:
            # Pull args from the event log.
            beans_amount = eth_chain.bean_to_float(event_log.args.get('beans'))
            beans_value = beans_amount * bean_price
            pods_amount = eth_chain.bean_to_float(event_log.args.get('pods'))

            if event_log.event == 'Sow':
                event_str += f'🚜 {round_num(beans_amount, 0)} Beans sown for ' \
                    f'{round_num(pods_amount, 0)} Pods (${round_num(beans_value, 0)})'
                event_str += f'\n{value_to_emojis(beans_value)}'
            elif event_log.event == 'Harvest':
                event_str += f'👩‍🌾 {round_num(beans_amount, 0)} Pods harvested for Beans (${round_num(beans_value, 0)})'
                event_str += f'\n{value_to_emojis(beans_value)}'
        
        # Chop event.
        elif event_log.event in ['Chop']:
            token = event_log.args.get('token')
            underlying = self.beanstalk_client.get_underlying_token(token)
            _, chopped_symbol, chopped_decimals = eth_chain.get_erc20_info(token, self._web3)
            chopped_amount = eth_chain.token_to_float(event_log.args.get('amount'), chopped_decimals)
            _, underlying_symbol, underlying_decimals = eth_chain.get_erc20_info(underlying, self._web3)
            underlying_amount = eth_chain.token_to_float(event_log.args.get('underlying'), underlying_decimals)
            if underlying == BEAN_ADDR:
                underlying_token_value = bean_price
            # If underlying assets are Bean-based LP represented in price aggregator.
            # If not in aggregator, will return none and not display value.
            else:
                underlying_token_value = self.bean_client.get_lp_token_value(underlying, underlying_decimals)
            event_str += f'🪓 {round_num(chopped_amount, 0)} {chopped_symbol} Chopped for {round_num(underlying_amount, 0)} {underlying_symbol}'
            if underlying_token_value is not None:
                underlying_value = underlying_amount * underlying_token_value
                event_str += f' (${round_num(underlying_value, 0)})'

        # Unknown event type.
        else:
            logging.warning(
                f'Unexpected event log from Beanstalk contract ({event_log}). Ignoring.')
            return ''

        event_str += f'\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>'
        # Empty line that does not get stripped.
        event_str += '\n_ _'
        return event_str

    def silo_conversion_str(self, event_logs, beanstalk_graph_client):
        """Create a human-readable string representing a silo position conversion.

        Assumes that there are no non-Bean swaps contained in the event logs.
        Assumes event_logs is not empty.
        Assumes embedded AddDeposit logs have been removed from logs.
        Uses events from Beanstalk contract.
        """
        bean_price = self.bean_client.avg_bean_price()
        # Find the relevant logs, should contain one RemoveDeposit and one AddDeposit.
        for event_log in event_logs:
            if event_log.event in ['RemoveDeposit', 'RemoveDeposits']:
                remove_token_name, remove_token_symbol, remove_decimals = eth_chain.get_erc20_info(
                    event_log.args.get('token'), web3=self._web3)
                remove_float = eth_chain.token_to_float(
                    event_log.args.get('amount'), remove_decimals)
            elif event_log.event == 'AddDeposit':
                add_token_name, add_token_symbol, add_decimals = eth_chain.get_erc20_info(
                    event_log.args.get('token'), web3=self._web3)
                add_float = eth_chain.token_to_float(
                    event_log.args.get('amount'), add_decimals)
                bdv_float = eth_chain.bean_to_float(event_log.args.get('bdv'))
                value = bdv_float * bean_price

        event_str = f'🔄 {round_num_auto(remove_float, min_precision=0)} of siloed {remove_token_symbol} ' \
                    f'converted to {round_num_auto(add_float, min_precision=0)} siloed {add_token_symbol} ' \
                    f'(${round_num(value, 0)})'

        event_str += f'\nLatest block price is ${round_num(bean_price, 4)}'
        event_str += f'\n{value_to_emojis(value)}'
        event_str += f'\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>'
        # Empty line that does not get stripped.
        event_str += '\n_ _'
        return event_str


class MarketMonitor(Monitor):
    """Monitor the Beanstalk contract for market events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__('Market', message_function,
                         BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run)
        self._eth_event_client = eth_chain.EthEventsClient(
            eth_chain.EventClientType.MARKET)
        self._web3 = eth_chain.get_web3_instance()
        self.bean_client = eth_chain.BeanClient(self._web3)
        self.bean_contract = eth_chain.get_bean_contract(self._web3)
        self.beanstalk_contract = eth_chain.get_beanstalk_contract(self._web3)
        # self.uniswap_client = eth_chain.UniswapClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + BEANSTALK_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_hash, event_logs in self._eth_event_client.get_new_logs(dry_run=self._dry_run).items():
                self._handle_txn_logs(txn_hash, event_logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        # Match the txn invoked method. Matching is done on the first 10 characters of the hash.
        transaction_receipt = eth_chain.get_txn_receipt_or_wait(
            self._web3, txn_hash)

        # Handle txn logs individually using default strings.
        for event_log in event_logs:
            event_str = self.farmers_market_str(event_log, transaction_receipt)
            event_str += f'\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>'
            # Empty line that does not get stripped.
            event_str += '\n_ _'
            self.message_function(event_str)

    def farmers_market_str(self, event_log, transaction_receipt):
        """Create a human-readable string representing an event related to the farmer's market.

        Assumes event_log is an event of one of the types implemented below.
        Uses events from Beanstalk contract.
        """
        event_str = ''
        # Pull args from event logs. Not all will be populated.
        # Amount of pods being listed/ordered.
        amount = eth_chain.pods_to_float(event_log.args.get('amount'))
        price_per_pod = eth_chain.bean_to_float(
            event_log.args.get('pricePerPod'))

        # Index of the plot (place in line of first pod of the plot).
        plot_index = eth_chain.pods_to_float(event_log.args.get('index'))
        # Index of earliest pod to list, relative to start of plot.
        relative_start_index = eth_chain.pods_to_float(
            event_log.args.get('start'))
        # Absolute index of the first pod to list.
        start_index = plot_index + relative_start_index
        # Current index at start of pod line (number of pods ever harvested).
        pods_harvested = eth_chain.pods_to_float(
            eth_chain.call_contract_function_with_retry(
                self.beanstalk_contract.functions.harvestableIndex()))
        # Lowest place in line of a listing.
        start_place_in_line = start_index - pods_harvested
        # Highest place in line an order will purchase.
        order_max_place_in_line = eth_chain.pods_to_float(
            event_log.args.get('maxPlaceInLine'))

        bean_price = self.bean_client.avg_bean_price()
        amount_str = round_num(amount, 0)
        price_per_pod_str = round_num(price_per_pod, 3)
        start_place_in_line_str = round_num(start_place_in_line, 0)
        order_max_place_in_line_str = round_num(order_max_place_in_line, 0)

        if event_log.event == 'PodListingCreated':
            # Check if this was a relist.
            listing_cancelled_log = self.beanstalk_contract.events['PodListingCancelled'](
            ).processReceipt(transaction_receipt, errors=eth_chain.DISCARD)
            if listing_cancelled_log:
                event_str += f'♻ Pods relisted'
            else:
                event_str += f'✏ Pods listed'
            event_str += f' - {amount_str} Pods queued at {start_place_in_line_str} listed @ {price_per_pod_str} Beans/Pod (${round_num(amount * bean_price * price_per_pod)})'
        elif event_log.event == 'PodOrderCreated':
            # Check if this was a relist.
            order_cancelled_log = self.beanstalk_contract.events['PodOrderCancelled'](
            ).processReceipt(transaction_receipt, errors=eth_chain.DISCARD)
            if order_cancelled_log:
                event_str += f'♻ Pods reordered'
            else:
                event_str += f'🖌 Pods ordered'
            event_str += f' - {amount_str} Pods queued before {order_max_place_in_line_str} ordered @ {price_per_pod_str} Beans/Pod (${round_num(amount * bean_price * price_per_pod)})'
        elif event_log.event in ['PodListingFilled', 'PodOrderFilled']:
            # Pull the Bean Transfer log to find cost.
            if event_log.event == 'PodListingFilled':
                transfer_logs = self.bean_contract.events['Transfer']().processReceipt(
                    transaction_receipt, errors=eth_chain.DISCARD)
                logging.info(f'Transfer log(s):\n{transfer_logs}')
                # There should be exactly one transfer log of Beans.
                beans_paid = 0
                # NOTE(funderberker): Unclear if we need to account for balance changes or if we 
                #   can entirely rely on transfers. Using balance changes creates a significant
                #   problem of determining value or arbitrary assets.
                # balance_change_logs = self.beanstalk_contract.events['InternalBalanceChanged']().processReceipt(
                #     transaction_receipt, errors=eth_chain.DISCARD)
                # logging.info(f'InternalBalanceChanged log(s):\n{balance_change_logs}')
                # for log in balance_change_logs:
                #     # Determine asset value.
                #     token = log.args.get('token')
                #     amount = int(log.args.get('delta'))
                #     if amount >= 0:
                #         continue
                #     if token == BEAN_ADDR:
                #         token_bdv = 1.0
                #         decimals = eth_chain.BEAN_DECIMALS
                #     elif token == WRAPPED_ETH:
                #         token_bdv = self.uniswap_client.current_eth_price()
                #         decimals = eth_chain.ETH_DECIMALS
                #     else:
                #         try:
                #             token_bdv = self.bean_client.get_lp_token_value(token)
                #         except KeyError:
                #             token_bdv = 1.0
                #         _, _, decimals = eth_chain.get_erc20_info(token, web3=self._web3)
                #     # Assumes all bean balance deltas are spent on the Fill.
                #     beans_paid += abs(eth_chain.token_to_float(
                #         log.args.get('delta'), decimals))
                for log in transfer_logs:
                    if log.address == BEAN_ADDR:
                        beans_paid += eth_chain.bean_to_float(
                            log.args.get('value'))
                        break
                if not beans_paid:
                    err_str = f'Unable to determine Beans paid in market fill txn ' \
                              f'({transaction_receipt.transactionHash.hex()}). Exiting...'
                    logging.error(err_str)
                    raise ValueError(err_str)
            elif event_log.event == 'PodOrderFilled':
                # Get price from original order creation.
                # NOTE(funderberker): This is a lot of duplicate logic from EthEventsClient.get_new_logs()
                # that I simply do not have the bandwidth right now to refactor in a way that can be
                # used in both places.
                beanstalk_contract = eth_chain.get_beanstalk_contract(
                    self._web3)
                event_filter = beanstalk_contract.events.PodOrderCreated.createFilter(
                    # Feb 1, 2022 (before marketplace implementation).
                    fromBlock=14120000,
                    toBlock=int(transaction_receipt.blockNumber),
                    argument_filters={'id': event_log.args.get('id')}
                )
                log_entries = event_filter.get_all_entries()
                if len(log_entries) == 0:
                    logging.error('No PodOrderCreated event found. Exiting...')
                    raise ValueError(
                        f'Failed to locate PodOrderCreated event with id={event_log.args.get("id").hex()}.')
                # Typically there will only be a single PodOrderCreated per id, but if the order was
                # re-ordered then we use the latest order for pricing. Contract behavior here may
                # change in the future, but using the latest order with id will always be ok.
                log_entry = log_entries[-1]
                txn_hash = log_entry['transactionHash']
                transaction_receipt = eth_chain.get_txn_receipt_or_wait(
                    self._web3, txn_hash)
                decoded_log_entry = beanstalk_contract.events['PodOrderCreated']().processReceipt(
                    transaction_receipt, errors=eth_chain.DISCARD)[0]
                logging.info(decoded_log_entry)
                price_per_pod = decoded_log_entry.args.pricePerPod
                beans_paid = eth_chain.bean_to_float(price_per_pod) * amount
            event_str += f'💰 Pods Exchanged - {amount_str} Pods queued at ' \
                         f'{start_place_in_line_str} purchased @ {round_num(beans_paid/amount, 3)} ' \
                         f'Beans/Pod (${round_num(bean_price * beans_paid)})'
            event_str += f'\n{value_to_emojis(bean_price * beans_paid)}'
        # NOTE(funderberker): There is no way to meaningfully identify what has been cancelled, in
        # terms of amount/cost/etc. We could parse all previous creation events to find matching
        # index, but it is not clear that it is worth it.
        # elif event_log.event == 'PodListingCancelled':
        # elif event_log.event == 'PodOrderCancelled':
        return event_str


class BarnRaiseMonitor(Monitor):
    def __init__(self, message_function, report_events=True, report_summaries=False, prod=False, dry_run=False):
        super().__init__('BarnRaise', message_function,
                         BARN_RAISE_CHECK_RATE, prod=prod, dry_run=dry_run)
        self._web3 = eth_chain.get_web3_instance()
        # Used for special init cases
        # self.SUMMARY_BLOCK_RANGE = self._web3.eth.get_block('latest').number - 14918083
        # self.SUMMARY_BLOCK_RANGE = 1430 # ~ 6 hours
        self.SUMMARY_BLOCK_RANGE = 5720 + 1192 # ~ 24 hours, offset by 5 hours
        self.EMOJI_RANKS = ['🥇','🥈','🥉']
        self.report_events = report_events
        self.report_summaries = report_summaries
        self.barn_raise_client = eth_chain.BarnRaiseClient()
        self._eth_event_client = eth_chain.EthEventsClient(
            eth_chain.EventClientType.BARN_RAISE)
        self.steps_complete = self.barn_raise_client.steps_complete()

    def _monitor_method(self):
        last_check_time = 0
        
        while self._thread_active:
            # Wait until check rate time has passed.
            if time.time() < last_check_time + BARN_RAISE_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()

            # If reporting summaries and a 6 hour block has passed.
            if self.report_summaries:
                current_block = eth_chain.safe_get_block(self._web3, 'latest')
                # # if (time.time() - self.barn_raise_client.barn_raise_start) % (self.SUMMARY_HOUR_RANGE*3600) < BARN_RAISE_CHECK_RATE + 0.5:
                if (current_block.number - 14915799) % self.SUMMARY_BLOCK_RANGE == 0:
                # if True:
                    from_block = eth_chain.safe_get_block(self._web3, current_block.number - self.SUMMARY_BLOCK_RANGE)
                    time_range = current_block.timestamp - from_block.timestamp
                    all_events_in_time_range = []
                    for event_logs in self._eth_event_client.get_log_range(from_block=from_block.number, to_block=current_block.number).values():
                        all_events_in_time_range.extend(event_logs)
                    # Do not report a summary if nothing happened.
                    if len(all_events_in_time_range) == 0:
                        logging.info('No events detected to summarize. Skipping summary.')
                        continue
                    # Sort events based on size.
                    all_events_in_time_range = sorted(all_events_in_time_range, key=lambda event: event.args.get('value') or sum(event.args.get('values')), reverse=True)
                    # all_events_in_time_range = sorted(all_events_in_time_range, lambda(event: int(event.args.value)))
                    total_raised = 0
                    for event in all_events_in_time_range:
                        usdc_amount = int(event.args.value)
                        total_raised += usdc_amount
                    msg_str = f'🚛 In the past {round_num(time_range/3600, 1)} hours ${round_num(total_raised, 0)} was raised from {len(all_events_in_time_range)} txns'
                    remaining = self.barn_raise_client.remaining()
                    msg_str += f'\n🌱 ${round_num(BARN_RAISE_USDC_TARGET - remaining, 0)} ({round_num((BARN_RAISE_USDC_TARGET - remaining)/BARN_RAISE_USDC_TARGET*100, 2)}%) raised in total'
                    msg_str += f'\n'
                    for i in range(3):
                        try:
                            event = all_events_in_time_range[i]
                        # There may not be 3 events in a time block.
                        except IndexError:
                            break
                        # msg_str += f'\n{self.EMOJI_RANKS[i]} ${round_num(event.args.value, 0)} ({event.args["to"]})' # {event.transactionHash.hex()}
                        msg_str += f'\n{self.EMOJI_RANKS[i]} ${round_num(event.args.value, 0)} (https://etherscan.io/tx/{event.transactionHash.hex()})'

                    self.message_function(msg_str)
            
            # If reporting events.
            if self.report_events:
                # Check for new Bids, Bid updates, and Sows.
                all_events = []
                for event_logs in self._eth_event_client.get_new_logs(dry_run=self._dry_run).values():
                    all_events.extend(event_logs)
                for event_log in all_events:
                    self._handle_event_log(event_log)

    def _handle_event_log(self, event_log):
        """Process a single event log for the Barn Raise."""
        usdc_amount = None
        # Mint single.
        if event_log.event == 'TransferSingle' and event_log.args['from'] == NULL_ADDR:
            usdc_amount = int(event_log.args.value)
        # Mint batch.   <- is this even possible???
        elif event_log.event == 'TransferBatch' and event_log.args['from'] == NULL_ADDR:
            usdc_amount = sum([int(value) for value in event_log.args.values])
        
        if usdc_amount is not None:
            event_str = f'🚛 Fertilizer Purchased - {round_num(usdc_amount, 0)} USDC'
            event_str += f' (${round_num(BARN_RAISE_USDC_TARGET - self.barn_raise_client.remaining(), 0)} raised total)'
            event_str += f'\n{value_to_emojis(usdc_amount)}'
            event_str += f'\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>'
            # Empty line that does not get stripped.
            event_str += '\n_ _'
            self.message_function(event_str)


class DiscordSidebarClient(discord.ext.commands.Bot):

    def __init__(self, monitor, prod=False):
        super().__init__(command_prefix=commands.when_mentioned_or("!"))
        # There is only production for this bot.
        logging.info('Configured as a production instance.')

        self.nickname = ''
        self.status_text = ''
        self.monitor = monitor(self.set_nickname, self.set_status) # subclass of util.Monitor
        self.monitor.start()

        # Use discord.py reconnect logic for exceptions of this type.
        # Note that proper logs will not be generated.
        # self._update_naming.add_exception_type(discord.errors.DiscordServerError)
        # Start the price display task in the background.
        self._update_naming.start()

    def stop(self):
        self.monitor.stop()

    def set_nickname(self, text):
        """Set bot server nickname."""
        self.nickname = text

    def set_status(self, text):
        """Set bot custom status text."""
        self.status_text = text

    async def on_ready(self):
        # Log the commit of this run.
        logging.info('Git commit is ' + subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=os.path.dirname(os.path.realpath(__file__))
            ).decode('ascii').strip())

        self.user_id = self.user.id
        self.beanstalk_guild = self.get_guild(BEANSTALK_GUILD_ID)

    @tasks.loop(seconds=0.1, reconnect=True)
    async def _update_naming(self):
        if self.nickname:
            # Note(funderberker): Is this rate limited?
            await self.beanstalk_guild.me.edit(nick=self.nickname)
            logging.info(f'Bot nickname changed to {self.nickname}')
            self.nickname = ''
        if self.status_text:
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,
                                                                 name=self.status_text))
            logging.info(f'Bot status changed to {self.status_text}')
            self.status_text = ''

    @_update_naming.before_loop
    async def before__update_nickname_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()



class MsgHandler(logging.Handler):
    """A handler class which sends a message on a text channel."""

    def __init__(self, message_function):
        """
        Initialize the handler.
        """
        logging.Handler.__init__(self)
        self.message_function = message_function

    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        """
        try:
            msg = self.format(record)
            self.message_function(msg)
        except Exception:
            self.handleError(record)

    def __repr__(self):
        level = getLevelName(self.level)
        return '<%s %s (%s)>' % (self.__class__.__name__, self.baseFilename, level)

def event_in_logs(name, event_logs):
    for event_log in event_logs:
        if event_log.event == name:
            return True
    return False

def get_logs_by_names(names, event_logs):
    if type(names) == str:
        names = [names]
    events = []
    for event_log in event_logs:
        if event_log.event in names:
            events.append(event_log)
    return events


def sig_compare(signature, signatures):
    """Compare a signature to one or many signatures and return if there are any matches. 

    Comparison is made based on 10 character prefix.
    """
    if type(signatures) is str:
        signatures = [signatures]

    for sig in signatures:
        if signature[:9] == sig[:9]:
            return True
    return False


def lp_properties(beanstalk_graph_client):
    current_season_stats = beanstalk_graph_client.current_season_stats()
    pooled_eth = float(current_season_stats['pooledEth'])
    pooled_beans = float(current_season_stats['pooledBeans'])
    total_lp = float(current_season_stats['lp'])
    return pooled_eth, pooled_beans, total_lp


def lp_eq_values(lp, total_lp=None, pooled_eth=None, pooled_beans=None, beanstalk_graph_client=None):
    """Return the amount of ETH and beans equivalent to an amount of LP.

    Args:
        total_lp: current amount of lp in pool.
        pooled_eth: current amount of eth in pool.
        pooled_beans: current amount of beans in pool.
        beanstalk_graph_client: a beanstalk graphsql client. If provided latest season stats will
            be retrieved and used.
    """
    if beanstalk_graph_client:
        pooled_eth, pooled_beans, total_lp = lp_properties(
            beanstalk_graph_client)

    if None in [total_lp, pooled_eth, pooled_beans]:
        raise ValueError(
            'Must provide (total_lp & pooled_eth & pooled_beans) OR beanstalk_graph_client')

    bean_pool_ratio = pooled_beans / total_lp
    eth_pool_ratio = pooled_eth / total_lp
    eth_lp = lp * eth_pool_ratio
    bean_lp = lp * bean_pool_ratio
    return eth_lp, bean_lp


def round_num(number, precision=2):
    """Round a string or float to requested precision and return as a string."""
    return f'{float(number):,.{precision}f}'


def round_num_auto(number, sig_fig_min=3, min_precision=2):
    """Round a string or float and return as a string.

    Caller specifies the minimum significant figures and precision that that very large and very
    small numbers can both be handled.
    """
    if number > 1:
        return round_num(number, min_precision)
    return '%s' % float(f'%.{sig_fig_min}g' % float(number))


def value_to_emojis(value):
    """Convert a rounded dollar value to a string of emojis."""
    value = int(value)
    if value < 0:
        return ''
    value = round(value, -3)
    if value < 10000:
        return '🐟' * (value // 1000) or '🐟'
    value = round(value, -4)
    if value < 100000:
        return '🦈' * (value // 10000)
    value = round(value, -5)
    return '🐳' * (value // 100000)


def msg_includes_embedded_links(msg):
    """Attempt to detect if there are embedded links in this message. Not an exact system."""
    if msg.count(']('):
        return True


def handle_sigterm(signal_number, stack_frame):
    """Process a sigterm with a python exception for clean exiting."""
    logging.warning("Handling SIGTERM. Exiting.")
    raise SystemExit

# Configure uncaught exception handling for threads.


def log_thread_exceptions(args):
    """Log uncaught exceptions for threads."""
    logging.critical("Uncaught exception", exc_info=(
        args.exc_type, args.exc_value, args.exc_traceback))


threading.excepthook = log_thread_exceptions


def log_exceptions(exc_type, exc_value, exc_traceback):
    """Log uncaught exceptions for main thread."""
    logging.critical("Uncaught exception", exc_info=(
        exc_type, exc_value, exc_traceback))


def configure_main_thread_exception_logging():
    sys.excepthook = log_exceptions


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

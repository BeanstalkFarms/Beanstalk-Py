import datetime
import logging
import os
import threading
import time

import telebot

from beanstalk_python.subgraphs import bean_subgraph

# Note(funderberker): There is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds), so frequency should not be set too low.
UPDATE_FREQUENCY = 0.1 # hz



TELE_CHAT_ID = "-1001655547288" # Bot channel
# TELE_CHAT_ID = "2133333819" # Private DMs with funderberker

def get_utc_time_string(timestamp):
    """Convert and format timestamp into the string used for bot messages."""
    return datetime.datetime.utcfromtimestamp(timestamp).strftime("%H:%M:%S") + ' UTC'

class PegBot(object):

    def __init__(self):
        self.bean_subgraph_client = bean_subgraph.BeanSqlClient()

        self.tele_bot = telebot.TeleBot(
            os.environ.get('TELE_BOT_KEY'), parse_mode=None)

        self._active = False
        self._crossing_thread = None
        return

    def start(self):
        logging.info('Starting peg monitoring thread...')
        self._crossing_thread = threading.Thread(target=self._monitor_for_cross)
        self._active = True
        self._crossing_thread.start()
        # self._monitor_for_cross()

    def stop(self):
        logging.info('Stopping peg monitoring thread...')
        self._active = False
        self._crossing_thread.join(1 / UPDATE_FREQUENCY * 10)

    def wait_indefinitely(self):
        """Efficiently block main thread until interrupt or the monitoring thread is stopped."""
        self._crossing_thread.join()


    # NOTE(funderberker): subgraph implementation of cross data will change soon.
    def _monitor_for_cross(self):
        """Continuously monitor for BEAN price crossing the peg.
        
        Note that this assumes that block time > period of subgraph checks.
        """
        # Initialize.
        last_known_cross = self.bean_subgraph_client.last_peg_cross()
        logging.info(f'Initialized with last peg cross = {get_utc_time_string(last_known_cross)}')

        while self._active:
            time.sleep(1 / UPDATE_FREQUENCY)
            last_cross = self.bean_subgraph_client.last_peg_cross()
            if last_cross > last_known_cross:
                last_known_cross = last_cross
                logging.info('Peg cross detected.')
                # Send out messages indication a peg cross has occurred.
                comms_msg = f'Peg crossed at {get_utc_time_string(last_known_cross)}'
                # discord.XXXXX()
                self.tele_bot.send_message(chat_id=TELE_CHAT_ID, text=comms_msg)
                # twitter.XXXXX()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    try:
        bot = PegBot()
        bot.start()
        # Keep main thread alive.
        bot.wait_indefinitely()
    except KeyboardInterrupt:
        logging.warning('Interrupt detected. Exiting gracefully...')
        bot.stop()

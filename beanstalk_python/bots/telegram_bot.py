import asyncio
import logging
import os
import threading
import time

import telebot

from beanstalk_python.subgraphs import bean_subgraph
from beanstalk_python.bots import util


TELE_CHAT_ID = "-1001655547288"  # Bot channel
# TELE_CHAT_ID = "2133333819" # Private DMs with funderberker


class TelegramBot(object):

    def __init__(self):

        self.tele_bot = telebot.TeleBot(
            os.environ.get('TELE_BOT_KEY'), parse_mode=None)
        self._threads_active = False
        self._peg_cross_monitor = util.PegCrossMonitor()
        self._crossing_thread = None
        return

    def start_monitoring(self):
        logging.info('Starting peg monitoring thread...')
        self._threads_active = True
        self._crossing_thread = threading.Thread(
            target=self._monitor_for_cross)
        self._crossing_thread.start()

        # TODO(funderberker): Remove once we have a stable server.
        self.tele_bot.send_message(chat_id=TELE_CHAT_ID, text='The peg cross bot is now running.'
                                   '\n\nNote that slow access for the unpublished subgraph may cause crosses very near '
                                   'each other to be missed.')

    def stop(self):
        logging.info('Stopping peg monitoring thread...')
        self._threads_active = False
        self._crossing_thread.join(1 / util.PEG_UPDATE_FREQUENCY * 10)

        # TODO(funderberker): Remove once we have a stable server.
        self.tele_bot.send_message(
            chat_id=TELE_CHAT_ID, text="The peg cross bot is now stopped.")

    # NOTE(funderberker): subgraph implementation of cross data will change soon.
    def _monitor_for_cross(self):
        """Continuously monitor for BEAN price crossing the peg.

        Note that this assumes that block time > period of subgraph checks.
        """
        while self._threads_active:
            time.sleep(1 / util.PEG_UPDATE_FREQUENCY)
            cross_type = asyncio.run(
                self._peg_cross_monitor.check_for_peg_cross())
            if cross_type != util.PegCrossType.NO_CROSS:
                self.tele_bot.send_message(
                    chat_id=TELE_CHAT_ID, text=util.peg_cross_string(cross_type))
                logging.info(util.peg_cross_string(cross_type))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    try:
        bot = TelegramBot()
        bot.start_monitoring()
        bot.tele_bot.infinity_polling()
    except KeyboardInterrupt:
        logging.warning('Interrupt detected. Exiting gracefully...')
    finally:
        bot.stop()

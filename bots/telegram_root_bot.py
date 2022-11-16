import logging
import logging.handlers
import os
import signal

import telebot

from bots import util
from data_access.eth_chain import EventClientType

TELE_CHAT_ID_STAGING = "-1001655547288"  # Beanstalk Bot Testing channel
TELE_CHAT_ID_ROOT_PRODUCTION = "-1001688877681"  # Root Tracker channel
TELE_CHAT_ID_PARADOX_PRODUCTION = "-1001830693664"  # Paradox Tracker channel


class TelegramBot(object):

    def __init__(self, token, prod=False):

        if prod:
            self._chat_id_root = TELE_CHAT_ID_ROOT_PRODUCTION
            self._chat_id_paradox = TELE_CHAT_ID_PARADOX_PRODUCTION
            logging.info('Configured as a production instance.')
        else:
            self._chat_id_root = TELE_CHAT_ID_STAGING
            self._chat_id_paradox = TELE_CHAT_ID_STAGING
            logging.info('Configured as a staging instance.')

        self.tele_bot = telebot.TeleBot(token, parse_mode='Markdown')

        self.token_monitor = util.RootMonitor(self.send_msg_root, prod=prod, dry_run=False)
        self.token_monitor.start()

        self.betting_monitor = util.BettingMonitor(self.send_msg_paradox, prod=prod, dry_run=False)
        self.betting_monitor.start()

    def clean_msg(self, msg):
        # Note that Telegram uses pseudo md style and must use '_' for italics, rather than '*'.
        # Remove URL pointy brackets used by md formatting to suppress link previews.
        return msg.replace('<', '').replace('>', '')

    def send_msg_root(self, msg):
        # Ignore empty messages.
        if not msg:
            return
        msg = self.clean_msg(msg)
        self.tele_bot.send_message(
            chat_id=self._chat_id_root, text=msg, disable_web_page_preview=True)
        logging.info(f'Message sent in root channel:\n{msg}\n')

    def send_msg_paradox(self, msg):
        # Ignore empty messages.
        if not msg:
            return
        msg = self.clean_msg(msg)
        self.tele_bot.send_message(
            chat_id=self._chat_id_paradox, text=msg, disable_web_page_preview=True)
        logging.info(f'Message sent in paradox channel:\n{msg}\n')

    def stop(self):
        self.token_monitor.stop()


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(format=f'Telegram Root Bot : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "telegram_root_bot.log", maxBytes=util.ONE_HUNDRED_MEGABYTES, backupCount=1),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["TELEGRAM_ROOT_BOT_TOKEN_PROD"]
        prod = True
    except KeyError:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        prod = False

    bot = TelegramBot(token=token, prod=prod)
    try:
        bot.tele_bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()

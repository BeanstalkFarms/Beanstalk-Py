import logging
import logging.handlers
import os
import signal

import telebot

from bots import util
from data_access.eth_chain import EventClientType

TELE_CHAT_ID_STAGING = "-1001655547288"  # Beanstalk Bot Testing channel
TELE_CHAT_ID_PRODUCTION = "-1001688877681"  # Root Tracker channel


class TelegramBot(object):

    def __init__(self, token, prod=False):

        if prod:
            self._chat_id = TELE_CHAT_ID_PRODUCTION
            logging.info('Configured as a production instance.')
        else:
            self._chat_id = TELE_CHAT_ID_STAGING
            logging.info('Configured as a staging instance.')

        self.tele_bot = telebot.TeleBot(token, parse_mode='Markdown')

        self.token_monitor = util.RootMonitor(self.send_msg, prod=prod, dry_run=False)
        self.token_monitor.start()

        self.betting_monitor = util.BettingMonitor(self.send_msg, prod=prod, dry_run=False)
        self.betting_monitor.start()

    def send_msg(self, msg):
        # Ignore empty messages.
        if not msg:
            return
        # Remove URL pointy brackets used by md formatting to suppress link previews.
        msg = msg.replace('<', '').replace('>', '')
        # Note that Telegram uses pseudo md style and must use '_' for italics, rather than '*'.
        self.tele_bot.send_message(
            chat_id=self._chat_id, text=msg, disable_web_page_preview=True)
        logging.info(f'Message sent:\n{msg}\n')

    def stop(self):
        self.token_monitor.stop()
        self.betting_monitor.stop()


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

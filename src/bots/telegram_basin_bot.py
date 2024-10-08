import logging
import logging.handlers
import os
import signal

import telebot
from telebot import apihelper

from bots import util
from constants.config import *
from constants.channels import *
from constants.addresses import *

from monitors.basin_periodic import BasinPeriodicMonitor
from monitors.well import WellsMonitor, OtherWellsMonitor

class TelegramBasinBot(object):
    def __init__(self, token, prod=False, dry_run=None):
        if prod:
            self._chat_id = DEX_TELE_CHAT_ID_PRODUCTION
            logging.info("Configured as a production instance.")
        else:
            self._chat_id = DEX_TELE_CHAT_ID_STAGING
            logging.info("Configured as a staging instance.")

        apihelper.SESSION_TIME_TO_LIVE = 5 * 60
        self.tele_bot = telebot.TeleBot(token, parse_mode="Markdown")

        self.period_monitor = BasinPeriodicMonitor(self.send_msg, prod=prod, dry_run=dry_run)
        self.period_monitor.start()

        self.wells_monitor = WellsMonitor(
            self.send_msg, WHITELISTED_WELLS, prod=prod, dry_run=dry_run
        )
        self.wells_monitor.start()

        self.wells_monitor_all = OtherWellsMonitor(
            self.send_msg, WHITELISTED_WELLS, discord=False, prod=prod, dry_run=dry_run
        )
        self.wells_monitor_all.start()

    def send_msg(self, msg):
        # Ignore empty messages.
        if not msg:
            return
        # Remove URL pointy brackets used by md formatting to suppress link previews.
        msg = msg.replace("<http", "http").replace(">", "")
        # Note that Telegram uses pseudo md style and must use '_' for italics, rather than '*'.
        self.tele_bot.send_message(chat_id=self._chat_id, text=msg, disable_web_page_preview=True)
        logging.info(f"Message sent:\n{msg}\n")

    def stop(self):
        self.period_monitor.stop()
        self.wells_monitor.stop()
        self.wells_monitor_all.stop()


if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(
        format=f"Telegram Basin Bot : {LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/telegram_basin_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    token = os.environ["TELEGRAM_DEX_BOT_TOKEN"]
    prod = os.environ["IS_PROD"].lower() == "true"
    dry_run = os.environ.get("DRY_RUN")
    if dry_run:
        dry_run = dry_run.split(',')

    bot = TelegramBasinBot(token=token, prod=prod, dry_run=dry_run)
    try:
        bot.tele_bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()

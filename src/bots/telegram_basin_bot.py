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
from monitors.well import WellMonitor, AllWellsMonitor

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

        self.well_monitor_bean_eth = WellMonitor(
            self.send_msg, BEAN_ETH_WELL_ADDR, prod=prod, dry_run=dry_run
        )
        self.well_monitor_bean_eth.start()
        
        self.well_monitor_bean_wsteth = WellMonitor(
            self.send_msg, BEAN_WSTETH_WELL_ADDR, prod=prod, dry_run=dry_run
        )
        self.well_monitor_bean_wsteth.start()

        self.well_monitor_all = AllWellsMonitor(
            self.send_msg, [BEAN_ETH_WELL_ADDR, BEAN_WSTETH_WELL_ADDR], discord=False, prod=prod, dry_run=dry_run
        )
        self.well_monitor_all.start()

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
        self.well_monitor_bean_eth.stop()
        self.well_monitor_bean_wsteth.stop()
        self.well_monitor_all.stop()


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

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["TELEGRAM_BASIN_BOT_TOKEN_PROD"]
        prod = True
    except KeyError:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        prod = False
        dry_run = os.environ.get("DRY_RUN")
        if dry_run:
            dry_run = dry_run.split(',')

    bot = TelegramBasinBot(token=token, prod=prod, dry_run=dry_run)
    try:
        bot.tele_bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()

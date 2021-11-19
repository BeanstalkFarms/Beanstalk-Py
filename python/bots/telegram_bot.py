import asyncio
import logging
import os
import threading
import time

import telebot

from bots import util


TELE_CHAT_ID = "-1001655547288"  # Bot channel


class TelegramBot(object):

    def __init__(self):
        self.tele_bot = telebot.TeleBot(
            os.environ.get('TELE_BOT_KEY'), parse_mode='Markdown')
        
        self.peg_cross_monitor = util.PegCrossMonitor(self.send_msg)
        self.peg_cross_monitor.start()

        self.sunrise_monitor = util.SunriseMonitor(self.send_msg)
        self.sunrise_monitor.start()

    def send_msg(self, text):
        self.tele_bot.send_message(chat_id=TELE_CHAT_ID, text=text)

    def stop(self):
        self.peg_cross_monitor.stop()
        self.sunrise_monitor.stop()
    

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    bot = TelegramBot()
    bot.tele_bot.infinity_polling()
    bot.stop()

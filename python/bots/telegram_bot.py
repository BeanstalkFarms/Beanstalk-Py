import logging
import os

import telebot

from bots import util

TELE_CHAT_ID_STAGING = "-1001655547288" # Beanstalk Bot Testing channel
TELE_CHAT_ID_PRODUCTION = "-1001770089535" # Beanstalk Tracker channel

class TelegramBot(object):

    def __init__(self, token, prod=False):

        if prod:
            self._chat_id = TELE_CHAT_ID_PRODUCTION
            logging.info('Configured as a production instance.')
        else:
            self._chat_id = TELE_CHAT_ID_STAGING
            logging.info('Configured as a staging instance.')

        self.tele_bot = telebot.TeleBot(token, parse_mode='Markdown')
        
        self.peg_cross_monitor = util.PegCrossMonitor(self.send_msg)
        self.peg_cross_monitor.start()

        self.sunrise_monitor = util.SunriseMonitor(self.send_msg)
        self.sunrise_monitor.start()

    def send_msg(self, text):
        self.tele_bot.send_message(chat_id=self._chat_id, text=text)

    def stop(self):
        self.peg_cross_monitor.stop()
        self.sunrise_monitor.stop()
    

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["TELEGRAM_BOT_TOKEN_PROD"]
        prod = True
    except KeyError:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        prod = False

    bot = TelegramBot(token=token, prod=prod)
    try:
        bot.tele_bot.infinity_polling()
    except KeyboardInterrupt:
        pass
    bot.stop()

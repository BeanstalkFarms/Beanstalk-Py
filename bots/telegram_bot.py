import logging
import logging.handlers
import os
import signal

import telebot

from bots import util
from data_access.eth_chain import EventClientType

TELE_CHAT_ID_STAGING = "-1001655547288"  # Beanstalk Bot Testing channel
TELE_CHAT_ID_PRODUCTION = "-1001770089535"  # Beanstalk Tracker channel


class TelegramBot(object):

    def __init__(self, token, prod=False):

        if prod:
            self._chat_id = TELE_CHAT_ID_PRODUCTION
            logging.info('Configured as a production instance.')
        else:
            self._chat_id = TELE_CHAT_ID_STAGING
            logging.info('Configured as a staging instance.')

        self.tele_bot = telebot.TeleBot(token, parse_mode='Markdown')

        self.peg_cross_monitor = util.PegCrossMonitor(self.send_msg, prod=prod)
        self.peg_cross_monitor.start()

        self.sunrise_monitor = util.SunriseMonitor(self.send_msg, prod=prod)
        self.sunrise_monitor.start()

        self.uniswap_pool_monitor = util.UniswapPoolMonitor(self.send_msg, prod=prod)
        self.uniswap_pool_monitor.start()

        self.curve_3crv_pool_monitor = util.CurvePoolMonitor(
            self.send_msg, EventClientType.CURVE_3CRV_POOL, prod=prod)
        self.curve_3crv_pool_monitor.start()

        self.curve_lusd_pool_monitor = util.CurvePoolMonitor(
            self.send_msg_pool, EventClientType.CURVE_LUSD_POOL, prod=prod)
        self.curve_lusd_pool_monitor.start()

        self.beanstalk_monitor = util.BeanstalkMonitor(self.send_msg, prod=prod)
        self.beanstalk_monitor.start()

        self.market_monitor = util.MarketMonitor(self.send_msg, prod=prod)
        self.market_monitor.start()

    def send_msg(self, msg):
        # Ignore empty messages.
        if not msg:
            return
        # Remove URL pointy brackets used by md formatting to suppress link previews.
        msg = msg.replace('<', '').replace('>', '')
        self.tele_bot.send_message(
            chat_id=self._chat_id, text=msg, disable_web_page_preview=True)
        logging.info(f'Message sent:\n{msg}\n')

    def stop(self):
        self.peg_cross_monitor.stop()
        self.sunrise_monitor.stop()
        self.uniswap_pool_monitor.stop()
        self.curve_3crv_pool_monitor.stop()
        self.curve_lusd_pool_monitor.stop()
        self.beanstalk_monitor.stop()
        self.market_monitor.stop()


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(format=f'Telegram Bot : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "telegram_bot.log", maxBytes=util.ONE_HUNDRED_MEGABYTES),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

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
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()

import logging
import logging.handlers
import os
import signal
import time
import tweepy

from bots import util
from constants.addresses import *


class TwitterBot(object):
    def set_keys_staging(self):
        self.api_key = os.environ["TWITTER_BOT_API_KEY"]
        self.api_key_secret = os.environ["TWITTER_BOT_API_KEY_SECRET"]
        self.access_token = os.environ["TWITTER_BOT_ACCESS_TOKEN"]
        self.access_token_secret = os.environ["TWITTER_BOT_ACCESS_TOKEN_SECRET"]

    def set_client(self):
        self.client = tweepy.Client(
            consumer_key=self.api_key, consumer_secret=self.api_key_secret,
            access_token=self.access_token, access_token_secret=self.access_token_secret
        )

    def send_msg(self, msg):
        logging.info(f'Attempting to tweet:\n{msg}\n')
        # Remove URL pointy brackets used by md formatting to suppress link previews.
        msg = msg.replace('<', '').replace('>', '')
        try:
            self.client.create_tweet(text=msg)
        except tweepy.errors.BadRequest as e:
            logging.error(f'HTTP Error 400 (Bad Request) for tweet with body "{msg}" '
                         f'\n{e.api_messages}\n\n{e.response}\n\n{e.api_errors}')
            return
        except tweepy.errors.Forbidden as e:
            logging.error(f'HTTP Error 403 (Forbidden) for tweet with body "{msg}" '
                         f'Was it a repeat tweet?\n{e.api_messages}\n\n{e.response}\n\n{e.api_errors}')
            return
        except tweepy.errors.TooManyRequests as e:
            logging.error(f'HTTP Error 429 (Too Many Requests) for tweet with body "{msg}" '
                         f'\n{e.api_messages}\n\n{e.response}\n\n{e.api_errors}'
                         f'\n\nAggressively idling...')
            time.sleep(16 * 60) # Wait 16 minutes to be safe, expect 15 minutes to reset.
            return
        logging.info(f'Tweeted:\n{msg}\n')



class BeanstalkTwitterBot(TwitterBot):

    def __init__(self, prod=False):
        if prod:
            self.api_key = os.environ["TWITTER_BOT_API_KEY_PROD"]
            self.api_key_secret = os.environ["TWITTER_BOT_API_KEY_SECRET_PROD"]
            self.access_token = os.environ["TWITTER_BOT_ACCESS_TOKEN_PROD"]
            self.access_token_secret = os.environ["TWITTER_BOT_ACCESS_TOKEN_SECRET_PROD"]
            logging.info('BeanstalkTwitterBot configured as a production instance.')
        else:
            self.set_keys_staging()
            logging.info('BeanstalkTwitterBot configured as a staging instance.')
        self.set_client()

        self.sunrise_monitor = util.SeasonsMonitor(self.send_msg, short_msgs=True, prod=prod)
        self.sunrise_monitor.start()

    def stop(self):
        self.sunrise_monitor.stop()


class RootTwitterBot(TwitterBot):

    def __init__(self, prod=False):
        if prod:
            self.api_key = os.environ["TWITTER_ROOT_BOT_API_KEY_PROD"]
            self.api_key_secret = os.environ["TWITTER_ROOT_BOT_API_KEY_SECRET_PROD"]
            self.access_token = os.environ["TWITTER_ROOT_BOT_ACCESS_TOKEN_PROD"]
            self.access_token_secret = os.environ["TWITTER_ROOT_BOT_ACCESS_TOKEN_SECRET_PROD"]
            logging.info('RootTwitterBot configured as a production instance.')
        else:
            self.set_keys_staging()
            logging.info('RootTwitterBot configured as a staging instance.')
        self.set_client()

        self.token_monitor = util.RootMonitor(self.send_msg, prod=prod, dry_run=False)
        self.token_monitor.start()

        self.uniswap_monitor = util.RootUniswapMonitor(
            self.send_msg, prod=prod, dry_run=False)
        self.uniswap_monitor.start()

    def stop(self):
        self.token_monitor.stop()
        self.uniswap_monitor.stop()


class ParadoxTwitterBot(TwitterBot):
    def __init__(self, prod=False):
        if prod:
            self.api_key = os.environ["TWITTER_PARADOX_BOT_API_KEY_PROD"]
            self.api_key_secret = os.environ["TWITTER_PARADOX_BOT_API_KEY_SECRET_PROD"]
            self.access_token = os.environ["TWITTER_PARADOX_BOT_ACCESS_TOKEN_PROD"]
            self.access_token_secret = os.environ["TWITTER_PARADOX_BOT_ACCESS_TOKEN_SECRET_PROD"]
            logging.info('ParadoxTwitterBot configured as a production instance.')
        else:
            self.set_keys_staging()
            logging.info('ParadoxTwitterBot configured as a staging instance.')
        self.set_client()

        self.betting_monitor = util.BettingMonitor(self.send_msg, prod=prod, dry_run=False)
        self.betting_monitor.start()

    def stop(self):
        self.betting_monitor.stop()


class BasinTwitterBot(TwitterBot):
    def __init__(self, prod=False):
        if prod:
            self.api_key = os.environ["TWITTER_BASIN_BOT_API_KEY_PROD"]
            self.api_key_secret = os.environ["TWITTER_BASIN_BOT_API_KEY_SECRET_PROD"]
            self.access_token = os.environ["TWITTER_BASIN_BOT_ACCESS_TOKEN_PROD"]
            self.access_token_secret = os.environ["TWITTER_BASIN_BOT_ACCESS_TOKEN_SECRET_PROD"]
            logging.info('BasinTwitterBot configured as a production instance.')
        else:
            self.set_keys_staging()
            logging.info('BasinTwitterBot configured as a staging instance.')
        self.set_client()

        self.betting_monitor = util.BettingMonitor(self.send_msg, prod=prod, dry_run=False)
        self.betting_monitor.start()

        self.well_monitor_bean_eth = util.WellMonitor(
            self.send_msg, BEAN_ETH_WELL_ADDR, prod=prod, dry_run=False)
        self.well_monitor_bean_eth.start()

    def stop(self):
        self.well_monitor_bean_eth.stop()


def infinity_polling():
    """Sleep forever while monitors run on background threads. Exit via interrupt."""
    while True:
        time.sleep(5)


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(format=f'Twitter Bots : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "twitter_bots.log", maxBytes=util.ONE_HUNDRED_MEGABYTES, backupCount=1),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["TWITTER_BOT_API_KEY_PROD"]
        prod = True
    except KeyError:
        prod = False

    beanstalk_bot = BeanstalkTwitterBot(prod=prod)
    root_bot = RootTwitterBot(prod=prod)
    paradox_bot = ParadoxTwitterBot(prod=prod)
    # basin_bot = BasinTwitterBot(prod=prod)
    try:
        infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    beanstalk_bot.stop()
    root_bot.stop()
    paradox_bot.stop()
    # basin_bot.stop()

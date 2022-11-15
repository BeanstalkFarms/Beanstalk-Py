import logging
import logging.handlers
import os
import signal
import time
import tweepy

from bots import util


class TwitterRootBot(object):

    def __init__(self, prod=False):

        if prod:
            api_key = os.environ["TWITTER_ROOT_BOT_API_KEY_PROD"]
            api_key_secret = os.environ["TWITTER_ROOT_BOT_API_KEY_SECRET_PROD"]
            access_token = os.environ["TWITTER_ROOT_BOT_ACCESS_TOKEN_PROD"]
            access_token_secret = os.environ["TWITTER_ROOT_BOT_ACCESS_TOKEN_SECRET_PROD"]
            logging.info('Configured as a production instance.')
        else:
            # Use same staging account as Beanstalk.
            api_key = os.environ["TWITTER_BOT_API_KEY"]
            api_key_secret = os.environ["TWITTER_BOT_API_KEY_SECRET"]
            access_token = os.environ["TWITTER_BOT_ACCESS_TOKEN"]
            access_token_secret = os.environ["TWITTER_BOT_ACCESS_TOKEN_SECRET"]
            logging.info('Configured as a staging instance.')

        self.client = tweepy.Client(
            consumer_key=api_key, consumer_secret=api_key_secret,
            access_token=access_token, access_token_secret=access_token_secret
        )

        self.betting_monitor = util.BettingMonitor(self.send_msg, prod=prod)
        self.betting_monitor.start()

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

    def stop(self):
        self.betting_monitor.stop()

    def infinity_polling(self):
        """Sleep forever while monitors run on background threads. Exit via interrupt."""
        while True:
            time.sleep(5)

if __name__ == '__main__':
    """Run with infinity polling using entire process."""
    logging.basicConfig(format=f'Twitter Root Bot : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "twitter_root_bot.log", maxBytes=util.ONE_HUNDRED_MEGABYTES, backupCount=1),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["TWITTER_ROOT_BOT_API_KEY_PROD"]
        prod = True
    except KeyError:
        prod = False

    bot = TwitterRootBot(prod=prod)
    try:
        bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()

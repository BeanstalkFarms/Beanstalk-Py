import logging
import logging.handlers
import os
import signal
import time
import tweepy

from bots import util


class TwitterBot(object):

    def __init__(self, prod=False):

        if prod:
            api_key = os.environ["TWITTER_BOT_API_KEY_PROD"]
            api_key_secret = os.environ["TWITTER_BOT_API_KEY_SECRET_PROD"]
            access_token = os.environ["TWITTER_BOT_ACCESS_TOKEN_PROD"]
            access_token_secret = os.environ["TWITTER_BOT_ACCESS_TOKEN_SECRET_PROD"]
            logging.info('Configured as a production instance.')
        else:
            api_key = os.environ["TWITTER_BOT_API_KEY"]
            api_key_secret = os.environ["TWITTER_BOT_API_KEY_SECRET"]
            access_token = os.environ["TWITTER_BOT_ACCESS_TOKEN"]
            access_token_secret = os.environ["TWITTER_BOT_ACCESS_TOKEN_SECRET"]
            logging.info('Configured as a staging instance.')

        self.client = tweepy.Client(
            consumer_key=api_key, consumer_secret=api_key_secret,
            access_token=access_token, access_token_secret=access_token_secret
        )

        ############ DISABLE SUNRISE MONITOR DURING BARN RAISE PRE SALE ############
        # self.sunrise_monitor = util.SeasonsMonitor(
        #     self.send_msg, short_msgs=True, prod=prod)
        # self.sunrise_monitor.start()
        #############################################################################
        self.barn_raise_monitor = util.BarnRaiseMonitor(
            self.send_msg, report_events=False, report_summaries=True, prod=prod)
        self.barn_raise_monitor.start()

    def send_msg(self, msg):
        # Remove URL pointy brackets used by md formatting to suppress link previews.
        msg = msg.replace('<', '').replace('>', '')
        try:
            self.client.create_tweet(text=msg)
        except tweepy.errors.BadRequest as e:
            logging.info(f'HTTP Error 400 (Bad Request) for tweet with body "{msg}" '
                         f'\n{e.api_messages}')
            return
        except tweepy.errors.Forbidden as e:
            logging.info(f'HTTP Error 403 (Forbidden) for tweet with body "{msg}" '
                         f'Was it a repeat tweet?\n{e.api_messages}')
            return
        except e:
            logging.info(f'HTTP Error 403 (Forbidden) for tweet with body "{msg}" '
                         f'Was it a repeat tweet?\n{e.api_messages}')
            return
        logging.info(f'Tweeted:\n{msg}\n')

    def stop(self):
        ############ DISABLE SUNRISE MONITOR DURING BARN RAISE PRE SALE ############
        # self.sunrise_monitor.stop()
        #############################################################################
        self.barn_raise_monitor.stop()

    def infinity_polling(self):
        """Sleep forever while monitors run on background threads. Exit via interrupt."""
        while True:
            time.sleep(5)


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(format=f'Twitter Bot : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "twitter_bot.log", maxBytes=util.ONE_HUNDRED_MEGABYTES),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["TWITTER_BOT_API_KEY_PROD"]
        prod = True
    except KeyError:
        prod = False

    bot = TwitterBot(prod=prod)
    try:
        bot.infinity_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    bot.stop()

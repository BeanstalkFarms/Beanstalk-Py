import logging
import logging.handlers
import os
import signal

from bots import util


if __name__ == '__main__':
    logging.basicConfig(format=f'Discord Price Bot : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "discord_price_bot.log", maxBytes=util.ONE_HUNDRED_MEGABYTES/5),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    price_bot_token = os.environ["DISCORD_PRICE_BOT_TOKEN_PROD"]
    discord_price_bot = util.DiscordSidebarClient(util.PricePreviewMonitor)

    try:
        discord_price_bot.run(price_bot_token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    discord_price_bot.stop()

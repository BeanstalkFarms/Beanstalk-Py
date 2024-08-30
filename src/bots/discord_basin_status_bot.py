import logging
import logging.handlers
import os
import signal

from constants.config import ONE_HUNDRED_MEGABYTES

from bots import util
from monitors.preview.basin import BasinStatusPreviewMonitor

if __name__ == "__main__":
    logging.basicConfig(
        format=f"Discord Basin Status Bot : {util.LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/discord_basin_status_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["DISCORD_BASIN_STATUS_BOT_TOKEN_PROD"]
        prod = True
        logging.info("Configured as a production instance.")
    except KeyError:
        # Note this is the *shared* discord staging bot.
        token = os.environ["DISCORD_BOT_TOKEN"]
        prod = False

    client = util.DiscordSidebarClient(BasinStatusPreviewMonitor)

    try:
        client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    client.stop()
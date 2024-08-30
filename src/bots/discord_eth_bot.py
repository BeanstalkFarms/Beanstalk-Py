"""Bot for the Discord sidebar that displays interesting status info about Eth Mainnet."""

import logging
import logging.handlers
import os
import signal

from constants.config import ONE_HUNDRED_MEGABYTES

from bots import util
from monitors.preview.eth import EthPreviewMonitor

if __name__ == "__main__":
    logging.basicConfig(
        format=f"Discord Eth Bot : {util.LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/discord_eth_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["DISCORD_ETH_BOT_TOKEN_PROD"]
        prod = True
        logging.info("Configured as a production instance.")
    except KeyError:
        # Note this is the shared discord staging bot.
        token = os.environ["DISCORD_BOT_TOKEN"]
        prod = False

    client = util.DiscordSidebarClient(EthPreviewMonitor)

    try:
        client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    client.stop()
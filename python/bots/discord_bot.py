from enum import Enum
import logging
import signal
import os

import discord
from discord.ext import tasks, commands

from bots import util


DISCORD_CHANNEL_ID_PEG_CROSSES = 911338190198169710
DISCORD_CHANNEL_ID_SEASONS = 911338078080221215
DISCORD_CHANNEL_ID_POOL = 915372733758603284
DISCORD_CHANNEL_ID_TEST_BOT = 908035718859874374


class DiscordClient(discord.Client):

    class Channel(Enum):
        PEG = 0
        SEASONS = 1
        POOL = 2

    def __init__(self, prod=False):
        super().__init__()

        if prod:
            self._chat_id_peg = DISCORD_CHANNEL_ID_PEG_CROSSES
            self._chat_id_seasons = DISCORD_CHANNEL_ID_SEASONS
            self._chat_id_pool = DISCORD_CHANNEL_ID_POOL
            logging.info('Configured as a production instance.')
        else:
            self._chat_id_peg = DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_seasons = DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_pool = DISCORD_CHANNEL_ID_TEST_BOT
            logging.info('Configured as a staging instance.')

        self.msg_queue = []

        self.peg_cross_monitor = util.PegCrossMonitor(self.send_msg_peg, prod=prod)
        self.peg_cross_monitor.start()

        self.sunrise_monitor = util.SunriseMonitor(self.send_msg_seasons, prod=prod)
        self.sunrise_monitor.start()

        self.pool_monitor = util.PoolMonitor(self.send_msg_pool, prod=prod)
        self.pool_monitor.start()

        # Start the message queue sending task in the background.
        self.send_queued_messages.start()

    def stop(self):
        self.peg_cross_monitor.stop()
        self.sunrise_monitor.stop()
        self.pool_monitor.stop()

    def send_msg_peg(self, text):
        """Send a message through the Discord bot in the peg channel."""
        self.msg_queue.append((self.Channel.PEG, text))

    def send_msg_seasons(self, text):
        """Send a message through the Discord bot in the seasons channel."""
        self.msg_queue.append((self.Channel.SEASONS, text))

    def send_msg_pool(self, text):
        """Send a message through the Discord bot in the pool channel."""
        self.msg_queue.append((self.Channel.POOL, text))

    async def on_ready(self):
        self._channel_peg = discord_client.get_channel(self._chat_id_peg)
        self._channel_seasons = discord_client.get_channel(self._chat_id_seasons)
        self._channel_pool = discord_client.get_channel(self._chat_id_pool)
        logging.info(
            f'Discord channels are {self._channel_peg}, {self._channel_seasons}, {self._channel_pool}')

    @tasks.loop(seconds=0.1, reconnect=True)
    async def send_queued_messages(self):
        """Send messages in queue."""
        for channel, msg in self.msg_queue:
            if channel is self.Channel.PEG:
                await self._channel_peg.send(msg)
            elif channel is self.Channel.SEASONS:
                await self._channel_seasons.send(msg)
            elif channel is self.Channel.POOL:
                await self._channel_pool.send(msg)
            else:
                logging.error('Unknown channel seen in msg queue: {channel}')
            self.msg_queue = self.msg_queue[1:]

    @send_queued_messages.before_loop
    async def before_send_queued_messages_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()


    async def on_message(self, message):
        """Respond to messages."""
        # Do not reply to itself.
        if message.author.id == self.user.id:
            return

        if message.content.startswith('!botstatus'):
            await message.channel.send('I am alive and running!')
            return


if __name__ == '__main__':
    logging.basicConfig(format='Discord Bot : %(levelname)s : %(asctime)s : %(message)s',
                        level=logging.INFO, handlers=[logging.FileHandler("discord_bot.log"),
                        logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["DISCORD_BOT_TOKEN_PROD"]
        prod = True
    except KeyError:
        token = os.environ["DISCORD_BOT_TOKEN"]
        prod = False

    discord_client = DiscordClient(prod=prod)
    try:
        discord_client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    discord_client.stop()

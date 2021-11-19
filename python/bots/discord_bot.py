import logging
import os

import discord
from discord.ext import tasks, commands

from bots import util


TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = 908035718859874374


class DiscordClient(discord.Client):
    def __init__(self):
        super().__init__()

        self.msg_queue = []
        self.peg_cross_monitor = util.PegCrossMonitor(self.send_msg)
        self.peg_cross_monitor.start()

        # Start the message queue sending task in the background.
        self.send_queued_messages.start()

    def send_msg(self, text):
        """Send a message through the Discord bot."""
        self.msg_queue.append(text)


    async def on_ready(self):
        logging.info('Logged on as', str(self.user))
        self.channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
        logging.info("Discord channel is " + str(self.channel))

    @tasks.loop(seconds=0.1, reconnect=True)
    async def send_queued_messages(self):
        """Send messages in queue."""
        for msg in self.msg_queue:
            await self.channel.send(msg)
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
    logging.basicConfig(level=logging.INFO)

    discord_client = DiscordClient()
    discord_client.run(TOKEN)
    discord_client.peg_cross_monitor.stop()

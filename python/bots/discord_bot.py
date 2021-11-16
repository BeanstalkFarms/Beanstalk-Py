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

        self.peg_cross_monitor = util.PegCrossMonitor()

        # Start the task in the background.
        self.check_for_peg_cross.start()
    
    async def on_ready(self):
        # logging.info('Logged on as', str(self.user))
        self.channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
        logging.info("Discord channel is " + str(self.channel))
        await self.channel.send("Starting peg cross monitoring...")

    @tasks.loop(seconds=1/util.PEG_UPDATE_FREQUENCY)
    async def check_for_peg_cross(self):
        """Repeatedly check if the peg has been crossed."""
        cross_type = await self.peg_cross_monitor.check_for_peg_cross()
        if cross_type != util.PegCrossType.NO_CROSS:
            await self.channel.send(util.peg_cross_string(cross_type))
            logging.info(util.peg_cross_string(cross_type))

    @check_for_peg_cross.before_loop
    async def before_peg_cross_loop(self):
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

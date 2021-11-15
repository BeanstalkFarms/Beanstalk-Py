import logging
import os
import util

import discord
from discord.ext import tasks

from beanstalk_python.bots import util


TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = 908035718859874374


class DiscordClient(discord.Client):
    async def on_ready(self):
        # logging.info('Logged on as', str(self.user))
        self.channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
        logging.info("Discord channel is " + str(self.channel))
        self.peg_cross_monitor = util.PegCrossMonitor()
        await self.channel.send("Starting peg cross monitoring...")
        self.check_for_peg_cross.start()

    @tasks.loop(seconds=1/util.PEG_UPDATE_FREQUENCY)
    async def check_for_peg_cross(self):
        cross_type = await self.peg_cross_monitor.check_for_peg_cross()
        if cross_type != util.PegCrossType.NO_CROSS:
            await self.channel.send(util.peg_cross_string(cross_type))
            logging.info(util.peg_cross_string(cross_type))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    discord_client = DiscordClient()
    discord_client.run(TOKEN)

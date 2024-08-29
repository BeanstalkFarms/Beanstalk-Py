import discord
from discord.ext import tasks, commands

from bots.util import *
from monitors.monitor import Monitor
from data_access.eth_chain import *
from data_access.graphs import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

class PreviewMonitor(Monitor):
    """Base class for Discord Sidebar monitors. Do not use directly.

    Discord bot applications permissions needed: Change Nickname
    """

    def __init__(
        self,
        name,
        name_function,
        status_function,
        display_count=0,
        check_period=PREVIEW_CHECK_PERIOD,
    ):
        super().__init__(name, lambda s: None, check_period, prod=True)
        self.name = name
        # can be changed on the fly by subclass.
        self.display_count = display_count
        self.name_function = name_function
        self.status_function = status_function
        self.check_period = check_period
        self.display_index = 0
        # Delay startup to protect against crash loops.
        self.min_update_time = time.time() + 1

    def wait_for_next_cycle(self):
        """Attempt to check as quickly as the graph allows, but no faster than set period."""
        while True:
            if not time.time() > self.min_update_time:
                time.sleep(1)
                continue
            self.min_update_time = time.time() + self.check_period
            break

    def iterate_display_index(self):
        """Iterate the display index by one, looping at max display count."""
        if self.display_count != 0:
            self.display_index = (self.display_index + 1) % self.display_count

class DiscordSidebarClient(discord.ext.commands.Bot):
    def __init__(self, monitor, prod=False):
        super().__init__(command_prefix=commands.when_mentioned_or("!"))

        self.nickname = ""
        self.last_nickname = ""
        self.status_text = ""

        # Try to avoid hitting Discord API rate limit when all bots starting together.
        time.sleep(1.1)

        # subclass of util.Monitor
        self.monitor = monitor(self.set_nickname, self.set_status)
        self.monitor.start()

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        # Ignore base class, because we always want to reconnect.
        # https://discordpy.readthedocs.io/en/latest/api.html#discord.ClientUser.edit
        # https://discordpy.readthedocs.io/en/latest/api.html#exceptions
        self._update_naming.add_exception_type(discord.DiscordException)

        # Start the price display task in the background.
        self._update_naming.start()

    def stop(self):
        self.monitor.stop()

    def set_nickname(self, text):
        """Set bot server nickname."""
        self.nickname = text

    def set_status(self, text):
        """Set bot custom status text."""
        self.status_text = text

    async def on_ready(self):
        # Log the commit of this run.
        logging.info(
            "Git commit is "
            + subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(os.path.realpath(__file__)),
            )
            .decode("ascii")
            .strip()
        )

        self.user_id = self.user.id
        # self.beanstalk_guild = self.get_guild(BEANSTALK_GUILD_ID)
        # Guild IDs for all servers this bot is in.
        self.current_guilds = []
        for guild in self.guilds:
            self.current_guilds.append(guild)
            logging.info(f"Guild found: {guild.id}")

    @tasks.loop(seconds=1, reconnect=True)
    async def _update_naming(self):
        if self.nickname:
            await update_discord_bot_name(self.nickname, self)
        self.nickname = ""
        if self.status_text:
            await self.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name=self.status_text)
            )
            logging.info(f"Bot status changed to {self.status_text}")
            self.status_text = ""

    @_update_naming.before_loop
    async def before__update_naming_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()


async def update_discord_bot_name(name, bot):
    emoji_accent = holiday_emoji()
    next_name = emoji_accent + name + emoji_accent
    # Discord character limit
    if len(next_name) > DISCORD_NICKNAME_LIMIT:
        pruned_name = next_name[: DISCORD_NICKNAME_LIMIT - 3] + "..."
        logging.info(f"Pruning nickname from {next_name} to {pruned_name}")
        next_name = pruned_name
    # Note(funderberker): Is this rate limited?s
    for guild in bot.current_guilds:
        logging.info(f"Attempting to set nickname in guild with id {guild.id}")
        await guild.me.edit(nick=next_name)
        logging.info(f"Bot nickname changed to {next_name} in guild with id {guild.id}")
    return next_name
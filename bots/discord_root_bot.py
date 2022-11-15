import abc
from enum import Enum
import logging
import logging.handlers
import os
import signal
import subprocess

import discord
from discord.ext import tasks, commands

from bots import util


DISCORD_CHANNEL_ID_TEST_BOT = 1039026320237142066
DISCORD_CHANNEL_ID_TOKEN = 1039026004594790430
DISCORD_CHANNEL_ID_BETTING = 1039026151168933928


class Channel(Enum):
    REPORT = 0
    TOKEN = 1
    BETTING = 1


class DiscordClient(discord.ext.commands.Bot):

    def __init__(self, prod=False):
        super().__init__(command_prefix=commands.when_mentioned_or("!"))
        self.nickname = ''
        # self._update_naming.start()

        # NOTE(funderberker): LOCAL TESTING
        # Retrieve bucket.
        # bucket = self.retrieve_or_init_bucket()

        if prod:
            self._chat_id_report = DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_token = DISCORD_CHANNEL_ID_TOKEN
            self._chat_id_betting = DISCORD_CHANNEL_ID_BETTING
            logging.info('Configured as a production instance.')
        else:
            self._chat_id_report = DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_token = DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_betting = DISCORD_CHANNEL_ID_TEST_BOT
            logging.info('Configured as a staging instance.')

        self.msg_queue = []

        # Update root logger to send logging Errors in a Discord channel.
        discord_report_handler = util.MsgHandler(self.send_msg_report)
        discord_report_handler.setLevel(logging.ERROR)
        discord_report_handler.setFormatter(util.LOGGING_FORMATTER)
        logging.getLogger().addHandler(discord_report_handler)

        self.token_monitor = util.RootMonitor(
            self.send_msg_token, prod=prod, dry_run=False)
        self.token_monitor.start()

        # self.betting_monitor = util.BettingMonitor(
        #     self.send_msg_betting, prod=prod, dry_run=False)
        # self.betting_monitor.start()

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        # Ignore base class, because we always want to reconnect.
        # https://discordpy.readthedocs.io/en/latest/api.html#discord.ClientUser.edit
        # https://discordpy.readthedocs.io/en/latest/api.html#exceptions
        # self._update_naming.add_exception_type(discord.DiscordException)

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        self.send_queued_messages.add_exception_type(
            discord.errors.DiscordServerError)
        # Start the message queue sending task in the background.
        self.send_queued_messages.start()

    def stop(self):
        self.token_monitor.stop()
        # self.betting_monitor.stop()

    def send_msg_report(self, text):
        """Send a message through the Discord bot in the report/test channel."""
        self.msg_queue.append((Channel.REPORT, text))

    def send_msg_token(self, text):
        """Send a message through the Discord bot in the token channel."""
        self.msg_queue.append((Channel.TOKEN, text))

    def send_msg_betting(self, text):
        """Send a message through the Discord bot in the betting channel."""
        self.msg_queue.append((Channel.BETTING, text))

    async def on_ready(self):
        self._channel_report = self.get_channel(self._chat_id_report)
        self._channel_token = self.get_channel(self._chat_id_token)
        self._channel_betting = self.get_channel(self._chat_id_betting)

        logging.info(
            f'Discord channels are {self._channel_report}, {self._channel_token}, '
            f'{self._channel_betting}')

        # Guild IDs for all servers this bot is in.
        self.current_guilds = []
        for guild in self.guilds:
            self.current_guilds.append(guild)
            logging.info(f'Guild found: {guild.id}')

        # Log the commit of this run.
        logging.info('Git commit is ' + subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=os.path.dirname(os.path.realpath(__file__))
        ).decode('ascii').strip())

    # @tasks.loop(seconds=10, reconnect=True)
    # async def _update_naming(self):
    #     emoji_accent = util.holiday_emoji()
    #     next_name = emoji_accent + 'RootBot' + emoji_accent
    #     if self.nickname != next_name:
    #         for guild in self.current_guilds:
    #             logging.info(
    #                 f'Attempting to set nickname in guild with id {guild.id}')
    #             await guild.me.edit(nick=next_name)
    #             logging.info(
    #                 f'Bot nickname changed to {next_name} in guild with id {guild.id}')
    #         self.nickname = next_name

    # @_update_naming.before_loop
    # async def before__update_naming_loop(self):
    #     """Wait until the bot logs in."""
    #     await self.wait_until_ready()

    @tasks.loop(seconds=0.4, reconnect=True)
    async def send_queued_messages(self):
        """Send messages in queue.

        Reconnect logic applies to Loop._valid_exception (OSError, discord.GatewayNotFound,
        discord.ConnectionClosed, aiohttp.ClientError, asyncio.TimeoutError).

        We handle unexpected exceptions in this method so that:
        1. We can log them usefully.
        2. This thread does not crash forever.
        The Discord.py lib allows us to ignore an exception and restart, or die on the exception. 
        We want to log it _and_ not die.
        """
        try:
            for channel, msg in self.msg_queue:
                if len(msg) > 2000:
                    msg = msg[-2000:]
                    logging.warning(f'Clipping message length down to 2000.')
                logging.info(
                    f'Sending message through {channel} channel:\n{msg}\n')
                # Ignore empty messages.
                if not msg:
                    pass
                elif channel is Channel.REPORT:
                    await self._channel_report.send(msg)
                elif channel is Channel.TOKEN:
                    await self._channel_token.send(msg)
                elif channel is Channel.BETTING:
                    await self._channel_betting.send(msg)
                else:
                    logging.error(
                        'Unknown channel seen in msg queue: {channel}')
                self.msg_queue = self.msg_queue[1:]
        except Exception as e:
            logging.warning(e, exc_info=True)
            logging.warning(
                'Failed to send message to Discord server. Will retry.')

    @send_queued_messages.before_loop
    async def before_send_queued_messages_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()

    async def on_message(self, message):
        """Respond to messages."""
        # Do not reply to itself.
        if message.author.id == self.user.id:
            return

        # Process commands.
        await self.process_commands(message)

    @abc.abstractmethod
    def isDM(self, channel):
        """Return True is this context is from a dm, else False."""
        return isinstance(channel, discord.channel.DMChannel)


def channel_id(ctx):
    """Returns a string representation of the channel id from a context object."""
    return str(ctx.channel.id)


if __name__ == '__main__':
    logging.basicConfig(format=f'Discord Root Bot : {util.LOGGING_FORMAT_STR_SUFFIX}',
                        level=logging.INFO, handlers=[
                            logging.handlers.RotatingFileHandler(
                                "discord_root_bot.log", maxBytes=util.ONE_HUNDRED_MEGABYTES,
                                backupCount=1),
                            logging.StreamHandler()])
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    # Automatically detect if this is a production environment.
    try:
        token = os.environ["DISCORD_ROOT_BOT_TOKEN_PROD"]
        prod = True
    except KeyError:
        token = os.environ["DISCORD_ROOT_BOT_TOKEN"]
        prod = False

    discord_client = DiscordClient(prod=prod)

    try:
        discord_client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    discord_client.stop()

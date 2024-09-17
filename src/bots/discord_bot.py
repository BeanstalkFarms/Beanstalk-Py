import abc
from enum import Enum
import json
import logging
import logging.handlers
import os
import signal
import subprocess
import telebot

import discord
from discord.ext import tasks, commands

from bots import util
from constants.addresses import *
from constants.channels import *
from constants.config import *
from data_access.contracts.eth_events import EventClientType
from data_access.contracts.util import is_valid_wallet_address

from monitors.barn import BarnRaiseMonitor
from monitors.beanstalk import BeanstalkMonitor
from monitors.market import MarketMonitor
from monitors.peg_cross import PegCrossMonitor
from monitors.seasons import SeasonsMonitor
from monitors.well import WellsMonitor

class Channel(Enum):
    PEG = 0
    SEASONS = 1
    POOL = 2
    BEANSTALK = 3
    MARKET = 4
    REPORT = 5
    BARN_RAISE = 6
    TELEGRAM_FWD = 7

class DiscordClient(discord.ext.commands.Bot):
    def __init__(self, prod=False, telegram_token=None, dry_run=None):
        super().__init__(command_prefix=commands.when_mentioned_or("!"))
        # self.add_cog(WalletMonitoring(self))
        configure_bot_commands(self)
        self.nickname = ""
        self._update_naming.start()

        if prod:
            self._chat_id_report = BS_DISCORD_CHANNEL_ID_REPORT
            self._chat_id_peg = BS_DISCORD_CHANNEL_ID_PEG_CROSSES
            self._chat_id_seasons = BS_DISCORD_CHANNEL_ID_SEASONS
            self._chat_id_pool = BS_DISCORD_CHANNEL_ID_POOL
            self._chat_id_beanstalk = BS_DISCORD_CHANNEL_ID_BEANSTALK
            self._chat_id_market = BS_DISCORD_CHANNEL_ID_MARKET
            self._chat_id_barn_raise = BS_DISCORD_CHANNEL_ID_BARN_RAISE
            self._chat_id_telegram_fwd = BS_TELEGRAM_FWD_CHAT_ID_PRODUCTION
            logging.info("Configured as a production instance.")
        else:
            self._chat_id_report = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_peg = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_seasons = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_pool = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_beanstalk = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_market = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_barn_raise = BS_DISCORD_CHANNEL_ID_TEST_BOT
            self._chat_id_telegram_fwd = BS_TELEGRAM_FWD_CHAT_ID_TEST
            logging.info("Configured as a staging instance.")

        # Load wallet map from source. Map may be modified by this thread only (via discord.py lib).
        # Sets self.channel_to_wallets.
        # NOTE(funderberker): LOCAL TESTING
        self.channel_to_wallets = {}
        # if not self.download_channel_to_wallets():
        #     logging.critical('Failed to download wallet data. Exiting...')
        #     exit(1)
        self.channel_id_to_channel = {}

        self.msg_queue = []

        self.channels_to_fwd = [BS_DISCORD_CHANNEL_ID_ANNOUNCEMENTS, BS_DISCORD_CHANNEL_ID_WEEKLY_UPDATES]
        self.tele_bot = None
        if telegram_token is not None:
            self.tele_bot = telebot.TeleBot(telegram_token, parse_mode="Markdown")

        # Update root logger to send logging Errors in a Discord channel.
        discord_report_handler = util.MsgHandler(self.send_msg_report)
        discord_report_handler.setLevel(logging.ERROR)
        discord_report_handler.setFormatter(LOGGING_FORMATTER)
        logging.getLogger().addHandler(discord_report_handler)

        self.peg_cross_monitor = PegCrossMonitor(self.send_msg_peg, prod=prod)
        self.peg_cross_monitor.start()

        self.sunrise_monitor = SeasonsMonitor(
            self.send_msg_seasons,
            channel_to_wallets=self.channel_to_wallets,
            prod=prod,
            dry_run=dry_run,
        )
        self.sunrise_monitor.start()

        self.well_monitor_whitelisted = WellsMonitor(
            self.send_msg_pool, WHITELISTED_WELLS, bean_reporting=True, prod=prod, dry_run=dry_run
        )
        self.well_monitor_whitelisted.start()

        self.beanstalk_monitor = BeanstalkMonitor(
            self.send_msg_beanstalk, prod=prod, dry_run=dry_run
        )
        self.beanstalk_monitor.start()

        self.market_monitor = MarketMonitor(self.send_msg_market, prod=prod, dry_run=dry_run)
        self.market_monitor.start()

        self.barn_raise_monitor = BarnRaiseMonitor(
            self.send_msg_barn_raise,
            report_events=True,
            report_summaries=False,
            prod=prod,
            dry_run=dry_run,
        )
        self.barn_raise_monitor.start()

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        # Ignore base class, because we always want to reconnect.
        # https://discordpy.readthedocs.io/en/latest/api.html#discord.ClientUser.edit
        # https://discordpy.readthedocs.io/en/latest/api.html#exceptions
        self._update_naming.add_exception_type(discord.DiscordException)

        # Ignore exceptions of this type and retry. Note that no logs will be generated.
        self.send_queued_messages.add_exception_type(discord.errors.DiscordServerError)
        # Start the message queue sending task in the background.
        self.send_queued_messages.start()

    def stop(self):
        # self.upload_channel_to_wallets()
        self.peg_cross_monitor.stop()
        self.sunrise_monitor.stop()
        self.well_monitor_whitelisted.stop()
        self.beanstalk_monitor.stop()
        self.market_monitor.stop()
        self.barn_raise_monitor.stop()

    def send_msg_report(self, text):
        """Send a message through the Discord bot in the error reporting channel."""
        self.msg_queue.append((Channel.REPORT, text))

    def send_msg_peg(self, text):
        """Send a message through the Discord bot in the peg channel."""
        self.msg_queue.append((Channel.PEG, text))

    def send_msg_seasons(self, text, channel_id=Channel.SEASONS):
        """Send a message through the Discord bot in the seasons channel."""
        self.msg_queue.append((channel_id, text))

    def send_msg_pool(self, text):
        """Send a message through the Discord bot in the pool channel."""
        self.msg_queue.append((Channel.POOL, text))

    def send_msg_beanstalk(self, text):
        """Send a message through the Discord bot in the beanstalk channel."""
        self.msg_queue.append((Channel.BEANSTALK, text))

    def send_msg_market(self, text):
        """Send a message through the Discord bot in the market channel."""
        self.msg_queue.append((Channel.MARKET, text))

    def send_msg_barn_raise(self, text):
        """Send a message through the Discord bot in the Barn Raise channel."""
        self.msg_queue.append((Channel.BARN_RAISE, text))

    def send_msg_telegram_fwd(self, text):
        """Forward a message through the Telegram bot in the Beanstalk chat."""
        self.msg_queue.append((Channel.TELEGRAM_FWD, text))

    async def on_ready(self):
        self._channel_report = self.get_channel(self._chat_id_report)
        self._channel_peg = self.get_channel(self._chat_id_peg)
        self._channel_seasons = self.get_channel(self._chat_id_seasons)
        self._channel_pool = self.get_channel(self._chat_id_pool)
        self._channel_beanstalk = self.get_channel(self._chat_id_beanstalk)
        self._channel_market = self.get_channel(self._chat_id_market)
        self._channel_barn_raise = self.get_channel(self._chat_id_barn_raise)

        # Init DM channels.
        for channel_id in self.channel_to_wallets.keys():
            self.channel_id_to_channel[channel_id] = await self.fetch_channel(channel_id)

        logging.info(
            f"Discord channels are {self._channel_report}, {self._channel_peg}, {self._channel_seasons}, "
            f"{self._channel_pool}, {self._channel_beanstalk}, {self._channel_market}, {self._channel_barn_raise}"
        )

        # Guild IDs for all servers this bot is in.
        self.current_guilds = []
        for guild in self.guilds:
            self.current_guilds.append(guild)
            logging.info(f"Guild found: {guild.id}")

    @tasks.loop(seconds=10, reconnect=True)
    async def _update_naming(self):
        if not self.nickname:
            self.nickname = await util.update_discord_bot_name("BeanBot", self)
            # NOTE(funderberker): will not update with holiday emojis.

    @_update_naming.before_loop
    async def before__update_naming_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()

    async def send_dm(self, channel_id, text):
        logging.warning(channel_id)
        try:
            # channel = await self.fetch_channel(channel_id)
            # channel = self.get_channel(int(channel_id))
            channel = self.channel_id_to_channel[channel_id]
            await channel.send(text)
        except AttributeError as e:
            logging.error("Failed to send DM")
            logging.exception(e)

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
                    logging.warning(f"Clipping message length down to 2000.")
                logging.info(f"Sending message through {channel} channel:\n{msg}\n")
                # Ignore empty messages.
                if not msg:
                    pass
                elif channel is Channel.REPORT:
                    await self._channel_report.send(msg)
                elif channel is Channel.PEG:
                    await self._channel_peg.send(msg)
                elif channel is Channel.SEASONS:
                    await self._channel_seasons.send(msg)
                elif channel is Channel.POOL:
                    await self._channel_pool.send(msg)
                elif channel is Channel.BEANSTALK:
                    await self._channel_beanstalk.send(msg)
                elif channel is Channel.MARKET:
                    await self._channel_market.send(msg)
                elif channel is Channel.BARN_RAISE:
                    await self._channel_barn_raise.send(msg)
                elif channel is Channel.TELEGRAM_FWD:
                    if self.tele_bot is not None:
                        self.tele_bot.send_message(chat_id=self._chat_id_telegram_fwd, text=msg)
                    else:
                        logging.warning("Discord tele_bot not configured to forward. Ignoring...")
                # If channel is a channel_id string.
                elif type(channel) == str:
                    await self.send_dm(channel, msg)
                else:
                    logging.error("Unknown channel seen in msg queue: {channel}")
                self.msg_queue = self.msg_queue[1:]
        except telebot.apihelper.ApiTelegramException as e:
            logging.warning(e, exc_info=True)
            logging.warning("Failed to send message to Telegram bot. Will ~not~ retry.")
            self.msg_queue = self.msg_queue[1:]
        except Exception as e:
            logging.warning(e, exc_info=True)
            logging.warning("Failed to send message to Discord server. Will retry.")

    @send_queued_messages.before_loop
    async def before_send_queued_messages_loop(self):
        """Wait until the bot logs in."""
        await self.wait_until_ready()

    async def on_message(self, message):
        """Respond to messages."""
        # Do not reply to itself.
        if message.author.id == self.user.id:
            return

        # If the message was in a channel we want to forward to Telegram.
        if message.channel.id in self.channels_to_fwd:
            forwarded_message = (
                f"Forwarded Discord message\n"
                f"From *{message.author}* in {message.channel.name}\n\n"
                f"{util.strip_custom_discord_emojis(message.content)}"
            )
            self.send_msg_telegram_fwd(forwarded_message)

        # Process commands.
        await self.process_commands(message)

    def add_to_watched_addresses(self, address, channel_id):
        try:
            wallets = self.channel_to_wallets[channel_id]
        except KeyError:
            # If nothing is being watched for this channel_id, initialize list.
            wallets = []
            self.channel_to_wallets[channel_id] = wallets

        # If this address is already being watched in this channel, do nothing.
        if address in wallets:
            return

        # Append the address to the existing watch list.
        wallets.append(address)
        logging.info(f"Discord channel {channel_id} is now watching {address}")

        # Update cloud source of truth with new data.
        self.upload_channel_to_wallets()

    def remove_from_watched_addresses(self, address, channel_id):
        try:
            wallets = self.channel_to_wallets[channel_id]
        except KeyError:
            # If nothing is being watched for this channel_id, then nothing to remove.
            return

        # If this address not already being watched in this channel, do nothing.
        if address not in wallets:
            return

        # Remove the address from the existing watch list.
        wallets.remove(address)
        logging.info(f"Discord channel {channel_id} is no longer watching {address}")

        # Update cloud source of truth with new data.
        self.upload_channel_to_wallets()

    def upload_channel_to_wallets(self):
        """Update cloud source of truth with new data. Returns True/False based on success."""
        try:
            self.wallets_blob.upload_from_string(
                json.dumps(self.channel_to_wallets), num_retries=3, timeout=20
            )
        except Exception as e:
            logging.error(
                "Failed to upload wallet watching changes to cloud. Will attempt again "
                "on next change."
            )
            logging.exception(e)
            return False
        logging.info("Successfully uploaded channel_to_wallets map.")
        return True

    @abc.abstractmethod
    def isDM(self, channel):
        """Return True is this context is from a dm, else False."""
        return isinstance(channel, discord.channel.DMChannel)


def configure_bot_commands(bot):
    """Define all bot chat commands that users can utilize.

    Due to quirks of the discord.py lib, these commands must be defined outside of the bot class
    definition.
    """

    @bot.command(pass_context=True)
    async def botstatus(ctx):
        """Check if bot is currently running."""
        await ctx.send("I am alive and running!")


class WalletMonitoring(commands.Cog):
    """Wallet watching commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    @commands.dm_only()
    async def list(self, ctx):
        """List all addresses you are currently watching."""
        logging.warning(f"list request from channel id == {channel_id(ctx)}")
        watched_addrs = self.bot.channel_to_wallets.get(channel_id(ctx)) or []
        addr_list_str = ", ".join([f"`{addr}`" for addr in watched_addrs])
        if addr_list_str:
            await ctx.send(f"Wallets you are watching:\n{addr_list_str}")
        else:
            await ctx.send(f"You are not currently watching any wallets.")

    # This is challenging because the synchronous subgraph access cannot be called by the
    # discord coroutines. Would we even want to allow random users to use our subgraph key to
    # make requests on demand?
    # @commands.command(pass_context=True)
    # @commands.dm_only()
    # async def status(self, ctx):
    #     """Get Beanstalk status of watched addresses."""
    #     # Check if no addresses are being watched.
    #     dm_id = channel_id(ctx)
    #     watched_addrs = self.bot.channel_to_wallets.get(dm_id)
    #     if not watched_addrs:
    #         await ctx.send(f'You are not currently watching any addresses.')
    #         return
    #     await ctx.send(self.bot.sunrise_monitor.wallets_str(self.bot.channel_to_wallets[dm_id]))

    @commands.command(pass_context=True)
    @commands.dm_only()
    async def add(self, ctx, *, address=None):
        """Get seasonal updates about the Beanstalk status of an address."""
        if address is None:
            await ctx.send(f"You must provide a wallet address to add. No change to watch list.")
            return

        # Address must be a valid ETH address.
        if not is_valid_wallet_address(address):
            await ctx.send(f"Invalid address provided (`{address}`). No change to watch list.")
            return

        # Limit user to 5 watched wallets. This prevents abuse/spam.
        watched_addrs = self.bot.channel_to_wallets.get(channel_id(ctx)) or []
        if len(watched_addrs) >= WALLET_WATCH_LIMIT:
            await ctx.send(
                f"Each user may only monitor up to {WALLET_WATCH_LIMIT} wallets. "
                "No change to watch list."
            )
            return

        # Check if address is already being watched.
        if address in watched_addrs:
            await ctx.send(f"You are already watching `{address}`. No change to watch list.")
            return

        # Append the address to the list of watched addresses.
        self.bot.add_to_watched_addresses(address, channel_id(ctx))

        # If DM channel is new, cache the channel.
        if channel_id(ctx) not in self.bot.channel_id_to_channel:
            self.bot.channel_id_to_channel[channel_id(ctx)] = ctx.channel

        await ctx.send(f"You are now watching `{address}` in this DM conversation.")

    @commands.command(pass_context=True)
    @commands.dm_only()
    async def remove(self, ctx, *, address=None):
        """Stop getting updates about the Beanstalk status of an address."""
        if address is None:
            await ctx.send(f"You must provide a wallet address to remove. No change to watch list.")
            return

        # Address must be a valid ETH address.
        if not is_valid_wallet_address(address):
            await ctx.send(f"Invalid address provided (`{address}`). No change to watch list.")
            return

        # Check if address is already being watched.
        watched_addrs = self.bot.channel_to_wallets.get(channel_id(ctx)) or []
        if address not in watched_addrs:
            await ctx.send(f"You are not already watching `{address}`. No change to watch list.")
            return

        self.bot.remove_from_watched_addresses(address, channel_id(ctx))
        await ctx.send(f"You are no longer watching `{address}` in this DM conversation.")


def channel_id(ctx):
    """Returns a string representation of the channel id from a context object."""
    return str(ctx.channel.id)


if __name__ == "__main__":
    logging.basicConfig(
        format=f"Discord Bot : {LOGGING_FORMAT_STR_SUFFIX}",
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                "logs/discord_bot.log", maxBytes=ONE_HUNDRED_MEGABYTES, backupCount=1
            ),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, util.handle_sigterm)

    util.configure_main_thread_exception_logging()

    token = os.environ["DISCORD_BS_BOT_TOKEN"]
    telegram_token = os.environ.get("TELEGRAM_BS_BOT_TOKEN") # Can be None
    prod = os.environ["IS_PROD"].lower() == "true"
    dry_run = os.environ.get("DRY_RUN")
    if dry_run:
        dry_run = dry_run.split(',')

    discord_client = DiscordClient(prod=prod, telegram_token=telegram_token, dry_run=dry_run)

    try:
        discord_client.run(token)
    except (KeyboardInterrupt, SystemExit):
        pass
    # Note that discord bot cannot send shutting down messages in its channel, due to lib impl.
    discord_client.stop()

import re
import logging
import sys
import threading
import time
import re
import subprocess

import discord
from discord.ext import tasks, commands

from data_access.contracts.util import *

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
        # logging.info(f"Attempting to set nickname in guild with id {guild.id}")
        await guild.me.edit(nick=next_name)
        logging.info(f"Bot nickname changed to {next_name} in guild with id {guild.id}")
    return next_name

class MsgHandler(logging.Handler):
    """A handler class which sends a message on a text channel."""

    def __init__(self, message_function):
        """
        Initialize the handler.
        """
        logging.Handler.__init__(self)
        self.message_function = message_function

    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        """
        try:
            msg = self.format(record)
            self.message_function(msg)
        except Exception:
            self.handleError(record)


def event_in_logs(name, event_logs):
    """Return True if an event with given name is in the set of logs. Else return False."""
    for event_log in event_logs:
        if event_log.event == name:
            return True
    return False


def remove_events_from_logs_by_name(name, event_logs):
    for event_log in event_logs:
        if event_log.event == name:
            event_logs.remove(event_log)


def event_sig_in_txn(event_sig, txn_hash, web3=None):
    """Return True if an event signature appears in any logs from a txn. Else return False."""
    if not web3:
        web3 = get_web3_instance()
    receipt = tools.util.get_txn_receipt_or_wait(web3, txn_hash)
    for log in receipt.logs:
        try:
            if log.topics[0].hex() == event_sig:
                return True
        # Ignore anonymous events (logs without topics).
        except IndexError:
            pass
    return False


def get_logs_by_names(names, event_logs):
    if type(names) == str:
        names = [names]
    events = []
    for event_log in event_logs:
        if event_log.event in names:
            events.append(event_log)
    return events


def sig_compare(signature, signatures):
    """Compare a signature to one or many signatures and return if there are any matches.

    Comparison is made based on 10 character prefix.
    """
    if type(signatures) is str:
        signatures = [signatures]

    for sig in signatures:
        if signature[:9] == sig[:9]:
            return True
    return False


def round_num(number, precision=2, avoid_zero=False, incl_dollar=False):
    """Round a string or float to requested precision and return as a string."""
    if avoid_zero and number == 0:
        return f"{'$' if incl_dollar else ''}0{'.' + '0' * precision if precision > 0 else ''}"
    ret_string = "$" if incl_dollar else ""
    ret_string += f"{float(number):,.{precision}f}"
    if avoid_zero and not re.search(r'[1-9]', ret_string):
        return f"<{' ' if incl_dollar else ''}{ret_string[:-1]}1"
    return ret_string


def round_num_auto(number, sig_fig_min=3, min_precision=2, abbreviate=False):
    """Round a string or float and return as a string.

    Caller specifies the minimum significant figures and precision that that very large and very
    small numbers can both be handled.

    If abbreviate is True, trailing zeros replaced by magnitude acronym letter
    """
    if number > 1:
        number = float(number)
        if abbreviate:
            if number > 1e9:
                return round_num(number / 1e9, min_precision) + "B"
            elif number > 1e6:
                return round_num(number / 1e6, min_precision) + "M"
            elif number > 1e3:
                return round_num(number / 1e3, min_precision) + "K"
        return round_num(number, min_precision)
    return "%s" % float(f"%.{sig_fig_min}g" % float(number))


def round_token(number, decimals, addr=''):
    if addr.lower() in {token.lower() for token in {WRAPPED_ETH, WSTETH, WBTC}}:
        precision = 2
    else:
        precision = 0
    return round_num(token_to_float(number, decimals), precision, avoid_zero=True)


def value_to_emojis(value):
    """Convert a rounded dollar value to a string of emojis."""
    value = int(value)
    if value < 0:
        return ""
    value = round(value, -3)
    if value < 10000:
        return "🐟" * (value // 1000) or "🐟"
    value = round(value, -4)
    if value < 100000:
        return "🦈" * (value // 10000)
    value = round(value, -5)
    return "🐳" * (value // 100000)


def latest_pool_price_str(bean_client, addr):
    pool_info = bean_client.get_pool_info(addr)
    if addr == BEAN_ADDR:
        type_str = "Bean"
    elif addr == CURVE_BEAN_3CRV_ADDR:
        type_str = "Pool"
    else:
        type_str = "Well"
    price = token_to_float(pool_info["price"], BEAN_DECIMALS)
    delta_b = token_to_float(pool_info["delta_b"], BEAN_DECIMALS)
    # liquidity = pool_info['liquidity']
    return f"{type_str}: deltaB [{round_num(delta_b, 0)}], price [${round_num(price, 4)}]"


def latest_well_lp_str(basin_client, addr):
    liquidity = basin_client.get_well_liquidity(addr)
    return f"Well liquidity: ${round_num(liquidity, 0)}"


def value_to_emojis_root(value):
    """Convert a rounded dollar value to a string of emojis."""
    return value_to_emojis(value * 10)


def number_to_emoji(n):
    """Take an int as a string or int and return the corresponding # emoji. Above 10 returns '#'."""
    n = int(n)
    if n == 0:
        return "🏆"
    elif n == 1:
        return "🥇"
    elif n == 2:
        return "🥈"
    elif n == 3:
        return "🥉"
    else:
        return "🏅"


def percent_to_moon_emoji(percent):
    """Convert a float percent (e.g. .34) to a gradient moon emoji."""
    percent = float(percent)
    if percent < 0:
        return ""
    elif percent < 0.20:
        return "🌑"
    elif percent < 0.40:
        return "🌘"
    elif percent < 0.70:
        return "🌗"
    elif percent < 0.99999999:  # safety for rounding/float imperfections
        return "🌖"
    else:
        return "🌕"


PDT_OFFSET = 7 * 60 * 60
holiday_schedule = [
    # Mid Autumn Festival, UTC+9 9:00 - UTC-7 24:00
    (1662768000, 1662854400 + PDT_OFFSET, "🏮"),
    (1666681200, 1667296800, "🎃"),  # Halloween, Oct 24 - Nov 1
    (1669287600, 1669374000, "🦃"),  # US Thanksgiving, Nov 24 - Nov 25
]


def holiday_emoji():
    """Returns an emoji with appropriate festive spirit."""
    utc_now = time.time()
    for start_time, end_time, emoji in holiday_schedule:
        if start_time < utc_now and utc_now < end_time:
            return emoji
    return ""


def strip_custom_discord_emojis(text):
    """Remove custom discord emojis using regex."""
    # <:beanstalker:1004908839394615347>
    stripped_type_0 = re.sub(r"<:[Z-z]+:[0-9]+>", " ", text)
    # :PU_PeepoPumpkin:
    # Unclear if this second type will come in normal workflow.
    stripped_type_1 = re.sub(r":[0-z]+:", " ", text)
    return stripped_type_1


def handle_sigterm(signal_number, stack_frame):
    """Process a sigterm with a python exception for clean exiting."""
    logging.warning("Handling SIGTERM. Exiting.")
    raise SystemExit


# Configure uncaught exception handling for threads.


def log_thread_exceptions(args):
    """Log uncaught exceptions for threads."""
    logging.critical(
        "Uncaught exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )


threading.excepthook = log_thread_exceptions


def log_exceptions(exc_type, exc_value, exc_traceback):
    """Log uncaught exceptions for main thread."""
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


def configure_main_thread_exception_logging():
    sys.excepthook = log_exceptions

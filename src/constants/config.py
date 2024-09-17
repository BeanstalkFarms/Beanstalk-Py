import sys
import os
import logging
from constants.addresses import *
from web3 import Web3

# Misc configuration constants

# Strongly encourage Python 3.8+.
# If not 3.8+ uncaught exceptions on threads will not be logged.
MIN_PYTHON = (3, 8)
if sys.version_info < MIN_PYTHON:
    logging.critical(
        "Python %s.%s or later is required for proper exception logging.\n" % MIN_PYTHON
    )
LOGGING_FORMAT_STR_SUFFIX = "%(levelname)s : %(asctime)s : %(message)s"
LOGGING_FORMATTER = logging.Formatter(LOGGING_FORMAT_STR_SUFFIX)

DAO_SNAPSHOT_NAME = "beanstalkdao.eth"
FARMS_SNAPSHOT_NAME = "beanstalkfarms.eth"

BEANSTALK_GRAPH_ENDPOINT = "https://graph.bean.money/beanstalk"
BEAN_GRAPH_ENDPOINT = "https://graph.bean.money/bean"
BASIN_GRAPH_ENDPOINT = "https://graph.bean.money/basin"
SNAPSHOT_GRAPH_ENDPOINT = "https://hub.snapshot.org/graphql"

# The duration of a season. Assumes that seasons align with Unix epoch.
SEASON_DURATION = 3600  # seconds
# How long to wait between discord preview bot updates.
PREVIEW_CHECK_PERIOD = 5  # seconds
# Rate at which to check for events on the Beanstalk contract.
BEANSTALK_CHECK_RATE = 5  # seconds
# How long to wait between peg checks.
PEG_CHECK_PERIOD = 5  # seconds
# How long to wait between checks for a sunrise when we expect a new season to begin.
SUNRISE_CHECK_PERIOD = 5  # seconds
# Rate at which to check chain for new Well interactions.
POOL_CHECK_RATE = 5  # seconds
# How long to wait between checks for fert purchases.
BARN_RAISE_CHECK_RATE = 10  # seconds
# Bytes in 100 megabytes.
ONE_HUNDRED_MEGABYTES = 100 * 1000000
# Initial time to wait before reseting dead monitor.
RESET_MONITOR_DELAY_INIT = 15  # seconds
# Timestamp for deployment of Basin.
BASIN_DEPLOY_EPOCH = 1692814103

DISCORD_NICKNAME_LIMIT = 32

# For WalletMonitoring - I dont think this is actually used
WALLET_WATCH_LIMIT = 10

RPC_URL = "https://" + os.environ["RPC_URL"]

# Decimals for conversion from chain int values to float decimal values.
ETH_DECIMALS = 18
LP_DECIMALS = 18
BEAN_DECIMALS = 6
SOIL_DECIMALS = 6
STALK_DECIMALS = 16
SEED_DECIMALS = 6
POD_DECIMALS = 6
WBTC_DECIMALS = 8
USDC_DECIMALS = 6
USDT_DECIMALS = 6
WELL_LP_DECIMALS = 18

# Number of txn hashes to keep in memory to prevent duplicate processing.
TXN_MEMORY_SIZE_LIMIT = 100

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = "\n"

ERC20_TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# Incomplete of Beanstalk Terming of Tokens for human use.
TOKEN_SYMBOL_MAP = {
    BEAN_ADDR.lower(): "BEAN",
    BEAN_ETH_ADDR.lower(): "BEANETH",
    BEAN_WSTETH_ADDR.lower(): "BEANwstETH",
    BEAN_WEETH_ADDR.lower(): "BEANweETH",
    BEAN_WBTC_ADDR.lower(): "BEANWBTC",
    BEAN_USDC_ADDR.lower(): "BEANUSDC",
    BEAN_USDT_ADDR.lower(): "BEANUSDT",
    UNRIPE_ADDR.lower(): "urBEAN",
    UNRIPE_LP_ADDR.lower(): "urBEANwstETH"
}

GRAPH_FIELDS_PLACEHOLDER = "_FIELDS_"
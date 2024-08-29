import sys
import os
import logging
from constants.addresses import *
from web3 import Web3

# Misc configuration constants
# TODO: some of these may be better suited as part of the docker .env

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
PREVIEW_CHECK_PERIOD = 4  # seconds
# For all check periods there is a built in assumption that we will update at least once per block
# TODO: if the above comment is true, this is a problem on L2
APPROX_BLOCK_TIME = 12  # seconds
# How long to wait between peg checks.
PEG_CHECK_PERIOD = APPROX_BLOCK_TIME  # seconds
# How long to wait between checks for a sunrise when we expect a new season to begin.
SUNRISE_CHECK_PERIOD = APPROX_BLOCK_TIME  # seconds
# Rate at which to check chain for new Uniswap V2 pool interactions.
POOL_CHECK_RATE = APPROX_BLOCK_TIME  # seconds
# Rate at which to check for events on the Beanstalk contract.
BEANSTALK_CHECK_RATE = APPROX_BLOCK_TIME  # seconds
# How long to wait between checks for fert purchases.
BARN_RAISE_CHECK_RATE = APPROX_BLOCK_TIME  # seconds
# Bytes in 100 megabytes.
ONE_HUNDRED_MEGABYTES = 100 * 1000000
# Initial time to wait before reseting dead monitor.
RESET_MONITOR_DELAY_INIT = 15  # seconds
# Timestamp for deployment of Basin.
BASIN_DEPLOY_EPOCH = 1692814103

DISCORD_NICKNAME_LIMIT = 32

# For WalletMonitoring - I dont think this is actually used
WALLET_WATCH_LIMIT = 10

# Alchemy node key.
try:
    API_KEY = os.environ["ALCHEMY_ETH_API_KEY_PROD"]
except KeyError:
    API_KEY = os.environ["ALCHEMY_ETH_API_KEY"]

RPC_URL = "https://eth-mainnet.g.alchemy.com/v2/" + API_KEY

# Decimals for conversion from chain int values to float decimal values.
ETH_DECIMALS = 18
LP_DECIMALS = 18
BEAN_DECIMALS = 6
SOIL_DECIMALS = 6
STALK_DECIMALS = 10
SEED_DECIMALS = 6
POD_DECIMALS = 6
DAI_DECIMALS = 18
USDC_DECIMALS = 6
USDT_DECIMALS = 6
CRV_DECIMALS = 18
LUSD_DECIMALS = 18
CURVE_POOL_TOKENS_DECIMALS = 18
WELL_LP_DECIMALS = 18

# Indices of tokens in Curve factory pool [bean, 3crv].
FACTORY_3CRV_INDEX_BEAN = 0
FACTORY_3CRV_INDEX_3CRV = 1
# Indices of underlying tokens in Curve factory pool [bean, dai, usdc, usdt].
FACTORY_3CRV_UNDERLYING_INDEX_BEAN = 0
FACTORY_3CRV_UNDERLYING_INDEX_DAI = 1
FACTORY_3CRV_UNDERLYING_INDEX_USDC = 2
FACTORY_3CRV_UNDERLYING_INDEX_USDT = 3

# Number of txn hashes to keep in memory to prevent duplicate processing.
TXN_MEMORY_SIZE_LIMIT = 100

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = "\n"

ERC20_TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# Incomplete of Beanstalk Terming of Tokens for human use.
TOKEN_SYMBOL_MAP = {
    BEAN_ADDR.lower(): "BEAN",
    CURVE_BEAN_3CRV_ADDR.lower(): "BEAN3CRV",
    UNRIPE_ADDR.lower(): "urBEAN",
    UNRIPE_LP_ADDR.lower(): "urBEANwstETH",
    BEAN_ETH_WELL_ADDR.lower(): "BEANETH",
    BEAN_WSTETH_WELL_ADDR.lower(): "BEANwstETH",
}

from abc import abstractmethod
import asyncio
from collections import OrderedDict
import datetime
from enum import Enum, IntEnum
import logging
import json
import os
import time
from discord.ext.commands.errors import ArgumentParsingError

from web3 import Web3, WebsocketProvider
from web3.logs import DISCARD

from constants.addresses import *

# Alchemy node key.
try:
    API_KEY = os.environ['ALCHEMY_ETH_API_KEY_PROD']
except KeyError:
    API_KEY = os.environ['ALCHEMY_ETH_API_KEY']
# URL = 'wss://eth-mainnet.alchemyapi.io/v2/' + API_KEY
# Rinkeby testing.
URL = 'wss://eth-rinkeby.alchemyapi.io/v2/***REMOVED***'

# Decimals for conversion from chain int values to float decimal values.
ETH_DECIMALS = 18
LP_DECIMALS = 18
BEAN_DECIMALS = 6
POD_DECIMALS = 6
SOIL_DECIMALS = 6
DAI_DECIMALS = 18
USDC_DECIMALS = 6
USDT_DECIMALS = 6
CRV_DECIMALS = 18
LUSD_DECIMALS = 18
CURVE_POOL_TOKENS_DECIMALS = 18

# Hardcoded human-readable names for tokens.
HARDCODE_ADDRESS_TO_NAME = {
    BEAN_ADDR:'Bean',
    UNI_V2_BEAN_ETH_ADDR:'Uni V2 BEAN:ETH LP',
    UNI_V2_ETH_USDC_ADDR:'Uni V2 ETH:USDC LP',
    CURVE_BEAN_3CRV_ADDR:'Curve BEAN:3CRV LP',
    CURVE_BEAN_LUSD_ADDR:'Curve BEAN:LUSD LP',
}


UNI_V2_POOL_FEE = 0.003  # %

# Indices of tokens in Curve factory pool [bean, 3crv].
FACTORY_3CRV_INDEX_BEAN = 0
FACTORY_3CRV_INDEX_3CRV = 1
# Indices of underlying tokens in Curve factory pool [bean, dai, usdc, usdt].
FACTORY_3CRV_UNDERLYING_INDEX_BEAN = 0
FACTORY_3CRV_UNDERLYING_INDEX_DAI = 1
FACTORY_3CRV_UNDERLYING_INDEX_USDC = 2
FACTORY_3CRV_UNDERLYING_INDEX_USDT = 3
# Indices of tokens in Curve factory pool [bean, LUSD].
FACTORY_LUSD_INDEX_BEAN = 0
FACTORY_LUSD_INDEX_LUSD = 1

# Number of txn hashes to keep in memory to prevent duplicate processing.
TXN_MEMORY_SIZE_LIMIT = 100

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = '\n'

# Index of values in tuples returned from web3 contract calls.
STARTSOIL_INDEX = 0

# NOTE(funderberker): Pretty lame that we cannot automatically parse these from the ABI files.
#   Technically it seems very straight forward, but it is not implemented in the web3 lib and
#   parsing it manually is not any better than just writing it out here.


def add_event_to_dict(signature, sig_dict, sig_list):
    """Add both signature_hash and event_name to the bidirectional dict.

    Configure as a bijective map. Both directions will be added for each event type:
        - signature_hash:event_name
        - event_name:signature_hash
    """
    event_name = signature.split('(')[0]
    event_signature_hash = Web3.keccak(text=signature).hex()
    sig_dict[event_name] = event_signature_hash
    sig_dict[event_signature_hash] = event_name
    sig_list.append(event_signature_hash)


UNISWAP_POOL_EVENT_MAP = {}
UNISWAP_POOL_SIGNATURES_LIST = []
add_event_to_dict('Mint(address,uint256,uint256)',
                  UNISWAP_POOL_EVENT_MAP, UNISWAP_POOL_SIGNATURES_LIST)
add_event_to_dict('Burn(address,uint256,uint256,address)',
                  UNISWAP_POOL_EVENT_MAP, UNISWAP_POOL_SIGNATURES_LIST)
add_event_to_dict('Swap(address,uint256,uint256,uint256,uint256,address)',
                  UNISWAP_POOL_EVENT_MAP, UNISWAP_POOL_SIGNATURES_LIST)

# NOTE(funderberker): This may not be the appropriate or comprehensive set of events.
CURVE_POOL_EVENT_MAP = {}
CURVE_POOL_SIGNATURES_LIST = []
add_event_to_dict('TokenExchange(address,int128,uint256,int128,uint256)',
                  CURVE_POOL_EVENT_MAP, CURVE_POOL_SIGNATURES_LIST)
add_event_to_dict('TokenExchangeUnderlying(address,int128,uint256,int128,uint256)',
                  CURVE_POOL_EVENT_MAP, CURVE_POOL_SIGNATURES_LIST)
add_event_to_dict('AddLiquidity(address,uint256[2],uint256[2],uint256,uint256)',
                  CURVE_POOL_EVENT_MAP, CURVE_POOL_SIGNATURES_LIST)
add_event_to_dict('RemoveLiquidity(address,uint256[2],uint256[2],uint256)',
                  CURVE_POOL_EVENT_MAP, CURVE_POOL_SIGNATURES_LIST)
add_event_to_dict('RemoveLiquidityOne(address,uint256,uint256,uint256)',
                  CURVE_POOL_EVENT_MAP, CURVE_POOL_SIGNATURES_LIST)
add_event_to_dict('RemoveLiquidityImbalance(address,uint256[2],uint256[2],uint256,uint256)',
                  CURVE_POOL_EVENT_MAP, CURVE_POOL_SIGNATURES_LIST)

BEANSTALK_EVENT_MAP = {}
BEANSTALK_SIGNATURES_LIST = []
add_event_to_dict('Sow(address,uint256,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# add_event_to_dict('BeanClaim(address,uint32[],uint256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# add_event_to_dict('LPClaim(address,uint32[],uint256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('BeanDeposit(address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('LPDeposit(address,uint256,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('BeanRemove(address,uint32[],uint256[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('LPRemove(address,uint32[],uint256[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('BeanWithdraw(address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('LPWithdraw(address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('Harvest(address,uint256[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# Generalized silo interactions.
add_event_to_dict('Deposit(address,address,uint256,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# Removes indicate the removal of a deposit, but not a withdraw. Seen in converts.
add_event_to_dict('RemoveSeasons(address,address,uint32[],uint256[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('RemoveSeason(address,address,uint32,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# Withdrawls indicate the removal of a deposit as well as adding a withdrawl. Not seen in converts.
add_event_to_dict('Withdraw(address,address,uint32,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# Claim withdrawl(s).
# add_event_to_dict('ClaimSeasons(address,address,uint32[],uint256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# add_event_to_dict('ClaimSeason(address,address,uint32,uint256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)


# Farmer's market events.
MARKET_EVENT_MAP = {}
MARKET_SIGNATURES_LIST = []
add_event_to_dict('PodListingCreated(address,uint256,uint256,uint256,uint24,uint256,bool)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodListingFilled(address,address,uint256,uint256,uint256)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
# add_event_to_dict('PodListingCancelled(address,uint256)',
#                   MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodOrderCreated(address,bytes32,uint256,uint24,uint256)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodOrderFilled(address,address,bytes32,uint256,uint256,uint256)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
# add_event_to_dict('PodOrderCancelled(address,bytes32)',
#                   MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)


# Barn Raise events.
BARN_RAISE_EVENT_MAP = {}
BARN_RAISE_SIGNATURES_LIST = []
add_event_to_dict('Sow(address,uint256,uint256)',
                  BARN_RAISE_EVENT_MAP, BARN_RAISE_SIGNATURES_LIST)
add_event_to_dict('CreateBid(address,uint256,uint256,uint256,uint256)',
                  BARN_RAISE_EVENT_MAP, BARN_RAISE_SIGNATURES_LIST)
add_event_to_dict('UpdateBid(address,uint256,uint256,uint256,uint256,uint256,uint256,uint256)',
                  BARN_RAISE_EVENT_MAP, BARN_RAISE_SIGNATURES_LIST)
print(BARN_RAISE_EVENT_MAP)


def generate_sig_hash_map(sig_str_list):
    return {sig.split('(')[0]: Web3.keccak(
        text=sig).hex() for sig in sig_str_list}


# Method signatures. We handle some logs differently when derived from different methods.
# Silo conversion signatures.
silo_conversion_sig_strs = ['convertDepositedLP(uint256,uint256,uint32[],uint256[])',
                            'convertDepositedBeans(uint256,uint256,uint32[],uint256[])']
silo_conversion_sigs = generate_sig_hash_map(silo_conversion_sig_strs)
# Signatures of methods with the explicit bean deposit (most txns include embedded deposit).
bean_deposit_sig_strs = ['depositBeans(uint256)',
                         'buyAndDepositBeans(uint256,uint256)',
                         'claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))',
                         'claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))']
bean_deposit_sigs = generate_sig_hash_map(bean_deposit_sig_strs)

# Claim type signatures.
# claim_sigs = ['claim', 'claimAndUnwrapBeans', 'claimConvertAddAndDepositLP', 'claimAndSowBeans', 'claimBuyAndSowBeans', 'claimAndCreatePodOrder', 'claimAndFillPodListing', 'claimBuyBeansAndCreatePodOrder', 'claimBuyBeansAndFillPodListing', 'claimAddAndDepositLP', 'claimAndDepositBeans', 'claimAndDepositLP', 'claimAndWithdrawBeans', 'claimAndWithdrawLP', 'claimBuyAndDepositBeans']
claim_deposit_beans_sig_strs = ['claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool))',
                                'claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool)))']
claim_deposit_beans_sigs = generate_sig_hash_map(claim_deposit_beans_sig_strs)

# Signatures of methods of interest for testing.
test_deposit_sig_strs = ['harvest(uint256[])', 'updateSilo(address)', 'BeanAllocation(address,uint256)']
test_deposit_sigs = generate_sig_hash_map(test_deposit_sig_strs)

with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/erc20_abi.json')) as erc20_abi_file:
    erc20_abi = json.load(erc20_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/uniswap_v2_pool_abi.json')) as uniswap_pool_abi_file:
    uniswap_pool_abi = json.load(uniswap_pool_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/curve_pool_abi.json')) as curve_pool_abi_file:
    curve_pool_abi = json.load(curve_pool_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/bean_abi.json')) as bean_abi_file:
    bean_abi = json.load(bean_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/beanstalk_abi.json')) as beanstalk_abi_file:
    beanstalk_abi = json.load(beanstalk_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/bean_price_oracle_abi.json')) as bean_price_oracle_abi_file:
    bean_price_abi = json.load(bean_price_oracle_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/barn_raise_abi.json')) as barn_raise_abi_file:
    barn_raise_abi = json.load(barn_raise_abi_file)


def get_web3_instance():
    """Get an instance of web3 lib."""
    # NOTE(funderberker): We are using websockets but we are not using any continuous watching
    # functionality. Monitoring is done through periodic get_new_events calls.
    return Web3(WebsocketProvider(URL, websocket_timeout=60))


def get_eth_bean_pool_contract(web3):
    """Get a web.eth.contract object for the ETH:BEAN pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=UNI_V2_BEAN_ETH_ADDR, abi=uniswap_pool_abi)


def get_eth_usdc_pool_contract(web3):
    """Get a web.eth.contract object for the ETH:USDC pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=UNI_V2_ETH_USDC_ADDR, abi=uniswap_pool_abi)


def get_bean_3crv_pool_contract(web3):
    """Get a web.eth.contract object for the curve BEAN:3CRV pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=CURVE_BEAN_3CRV_ADDR, abi=curve_pool_abi)

def get_bean_lusd_pool_contract(web3):
    """Get a web.eth.contract object for the curve BEAN:LUSD pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=CURVE_BEAN_LUSD_ADDR, abi=curve_pool_abi)

def get_bean_contract(web3):
    """Get a web.eth.contract object for the Bean token contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEAN_ADDR, abi=bean_abi)


def get_beanstalk_contract(web3):
    """Get a web.eth.contract object for the Beanstalk contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEANSTALK_ADDR, abi=beanstalk_abi)


def get_bean_price_contract(web3):
    """Get a web.eth.contract object for the Bean price oracle contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEAN_PRICE_ORACLE_ADDR, abi=bean_price_abi)

def get_barn_raise_contract(web3):
    """Get a web.eth.contract object for the Barn Raise contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BARN_RAISE_ADDR, abi=barn_raise_abi)


class ChainClient():
    """Base class for clients of Eth chain data."""

    def __init__(self, web3=None):
        self._web3 = web3 or get_web3_instance()


class BeanstalkClient(ChainClient):
    """Common functionality related to the Beanstalk contract."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_beanstalk_contract(self._web3)

    def get_weather(self):
        """Get current weather object."""
        return call_contract_function_with_retry(self.contract.functions.weather())

    def get_season_start_soil(self):
        """Amount of soil added/removed this season."""
        return soil_to_float(self.get_weather()[STARTSOIL_INDEX])
    
    def get_total_deposited_beans(self):
        """Get current total deposited Beans in the Silo."""
        return bean_to_float(call_contract_function_with_retry(self.contract.functions.totalDepositedBeans()))

    def get_total_deposited_uni_v2_bean_eth_lp(self):
        """Get current total deposited Uniswap V2 BEAN:ETH LP in the Silo."""
        return lp_to_float(call_contract_function_with_retry(self.contract.functions.totalDepositedLP()))

    def get_total_deposited(self, address, decimals):
        """Return the total deposited of the token at address as a float."""
        return token_to_float(call_contract_function_with_retry(self.contract.functions.getTotalDeposited(address)), decimals)

class BeanClient(ChainClient):
    """Common functionality related to the Bean token."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.price_contract = get_bean_price_contract(self._web3)

    def get_price_info(self):
        """Get all pricing info from oracle.

        Pricing data is returned as an array. See abi for structure.
        """
        raw_price_info = call_contract_function_with_retry(
            self.price_contract.functions.price())
        return BeanClient.map_price_info(raw_price_info)

    @abstractmethod
    def map_price_info(raw_price_info):
        price_dict = {}
        price_dict['price'] = raw_price_info[0]
        price_dict['liquidity'] = raw_price_info[1]
        price_dict['delta_b'] = raw_price_info[2]
        price_dict['pool_infos'] = {}
        # Map address:pool_info for each supported pool.
        for pool_info in raw_price_info[3]:
            pool_dict = {}
            pool_dict['pool'] = pool_info[0] # address
            pool_dict['tokens'] = pool_info[1]
            pool_dict['balances'] = pool_info[2]
            pool_dict['price'] = pool_info[3] # Bean price of pool (6 decimals)
            pool_dict['liquidity'] = pool_info[4] # USD value of the liquidity in the pool
            pool_dict['delta_b'] = pool_info[5]
            price_dict['pool_infos'][pool_dict['pool']] = pool_dict
        return price_dict

    def get_lp_token_value(self, token_address, decimals, liquidity_long=None):
        """Return the $/LP token value of an LP token at address as a float."""
        if liquidity_long is None:
            liquidity_long = self.get_price_info()['pool_infos'][token_address]['liquidity']
        liquidity_usd = token_to_float(liquidity_long, 6)
        token_supply = get_erc20_total_supply(token_address, decimals)
        return liquidity_usd / token_supply

    def avg_bean_price(self):
        """Current float bean price average across LPs from the Bean price oracle contract."""
        return bean_to_float(self.get_price_info()['price'])

    def uniswap_v2_pool_info(self):
        return self.get_price_info()['pool_infos'][UNI_V2_BEAN_ETH_ADDR]

    def curve_3crv_pool_info(self):
        return self.get_price_info()['pool_infos'][CURVE_BEAN_3CRV_ADDR]

    def curve_lusd_pool_info(self):
        return self.get_price_info()['pool_infos'][CURVE_BEAN_LUSD_ADDR]

    def uniswap_v2_bean_price(self):
        """Current float Bean price in the Uniswap V2 Bean:ETH pool."""
        return bean_to_float(self.uniswap_v2_pool_info()['price'])

    def curve_3crv_bean_price(self):
        """Current float Bean price in the Curve Bean:3CRV pool."""
        return bean_to_float(self.curve_3crv_pool_info()['price'])

    def curve_lusd_bean_price(self):
        """Current float Bean price in the Curve Bean:LUSD pool."""
        return bean_to_float(self.curve_lusd_pool_info()['price'])

class UniswapClient(ChainClient):
    def __init__(self, web3=None):
        super().__init__(web3)
        self.eth_usdc_pool_contract = get_eth_usdc_pool_contract(self._web3)
        self.eth_bean_pool_contract = get_eth_bean_pool_contract(self._web3)

    def current_eth_price(self):
        reserve0, reserve1, last_swap_block_time = self.eth_usdc_pool_contract.functions.getReserves().call()
        eth_reserves = eth_to_float(reserve1)
        usdc_reserves = usdc_to_float(reserve0)
        eth_price = usdc_reserves / eth_reserves
        logging.info(f'Current ETH Price: {eth_price} (last ETH:USDC txn block time: '
                     f'{datetime.datetime.fromtimestamp(last_swap_block_time).strftime("%c")})')
        return eth_price

    """
    DEPRECATED. Waiting for next implementation of Bean Price Oracle with $/LP to remove.
    """
    def current_eth_and_bean_price(self):
        reserve0, reserve1, last_swap_block_time = self.eth_bean_pool_contract.functions.getReserves().call()
        eth_reserves = eth_to_float(reserve0)
        bean_reserves = bean_to_float(reserve1)
        eth_price = self.current_eth_price()
        bean_price = eth_price * eth_reserves / bean_reserves
        logging.info(f'Current bean price: {bean_price} (last ETH:BEAN txn block time: '
                     f'{datetime.datetime.fromtimestamp(last_swap_block_time).strftime("%c")})')
        return eth_price, bean_price


class CurveClient(ChainClient):
    def __init__(self, web3=None):
        super().__init__(web3)
        self.bean_3crv_contract = get_bean_3crv_pool_contract(self._web3)



class BarnRaiseClient(ChainClient):
    """Common functionality related to the Barn Raise contract."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_barn_raise_contract(self._web3)
        # Set immutable contract variables.
        # contract_variables = call_contract_function_with_retry(self.contract.call())
        self.bid_start = call_contract_function_with_retry(self.contract.functions.bidStart()) # seconds epoch
        self.bonus_per_day = call_contract_function_with_retry(self.contract.functions.bonusPerDay()) # %
        self.bid_days = call_contract_function_with_retry(self.contract.functions.bidDays())
        self.seconds_per_day = call_contract_function_with_retry(self.contract.functions.secondsPerDay()) # %
        self.sowing_start = call_contract_function_with_retry(self.contract.functions.start()) # seconds epoch
        self.sowing_length = call_contract_function_with_retry(self.contract.functions.length()) # seconds
        self.base_weather = call_contract_function_with_retry(self.contract.functions.baseWeather()) # %
        self.step = call_contract_function_with_retry(self.contract.functions.step()) # seconds
        self.target = 77_000_000 * 1e18 # call_contract_function_with_retry(self.contract.functions.target()) # USD pegged token
        self.max_weather = call_contract_function_with_retry(self.contract.functions.maxWeather()) # %

    def steps_complete(self):
        """Return the total number of steps that have fully completed."""
        # If sowing period has not yet started, return 0.
        if time.time() < self.sowing_start:
            return 0
        return (time.time() - self.sowing_start) // self.step

    def weather(self):
        """Calculate and return current weather."""
        # If sowing period has not yet started, return 0.
        if time.time() < self.sowing_start:
            return 0
        # Weather starts at the base and increases 1% every step.
        return self.steps_complete() + self.base_weather

    def weather_at_step(self, step_number):
        """Return the weather at a given step."""
        return step_number+ self.base_weather

    def seconds_until_step_end(self):
        """Calculate and return the seconds until the current weather step ends."""
        sowing_time = time.time() - self.sowing_start
        # If sowing period has not yet started, return time to start of sowing period.
        if sowing_time < 0:
            return abs(sowing_time)
        return self.step * (sowing_time % self.step)


def avg_eth_to_bean_swap_price(eth_in, bean_out, eth_price):
    """Returns the $/bean cost for a swap txn using the $/ETH price and approximate fee."""
    # Approximate fee by reducing input amount by pool fee %.
    eth_in = eth_in * (1 - UNI_V2_POOL_FEE)
    return eth_price * (eth_in / bean_out)


def avg_bean_to_eth_swap_price(bean_in, eth_out, eth_price):
    """Returns the $/bean cost for a swap txn using the $/ETH price and approximate fee."""
    # Approximate fee by reducing input amount by pool fee %.
    bean_in = bean_in * (1 - UNI_V2_POOL_FEE)
    return eth_price * (eth_out / bean_in)



class EventClientType(IntEnum):
    UNISWAP_POOL = 0
    CURVE_3CRV_POOL = 1
    BEANSTALK = 2
    MARKET = 3
    CURVE_LUSD_POOL = 4
    BARN_RAISE = 5


class EthEventsClient():
    def __init__(self, event_client_type):
        # Track recently seen txns to avoid processing same txn multiple times.
        self._recent_processed_txns = OrderedDict()
        self._web3 = get_web3_instance()
        self._event_client_type = event_client_type
        if self._event_client_type == EventClientType.UNISWAP_POOL:
            self._contract = get_eth_bean_pool_contract(self._web3)
            self._contract_address = UNI_V2_BEAN_ETH_ADDR
            self._events_dict = UNISWAP_POOL_EVENT_MAP
            self._signature_list = UNISWAP_POOL_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.CURVE_3CRV_POOL:
            self._contract = get_bean_3crv_pool_contract(self._web3)
            self._contract_address = CURVE_BEAN_3CRV_ADDR
            self._events_dict = CURVE_POOL_EVENT_MAP
            self._signature_list = CURVE_POOL_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.CURVE_LUSD_POOL:
            self._contract = get_bean_lusd_pool_contract(self._web3)
            self._contract_address = CURVE_BEAN_LUSD_ADDR
            self._events_dict = CURVE_POOL_EVENT_MAP
            self._signature_list = CURVE_POOL_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._contract = get_beanstalk_contract(self._web3)
            self._contract_address = BEANSTALK_ADDR
            self._events_dict = BEANSTALK_EVENT_MAP
            self._signature_list = BEANSTALK_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.MARKET:
            self._contract = get_beanstalk_contract(self._web3)
            self._contract_address = BEANSTALK_ADDR
            self._events_dict = MARKET_EVENT_MAP
            self._signature_list = MARKET_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.BARN_RAISE:
            self._contract = get_barn_raise_contract(self._web3)
            self._contract_address = BARN_RAISE_ADDR
            self._events_dict = BARN_RAISE_EVENT_MAP
            self._signature_list = BARN_RAISE_SIGNATURES_LIST
            self._set_filter()
        else:
            raise ValueError("Illegal event client type.")

    def _set_filter(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filter = self._web3.eth.filter({
            "address": self._contract_address,
            "topics": [self._signature_list],
            # "fromBlock": 10581687, # Use this to search for old events. # Rinkeby
            # "fromBlock": 14205000, # Use this to search for old events. # Mainnet
            "toBlock": 'latest'
        })

    def get_new_logs(self, dry_run=False):
        """Iterate through all entries passing filter and return list of decoded Log Objects.

        Each on-chain event triggered creates one log, which is associated with one entry. We
        assume that an entry here will contain only one log of interest. It is
        possible to have multiple entries on the same block though, with each entry
        representing a unique txn.

        Note that there may be multiple unique entries with the same topic. Though we assume
        each entry indicates one log of interest.
        """
        # All decoded logs of interest from each txn.
        txn_logs_dict = {}

        if not dry_run:
            new_entries = self.safe_get_new_entries(self._event_filter)
        else:
            new_entries = get_test_entries()
            time.sleep(3)

        # Track which unique logs have already been processed from this event batch.
        for entry in new_entries:
            # This should only be triggered when pulling dry run test entries directly.
            if entry.address != self._contract_address:
                continue
            # The event topic associated with this entry.
            topic_hash = entry['topics'][0].hex()

            # Do not process topics outside of this classes topics of interest.
            if topic_hash not in self._events_dict:
                if not dry_run:
                    logging.warning(f'Unexpected topic ({topic_hash}) seen in '
                                    f'{self._event_client_type.name} EthEventsClient')
                else:
                    logging.info(
                        f'Ignoring unexpected topic ({topic_hash}) from dry run data.')
                continue

            # Print out entry.
            logging.info(
                f'{self._event_client_type.name} entry:\n{str(entry)}\n')

            # Do not process the same txn multiple times.
            txn_hash = entry['transactionHash']
            if txn_hash in txn_logs_dict:
                continue

            logging.info(
                f'{self._event_client_type.name} processing {txn_hash.hex()} logs.')

            # Retrieve the full txn and txn receipt.
            receipt = get_txn_receipt_or_wait(self._web3, txn_hash)

            # Get and decode all logs of interest from the txn. There may be many logs.
            decoded_logs = []
            for signature in self._signature_list:
                decoded_logs.extend(self._contract.events[
                    self._events_dict[signature]]().processReceipt(receipt, errors=DISCARD)) 
            logging.info(f'Decoded logs:\n{decoded_logs}')

            # Prune unrelated logs - logs that are of the same event types we watch, but are
            # not related to Beanstalk (i.e. swaps of non-Bean tokens).
            decoded_logs_copy = decoded_logs.copy()
            decoded_logs.clear()
            for log in decoded_logs_copy:
                if log.event == 'Swap':
                    # Only process uniswap swaps with the ETH:BEAN pool.
                    if log.address != UNI_V2_BEAN_ETH_ADDR:
                        continue
                elif log.event == 'TokenExchangeUnderlying' or log.event == 'TokenExchange':
                    # Only process curve exchanges in the BEAN pools.
                    if log.address not in [CURVE_BEAN_3CRV_ADDR, CURVE_BEAN_LUSD_ADDR]:
                        continue
                decoded_logs.append(log)

            # Add all remaining txn logs to log map.
            txn_logs_dict[txn_hash] = decoded_logs
            logging.info(
                f'Transaction: {txn_hash}\nAll txn logs of interest:\n'
                f'{NEWLINE_CHAR.join([str(l) for l in decoded_logs])}')

        return txn_logs_dict

    def safe_get_new_entries(self, filter):
        """Retrieve all new entries that pass the filter.

        Returns one entry for every log that matches a filter. So if a single txn has multiple logs
        of interest this will return multiple entries.
        Catch any exceptions that may arise when attempting to connect to Infura.
        """
        logging.info(
            f'Checking for new {self._event_client_type.name} entries with '
            f'{self._event_filter}.')
        try_count = 0
        while try_count < 5:
            try_count += 1
            try:
                # We must verify new_entries because get_new_entries() will occasionally pull
                # entries that are not actually new. May be a bug with web3 or may just be a relic
                # of the way block confirmations work.
                new_entries = filter.get_new_entries()
                new_unique_entries = []
                # Remove entries w txn hashes that already processed on past get_new_entries calls.
                for i in range(len(new_entries)):
                    entry = new_entries[i]
                    # If we have not already processed this txn hash.
                    if entry.transactionHash not in self._recent_processed_txns:
                        new_unique_entries.append(entry)
                    else:
                        logging.warning(f'Ignoring txn that has already been processed ({entry.transactionHash})')
                # Add all new txn hashes to recent processed set/dict.
                for entry in new_unique_entries:
                    # Arbitrary value. Using this as a set.
                    self._recent_processed_txns[entry.transactionHash] = True
                # Keep the recent txn queue size within limit.
                for _ in range(max(0, len(self._recent_processed_txns) - TXN_MEMORY_SIZE_LIMIT)):
                    self._recent_processed_txns.popitem(last=False)
                return new_unique_entries
                # return filter.get_all_entries() # Use this to search for old events.
            except (ValueError, asyncio.TimeoutError, Exception) as e:
                logging.warning(e, exc_info=True)
                logging.warning(
                    'filter.get_new_entries() failed or timed out. Retrying...')
                time.sleep(1)
        # Filters rely on server state and may be arbitrarily uninstalled by server.
        # https://github.com/ethereum/web3.py/issues/551
        # If we are failing too much recreate the filter.
        self._set_filter()
        logging.error('Failed to get new event entries. Passing.')
        return []

def get_txn_receipt_or_wait(web3, txn_hash, max_retries=5):
    try_count = 0
    while True:
        try_count += 1
        try:
            return web3.eth.get_transaction_receipt(txn_hash)
        # Occassionally web3 will fail to pull the txn with "not found" error. This is likely
        # because the txn has not been confirmed at the time of call, even though the logs may
        # have already been seen. In this case, wait and hope it will confirm soon.
        except Exception as e:
            if try_count < max_retries:
                # At least 1 ETH block time.
                time.sleep(15)
                continue
            logging.error(f'Failed to get txn after {try_count} retries. Was the block orphaned?')
            raise(e)

def get_erc20_total_supply(addr, decimals, web3=None):
    """Get the total supply of ERC-20 token in circulation as float."""
    if not web3:
        web3 = get_web3_instance()
    partial_contract = web3.eth.contract(address=addr, abi=erc20_abi)
    return token_to_float(partial_contract.functions.totalSupply().call(), decimals)

def get_erc20_info(addr, web3=None):
    """Get the name, symbol, and decimals of an ERC-20 token."""
    if not web3:
        web3 = get_web3_instance()
    contract = web3.eth.contract(address=addr, abi=erc20_abi)
    name = contract.functions.name().call()
    symbol = contract.functions.symbol().call()
    decimals = contract.functions.decimals().call()
    return name, symbol, decimals


def is_valid_wallet_address(address):
    """Return True is address is a valid ETH address. Else False."""
    if not Web3.isAddress(address):
        return False
    return True


def txn_topic_combo_id(entry):
    """Return a unique string identifying this transaction and topic combo."""
    return entry['transactionHash'].hex() + entry['topics'][0].hex()


def call_contract_function_with_retry(function, max_tries=10):
    """Try to call a web3 contract object function and retry with exponential backoff."""
    try_count = 1
    while True:
        try:
            return function.call()
        except Exception as e:
            if try_count < max_tries:
                try_count += 1
                continue
            else:
                logging.error(
                    f'Failed to access "{function.fn_name}" function at contract address "{function.address}" after {max_tries} attempts. Raising exception...')
                raise(e)



def token_to_float(token_long, decimals):
    if not token_long:
        return 0
    return int(token_long) / (10 ** decimals)


def eth_to_float(gwei):
    return token_to_float(gwei, ETH_DECIMALS)


def lp_to_float(lp_long):
    return token_to_float(lp_long, LP_DECIMALS)


def bean_to_float(bean_long):
    return token_to_float(bean_long, BEAN_DECIMALS)


def soil_to_float(soil_long):
    return token_to_float(soil_long, SOIL_DECIMALS)


def pods_to_float(pod_long):
    return token_to_float(pod_long, POD_DECIMALS)


def dai_to_float(dai_long):
    return token_to_float(dai_long, DAI_DECIMALS)


def usdc_to_float(usdc_long):
    return token_to_float(usdc_long, USDC_DECIMALS)


def usdt_to_float(usdt_long):
    return token_to_float(usdt_long, USDT_DECIMALS)


def crv_to_float(crv_long):
    return token_to_float(crv_long, CRV_DECIMALS)


def lusd_to_float(lusd_long):
    return token_to_float(lusd_long, LUSD_DECIMALS)


def get_test_entries():
    """Get a list of old encoded entries to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes
    time.sleep(1)
    entries = [
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x9ec4bb0665ea05462c94c6482051d656f0d8d9f087acc9f835b4ee26f4944f9e'), 'blockNumber': 13816727, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c4c0000000000000000000000000000000000000000000000000000000000168678',
                      'logIndex': 698, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x000000000000000000000000821acf4602b9d57da21dee0c3db45e71143c0b45')], 'transactionHash': HexBytes('0xf9665147a5d4f518b71c6f1239a84b5db3aaac980d5992a075e45249959bf1de'), 'transactionIndex': 158}),
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xd1e2eba6747cf9598e155b6d2da9eac7d24c0601b5a5842a6ae6b72a6e16fe65'), 'blockNumber': 13817493, 'data': '0x000000000000000000000000000000000000000000000000554528d91e9a45ce0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006164581d0',
                      'logIndex': 61, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x00000000000000000000000019c5bad4354e9a78a1ca0235af29b9eacf54ff2b')], 'transactionHash': HexBytes('0x490a140cd3d7255c06ca9d12406de1a87de7629a4f46383105e52b39dad6c1c7'), 'transactionIndex': 69}),
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x77f89165ca0064f418b1ea9e2ff0c200e20b01e9ae1d63cd1485336ec47ea6cb'), 'blockNumber': 13817422, 'data': '0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000306dc42000000000000000000000000000000000000000000000000002a079765d60cb90b0000000000000000000000000000000000000000000000000000000000000000',
                      'logIndex': 377, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x22f86ad3aae677137a23e7a68c706437e720fb9b00a67a0d4d8c1f6ddc81ab6e'), 'transactionIndex': 262}),
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x9291e97872b11651ff4eefc5536f7cd3ed7e7e36682adec332a051a3e87745a5'), 'blockNumber': 13817408, 'data': '0x000000000000000000000000000000000000000000000000d1e28f86a7ff82500000000000000000000000000000000000000000000000000000000ea1964db3', 'logIndex': 396, 'removed': False, 'topics': [
                      HexBytes('0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x44704927226aa3f01aba28d7d44812880d97cfbca22a89880c2dd930c9062747'), 'transactionIndex': 226}),
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xf52956493f1cd7feafd23a0a7ee9cf8a9d49ded9a409e27cee213fd0c5a312cf'), 'blockNumber': 13817773, 'data': '0x0000000000000000000000000000000000000000000000000001702ba6c7714100000000000000000000000000000000000000000000000000000000fbfa2ed70000000000000000000000000000000000000000000000000000001c4eddd279',
                      'logIndex': 226, 'removed': False, 'topics': [HexBytes('0xdd43b982e9a6350577cad86db14e254b658fb741d7864a6860409c4526bcc641'), HexBytes('0x0000000000000000000000000a6f465033a42b1ec9d8cd371386d124e9d3b408')], 'transactionHash': HexBytes('0xbfbed5a6e720aa9cd422c1b2bc6e25616edc1a0b4658c81348556a150f26b55a'), 'transactionIndex': 155}),
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xacab853acdebf139d234a39a7dbdf0dd8f3df54bb31b7564839ad2ff524dcb27'), 'blockNumber': 13817815, 'data': '0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a3e9ab8000000000000000000000000000000000000000000000000008e040fa032acd3f40000000000000000000000000000000000000000000000000000000000000000',
                      'logIndex': 363, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x000000000000000000000000b4e16d0168e52d35cacd2c6185b44281ec28c9dc')], 'transactionHash': HexBytes('0xd4e66c54a535ec41e92fcb9308109292bebce53ea5504e9f234ff7bca06f778f'), 'transactionIndex': 168}),  # multiswap
        # Silo Deposit (Uniswap LP).
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0x444cac6c85446e08741f799b6ed7d005bf53b5226b369e0bc0640bf3db9a1e5d'), HexBytes('0x000000000000000000000000c327f2f6c5df87673e6e12e674ba26654a25a7b5')], 'data': '0x00000000000000000000000000000000000000000000000000000000000012c000000000000000000000000000000000000000000000000000002b8ee40fa7f500000000000000000000000000000000000000000000000000000005054bcf5c',
                      'blockNumber': 14261767, 'transactionHash': HexBytes('0x3db396e1ada441294a2c65954e99710304b7a5d3cee974e9ba7589494bcc238f'), 'transactionIndex': 51, 'blockHash': HexBytes('0xb2734ad8458a1b2394de89d6f283c1ac89002e05e379f502c9d90a5ef0b38ad8'), 'logIndex': 64, 'removed': False}),
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x20162ea3724564603cb7d1f6d77f0f8760d10b1888f2b4f0a5817694f0aa4cd5'), 'blockNumber': 13817843, 'data': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000036d4669d00000000000000000000000000000000000000000000000002eeb669620f72bfe0000000000000000000000000000000000000000000000000000000000000000',
                      'logIndex': 66, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x3df8be86781d177f7a554bea6fdc79bfe5385f0a04f5a59255e65656093182d8'), 'transactionIndex': 57}),
        # LPDeposit.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x004d87b485e96285aefc8ed7df69f18573d16705dac3e56de0d3e1af283c2c7d'), 'blockNumber': 14205139, 'data': '0x00000000000000000000000000000000000000000000000000000000000011ed000000000000000000000000000000000000000000000000000006d7cd1833bc00000000000000000000000000000000000000000000000000000000d2f8140c',
                      'logIndex': 281, 'removed': False, 'topics': [HexBytes('0x444cac6c85446e08741f799b6ed7d005bf53b5226b369e0bc0640bf3db9a1e5d'), HexBytes('0x00000000000000000000000035f105e802da60d3312e5a89f51453a0c46b9dad')], 'transactionHash': HexBytes('0x07c7a744f64640327e33116b9435fbded90545debd52f791cba57373f9adda4b'), 'transactionIndex': 171}),
        # Silo Withdrawal, generalized.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0xb865b046f9ffd235ecbca9f3a2d7651d2195fd1dad49b619b2f55db56763533c'), HexBytes('0x0000000000000000000000006c3e007377effd74afe237ce3b0aeef969b63c91'), HexBytes('0x0000000000000000000000003a70dfa7d2262988064a2d051dd47521e43c9bdd')],
                      'data': '0x00000000000000000000000000000000000000000000000000000000000015f7000000000000000000000000000000000000000000002a5a058fc295ed000000', 'blockNumber': 14482448, 'transactionHash': HexBytes('0x78378de463adbe0350ff52be1729f581f3feacfa95bcd3a0427109f532953b53'), 'transactionIndex': 28, 'blockHash': HexBytes('0x0456819951f7c541a21b4f2f92715e7c3d278fb75e3546689378a5164761a761'), 'logIndex': 78, 'removed': False}),
        # Harvest.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xee21f9e6c957024a66f53ab0ad84b966ab046f6a5c65e6ee81e6a5aa8493c2f8'), 'blockNumber': 14174589, 'data': '0x00000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000df54c678000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000148015876622',
                      'logIndex': 219, 'removed': False, 'topics': [HexBytes('0x2250a3497055c8a54223a5ea64f100a209e9c1c4ab39d3cae64c64a493065fa1'), HexBytes('0x000000000000000000000000028afa72dadb6311107c382cf87504f37f11d482')], 'transactionHash': HexBytes('0x8298dd7fa773f58f04a708dca23bb2c43c96fd57400c2959e82b41a18f32eef4'), 'transactionIndex': 50}),
        # Harvest + Deposit.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0x2250a3497055c8a54223a5ea64f100a209e9c1c4ab39d3cae64c64a493065fa1'), HexBytes('0x00000000000000000000000010bf1dcb5ab7860bab1c3320163c6dddf8dcc0e4')], 'data': '0x0000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000b0824e064c00000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000150854058140', 'blockNumber': 14411693, 'transactionHash': HexBytes(
                      '0x510bca99224ba448d8e90154c06880b819c357f9d7a91ed33a8e744d3c2bdb03'), 'transactionIndex': 61, 'blockHash': HexBytes('0xe241b43c0187ca80795d9a33705c25c9c26e2dc03485f69fb5089aa7d2e24bdb'), 'logIndex': 119, 'removed': False}),
        # ConvertDepositedBeans. Made manually, not accurate to chain.
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xe7300ad8ff662b19cf4fa86362fbccfd241d4a7a78ec894a4878b69c4682648f'), 'blockNumber': 13805622, 'data': '0x000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
                       'logIndex': 66, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x05858da0ac3a85bd75bb389e02e5df35bcbb1ca1b16f0e068038734f21ec23a0'), 'transactionIndex': 57}),
        # Beans bought.
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xb2ea6b5de747b36bb68950b57d683a74a4686d37daee238c5ee695bb4a60819b'), 'blockNumber': 13858696, 'data': '0x00000000000000000000000000000000000000000000000069789fbbc4f800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006f868aa83',
                      'logIndex': 454, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5')], 'transactionHash': HexBytes('0x9f8dc6b759cc32bc75e4057e5ad7f1f3db550a48de402a78c2292f4f4ebf9d1c'), 'transactionIndex': 337}),
        # ConvertDepositedLP.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xbdbf40bb84a198fdd3c294dd43ad52054bbff98bed392f2394070cc2edfe8fc2'), 'blockNumber': 13862755, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c380000000000000000000000000000000000000000000000000000adc44c0a5dab00000000000000000000000000000000000000000000000000000017ef49b268',
                      'logIndex': 52, 'removed': False, 'topics': [HexBytes('0x444cac6c85446e08741f799b6ed7d005bf53b5226b369e0bc0640bf3db9a1e5d'), HexBytes('0x0000000000000000000000009c88cd7743fbb32d07ed6dd064ac71c6c4e70753')], 'transactionHash': HexBytes('0xfc392ee8cd988a0838864620a1eec9c8e7fd6a49e9c611cac5852b7dbaed4ac5'), 'transactionIndex': 44}),
        # Curve pool: TokenExchangeUnderlying BEAN->DAI.
        AttributeDict({'address': '0x3a70DfA7d2262988064A2D051dd47521E43c9BdD', 'blockHash': HexBytes('0x5a54cd6da8bfb0ed994162eefe5ce1f49568c40194aeb62eae6c7ec5fe154ac4'), 'blockNumber': 14058145, 'data': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000038878cd2000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000002ecb6e36d49d9092984',
                      'logIndex': 9, 'removed': False, 'topics': [HexBytes('0xd013ca23e77a65003c2c659c5442c00c805371b7fc1ebd4c206c41d1536bd90b'), HexBytes('0x0000000000000000000000000000000000007f150bd6f54c40a34d7c3d5e9f56')], 'transactionHash': HexBytes('0x7b7cec2b1c72053945390818320ba08e8b2c2d8fb2fd24319c19519db4b2629e'), 'transactionIndex': 0}),
        # Curve pool: TokenExchangeUnderlying BEAN->USDC.
        AttributeDict({'address': '0x3a70DfA7d2262988064A2D051dd47521E43c9BdD', 'blockHash': HexBytes('0xdce039037dac5caade192e8f583289b146aa15526c23eacc6b27ed4e69e6c300'), 'blockNumber': 14058200, 'data': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000048c0b871d0000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000041bbe9aa8',
                      'logIndex': 77, 'removed': False, 'topics': [HexBytes('0xd013ca23e77a65003c2c659c5442c00c805371b7fc1ebd4c206c41d1536bd90b'), HexBytes('0x0000000000000000000000000000000000007f150bd6f54c40a34d7c3d5e9f56')], 'transactionHash': HexBytes('0x2076ddf03449a024290c4123ad69bde5fb2629770ea76577fb59574b359859ba'), 'transactionIndex': 8}),
        # Curve pool: Remove liquidity in non-bean coin.
        AttributeDict({'address': '0x3a70DfA7d2262988064A2D051dd47521E43c9BdD', 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000a79828df1850e8a3a3064576f380d90aecdd3359')], 'data': '0x000000000000000000000000000000000000000000003a2e714ea0844129111200000000000000000000000000000000000000000000393423c91b8458cb294000000000000000000000000000000000000000000004a0f04d93a402ea31d168', 'blockNumber': 14393420, 'transactionHash': HexBytes(
                      '0xdf5c3e1d4ad834c868ee41073dbe356f56b2b95d356b6552bcf38ff70ec1ffa1'), 'transactionIndex': 111, 'blockHash': HexBytes('0xb590ea15f1e8066815fc39dbcae30d3baf55a4df3197e114c1be17cc36ef182e'), 'logIndex': 92, 'removed': False}),
        # Curve pool: Remove liquidity in Bean coin.
        AttributeDict({'address': '0x3a70DfA7d2262988064A2D051dd47521E43c9BdD', 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000a79828df1850e8a3a3064576f380d90aecdd3359')], 'data': '0x0000000000000000000000000000000000000000000000ee19ae3974b26427b30000000000000000000000000000000000000000000000000000000106f2ef690000000000000000000000000000000000000000000293b5a14349ddb9b923b5', 'blockNumber': 14322919, 'transactionHash': HexBytes(
                      '0x0683e44f53206ce2930a55e4fa0449d66feb109c2baa044b2430f8c08fdd8d85'), 'transactionIndex': 97, 'blockHash': HexBytes('0x863666ed9b57444b031265a8b5cb42c66d903a46e4e4b56d12855b820607af7f'), 'logIndex': 199, 'removed': False}),
        # Curve pool: Remove liquidity in non-bean coin (transplanted to LUSD pool from 3CRV pool).
        AttributeDict({'address': '0xD652c40fBb3f06d6B58Cb9aa9CFF063eE63d465D', 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000a79828df1850e8a3a3064576f380d90aecdd3359')], 'data': '0x000000000000000000000000000000000000000000003a2e714ea0844129111200000000000000000000000000000000000000000000393423c91b8458cb294000000000000000000000000000000000000000000004a0f04d93a402ea31d168', 'blockNumber': 14393420, 'transactionHash': HexBytes(
                      '0xdf5c3e1d4ad834c868ee41073dbe356f56b2b95d356b6552bcf38ff70ec1ffa1'), 'transactionIndex': 111, 'blockHash': HexBytes('0xb590ea15f1e8066815fc39dbcae30d3baf55a4df3197e114c1be17cc36ef182e'), 'logIndex': 92, 'removed': False}),
        # Curve pool: Remove liquidity in Bean coin (transplanted to LUSD pool from 3CRV pool).
        AttributeDict({'address': '0xD652c40fBb3f06d6B58Cb9aa9CFF063eE63d465D', 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000a79828df1850e8a3a3064576f380d90aecdd3359')], 'data': '0x0000000000000000000000000000000000000000000000ee19ae3974b26427b30000000000000000000000000000000000000000000000000000000106f2ef690000000000000000000000000000000000000000000293b5a14349ddb9b923b5', 'blockNumber': 14322919, 'transactionHash': HexBytes(
                      '0x0683e44f53206ce2930a55e4fa0449d66feb109c2baa044b2430f8c08fdd8d85'), 'transactionIndex': 97, 'blockHash': HexBytes('0x863666ed9b57444b031265a8b5cb42c66d903a46e4e4b56d12855b820607af7f'), 'logIndex': 199, 'removed': False}),
        # Farmer's market: Pods ordered.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xfaef7c069fe09ea1bd4f6cdfbd1550ebb7bd2986e2759c4e8d6a9db6a16e19e4'), 'blockNumber': 14163350, 'data': '0x0087d1b16afbd5fbcb2b99f57ad11fa160135b88e203781b2142cbc1823219810000000000000000000000000000000000000000000000000000000b2d05e000000000000000000000000000000000000000000000000000000000000003d09000000000000000000000000000000000000000000000000000000da475abf000',
                      'logIndex': 175, 'removed': False, 'topics': [HexBytes('0x9d0f352519bb87be0593a36adf8feb8ee677ef1b9932894db339a3537ca2df8b'), HexBytes('0x000000000000000000000000eafc0e4acf147e53398a4c9ae5f15950332cce06')], 'transactionHash': HexBytes('0x153a103e21cce2f7847325c2c3ca47dafb20a83ba8e18f1e549298edab7cf629'), 'transactionIndex': 81}),
        # Farmer's market: Pods listing.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xc4545c2140e05b6200efa7ecf6c626135eeb85a91aea76f9c5563af925d1abfe'), 'blockNumber': 14161745, 'data': '0x0000000000000000000000000000000000000000000000000000287d7bdf723600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b11ece81400000000000000000000000000000000000000000000000000000000000aae600000000000000000000000000000000000000000000000000000287d7bdf72360000000000000000000000000000000000000000000000000000000000000000',
                      'logIndex': 364, 'removed': False, 'topics': [HexBytes('0xdbb99ae82f53a8f7a558e71f0c098ebc981afc0379125c7e03d87fc3282bfbc0'), HexBytes('0x0000000000000000000000002cd896e533983c61b0f72e6f4bbf809711acc5ce')], 'transactionHash': HexBytes('0x4d46a09d387a62430cea83011badc60a5ba62f14423303de0b94778c01951f40'), 'transactionIndex': 200}),
        # Farmer's market: Pod relist
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x4f669728e4379119b3f0ee5666c24ef82f1bdcfa7e68b4c5356f8de0ac14cd08'), 'blockNumber': 14161840, 'data': '0x00000000000000000000000000000000000000000000000000002526b89139260000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000231485252b000000000000000000000000000000000000000000000000000000000009eb1000000000000000000000000000000000000000000000000000002526b89139260000000000000000000000000000000000000000000000000000000000000000',
                      'logIndex': 262, 'removed': False, 'topics': [HexBytes('0xdbb99ae82f53a8f7a558e71f0c098ebc981afc0379125c7e03d87fc3282bfbc0'), HexBytes('0x000000000000000000000000c1e607b7730c43c8d15562ffa1ad27b4463dc4c4')], 'transactionHash': HexBytes('0x04597926ca1e080b510d9c7b1450a8b80570707b74436a69c6779377cf01668d'), 'transactionIndex': 188}),
        # Farmer's market: Exchange
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x7c19f6c2ff0b120aa59e7e47b4bb7ca8517e9e2968fdad559a1c1caa7b0c23e0'), 'blockNumber': 14162025, 'data': '0x0000000000000000000000000000000000000000000000000000ee106d3ea0da0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000065094de03', 'logIndex': 260,
                      'removed': False, 'topics': [HexBytes('0x04747662e13fb76b3eed402e26661377c3ddf3b1fdaf2ebf22638037754677da'), HexBytes('0x000000000000000000000000550586fc064315b54af25024415786843131c8c1'), HexBytes('0x00000000000000000000000041dd131e460e18befd262cf4fe2e2b2f43f6fb7b')], 'transactionHash': HexBytes('0xca33aef9a4f5fb9b52da37f17e19d06bf92b3a880656e6c839f7fba78dbaccd9'), 'transactionIndex': 118}),
        # Farmer's market: PodOrderFilled.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0xcde76f76bb5e9a4f97126b0428845b44e01404c9fc99ce9eeb029533f77e5ca9'), HexBytes('0x0000000000000000000000005a57107a58a0447066c376b211059352b617c3ba'), HexBytes('0x0000000000000000000000003efcb1c1b64e2ddd3ff1cab28ad4e5ba9cc90c1c')],
                      'data': '0x1b2239b4a2ea5dd08c9a089a3616784ba9b7d541bbe955fc1dc8b04b2e69680e0000000000000000000000000000000000000000000000000000170f1d7b91e90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001dc5639c', 'blockNumber': 14252611, 'transactionHash': HexBytes('0xad8f724dcd1214a00ad290904c1c8f4682c81dccd70c063fdf66be0cff616c9c'), 'transactionIndex': 156, 'blockHash': HexBytes('0x407233b0e6db85babb42286b135b21c89e6d866882c4414d32efe123ccb74adf'), 'logIndex': 289, 'removed': False}),
        # Farmer's market: PodOrderFilled, after re-order.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0xcde76f76bb5e9a4f97126b0428845b44e01404c9fc99ce9eeb029533f77e5ca9'), HexBytes('0x000000000000000000000000de13b8b32a0c7c1c300cd4151772b7ebd605660b'), HexBytes('0x000000000000000000000000eafc0e4acf147e53398a4c9ae5f15950332cce06')],
                      'data': '0x656f15e31fde7a753fa054712ff9a3f3fd50bf38c365f6eb917d1872ccb3dca80000000000000000000000000000000000000000000000000000265ac54b663b0000000000000000000000000000000000000000000000000000004015d49b3e00000000000000000000000000000000000000000000000000000000c75315aa', 'blockNumber': 14374880, 'transactionHash': HexBytes('0xc9c8ecf03558d4c4bbdbf02f9cf2fdafa6b0e186b754ef2d6cd6c18af5c0cb71'), 'transactionIndex': 288, 'blockHash': HexBytes('0x99111767441abfbf1094ecb8b96c17ad16ba90635da5d0b5578de541380d60f1'), 'logIndex':372, 'removed': False}),
        # Farmer's market: Fill payed with BeanAllocation.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0x04747662e13fb76b3eed402e26661377c3ddf3b1fdaf2ebf22638037754677da'), HexBytes('0x000000000000000000000000eafc0e4acf147e53398a4c9ae5f15950332cce06'), HexBytes('0x000000000000000000000000f28df3a3924eec94853b66daaace2c85e1eb24ca')],
                      'data': '0x00000000000000000000000000000000000000000000000000027681c7755547000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000008d33f790c', 'blockNumber': 14367955, 'transactionHash': HexBytes('0x917358c88d6b3c5be4c0a968877a30236783585de6a796ca5e0a4b1330bcf2c5'), 'transactionIndex': 178, 'blockHash': HexBytes('0x1b6d23607a523bd2eecef1aec6c4c7139d01644d9d8a8259e574e660a2714ffa'), 'logIndex': 362, 'removed': False}),
        # Deposit.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xc029ec31661394b8aeb2a4598bf332b51272255c4843c7401de2f2624a53b59a'), 'blockNumber': 14219352, 'data': '0x000000000000000000000000000000000000000000000000000000000000122200000000000000000000000000000000000000000000021d92c60f1bf35400b10000000000000000000000000000000000000000000000000000000254274980', 'logIndex': 225,
                       'removed': False, 'topics': [HexBytes('0x4e2ca0515ed1aef1395f66b5303bb5d6f1bf9d61a353fa53f73f8ac9973fa9f6'), HexBytes('0x000000000000000000000000771433c3bb5b9ef6e97d452d265cfff930e6dddb'), HexBytes('0x0000000000000000000000003a70dfa7d2262988064a2d051dd47521e43c9bdd')], 'transactionHash': HexBytes('0x697e588801005031f905f3fbd009a24d643cfb4d715deaff92059d15f4143320'), 'transactionIndex': 167}),
        # Barn Raise - Bid.
        AttributeDict({'address': '0x928969D2C9D7E6a91125f2DCc459Bf20D1E59E28', 'topics': [HexBytes('0xfc42a7e435a90ab46569cd557b08096267740a8dca5db055f8a8d38b5bb9c2c1'), HexBytes('0x000000000000000000000000d173c90f6cb294ac61512f03c25388f6a41622bb')], 'data': '0x0000000000000000000000000000000000000000000000000000000981eed51e000000000000000000000000000000000000000000000000000000000000003200000000000000000000000000000000000000000000000000000000626c96270000000000000000000000000000000000000000000000000000000000000009', 'blockNumber': 10591936, 'transactionHash': HexBytes(
                       '0x6bc7482dcef320178446ea3cb4122e7de0d81ad474118b5a8da95fa231c83f8f'), 'transactionIndex': 41, 'blockHash': HexBytes('0x5fc68bf64dcc9b6a5ce45b7d5bfff8869e9d102470417944875b7d2e990dc85a'), 'logIndex': 58, 'removed': False})
    ]
    return entries


# For testing purposes.
# Verify at https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371.
def monitor_uni_v2_pair_events():
    client = EthEventsClient(EventClientType.UNISWAP_POOL)
    while True:
        events = client.get_new_logs(dry_run=True)
        time.sleep(5)

# For testing purposes.


def monitor_curve_pool_events():
    client = EthEventsClient(EventClientType.CURVE_3CRV_POOL)
    while True:
        events = client.get_new_logs(dry_run=False)
        time.sleep(5)

# For testing purposes.


def monitor_beanstalk_events():
    client = EthEventsClient(EventClientType.BEANSTALK)
    while True:
        events = client.get_new_logs(dry_run=True)
        time.sleep(5)


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)
    # monitor_uni_v2_pair_events()
    # monitor_beanstalk_events()
    # monitor_curve_pool_events()
    bean_client = BeanClient()
    bean_client.avg_bean_price()

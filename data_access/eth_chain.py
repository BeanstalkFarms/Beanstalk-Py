from abc import abstractmethod
import asyncio
from collections import OrderedDict
import datetime
from enum import Enum, IntEnum
import logging
import json
import os
import time
import websockets

# NOTE(funderberker): LOCAL TESTING
from web3 import Web3, HTTPProvider, WebsocketProvider
from web3.logs import DISCARD

from constants.addresses import *
import tools.util

# Alchemy node key.
try:
    API_KEY = os.environ['ALCHEMY_ETH_API_KEY_PROD']
except KeyError:
    API_KEY = os.environ['ALCHEMY_ETH_API_KEY']


# # Local node testing address for foundry anvil node using https.
# LOCAL_TESTING_URL = 'http://localhost:8545/'
# # Goerli testing address.
# GOERLI_API_KEY = os.environ['ALCHEMY_GOERLI_API_KEY']
# URL = 'wss://eth-goerli.g.alchemy.com/v2/' + GOERLI_API_KEY
URL = 'wss://eth-mainnet.g.alchemy.com/v2/' + API_KEY

# Decimals for conversion from chain int values to float decimal values.
ETH_DECIMALS = 18
LP_DECIMALS = 18
BEAN_DECIMALS = 6
SOIL_DECIMALS = 6
STALK_DECIMALS = 10
SEED_DECIMALS = 6
POD_DECIMALS = 6
ROOT_DECIMALS = 18
DAI_DECIMALS = 18
USDC_DECIMALS = 6
USDT_DECIMALS = 6
CRV_DECIMALS = 18
LUSD_DECIMALS = 18
CURVE_POOL_TOKENS_DECIMALS = 18


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

# Incomplete of Beanstalk Terming of Tokens for human use.
TOKEN_SYMBOL_MAP = {
    BEAN_ADDR.lower() : 'BEAN',
    CURVE_BEAN_3CRV_ADDR.lower() : 'BEAN3CRV',
    UNRIPE_ADDR.lower() : 'urBEAN',
    UNRIPE_3CRV_ADDR.lower() : 'urBEAN3CRV'
}


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
add_event_to_dict('Harvest(address,uint256[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# Depositing an asset => AddDeposit()
# Withdrawing an asset => AddWithdrawal() & RemoveDeposit() 
# Claiming an asset => RemoveWithdrawal()
# AddWithdrawal and RemoveDeposit are separate because Converting emits a RemoveDeposit but not an AddWithdrawal
add_event_to_dict('AddDeposit(address,address,uint32,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('AddWithdrawal(address,address,uint32,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('RemoveWithdrawal(address,address,uint32,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('RemoveWithdrawals(address,address,uint32[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('RemoveDeposit(address,address,uint32,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('RemoveDeposits(address,address,uint32[],uint256[],uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('Convert(address,address,address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# add_event_to_dict('SeedsBalanceChanged(address,int256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# add_event_to_dict('StalkBalanceChanged(address,int256,int256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('Chop(address,address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('Plant(address,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('Pick(address,address,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)

# Farmer's market events.
MARKET_EVENT_MAP = {}
MARKET_SIGNATURES_LIST = []
add_event_to_dict('PodListingCreated(address,uint256,uint256,uint256,uint24,uint256,uint256,bytes,uint8,uint8)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodListingFilled(address,address,uint256,uint256,uint256,uint256)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodListingCancelled(address,uint256)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodOrderCreated(address,bytes32,uint256,uint24,uint256,uint256,bytes,uint8)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodOrderFilled(address,address,bytes32,uint256,uint256,uint256,uint256)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict('PodOrderCancelled(address,bytes32)',
                  MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)


# Barn Raise events.
FERTILIZER_EVENT_MAP = {}
FERTILIZER_SIGNATURES_LIST = []
add_event_to_dict('TransferSingle(address,address,address,uint256,uint256)',
                  FERTILIZER_EVENT_MAP, FERTILIZER_SIGNATURES_LIST)
add_event_to_dict('TransferBatch(address,address,address,uint256[],uint256[])',
                  FERTILIZER_EVENT_MAP, FERTILIZER_SIGNATURES_LIST)


# Root token events.
ROOT_EVENT_MAP = {}
ROOT_SIGNATURES_LIST = []
# add_event_to_dict('Mint(address,(address,uint32[],uint256[])[],uint256,uint256,uint256,uint256)',
#                   ROOT_EVENT_MAP, ROOT_SIGNATURES_LIST)
# add_event_to_dict('Redeem(address,(address,uint32[],uint256[])[],uint256,uint256,uint256,uint256)',
#                   ROOT_EVENT_MAP, ROOT_SIGNATURES_LIST)
add_event_to_dict('Transfer(address,address,uint256)',
                  ROOT_EVENT_MAP, ROOT_SIGNATURES_LIST)
# Watch for Root account Plants.
add_event_to_dict('Plant(address,uint256)',
                  ROOT_EVENT_MAP, ROOT_SIGNATURES_LIST)


# Root token events.
BETTING_EVENT_MAP = {}
BETTING_SIGNATURES_LIST = []
# Betting contract.
add_event_to_dict('BetPlaced(uint256,address,uint256,uint256)',
                  BETTING_EVENT_MAP, BETTING_SIGNATURES_LIST)
# Pool management contract.
add_event_to_dict('PoolCreated(uint256,uint256,uint256)',
                  BETTING_EVENT_MAP, BETTING_SIGNATURES_LIST)
# Event not actually in use on chain.
# add_event_to_dict('PoolStarted(uint256)',
#                   BETTING_EVENT_MAP, BETTING_SIGNATURES_LIST)
add_event_to_dict('PoolGraded(uint256,uint256[])',
                  BETTING_EVENT_MAP, BETTING_SIGNATURES_LIST)
add_event_to_dict('WinningsClaimed(uint256,address,uint256)',
                  BETTING_EVENT_MAP, BETTING_SIGNATURES_LIST)


def generate_sig_hash_map(sig_str_list):
    return {sig.split('(')[0]: Web3.keccak(
        text=sig).hex() for sig in sig_str_list}

# Silo Convert signature.
convert_function_sig_strs = ['convert(bytes,uint32[],uint256[])']
convert_sigs = generate_sig_hash_map(convert_function_sig_strs)

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
# Buy Fertilizer signature.
buy_fert_function_sig_strs = ['buyAndMint(uint256)', 'mint(uint256)', 'mintFertilizer(uint128,uint256,uint8)','farm(bytes[])']
buy_fert_sigs = generate_sig_hash_map(buy_fert_function_sig_strs)

# Claim type signatures.
# claim_sigs = ['claim', 'claimAndUnwrapBeans', 'claimConvertAddAndDepositLP', 'claimAndSowBeans', 'claimBuyAndSowBeans', 'claimAndCreatePodOrder', 'claimAndFillPodListing', 'claimBuyBeansAndCreatePodOrder', 'claimBuyBeansAndFillPodListing', 'claimAddAndDepositLP', 'claimAndDepositBeans', 'claimAndDepositLP', 'claimAndWithdrawBeans', 'claimAndWithdrawLP', 'claimBuyAndDepositBeans']
claim_deposit_beans_sig_strs = ['claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool))',
                                'claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool)))']
claim_deposit_beans_sigs = generate_sig_hash_map(claim_deposit_beans_sig_strs)

# Signatures of methods of interest for testing.
test_deposit_sig_strs = ['harvest(uint256[])', 'updateSilo(address)']
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
                       '../constants/abi/bean_price_abi.json')) as bean_price_abi_file:
    bean_price_abi = json.load(bean_price_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/fertilizer_abi.json')) as fertilizer_abi_file:
    fertilizer_abi = json.load(fertilizer_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/root_abi.json')) as root_abi_file:
    root_abi = json.load(root_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/betting_abi.json')) as betting_abi_file:
    betting_abi = json.load(betting_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../constants/abi/betting_admin_abi.json')) as betting_admin_abi_file:
    betting_admin_abi = json.load(betting_admin_abi_file)


def get_web3_instance():
    """Get an instance of web3 lib."""
    # # NOTE(funderberker): LOCAL TESTING (uses https due to local network constraints).
    # return Web3(HTTPProvider(LOCAL_TESTING_URL))
    # NOTE(funderberker): We are using websockets but we are not using any continuous watching
    # functionality. Monitoring is done through periodic get_new_events calls.
    return Web3(WebsocketProvider(URL, websocket_timeout=60))

def get_eth_usdc_pool_contract(web3):
    """Get a web.eth.contract object for the uniswap ETH:USDC pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=UNI_V2_ETH_USDC_ADDR, abi=uniswap_pool_abi)

def get_bean_3crv_pool_contract(web3):
    """Get a web.eth.contract object for the curve BEAN:3CRV pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=CURVE_BEAN_3CRV_ADDR, abi=curve_pool_abi)

def get_curve_3pool_contract(web3):
    """Get a web.eth.contract object for a curve 3pool contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=POOL_3POOL_ADDR, abi=curve_pool_abi)

def get_bean_contract(web3):
    """Get a web.eth.contract object for the Bean token contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEAN_ADDR, abi=bean_abi)

def get_unripe_contract(web3):
    """Get a web.eth.contract object for the unripe bean token. Contract is not thread safe."""
    return get_erc20_contract(web3, UNRIPE_ADDR)

def get_unripe_lp_contract(web3):
    """Get a web.eth.contract object for the unripe LP token. Contract is not thread safe."""
    return get_erc20_contract(web3, UNRIPE_3CRV_ADDR)

def get_beanstalk_contract(web3):
    """Get a web.eth.contract object for the Beanstalk contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEANSTALK_ADDR, abi=beanstalk_abi)

def get_bean_price_contract(web3):
    """Get a web.eth.contract object for the Bean price oracle contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEAN_PRICE_ORACLE_ADDR, abi=bean_price_abi)

def get_fertilizer_contract(web3):
    """Get a web.eth.contract object for the Barn Raise Fertilizer contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=FERTILIZER_ADDR, abi=fertilizer_abi)

def get_root_contract(web3):
    """Get a web.eth.contract object for the Root Token contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=ROOT_ADDR, abi=root_abi)

def get_betting_admin_contract(web3):
    """Get a web.eth.contract object for the betting pools contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BETTING_ADMIN_ADDR, abi=betting_admin_abi)

def get_betting_contract(web3):
    """Get a web.eth.contract object for the betting bets contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BETTING_ADDR, abi=betting_abi)

def get_erc20_contract(web3, address):
    """Get a web3.eth.contract object for a standard ERC20 token contract."""
    # Ignore checksum requirement.
    address = web3.toChecksumAddress(address.lower())
    return web3.eth.contract(address=address, abi=erc20_abi)

class ChainClient():
    """Base class for clients of Eth chain data."""

    def __init__(self, web3=None):
        self._web3 = web3 or get_web3_instance()


class BeanstalkClient(ChainClient):
    """Common functionality related to the Beanstalk contract."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_beanstalk_contract(self._web3)
        self.replant_season = 6074
        self.base_humidity = 2500 / 10
        self.final_humidity = 200 / 10
        self.humidity_step_size = 0.5 # %
        # Number of seasons to min humidity.
        self.max_steps = (self.base_humidity - self.final_humidity) / self.humidity_step_size

    def get_season(self):
        """Get current season."""
        return call_contract_function_with_retry(self.contract.functions.season())

    def get_weather(self):
        """Get current weather (temperature) object."""
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

    def get_underlying_token(self, unripe_token):
        """Return the address of the token that will be redeemed for a given unripe token."""
        return call_contract_function_with_retry(self.contract.functions.getUnderlyingToken(unripe_token))

    def get_recap_funded_percent(self):
        """Return the % of target funds that have already been funded via fertilizer sales."""
        # Note that % recap is same for all unripe tokens.
        return token_to_float(call_contract_function_with_retry(self.contract.functions.getRecapFundedPercent(UNRIPE_3CRV_ADDR)), 6)

    def get_remaining_recapitalization(self):
        """Return the USDC amount remaining to full capitalization."""
        return usdc_to_float(call_contract_function_with_retry(self.contract.functions.remainingRecapitalization()))

    def get_target_amount(self, remaining_recap, recap_funded_percent):
        return remaining_recap / (1 - recap_funded_percent)

    def get_amount_funded(self, remaining_recap, recap_funded_percent):
        """Return amount in USDC that has already been recapitalized.
        
        WARNING: This is imperfect. Will vary slightly based on unknown conditions of Beanstalk.
        Use graph to acquire supply when possible.
        """
        target = self.get_target_amount(remaining_recap, recap_funded_percent)
        return target - remaining_recap

    def get_humidity(self):
        """Calculate and return current humidity."""
        current_season = self.get_season()
        if current_season <= self.replant_season:
            return self.base_humidity
        elif current_season > self.replant_season + self.max_steps:
            return self.final_humidity
        return self.base_humidity - (current_season - self.replant_season) * self.humidity_step_size

class BeanClient(ChainClient):
    """Common functionality related to the Bean token."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.price_contract = get_bean_price_contract(self._web3)

    def get_price_info(self):
        """Get all pricing info from oracle.

        Pricing data is returned as an array. See abi for structure.
        """
        logging.info('Getting bean price...', exc_info=True)
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
            pool_dict['pool'] = pool_info[0] # Address
            pool_dict['tokens'] = pool_info[1]
            pool_dict['balances'] = pool_info[2]
            pool_dict['price'] = pool_info[3] # Bean price of pool (6 decimals)
            pool_dict['liquidity'] = pool_info[4] # USD value of the liquidity in the pool
            pool_dict['delta_b'] = pool_info[5]
            pool_dict['lp_usd'] = pool_info[6] # LP Token price in USD
            pool_dict['lp_bdv'] = pool_info[7] # LP Token price in BDV
            price_dict['pool_infos'][pool_dict['pool']] = pool_dict
        return price_dict

    def get_lp_token_value(self, token_address, decimals, liquidity_long=None):
        """Return the $/LP token value of an LP token at address as a float."""
        if liquidity_long is None:
            try:
                liquidity_long = self.get_price_info()['pool_infos'][token_address]['liquidity']
            # If the LP is not in the price aggregator, we do not know its value.
            except KeyError:
                return None
        liquidity_usd = token_to_float(liquidity_long, 6)
        token_supply = get_erc20_total_supply(token_address, decimals)
        return liquidity_usd / token_supply

    def avg_bean_price(self, price_info=None):
        """Current float bean price average across LPs from the Bean price oracle contract."""
        if price_info:
            price = price_info['price']
        else:
            price = self.get_price_info()['price']
        return bean_to_float(price)

    def total_delta_b(self, price_info=None):
        """Current deltaB across all pools."""
        if price_info:
            delta_b = price_info['delta_b']
        else:
            delta_b = self.get_price_info()['delta_b']
        return bean_to_float(delta_b)

    def curve_3crv_price(self):
        """Current float 3CRV price from Bean:3CRV Pool."""
        pool_info = self.curve_bean_3crv_pool_info()
        return (pool_info['liquidity'] - pool_info['balances'][1] * pool_info['price']) / pool_info['balances'][0]
    
    def curve_bean_3crv_pool_info(self):
        """Return pool info as list."""
        return self.get_price_info()['pool_infos'][CURVE_BEAN_3CRV_ADDR]

    def curve_bean_3crv_bean_price(self):
        """Current float Bean price in the Curve Bean:3CRV pool."""
        return bean_to_float(self.curve_bean_3crv_pool_info()['price'])

    def curve_bean_3crv_token_value(self):
        """Current float LP Token price of the Curve Bean:3CRV pool in USD."""
        return bean_to_float(self.curve_bean_3crv_pool_info()['lp_usd'])


class RootClient(ChainClient):
    """Common functionality related to the Root token."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.price_contract = get_root_contract(self._web3)

    def get_root_token_bdv(self):
        """Get BDV of the root token and return as float."""
        logging.info('Getting Root BDV...', exc_info=True)
        return bean_to_float(call_contract_function_with_retry(
            self.price_contract.functions.bdvPerRoot()))
    
    def get_total_supply(self):
        """Get total supply of the root token and return as float."""
        logging.info('Getting Root supply...', exc_info=True)
        return root_to_float(call_contract_function_with_retry(
            self.price_contract.functions.totalSupply()))


class BettingClient(ChainClient):
    """Common functionality related to the Betting system."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.pools_contract = get_betting_admin_contract(self._web3)
        # self.bets_contract = get_betting_contract(self._web3)

    def get_pool_count(self):
        """Get number of active pools and return as int."""
        logging.info(f'Getting pool count...')
        return call_contract_function_with_retry(self.pools_contract.functions.getTotalPools())

    def get_pool(self, pool_id):
        """Get pool struct."""
        pool_id = int(pool_id)
        logging.info(f'Getting pool info for pool {pool_id}...')
        return_list = call_contract_function_with_retry(
            self.pools_contract.functions.getPool(pool_id))
        return {
            'id': return_list[0],
            'numberOfTeams': return_list[1],
            'eventName': return_list[2],
            'totalBets': return_list[3],
            'totalAmount': root_to_float(return_list[4]),
            'status': return_list[8],
            'startTime': return_list[10]
        }

    # NOTE(funderberker): Very inefficient. Need better impl contract side.
    def get_all_pools(self):
        """
        Get all pools stored on contract.
        
        Assumes pool IDs are ascending ints from 0 to getTotalPools().
        """
        logging.info(f'Getting all pools...')
        pool_list = []
        num_pools = self.get_pool_count()
        for i in range(num_pools):
            pool_list.append(self.get_pool(i))
        return pool_list
    
    # NOTE(funderberker): Very inefficient. Need better impl contract side.
    def get_active_pools(self):
        """Get all pools stored on contract."""
        logging.info(f'Getting active pools...')
        active_pools = []
        pools = self.get_all_pools()
        current_time = time.time()
        for pool in pools:
            if pool['status'] == 1 and pool['startTime'] < current_time:
                active_pools.append(pool)
        return active_pools

    def get_pool_team(self, pool_id, team_id):
        """Get team struct."""
        pool_id = int(pool_id)
        team_id = int(team_id)
        logging.info(f'Getting pool team info for pool {pool_id} and team {team_id}...')
        return_list = call_contract_function_with_retry(
            self.pools_contract.functions.getPoolTeam(pool_id, team_id))
        return {
            'id': return_list[0],
            'name': return_list[1],
            'status': return_list[2],
            'totalAmount': root_to_float(return_list[3])
        }


# NOTE(funderberker): Deprecated. No longer in use, has not been updated post Replant.
class UniswapClient(ChainClient):
    def __init__(self, web3=None):
        super().__init__(web3)
        self.eth_usdc_pool_contract = get_eth_usdc_pool_contract(self._web3)
        # self.eth_bean_pool_contract = get_eth_bean_pool_contract(self._web3)

    def current_eth_price(self):
        reserve0, reserve1, last_swap_block_time = call_contract_function_with_retry(
            self.eth_usdc_pool_contract.functions.getReserves())
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
        reserve0, reserve1, last_swap_block_time = call_contract_function_with_retry(
            self.eth_bean_pool_contract.functions.getReserves())
        eth_reserves = eth_to_float(reserve0)
        bean_reserves = bean_to_float(reserve1)
        eth_price = self.current_eth_price()
        bean_price = eth_price * eth_reserves / bean_reserves
        logging.info(f'Current bean price: {bean_price} (last ETH:BEAN txn block time: '
                     f'{datetime.datetime.fromtimestamp(last_swap_block_time).strftime("%c")})')
        return eth_price, bean_price

class CurveClient(ChainClient):
    """Client for interacting with standard curve pools."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_curve_3pool_contract(self._web3)

    def get_3crv_price(self):
        return crv_to_float(call_contract_function_with_retry(self.contract.functions.get_virtual_price()))

class BarnRaiseClient(ChainClient):
    """Common functionality related to the Barn Raise Fertilizer contract."""

    def __init__(self, web3=None, beanstalk_client=None):
        super().__init__(web3)
        self.contract = get_fertilizer_contract(self._web3)
        # self.token_contract = get_fertilizer_token_contract(self._web3)
        # Set immutable variables.
        self.barn_raise_start = 1654516800 # seconds, epoch
        self.unpause_start = 1660564800 # seconds, epoch # August 15 2022, 12pm
        self.replant_season = 6074
        # self.pre_sale_humidity = 5000 / 10
        self.base_humidity = 2500 / 10
        self.step_size = 0.5 # %
        self.step_duration = 3600 # seconds
        if beanstalk_client is not None:
            self.beanstalk_client = beanstalk_client
        else:
            self.beanstalk_client = BeanstalkClient()

    def get_humidity(self):
        """Calculate and return current humidity."""
        # If unpause has not yet occurred, return 0.
        return self.beanstalk_client.get_humidity()

    def weather_at_step(self, step_number):
        """Return the weather at a given step."""
        return step_number+ self.base_weather

    def seconds_until_step_end(self):
        """Calculate and return the seconds until the current humidity step ends."""
        unpaused_time = time.time() - self.unpause_start
        # If barn raise has not yet started, return time to unpause.
        if unpaused_time < 0:
            return abs(unpaused_time)
        return unpaused_time % self.step_duration

    def remaining(self):
        """Amount of USDC still needed to be raised as decimal float."""
        return usdc_to_float(call_contract_function_with_retry(self.contract.functions.remaining()))

    # def purchased(self):
    #     """Amount of fertilizer that has been purchased.

    #     Note that this is not the same as amount 'raised', since forfeit silo assets contribute
    #     to the raised amount.
    #     """
    #     return self.token_contract 


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
    BEANSTALK = 0
    MARKET = 1
    BARN_RAISE = 2
    CURVE_BEAN_3CRV_POOL = 3
    ROOT_TOKEN = 4
    BETTING = 5


class EthEventsClient():
    def __init__(self, event_client_type):
        # Track recently seen txns to avoid processing same txn multiple times.
        self._recent_processed_txns = OrderedDict()
        self._web3 = get_web3_instance()
        self._event_client_type = event_client_type
        if self._event_client_type == EventClientType.CURVE_BEAN_3CRV_POOL:
            self._contracts = [get_bean_3crv_pool_contract(self._web3)]
            self._contract_addresses = [CURVE_BEAN_3CRV_ADDR]
            self._events_dict = CURVE_POOL_EVENT_MAP
            self._signature_list = CURVE_POOL_SIGNATURES_LIST
            self._set_filters()
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._contracts = [get_beanstalk_contract(self._web3)]
            self._contract_addresses = [BEANSTALK_ADDR]
            self._events_dict = BEANSTALK_EVENT_MAP
            self._signature_list = BEANSTALK_SIGNATURES_LIST
            self._set_filters()
        elif self._event_client_type == EventClientType.MARKET:
            self._contracts = [get_beanstalk_contract(self._web3)]
            self._contract_addresses = [BEANSTALK_ADDR]
            self._events_dict = MARKET_EVENT_MAP
            self._signature_list = MARKET_SIGNATURES_LIST
            self._set_filters()
        elif self._event_client_type == EventClientType.BARN_RAISE:
            self._contracts = [get_fertilizer_contract(self._web3)]
            self._contract_addresses = [FERTILIZER_ADDR]
            self._events_dict = FERTILIZER_EVENT_MAP
            self._signature_list = FERTILIZER_SIGNATURES_LIST
            self._set_filters()
        elif self._event_client_type == EventClientType.ROOT_TOKEN:
            self._contracts = [get_root_contract(self._web3)]
            self._contract_addresses = [ROOT_ADDR]
            self._events_dict = ROOT_EVENT_MAP
            self._signature_list = ROOT_SIGNATURES_LIST
            self._set_filters()
        elif self._event_client_type == EventClientType.BETTING:
            self._contracts = [get_betting_admin_contract(self._web3), get_betting_contract(self._web3)]
            self._contract_addresses = [BETTING_ADMIN_ADDR, BETTING_ADDR]
            self._events_dict = BETTING_EVENT_MAP
            self._signature_list = BETTING_SIGNATURES_LIST
            self._set_filters()
        else:
            raise ValueError("Illegal event client type.")



    def _set_filters(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filters = []
        for address in self._contract_addresses:
            self._event_filters.append(
                safe_create_filter(self._web3,
                    address=address,
                    topics=[self._signature_list],
                    # from_block=10581687, # Use this to search for old events. # Rinkeby
                    # from_block=14205000, # Use this to search for old events. # Mainnet
                    from_block='latest',
                    to_block='latest'
                )
            )

    def get_log_range(self, from_block, to_block='latest'):
        filters = []
        for address in self._contract_addresses:
            filters.append(
                safe_create_filter(self._web3,
                    address=address,
                    topics=[self._signature_list],
                    from_block=from_block,
                    to_block=to_block
                )
            )
        return self.get_new_logs(filters=filters, get_all=True)

    def get_new_logs(self, dry_run=False, filters=None, get_all=False):
        """Iterate through all entries passing filter and return list of decoded Log Objects.

        Each on-chain event triggered creates one log, which is associated with one entry. We
        assume that an entry here will contain only one log of interest. It is
        possible to have multiple entries on the same block though, with each entry
        representing a unique txn.

        Note that there may be multiple unique entries with the same topic. Though we assume
        each entry indicates one log of interest.
        """
        if filters is None:
            filters = self._event_filters
        # All decoded logs of interest from each txn.
        txn_logs_dict = {}

        if not dry_run:
            new_entries = []
            for filter in filters:
                new_entries.extend(self.safe_get_new_entries(filter, get_all=get_all))
        else:
            new_entries = get_test_entries()
            time.sleep(3)

        # Track which unique logs have already been processed from this event batch.
        for entry in new_entries:
            # # This should only be triggered when pulling dry run test entries set directly since it
            # # will include entries from other contracts.
            # if entry.address != self._contract_address:
            #     continue
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
            receipt = tools.util.get_txn_receipt_or_wait(self._web3, txn_hash)

            # Get and decode all logs of interest from the txn. There may be many logs.
            decoded_logs = []
            for signature in self._signature_list:
                for contract in self._contracts:
                    try:
                        decoded_logs.extend(contract.events[
                            self._events_dict[signature]]().processReceipt(receipt, errors=DISCARD))
                    except Exception:
                        # Try next contract if cannot decode from this contract.
                        continue
            logging.info(f'Decoded logs:\n{decoded_logs}')

            # Prune unrelated logs - logs that are of the same event types we watch, but are
            # not related to Beanstalk (i.e. swaps of non-Bean tokens).
            decoded_logs_copy = decoded_logs.copy()
            decoded_logs.clear()
            for log in decoded_logs_copy:
                # if log.event == 'Swap':
                #     # Only process uniswap swaps with the ETH:BEAN pool.
                #     if log.address != UNI_V2_BEAN_ETH_ADDR:
                #         continue
                if log.event == 'TokenExchangeUnderlying' or log.event == 'TokenExchange':
                    # Only process curve exchanges in supported BEAN pools.
                    if log.address not in [CURVE_BEAN_3CRV_ADDR]:
                        continue
                decoded_logs.append(log)

            # Add all remaining txn logs to log map.
            txn_logs_dict[txn_hash] = decoded_logs
            logging.info(
                f'Transaction: {txn_hash}\nAll txn logs of interest:\n'
                f'{NEWLINE_CHAR.join([str(l) for l in decoded_logs])}')

        return txn_logs_dict

    def safe_get_new_entries(self, filter, get_all=False):
        """Retrieve all new entries that pass the filter.

        Returns one entry for every log that matches a filter. So if a single txn has multiple logs
        of interest this will return multiple entries.
        Catch any exceptions that may arise when attempting to connect to Infura.
        """
        logging.info(
            f'Checking for new {self._event_client_type.name} entries with '
            f'{filter}.')
        try_count = 0
        while try_count < 5:
            try_count += 1
            try:
                if get_all:
                    return filter.get_all_entries()
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
            except (ValueError, asyncio.TimeoutError, websockets.exceptions.ConnectionClosedError, Exception) as e:
                logging.warning(e, exc_info=True)
                logging.warning(
                    'filter.get_new_entries() (or .get_all_entries()) failed or timed out. Retrying...')
                time.sleep(1)
        # Filters rely on server state and may be arbitrarily uninstalled by server.
        # https://github.com/ethereum/web3.py/issues/551
        # If we are failing too much recreate the filter.
        self._set_filter()
        logging.error('Failed to get new event entries. Passing.')
        return []

def safe_create_filter(web3, address, topics, from_block, to_block):
    """Create a filter but handle connection exceptions that web3 cannot manage."""
    max_tries=15
    try_count=0
    while try_count < max_tries:
        try:
            return web3.eth.filter({
                "address": address,
                "topics": topics,
                "fromBlock": from_block,
                "toBlock": to_block
            })
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception('Failed to safely create filter')

def safe_get_block(web3, block_number='latest'):
    max_tries=15
    try_count=0
    while try_count < max_tries:
        try:
            return web3.eth.get_block(block_number)
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception('Failed to safely get block')

def get_erc20_total_supply(addr, decimals, web3=None):
    """Get the total supply of ERC-20 token in circulation as float."""
    if not web3:
        web3 = get_web3_instance()
    contract = get_erc20_contract(web3, address=addr)
    return token_to_float(call_contract_function_with_retry(
        contract.functions.totalSupply()), decimals)

# Global cache for erc20 info that is static.
erc20_info_cache = {}
def get_erc20_info(addr, web3=None):
    """Get the name, symbol, and decimals of an ERC-20 token."""
    addr = addr.lower()
    if addr not in erc20_info_cache:
        logging.info(f'Querying chain for erc20 token info of {addr}.')
        if not web3:
            web3 = get_web3_instance()
        # addr = web3.toChecksumAddress(addr)
        contract = get_erc20_contract(web3, address=addr)
        name = call_contract_function_with_retry(contract.functions.name())
        # Use custom in-house Beanstalk Symbol name, if set, otherwise default to on-chain symbol.
        symbol = TOKEN_SYMBOL_MAP.get(addr) or call_contract_function_with_retry(contract.functions.symbol())
        decimals = call_contract_function_with_retry(contract.functions.decimals())
        erc20_info_cache[addr] = (name, symbol, decimals)
    return erc20_info_cache[addr]


def is_valid_wallet_address(address):
    """Return True is address is a valid ETH address. Else False."""
    if not Web3.isAddress(address):
        return False
    return True

# NOTE(funderberker): What an atrocious name I have chosen. I apologize to readers.
def is_6_not_18_decimal_token_amount(amount):
    """Attempt to determine if the amount belongs to Bean (6 decimal) or an 18 decimal token."""
    amount = int(amount)
    # If at least 16 digits present assume it is an 18 decimal token (1 billion Bean).
    if amount > 1000000000000000:
        return False
    else:
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
                time.sleep(0.5)
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


def stalk_to_float(soil_long):
    return token_to_float(soil_long, STALK_DECIMALS)


def seeds_to_float(soil_long):
    return token_to_float(soil_long, SEED_DECIMALS)


def pods_to_float(pod_long):
    return token_to_float(pod_long, POD_DECIMALS)


def root_to_float(root_long):
    return token_to_float(root_long, ROOT_DECIMALS)


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

        # Entries are a 1:1 mapping with events. A single txn can have have multiple entries and
        # multiple events. Different events/entries for the same txn will have different topics
        # if they are for a different event type. So a single txn may need multiple entries here.

        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x9ec4bb0665ea05462c94c6482051d656f0d8d9f087acc9f835b4ee26f4944f9e'), 'blockNumber': 13816727, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c4c0000000000000000000000000000000000000000000000000000000000168678',
        #               'logIndex': 698, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x000000000000000000000000821acf4602b9d57da21dee0c3db45e71143c0b45')], 'transactionHash': HexBytes('0xf9665147a5d4f518b71c6f1239a84b5db3aaac980d5992a075e45249959bf1de'), 'transactionIndex': 158}),
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xd1e2eba6747cf9598e155b6d2da9eac7d24c0601b5a5842a6ae6b72a6e16fe65'), 'blockNumber': 13817493, 'data': '0x000000000000000000000000000000000000000000000000554528d91e9a45ce0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006164581d0',
        #               'logIndex': 61, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x00000000000000000000000019c5bad4354e9a78a1ca0235af29b9eacf54ff2b')], 'transactionHash': HexBytes('0x490a140cd3d7255c06ca9d12406de1a87de7629a4f46383105e52b39dad6c1c7'), 'transactionIndex': 69}),
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x77f89165ca0064f418b1ea9e2ff0c200e20b01e9ae1d63cd1485336ec47ea6cb'), 'blockNumber': 13817422, 'data': '0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000306dc42000000000000000000000000000000000000000000000000002a079765d60cb90b0000000000000000000000000000000000000000000000000000000000000000',
        #               'logIndex': 377, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x22f86ad3aae677137a23e7a68c706437e720fb9b00a67a0d4d8c1f6ddc81ab6e'), 'transactionIndex': 262}),
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x9291e97872b11651ff4eefc5536f7cd3ed7e7e36682adec332a051a3e87745a5'), 'blockNumber': 13817408, 'data': '0x000000000000000000000000000000000000000000000000d1e28f86a7ff82500000000000000000000000000000000000000000000000000000000ea1964db3', 'logIndex': 396, 'removed': False, 'topics': [
        #               HexBytes('0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x44704927226aa3f01aba28d7d44812880d97cfbca22a89880c2dd930c9062747'), 'transactionIndex': 226}),
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xf52956493f1cd7feafd23a0a7ee9cf8a9d49ded9a409e27cee213fd0c5a312cf'), 'blockNumber': 13817773, 'data': '0x0000000000000000000000000000000000000000000000000001702ba6c7714100000000000000000000000000000000000000000000000000000000fbfa2ed70000000000000000000000000000000000000000000000000000001c4eddd279',
        #               'logIndex': 226, 'removed': False, 'topics': [HexBytes('0xdd43b982e9a6350577cad86db14e254b658fb741d7864a6860409c4526bcc641'), HexBytes('0x0000000000000000000000000a6f465033a42b1ec9d8cd371386d124e9d3b408')], 'transactionHash': HexBytes('0xbfbed5a6e720aa9cd422c1b2bc6e25616edc1a0b4658c81348556a150f26b55a'), 'transactionIndex': 155}),
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xacab853acdebf139d234a39a7dbdf0dd8f3df54bb31b7564839ad2ff524dcb27'), 'blockNumber': 13817815, 'data': '0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a3e9ab8000000000000000000000000000000000000000000000000008e040fa032acd3f40000000000000000000000000000000000000000000000000000000000000000',
        #               'logIndex': 363, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x000000000000000000000000b4e16d0168e52d35cacd2c6185b44281ec28c9dc')], 'transactionHash': HexBytes('0xd4e66c54a535ec41e92fcb9308109292bebce53ea5504e9f234ff7bca06f778f'), 'transactionIndex': 168}),  # multiswap
        # # Silo Deposit (Uniswap LP).
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0x444cac6c85446e08741f799b6ed7d005bf53b5226b369e0bc0640bf3db9a1e5d'), HexBytes('0x000000000000000000000000c327f2f6c5df87673e6e12e674ba26654a25a7b5')], 'data': '0x00000000000000000000000000000000000000000000000000000000000012c000000000000000000000000000000000000000000000000000002b8ee40fa7f500000000000000000000000000000000000000000000000000000005054bcf5c',
        #               'blockNumber': 14261767, 'transactionHash': HexBytes('0x3db396e1ada441294a2c65954e99710304b7a5d3cee974e9ba7589494bcc238f'), 'transactionIndex': 51, 'blockHash': HexBytes('0xb2734ad8458a1b2394de89d6f283c1ac89002e05e379f502c9d90a5ef0b38ad8'), 'logIndex': 64, 'removed': False}),
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x20162ea3724564603cb7d1f6d77f0f8760d10b1888f2b4f0a5817694f0aa4cd5'), 'blockNumber': 13817843, 'data': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000036d4669d00000000000000000000000000000000000000000000000002eeb669620f72bfe0000000000000000000000000000000000000000000000000000000000000000',
        #               'logIndex': 66, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x3df8be86781d177f7a554bea6fdc79bfe5385f0a04f5a59255e65656093182d8'), 'transactionIndex': 57}),
        # # LPDeposit.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x004d87b485e96285aefc8ed7df69f18573d16705dac3e56de0d3e1af283c2c7d'), 'blockNumber': 14205139, 'data': '0x00000000000000000000000000000000000000000000000000000000000011ed000000000000000000000000000000000000000000000000000006d7cd1833bc00000000000000000000000000000000000000000000000000000000d2f8140c',
        #               'logIndex': 281, 'removed': False, 'topics': [HexBytes('0x444cac6c85446e08741f799b6ed7d005bf53b5226b369e0bc0640bf3db9a1e5d'), HexBytes('0x00000000000000000000000035f105e802da60d3312e5a89f51453a0c46b9dad')], 'transactionHash': HexBytes('0x07c7a744f64640327e33116b9435fbded90545debd52f791cba57373f9adda4b'), 'transactionIndex': 171}),
        # # Silo Withdrawal, generalized.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0xb865b046f9ffd235ecbca9f3a2d7651d2195fd1dad49b619b2f55db56763533c'), HexBytes('0x0000000000000000000000006c3e007377effd74afe237ce3b0aeef969b63c91'), HexBytes('0x0000000000000000000000003a70dfa7d2262988064a2d051dd47521e43c9bdd')],
        #               'data': '0x00000000000000000000000000000000000000000000000000000000000015f7000000000000000000000000000000000000000000002a5a058fc295ed000000', 'blockNumber': 14482448, 'transactionHash': HexBytes('0x78378de463adbe0350ff52be1729f581f3feacfa95bcd3a0427109f532953b53'), 'transactionIndex': 28, 'blockHash': HexBytes('0x0456819951f7c541a21b4f2f92715e7c3d278fb75e3546689378a5164761a761'), 'logIndex': 78, 'removed': False}),
        # # Harvest.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xee21f9e6c957024a66f53ab0ad84b966ab046f6a5c65e6ee81e6a5aa8493c2f8'), 'blockNumber': 14174589, 'data': '0x00000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000df54c678000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000148015876622',
        #               'logIndex': 219, 'removed': False, 'topics': [HexBytes('0x2250a3497055c8a54223a5ea64f100a209e9c1c4ab39d3cae64c64a493065fa1'), HexBytes('0x000000000000000000000000028afa72dadb6311107c382cf87504f37f11d482')], 'transactionHash': HexBytes('0x8298dd7fa773f58f04a708dca23bb2c43c96fd57400c2959e82b41a18f32eef4'), 'transactionIndex': 50}),
        # # Harvest + Deposit.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0x2250a3497055c8a54223a5ea64f100a209e9c1c4ab39d3cae64c64a493065fa1'), HexBytes('0x00000000000000000000000010bf1dcb5ab7860bab1c3320163c6dddf8dcc0e4')], 'data': '0x0000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000b0824e064c00000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000150854058140', 'blockNumber': 14411693, 'transactionHash': HexBytes(
        #               '0x510bca99224ba448d8e90154c06880b819c357f9d7a91ed33a8e744d3c2bdb03'), 'transactionIndex': 61, 'blockHash': HexBytes('0xe241b43c0187ca80795d9a33705c25c9c26e2dc03485f69fb5089aa7d2e24bdb'), 'logIndex': 119, 'removed': False}),
        # # ConvertDepositedBeans. Made manually, not accurate to chain.
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xe7300ad8ff662b19cf4fa86362fbccfd241d4a7a78ec894a4878b69c4682648f'), 'blockNumber': 13805622, 'data': '0x000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
        #                'logIndex': 66, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x05858da0ac3a85bd75bb389e02e5df35bcbb1ca1b16f0e068038734f21ec23a0'), 'transactionIndex': 57}),
        # # Beans bought.
        # AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': H,exBytes('0xb2ea6b5de747b36bb68950b57d683a74a4686d37daee238c5ee695bb4a60819b'), 'blockNumber': 13858696, 'data': '0x00000000000000000000000000000000000000000000000069789fbbc4f800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000006f868aa83',
        #               'logIndex': 454, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5')], 'transactionHash': HexBytes('0x9f8dc6b759cc32bc75e4057e5ad7f1f3db550a48de402a78c2292f4f4ebf9d1c'), 'transactionIndex': 337}),
        # # ConvertDepositedLP.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xbdbf40bb84a198fdd3c294dd43ad52054bbff98bed392f2394070cc2edfe8fc2'), 'blockNumber': 13862755, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c380000000000000000000000000000000000000000000000000000adc44c0a5dab00000000000000000000000000000000000000000000000000000017ef49b268',
        #               'logIndex': 52, 'removed': False, 'topics': [HexBytes('0x444cac6c85446e08741f799b6ed7d005bf53b5226b369e0bc0640bf3db9a1e5d'), HexBytes('0x0000000000000000000000009c88cd7743fbb32d07ed6dd064ac71c6c4e70753')], 'transactionHash': HexBytes('0xfc392ee8cd988a0838864620a1eec9c8e7fd6a49e9c611cac5852b7dbaed4ac5'), 'transactionIndex': 44}),
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
        # Curve pool: Sell Beans for 3CRV.
        AttributeDict({'address': '0xc9C32cd16Bf7eFB85Ff14e0c8603cc90F6F2eE49', 'blockHash': HexBytes('0xc991b5df93e6ceb05d56561cd328f9b38f0b5fae1929c44abbe5093e7d641874'), 'blockNumber': 15344285, 'data': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fa4151a000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000dea6eed2a43b1a618',
                      'logIndex': 397, 'removed': False, 'topics': [HexBytes('0x8b3e96f2b889fa771c53c981b40daf005f63f637f1869f707052d15a3dd97140'), HexBytes('0x00000000000000000000000081c46feca27b31f3adc2b91ee4be9717d1cd3dd7')], 'transactionHash': HexBytes('0x0c7d7ccade419d01a7596bc8bf998eaf29d91317df37f19f3fe56ba965457ed7'), 'transactionIndex': 209}),
        # # Farmer's market: Pods ordered.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xfaef7c069fe09ea1bd4f6cdfbd1550ebb7bd2986e2759c4e8d6a9db6a16e19e4'), 'blockNumber': 14163350, 'data': '0x0087d1b16afbd5fbcb2b99f57ad11fa160135b88e203781b2142cbc1823219810000000000000000000000000000000000000000000000000000000b2d05e000000000000000000000000000000000000000000000000000000000000003d09000000000000000000000000000000000000000000000000000000da475abf000',
        #               'logIndex': 175, 'removed': False, 'topics': [HexBytes('0x9d0f352519bb87be0593a36adf8feb8ee677ef1b9932894db339a3537ca2df8b'), HexBytes('0x000000000000000000000000eafc0e4acf147e53398a4c9ae5f15950332cce06')], 'transactionHash': HexBytes('0x153a103e21cce2f7847325c2c3ca47dafb20a83ba8e18f1e549298edab7cf629'), 'transactionIndex': 81}),
        # # Farmer's market: Pods listing.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xc4545c2140e05b6200efa7ecf6c626135eeb85a91aea76f9c5563af925d1abfe'), 'blockNumber': 14161745, 'data': '0x0000000000000000000000000000000000000000000000000000287d7bdf723600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001b11ece81400000000000000000000000000000000000000000000000000000000000aae600000000000000000000000000000000000000000000000000000287d7bdf72360000000000000000000000000000000000000000000000000000000000000000',
        #               'logIndex': 364, 'removed': False, 'topics': [HexBytes('0xdbb99ae82f53a8f7a558e71f0c098ebc981afc0379125c7e03d87fc3282bfbc0'), HexBytes('0x0000000000000000000000002cd896e533983c61b0f72e6f4bbf809711acc5ce')], 'transactionHash': HexBytes('0x4d46a09d387a62430cea83011badc60a5ba62f14423303de0b94778c01951f40'), 'transactionIndex': 200}),
        # # Farmer's market: Pod relist
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x4f669728e4379119b3f0ee5666c24ef82f1bdcfa7e68b4c5356f8de0ac14cd08'), 'blockNumber': 14161840, 'data': '0x00000000000000000000000000000000000000000000000000002526b89139260000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000231485252b000000000000000000000000000000000000000000000000000000000009eb1000000000000000000000000000000000000000000000000000002526b89139260000000000000000000000000000000000000000000000000000000000000000',
        #               'logIndex': 262, 'removed': False, 'topics': [HexBytes('0xdbb99ae82f53a8f7a558e71f0c098ebc981afc0379125c7e03d87fc3282bfbc0'), HexBytes('0x000000000000000000000000c1e607b7730c43c8d15562ffa1ad27b4463dc4c4')], 'transactionHash': HexBytes('0x04597926ca1e080b510d9c7b1450a8b80570707b74436a69c6779377cf01668d'), 'transactionIndex': 188}),
        # # Farmer's market: Exchange
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x7c19f6c2ff0b120aa59e7e47b4bb7ca8517e9e2968fdad559a1c1caa7b0c23e0'), 'blockNumber': 14162025, 'data': '0x0000000000000000000000000000000000000000000000000000ee106d3ea0da0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000065094de03', 'logIndex': 260,
        #               'removed': False, 'topics': [HexBytes('0x04747662e13fb76b3eed402e26661377c3ddf3b1fdaf2ebf22638037754677da'), HexBytes('0x000000000000000000000000550586fc064315b54af25024415786843131c8c1'), HexBytes('0x00000000000000000000000041dd131e460e18befd262cf4fe2e2b2f43f6fb7b')], 'transactionHash': HexBytes('0xca33aef9a4f5fb9b52da37f17e19d06bf92b3a880656e6c839f7fba78dbaccd9'), 'transactionIndex': 118}),
        # # Farmer's market: PodOrderFilled.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0xcde76f76bb5e9a4f97126b0428845b44e01404c9fc99ce9eeb029533f77e5ca9'), HexBytes('0x0000000000000000000000005a57107a58a0447066c376b211059352b617c3ba'), HexBytes('0x0000000000000000000000003efcb1c1b64e2ddd3ff1cab28ad4e5ba9cc90c1c')],
        #               'data': '0x1b2239b4a2ea5dd08c9a089a3616784ba9b7d541bbe955fc1dc8b04b2e69680e0000000000000000000000000000000000000000000000000000170f1d7b91e90000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001dc5639c', 'blockNumber': 14252611, 'transactionHash': HexBytes('0xad8f724dcd1214a00ad290904c1c8f4682c81dccd70c063fdf66be0cff616c9c'), 'transactionIndex': 156, 'blockHash': HexBytes('0x407233b0e6db85babb42286b135b21c89e6d866882c4414d32efe123ccb74adf'), 'logIndex': 289, 'removed': False}),
        # # Farmer's market: PodOrderFilled, after re-order.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0xcde76f76bb5e9a4f97126b0428845b44e01404c9fc99ce9eeb029533f77e5ca9'), HexBytes('0x000000000000000000000000de13b8b32a0c7c1c300cd4151772b7ebd605660b'), HexBytes('0x000000000000000000000000eafc0e4acf147e53398a4c9ae5f15950332cce06')],
        #               'data': '0x656f15e31fde7a753fa054712ff9a3f3fd50bf38c365f6eb917d1872ccb3dca80000000000000000000000000000000000000000000000000000265ac54b663b0000000000000000000000000000000000000000000000000000004015d49b3e00000000000000000000000000000000000000000000000000000000c75315aa', 'blockNumber': 14374880, 'transactionHash': HexBytes('0xc9c8ecf03558d4c4bbdbf02f9cf2fdafa6b0e186b754ef2d6cd6c18af5c0cb71'), 'transactionIndex': 288, 'blockHash': HexBytes('0x99111767441abfbf1094ecb8b96c17ad16ba90635da5d0b5578de541380d60f1'), 'logIndex':372, 'removed': False}),
        # Convert to Beans (x5), each with different topics from different entries / logs.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xe33e870abfdc94f16b84690bb691174f893d5c11c376f4ed4b7c9cda7fc12a10'), 'blockNumber': 15721919, 'data': '0x0000000000000000000000000000000000000000000000000000000000001ddc0000000000000000000000000000000000000000000000000000000000310ee50000000000000000000000000000000000000000000000000000000000310ee5', 'logIndex': 17,
                      'removed': False, 'topics': [HexBytes('0xdbe49eaf5c2a8a7f65920c200ca5d47395540b884f6a1886fdb2611624f9981b'), HexBytes('0x00000000000000000000000087c9e571ae1657b19030eee27506c5d7e66ac29e'), HexBytes('0x000000000000000000000000bea0000029ad1c77d3d5d23ba2d8893db9d1efab')], 'transactionHash': HexBytes('0xaa09fc851308f808acec5badb44df10234a2beb128b4bd609d6368b88bb3e954'), 'transactionIndex': 6}),
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xe33e870abfdc94f16b84690bb691174f893d5c11c376f4ed4b7c9cda7fc12a10'), 'blockNumber': 15721919, 'data': '0x000000000000000000000000c9c32cd16bf7efb85ff14e0c8603cc90f6f2ee49000000000000000000000000bea0000029ad1c77d3d5d23ba2d8893db9d1efab00000000000000000000000000000000000000000000018b7a074d6eae]206eee00000000000000000000000000000000000000000000000000000001b2e2854c',
                      'logIndex': 30, 'removed': False, 'topics': [HexBytes('0x3f7117900f070f33613da64255c3e8a5b791ff071197653712e53fde9c3dab3d'), HexBytes('0x00000000000000000000000087c9e571ae1657b19030eee27506c5d7e66ac29e')], 'transactionHash': HexBytes('0xaa09fc851308f808acec5badb44df10234a2beb128b4bd609d6368b88bb3e954'), 'transactionIndex': 6}),
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xe33e870abfdc94f16b84690bb691174f893d5c11c376f4ed4b7c9cda7fc12a10'), 'blockNumber': 15721919, 'data': '0x000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000018b7a074d6eae206eee000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000017d4000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000018b7a074d6eae206eee',
                      'logIndex': 24, 'removed': False, 'topics': [HexBytes('0x5546b2ec4df884f6457f3f55f277a96bceff5c3d163925fd706cfc65c3bc5bc3'), HexBytes('0x00000000000000000000000087c9e571ae1657b19030eee27506c5d7e66ac29e'), HexBytes('0x000000000000000000000000c9c32cd16bf7efb85ff14e0c8603cc90f6f2ee49')], 'transactionHash': HexBytes('0xaa09fc851308f808acec5badb44df10234a2beb128b4bd609d6368b88bb3e954'), 'transactionIndex': 6}),
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xe33e870abfdc94f16b84690bb691174f893d5c11c376f4ed4b7c9cda7fc12a10'), 'blockNumber': 15721919, 'data': '0x0000000000000000000000000000000000000000000000000000000000310ee5', 'logIndex': 20, 'removed': False, 'topics': [
                      HexBytes('0xa5b32e50fecda2ccbfc130436ca7957154138f097b2a834f19ce579afd2d8427'), HexBytes('0x00000000000000000000000087c9e571ae1657b19030eee27506c5d7e66ac29e')], 'transactionHash': HexBytes('0xaa09fc851308f808acec5badb44df10234a2beb128b4bd609d6368b88bb3e954'), 'transactionIndex': 6}),
        AttributeDict({'address': '0xc9C32cd16Bf7eFB85Ff14e0c8603cc90F6F2eE49', 'blockHash': HexBytes('0xe33e870abfdc94f16b84690bb691174f893d5c11c376f4ed4b7c9cda7fc12a10'), 'blockNumber': 15721919, 'data': '0x00000000000000000000000000000000000000000000018b7a074d6eae206eee00000000000000000000000000000000000000000000000000000001b2e2854c0000000000000000000000000000000000000000001741f2fc140e556ee0469e',
                      'logIndex': 23, 'removed': False, 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5')], 'transactionHash': HexBytes('0xaa09fc851308f808acec5badb44df10234a2beb128b4bd609d6368b88bb3e954'), 'transactionIndex': 6}),
        # Bean:3CRV RemoveLiquidityOne - remove Bean.
        AttributeDict({'address': '0xc9C32cd16Bf7eFB85Ff14e0c8603cc90F6F2eE49', 'blockHash': HexBytes('0x1b6ea196d0a669dac906db5d20105a34ba6cd881b4ee2904a40c496599ff485f'), 'blockNumber': 15318843, 'data': '0x000000000000000000000000000000000000000000000f0410de0ab4bcf3ab7a0000000000000000000000000000000000000000000000000000001084364d840000000000000000000000000000000000000000001dbcbf16c93639317b55dd',
                      'logIndex': 242, 'removed': False, 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5')], 'transactionHash': HexBytes('0xc91ae5056aebbf162ddcbaf6c6767e0c7d70d704f1b923cf883d7ff5e0051c0f'), 'transactionIndex': 165}),
        # Bean:3CRV RemoveLiquidityOne - remove 3CRV.
        AttributeDict({'address': '0xc9C32cd16Bf7eFB85Ff14e0c8603cc90F6F2eE49', 'blockHash': HexBytes('0x72f7458127752eb6d8fe2bdd987e4524b3a21798168bc283cf9f0b3afdfe57b4'), 'blockNumber': 15318758, 'data': '0x000000000000000000000000000000000000000000001de7f3f28265d1e49016000000000000000000000000000000000000000000001d3c59efbb5be72fa4590000000000000000000000000000000000000000001dda0ecbc7e515c1b9b8ad',
                      'logIndex': 14, 'removed': False, 'topics': [HexBytes('0x5ad056f2e28a8cec232015406b843668c1e36cda598127ec3b8c59b8c72773a0'), HexBytes('0x000000000000000000000000a79828df1850e8a3a3064576f380d90aecdd3359')], 'transactionHash': HexBytes('0x66f626e3c556cf8130f80fb26a4ac41008ace62ac220b5ba4915fb0aaaad6676'), 'transactionIndex': 23}),

        # Curve sell Bean for USDC for Fertilizer.
        AttributeDict({'address': '0xc9C32cd16Bf7eFB85Ff14e0c8603cc90F6F2eE49', 'topics': [HexBytes('0xd013ca23e77a65003c2c659c5442c00c805371b7fc1ebd4c206c41d1536bd90b'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5')], 'data': '0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000005cfe91e00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000005ce841f', 'blockNumber': 15307175, 'transactionHash': HexBytes(
            '0x811ad63e3b3b8b85132e173489e5bba113cf83e1c57f02d1535616a0a49c1b94'), 'transactionIndex': 311, 'blockHash': HexBytes('0xa47d500dbaaa378475e0c2156c5129353a7ce924b040f63beaf6448b8ff52a99'), 'logIndex': 457, 'removed': False}),
        # Curve sell Bean for USDC for Fertilizer via farm() calls.
        AttributeDict({'address': '0xc9C32cd16Bf7eFB85Ff14e0c8603cc90F6F2eE49', 'topics': [HexBytes('0xd013ca23e77a65003c2c659c5442c00c805371b7fc1ebd4c206c41d1536bd90b'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5')], 'data': '0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000068e8034100000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000067c3e12a', 'blockNumber': 15309082, 'transactionHash': HexBytes(
            '0xd8d6b3bec9d01e59df972c06b39cc2eb724fe81788421c79d6f929d60ac1bf58'), 'transactionIndex': 64, 'blockHash': HexBytes('0xc60566ec4ce63e52885a49a91c360791b724c6ea8ef071b0abf36e9656914909'), 'logIndex': 136, 'removed': False}),
        # Transfer a deposit.
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x5d6022b4ebc8514a4719b055e7ac28d2067aae461ba4f151e84e8bf63bc89948'), 'blockNumber': 15568228, 'data': '0x000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000c0000000000000000000000000000000000000000000000000000000025463c80000000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000001b6200000000000000000000000000000000000000000000000000000000000019e90000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000057e40000000000000000000000000000000000000000000000000000000002540be400',
                      'logIndex': 34, 'removed': False, 'topics': [HexBytes('0x5546b2ec4df884f6457f3f55f277a96bceff5c3d163925fd706cfc65c3bc5bc3'), HexBytes('0x000000000000000000000000a4be84c37287350aa58eaea4d2f736463c03c893'), HexBytes('0x000000000000000000000000bea0000029ad1c77d3d5d23ba2d8893db9d1efab')], 'transactionHash': HexBytes('0x3f71ae6e96e0b0f2009004c45e98f31f05640862c82be00e9228abb555c12c18'), 'transactionIndex': 31}),
        # # PodListingFilled.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'topics': [HexBytes('0x04747662e13fb76b3eed402e26661377c3ddf3b1fdaf2ebf22638037754677da'), HexBytes('0x0000000000000000000000002a5c5e614ac54969790c8e383487289cbaa0af82'), HexBytes('0x00000000000000000000000019a4fe7d0c76490cca77b45580846cdb38b9a406')],
        #               'data': '0x00000000000000000000000000000000000000000000000000007cbe7c4cdc2d0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000124821a', 'blockNumber': 15279985, 'transactionHash': HexBytes('0x0842d92860e59a351ab1d31e018886005f5bd83ab67a5bf6c9fd6c8017cb6248'), 'transactionIndex': 262, 'blockHash': HexBytes('0x63c83e5919d45bdc6ee29b1f8035456a9ff890be3577a827f356e4f87946544e'), 'logIndex': 236, 'removed': False}),

        # # PodListingFilled.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xdb9022996d0dec8c5e921eaec06daff9e312d348f61eba5357f79fb8d2491523'), 'blockNumber': 15318189, 'data': '0x0000000000000000000000000000000000000000000000000002869000db510e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000d6ea891', 'logIndex': 358,
        #               'removed': False, 'topics': [HexBytes('0x04747662e13fb76b3eed402e26661377c3ddf3b1fdaf2ebf22638037754677da'), HexBytes('0x0000000000000000000000002303fd39e04cf4d6471df5ee945bd0e2cfb6c7a2'), HexBytes('0x00000000000000000000000019a4fe7d0c76490cca77b45580846cdb38b9a406')], 'transactionHash': HexBytes('0x0db6de354f66009689507376ab623209101809ebe5476712312a411c77060569'), 'transactionIndex': 146}),
        # # PodOrderFilled.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x8437c5cd9d567b539c18ac4e703135f123bd55ff90f82201cf7b50ad07dad143'), 'blockNumber': 15625683, 'data': '0x8d71748532cc94babba4dd882d52050996b9427b45770445750c4db50194d28a0000000000000000000000000000000000000000000000000000547d4835ff8f0000000000000000000000000000000000000000000000000000000000000000000000000000\000000000000000000000000000000000000000000004b45de0c',
        #               'logIndex': 130, 'removed': False, 'topics': [HexBytes('0xcde76f76bb5e9a4f97126b0428845b44e01404c9fc99ce9eeb029533f77e5ca9'), HexBytes('0x000000000000000000000000a9b13316697deb755cd86585de872ea09894ef0f'), HexBytes('0x0000000000000000000000009a00beffa3fc064104b71f6b7ea93babdc44d9da')], 'transactionHash': HexBytes('0x2a6ad056c0c0adfd0c13065369f9213a1e27109aa4f4fdb375f787f22a751f38'), 'transactionIndex': 63}),
        # # PodListingCancelled.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x04aa304bf1c4bc525d051cbaf1731478811069333e297ba41973e7733b1b63a1'), 'blockNumber': 16011128, 'data': '0x0000000000000000000000000000000000000000000000000002ee9de1f6d90d', 'logIndex': 164, 'removed': False, 'topics': [
        #               HexBytes('0xe9dc43fcbeb08ecb743b537fa98567049e3b77e283833f89ab216b22ede6ba0a'), HexBytes('0x0000000000000000000000009a00beffa3fc064104b71f6b7ea93babdc44d9da')], 'transactionHash': HexBytes('0xc3fb26c8de6527ae249b0932b4cca5d1574d5445e0ead8e59cdab63be68f9734'), 'transactionIndex': 73}),
        # # PodOrderCancelled.
        # AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x74ac17f022b692c06a3ff6d851bca27dd83ac7405ece649ad2dcfbeb71de2d84'), 'blockNumber': 15519178, 'data': '0xa916fb40410a322048278608e62233f31596e8d02b0ed2c5c5d52684f7377b60', 'logIndex': 267, 'removed': False, 'topics': [
        #               HexBytes('0x531180eb4d1153cb99f00e54fef0a473edc9e3e951f9a88468fec65988e9e4f8'), HexBytes('0x000000000000000000000000cde68f6a7078f47ee664ccbc594c9026a8a72d25')], 'transactionHash': HexBytes('0xa2f923a5245c23ac9d52e21a96224a10997d9acc10c57239397ad3e7a2826a63'), 'transactionIndex': 92}),
        # Barn Raise - TransferSingle from Null address (Mint). ROPSTEN.
        AttributeDict({'address': '0xd598d3799521a3F95784A81c883ddf1122Ad769B', 'topics': [HexBytes('0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'), HexBytes('0x000000000000000000000000a3c5a4df1c8ddad68af70c0f26ddd4ea99f323a4'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000'), HexBytes('0x000000000000000000000000a3c5a4df1c8ddad68af70c0f26ddd4ea99f323a4')],
                      'data': '0x00000000000000000000000000000000000000000000000000000000000017ba0000000000000000000000000000000000000000000000000000000000000001', 'blockNumber': 12312645, 'transactionHash': HexBytes('0x57e89d1f5bddddb2199ada7aabf46b9178e51e37401a7606f0bdb2a9174034e4'), 'transactionIndex': 3, 'blockHash': HexBytes('0x88da4209db288be2140634db3855bf464240fc54cb2f5f8c8241c5d7f9eff0c3'), 'logIndex': 5, 'removed': False}),
        # Fert Purchase
        AttributeDict({'address': '0x402c84De2Ce49aF88f5e2eF3710ff89bFED36cB6', 'blockHash': HexBytes('0x051c7a75f5a2941bf35054770a9c876ea0212c6ca7c1d7ed96b60b7fb8dd8b96'), 'blockNumber': 15399679, 'data': '0x000000000000000000000000000000000000000000000000000000000017b512000000000000000000000000000000000000000000000000000000000000000a', 'logIndex': 112, 'removed': False, 'topics': [HexBytes(
                      '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'), HexBytes('0x000000000000000000000000c1e088fc1323b20bcbee9bd1b9fc9546db5624c5'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000'), HexBytes('0x000000000000000000000000c9f817ea7aabe604f5677bf9c1339e32ef1b90f0')], 'transactionHash': HexBytes('0xf9eaf497b51d604185fffb00e00e440fda588c64b3643b0ae89780e2b5af459d'), 'transactionIndex': 54}),
        # Bet Placed
        AttributeDict({'address': '0xF3266919C00Aa61929b8C4fC5112e8F36665b2aa', 'blockHash': HexBytes('0xdb7c4f3d4c6a2c974a78918591e9a40ae7703fdf3b9d7f86b6bce001d6818d98'), 'blockNumber': 15988634, 'data': '0x00000000000000000000000000000000000000000000001578274de46bcb0000', 'logIndex': 32, 'removed': False, 'topics': [HexBytes('0x1b8a9031cb9351278d70a994f81536e9e08c91162e64f92b2fe4766fb7a891b4'), HexBytes(
            '0x0000000000000000000000000000000000000000000000000000000000000003'), HexBytes('0x000000000000000000000000c997b8078a2c4aa2ac8e17589583173518f3bc94'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000')], 'transactionHash': HexBytes('0xe3402d6f9ffe537909be457cad9146b084d5d6b7b3db70394184e86c1956584a'), 'transactionIndex': 23}),
        # Pool Created
        AttributeDict({'address': '0xbAB1c9BF99E1aebb809Fa19d5A20b8E13F9Fb8BF', 'blockHash': HexBytes('0x4e56676a2efe14757e52017d78a72c53ffe5f2e85284ca2ca09a401978e6df35'), 'blockNumber': 15987034, 'data': '0x00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000063824610', 'logIndex': 137, 'removed': False, 'topics': [HexBytes('0x6a0c7fbf44f6331867816b75328f586816c7ff60b5f3b71d7ccd1da786a93898'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000002')], 'transactionHash': HexBytes('0x6d5628da740f2d8bab442938a001ef276c797620e39c8d1fe9574906be1c6ac1'), 'transactionIndex': 58}),
        # Pool Started
        AttributeDict({'address': '0xbAB1c9BF99E1aebb809Fa19d5A20b8E13F9Fb8BF', 'blockHash': HexBytes('0x77bd7338676da563b871105ea1cc4fe37da1a47b2d7f8726dd861424f1d05b19'), 'blockNumber': 15987829, 'data': '0x', 'logIndex': 213, 'removed': False, 'topics': [HexBytes(
            '0x510ad7fdc6893c3992445eb80eeade3af54768c0d8dc2cc8fc57b1c9afa1491d'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000003')], 'transactionHash': HexBytes('0x970750d83a9cc6f27bdbf68c3eb7ed04d41c2fd06aafdb4e7794dc033cafa1e8'), 'transactionIndex': 99}),
        # Pool Graded
        AttributeDict({'address': '0xbAB1c9BF99E1aebb809Fa19d5A20b8E13F9Fb8BF', 'blockHash': HexBytes('0x00a51b17454a28587dbd6c0c6dc98bf36b9de9258c966a6c6166f14a9e898d01'), 'blockNumber': 15986747, 'data': '0x000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000001',
                      'logIndex': 192, 'removed': False, 'topics': [HexBytes('0xfc5202f8bdf8ee68ee02ef3a56b265a2d6f9c5102b232ab3b5d1636adf0057de'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000')], 'transactionHash': HexBytes('0x735c00cbfe64f85ad59a4967fc11b4a829109f08157c44590474c7c24ff6706f'), 'transactionIndex': 37}),
        # Root Minted
        AttributeDict({'address': '0x77700005BEA4DE0A78b956517f099260C2CA9a26', 'blockHash': HexBytes('0xf366304e66ba607dcd0c68f2a31c4e29110d6e263049c0f8aad9aaaa159f0a62'), 'blockNumber': 15985922, 'data': '0x00000000000000000000000000000000000000000000006da9742e9c940e2396', 'logIndex': 174, 'removed': False, 'topics': [HexBytes(
            '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000'), HexBytes('0x000000000000000000000000c997b8078a2c4aa2ac8e17589583173518f3bc94')], 'transactionHash': HexBytes('0x15f7714af939c4ab6e18a3d5c5676ea1113b60311a8d8b1e2b3a32bec5550027'), 'transactionIndex': 50}),
        # Root Redeemed
        AttributeDict({'address': '0x77700005BEA4DE0A78b956517f099260C2CA9a26', 'blockHash': HexBytes('0xbb89f4c8b5784281043e8df03bfeeec52f7ddc2f2ffd7531fbe0be8717009ac0'), 'blockNumber': 15989807, 'data': '0x00000000000000000000000000000000000000000000000068f270a4f2c43b14', 'logIndex': 105, 'removed': False, 'topics': [HexBytes(
            '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'), HexBytes('0x0000000000000000000000007e946603f26b7f46fdb0d106124db35bf14fcdb8'), HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000')], 'transactionHash': HexBytes('0x31bb9114845ecbd6208d96089c038b1feb8cf48c06deac31f3e90d3d8adeaf36'), 'transactionIndex': 99})
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
    client = EthEventsClient(EventClientType.CURVE_BEAN_3CRV_POOL)
    while True:
        events = client.get_new_logs(dry_run=False)
        time.sleep(5)

# For testing purposes.


def monitor_beanstalk_events():
    client = EthEventsClient(EventClientType.BEANSTALK)
    while True:
        events = client.get_new_logs(dry_run=True)
        time.sleep(5)


def monitor_betting_events():
    # client = EthEventsClient(EventClientType.BETTING)
    # while True:
    #     events = client.get_new_logs(dry_run=False)
    #     time.sleep(5)
    web3 = get_web3_instance()
    filter = safe_create_filter(web3,
        address=BETTING_ADMIN_ADDR,
        topics=[BETTING_SIGNATURES_LIST],
        # from_block=10581687, # Use this to search for old events. # Rinkeby
        # from_block=14205000, # Use this to search for old events. # Mainnet
        from_block=7931434,
        to_block='latest'
    )
    entries = filter.get_all_entries()
    for entry in entries:
        logging.warning(entry)

    client = RootClient(web3)
    client.get_total_supply()
    client.get_root_token_bdv()

    client = BettingClient(web3)
    logging.info(client.get_active_pools())


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)
    # monitor_uni_v2_pair_events()
    # monitor_beanstalk_events()
    # monitor_curve_pool_events()
    # bean_client = BeanClient()
    # bean_client.avg_bean_price()
    # curve_client = CurveClient()
    # print(curve_client.get_3crv_price())
    monitor_betting_events()

from abc import abstractmethod
import asyncio
from collections import OrderedDict
from enum import IntEnum
import logging
import json
import os
import time
import websockets

from web3 import Web3
from web3 import HTTPProvider
from web3 import exceptions as web3_exceptions
from web3.logs import DISCARD

from constants.addresses import *
from constants.config import *
from data_access.coin_gecko import get_token_price
import tools.util

from constants import dry_run_entries


# NOTE(funderberker): Pretty lame that we cannot automatically parse these from the ABI files.
#   Technically it seems very straight forward, but it is not implemented in the web3 lib and
#   parsing it manually is not any better than just writing it out here.


def add_event_to_dict(signature, sig_dict, sig_list):
    """Add both signature_hash and event_name to the bidirectional dict.

    Configure as a bijective map. Both directions will be added for each event type:
        - signature_hash:event_name
        - event_name:signature_hash
    """
    event_name = signature.split("(")[0]
    event_signature_hash = Web3.keccak(text=signature).hex()
    sig_dict[event_name] = event_signature_hash
    sig_dict[event_signature_hash] = event_name
    sig_list.append(event_signature_hash)
    # NOTE ERROR logging here silently breaks all logging. very cool python feature.
    # logging.info(f'event signature: {signature}  -  hash: {event_signature_hash}')


AQUIFER_EVENT_MAP = {}
AQUIFER_SIGNATURES_LIST = []
# IERC20 types will just be addresses.
add_event_to_dict(
    "BoreWell(address,address,address[],(address,bytes),(address,bytes)[],bytes)",  # IERC == address
    AQUIFER_EVENT_MAP,
    AQUIFER_SIGNATURES_LIST,
)


WELL_EVENT_MAP = {}
WELL_SIGNATURES_LIST = []
# IERC20 types will just be addresses.
add_event_to_dict(
    "Swap(address,address,uint256,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict("AddLiquidity(uint256[],uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)
add_event_to_dict(
    "RemoveLiquidity(uint256,uint256[],address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict(
    "RemoveLiquidityOneToken(uint256,address,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict("Shift(uint256[],address,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)
add_event_to_dict("Sync(uint256[],uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)


CURVE_POOL_EVENT_MAP = {}
CURVE_POOL_SIGNATURES_LIST = []
add_event_to_dict(
    "TokenExchange(address,int128,uint256,int128,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "TokenExchangeUnderlying(address,int128,uint256,int128,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "AddLiquidity(address,uint256[2],uint256[2],uint256,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidity(address,uint256[2],uint256[2],uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidityOne(address,uint256,uint256,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidityImbalance(address,uint256[2],uint256[2],uint256,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)

BEANSTALK_EVENT_MAP = {}
BEANSTALK_SIGNATURES_LIST = []
add_event_to_dict(
    "Sow(address,uint256,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict(
    "Harvest(address,uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
# Depositing an asset => AddDeposit()
# Withdrawing an asset => RemoveDeposit()
# Claiming an asset => RemoveWithdrawal()
# add_event_to_dict('RemoveDeposit(address,address,uint32,uint256)', # SILO V2
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict(
    "RemoveDeposit(address,address,int96,uint256,uint256)",  # SILO v3
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveDeposits(address,address,int96[],uint256[],uint256,uint256[])",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "AddDeposit(address,address,int96,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveWithdrawal(address,address,uint32,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveWithdrawals(address,address,uint32[],uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Convert(address,address,address,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
# add_event_to_dict('StalkBalanceChanged(address,int256,int256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict(
    "Chop(address,address,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict("Plant(address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict("Pick(address,address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# On Fertilizer contract.
add_event_to_dict(
    "ClaimFertilizer(uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)

# Season/sunrise events
SEASON_EVENT_MAP = {}
SEASON_SIGNATURES_LIST = []
add_event_to_dict(
    "Incentivization(address,uint256)",
    SEASON_EVENT_MAP,
    SEASON_SIGNATURES_LIST,
)

# Farmer's market events.
MARKET_EVENT_MAP = {}
MARKET_SIGNATURES_LIST = []
add_event_to_dict(
    "PodListingCreated(address,uint256,uint256,uint256,uint24,uint256,uint256,bytes,uint8,uint8)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodListingFilled(address,address,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodListingCancelled(address,uint256)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict(
    "PodOrderCreated(address,bytes32,uint256,uint24,uint256,uint256,bytes,uint8)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodOrderFilled(address,address,bytes32,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodOrderCancelled(address,bytes32)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)


# Barn Raise events.
FERTILIZER_EVENT_MAP = {}
FERTILIZER_SIGNATURES_LIST = []
add_event_to_dict(
    "TransferSingle(address,address,address,uint256,uint256)",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)
add_event_to_dict(
    "TransferBatch(address,address,address,uint256[],uint256[])",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)


def generate_sig_hash_map(sig_str_list):
    return {sig.split("(")[0]: Web3.keccak(text=sig).hex() for sig in sig_str_list}


# Silo Convert signature.
convert_function_sig_strs = ["convert(bytes,uint32[],uint256[])"]
convert_sigs = generate_sig_hash_map(convert_function_sig_strs)

# Method signatures. We handle some logs differently when derived from different methods.
# Silo conversion signatures.
silo_conversion_sig_strs = [
    "convertDepositedLP(uint256,uint256,uint32[],uint256[])",
    "convertDepositedBeans(uint256,uint256,uint32[],uint256[])",
]
silo_conversion_sigs = generate_sig_hash_map(silo_conversion_sig_strs)
# Signatures of methods with the explicit bean deposit (most txns include embedded deposit).
bean_deposit_sig_strs = [
    "depositBeans(uint256)",
    "buyAndDepositBeans(uint256,uint256)",
    "claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))",
    "claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))",
]
bean_deposit_sigs = generate_sig_hash_map(bean_deposit_sig_strs)
# Buy Fertilizer signature.
buy_fert_function_sig_strs = [
    "buyAndMint(uint256)",
    "mint(uint256)",
    "mintFertilizer(uint128,uint256,uint8)",
    "farm(bytes[])",
]
buy_fert_sigs = generate_sig_hash_map(buy_fert_function_sig_strs)

# Claim type signatures.
# claim_sigs = ['claim', 'claimAndUnwrapBeans', 'claimConvertAddAndDepositLP', 'claimAndSowBeans', 'claimBuyAndSowBeans', 'claimAndCreatePodOrder', 'claimAndFillPodListing', 'claimBuyBeansAndCreatePodOrder', 'claimBuyBeansAndFillPodListing', 'claimAddAndDepositLP', 'claimAndDepositBeans', 'claimAndDepositLP', 'claimAndWithdrawBeans', 'claimAndWithdrawLP', 'claimBuyAndDepositBeans']
claim_deposit_beans_sig_strs = [
    "claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool))",
    "claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool)))",
]
claim_deposit_beans_sigs = generate_sig_hash_map(claim_deposit_beans_sig_strs)

# Signatures of methods of interest for testing.
test_deposit_sig_strs = ["harvest(uint256[])", "updateSilo(address)"]
test_deposit_sigs = generate_sig_hash_map(test_deposit_sig_strs)

with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/erc20_abi.json")
) as erc20_abi_file:
    erc20_abi = json.load(erc20_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/aquifer_abi.json")
) as aquifer_abi_file:
    aquifer_abi = json.load(aquifer_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/well_abi.json")
) as well_abi_file:
    well_abi = json.load(well_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/curve_pool_abi.json")
) as curve_pool_abi_file:
    curve_pool_abi = json.load(curve_pool_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/beanstalk_abi.json")
) as beanstalk_abi_file:
    beanstalk_abi = json.load(beanstalk_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/beanstalk_abi_silo_v2.json")
) as beanstalk_abi_file_silo_v2:
    beanstalk_v2_abi = json.load(beanstalk_abi_file_silo_v2)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/bean_price_abi.json")
) as bean_price_abi_file:
    bean_price_abi = json.load(bean_price_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/fertilizer_abi.json")
) as fertilizer_abi_file:
    fertilizer_abi = json.load(fertilizer_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../constants/abi/eth_usd_oracle_abi.json")
) as eth_usd_oracle_abi_file:
    eth_usd_oracle_abi = json.load(eth_usd_oracle_abi_file)


def get_web3_instance():
    """Get an instance of web3 lib."""
    # # NOTE(funderberker): LOCAL TESTING (uses http due to local network constraints).
    # return Web3(HTTPProvider(LOCAL_TESTING_URL))
    # NOTE(funderberker): We are using websockets but we are not using any continuous watching
    # functionality. Monitoring is done through periodic get_new_events calls.
    # return Web3(WebsocketProvider(URL, websocket_timeout=60))
    return Web3(HTTPProvider(RPC_URL))


def get_well_contract(web3, address):
    """Get a web.eth.contract object for a well. Contract is not thread safe."""
    return web3.eth.contract(address=address, abi=well_abi)


def get_aquifer_contract(web3):
    """Get a web.eth.contract object for the aquifer. Contract is not thread safe."""
    return web3.eth.contract(address=AQUIFER_ADDR, abi=aquifer_abi)


def get_bean_3crv_pool_contract(web3):
    """Get a web.eth.contract object for the curve BEAN:3CRV pool. Contract is not thread safe."""
    return web3.eth.contract(address=CURVE_BEAN_3CRV_ADDR, abi=curve_pool_abi)


def get_curve_3pool_contract(web3):
    """Get a web.eth.contract object for a curve 3pool contract. Contract is not thread safe."""
    return web3.eth.contract(address=POOL_3POOL_ADDR, abi=curve_pool_abi)


def get_bean_contract(web3):
    """Get a web.eth.contract object for the Bean token contract. Contract is not thread safe."""
    return web3.eth.contract(address=BEAN_ADDR, abi=erc20_abi)


def get_unripe_contract(web3):
    """Get a web.eth.contract object for the unripe bean token. Contract is not thread safe."""
    return get_erc20_contract(web3, UNRIPE_ADDR)


def get_unripe_lp_contract(web3):
    """Get a web.eth.contract object for the unripe LP token. Contract is not thread safe."""
    return get_erc20_contract(web3, UNRIPE_LP_ADDR)


def get_beanstalk_contract(web3):
    """Get a web.eth.contract object for the Beanstalk contract. Contract is not thread safe."""
    return web3.eth.contract(address=BEANSTALK_ADDR, abi=beanstalk_abi)


def get_beanstalk_v2_contract(web3):
    """Get a web.eth.contract object for the Beanstalk contract ft Silo v2. Contract is not thread safe."""
    return web3.eth.contract(address=BEANSTALK_ADDR, abi=beanstalk_v2_abi)


def get_bean_price_contract(web3):
    """Get a web.eth.contract object for the Bean price oracle contract. Contract is not thread safe."""
    return web3.eth.contract(address=BEAN_PRICE_ORACLE_ADDR, abi=bean_price_abi)


def get_fertilizer_contract(web3):
    """Get a web.eth.contract object for the Barn Raise Fertilizer contract. Contract is not thread safe."""
    return web3.eth.contract(address=FERTILIZER_ADDR, abi=fertilizer_abi)


def get_eth_usd_oracle_contract(web3):
    """Get a web.eth.contract object for in-house eth usd price feed. Contract is not thread safe."""
    return web3.eth.contract(address=ETH_USD_ORACLE_ADDR, abi=eth_usd_oracle_abi)


def get_erc20_contract(web3, address):
    """Get a web3.eth.contract object for a standard ERC20 token contract."""
    # Ignore checksum requirement.
    address = web3.toChecksumAddress(address.lower())
    return web3.eth.contract(address=address, abi=erc20_abi)


class ChainClient:
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
        self.humidity_step_size = 0.5  # %
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
        return soil_to_float(self.get_weather()[0])
    
    def get_season_block(self):
        """Get the block in which the latest season started"""
        return call_contract_function_with_retry(self.contract.functions.sunriseBlock())

    def get_total_deposited_beans(self):
        """Get current total deposited Beans in the Silo."""
        return bean_to_float(
            call_contract_function_with_retry(self.contract.functions.totalDepositedBeans())
        )

    def get_total_deposited_uni_v2_bean_eth_lp(self):
        """Get current total deposited Uniswap V2 BEAN:ETH LP in the Silo."""
        return lp_to_float(
            call_contract_function_with_retry(self.contract.functions.totalDepositedLP())
        )

    def get_total_deposited(self, address, decimals):
        """Return the total deposited of the token at address as a float."""
        return token_to_float(
            call_contract_function_with_retry(self.contract.functions.getTotalDeposited(address)),
            decimals,
        )

    def get_underlying_token(self, unripe_token):
        """Return the address of the token that will be redeemed for a given unripe token."""
        return call_contract_function_with_retry(
            self.contract.functions.getUnderlyingToken(unripe_token)
        )

    def get_recap_funded_percent(self):
        """Return the % of target funds that have already been funded via fertilizer sales."""
        # Note that % recap is same for all unripe tokens.
        return token_to_float(
            call_contract_function_with_retry(
                self.contract.functions.getRecapFundedPercent(UNRIPE_LP_ADDR)
            ),
            6,
        )

    def get_remaining_recapitalization(self):
        """Return the USDC amount remaining to full capitalization."""
        return usdc_to_float(
            call_contract_function_with_retry(self.contract.functions.remainingRecapitalization())
        )

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

    def get_seeds(self, token, block_number='latest'):
        """Returns the current amount of Seeds awarded for depositing `token` in the silo."""
        token = Web3.to_checksum_address(token)
        token_settings = call_contract_function_with_retry(self.contract.functions.tokenSettings(token), block_number=block_number)
        return (token_settings[1] * 10000) / 10 ** STALK_DECIMALS

    def get_bdv(self, erc20_info, block_number='latest'):
        """Returns the current bdv `token`."""
        token = Web3.to_checksum_address(erc20_info.addr)
        bdv = call_contract_function_with_retry(self.contract.functions.bdv(token, 10 ** erc20_info.decimals), block_number=block_number)
        return bean_to_float(bdv)


class BeanClient(ChainClient):
    """Common functionality related to the Bean token."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.price_contract = get_bean_price_contract(self._web3)

    def get_price_info(self):
        """Get all pricing info from oracle.

        Pricing data is returned as an array. See abi for structure.
        """
        logging.info("Getting bean price...", exc_info=True)
        raw_price_info = call_contract_function_with_retry(self.price_contract.functions.price())
        return BeanClient.map_price_info(raw_price_info)

    @abstractmethod
    def map_price_info(raw_price_info):
        price_dict = {}
        price_dict["price"] = raw_price_info[0]
        price_dict["liquidity"] = raw_price_info[1]
        price_dict["delta_b"] = raw_price_info[2]
        price_dict["pool_infos"] = {}
        # Map address:pool_info for each supported pool.
        for pool_info in raw_price_info[3]:
            pool_dict = {}
            pool_dict["pool"] = pool_info[0]  # Address
            pool_dict["tokens"] = pool_info[1]
            pool_dict["balances"] = pool_info[2]
            # Bean price of pool (6 decimals)
            pool_dict["price"] = pool_info[3]
            # USD value of the liquidity in the pool
            pool_dict["liquidity"] = pool_info[4]
            pool_dict["delta_b"] = pool_info[5]
            pool_dict["lp_usd"] = pool_info[6]  # LP Token price in USD
            pool_dict["lp_bdv"] = pool_info[7]  # LP Token price in BDV
            price_dict["pool_infos"][pool_dict["pool"]] = pool_dict
        return price_dict

    def get_curve_lp_token_value(self, token_address, decimals, liquidity_long=None):
        """Return the $/LP token value of an LP token at address as a float."""
        if liquidity_long is None:
            try:
                liquidity_long = self.get_price_info()["pool_infos"][token_address]["liquidity"]
            # If the LP is not in the price aggregator, we do not know its value.
            except KeyError:
                return None
        liquidity_usd = token_to_float(liquidity_long, 6)
        token_supply = get_erc20_total_supply(token_address, decimals)
        return liquidity_usd / token_supply

    def avg_bean_price(self, price_info=None):
        """Current float bean price average across LPs from the Bean price oracle contract."""
        if price_info:
            price = price_info["price"]
        else:
            price = self.get_price_info()["price"]
        return bean_to_float(price)

    def total_delta_b(self, price_info=None):
        """Current deltaB across all pools."""
        if price_info:
            delta_b = price_info["delta_b"]
        else:
            delta_b = self.get_price_info()["delta_b"]
        return bean_to_float(delta_b)

    # def curve_3crv_price(self):
    #     """Current float 3CRV price from Bean:3CRV Pool."""
    #     pool_info = self.curve_bean_3crv_pool_info()
    #     return (pool_info['liquidity'] - pool_info['balances'][1] * pool_info['price']) / pool_info['balances'][0]

    # def curve_3crv_price(self):
    #     """Current 3CRV price in USD as float."""
    #     return get_token_price(TOKEN_3CRV_ADDR)

    def get_pool_info(self, addr):
        """Return pool info as dict. If addr is Bean addr, return all info."""
        price_info = self.get_price_info()
        if addr == BEAN_ADDR:
            return price_info
        else:
            return price_info["pool_infos"][addr]

    def curve_bean_3crv_pool_info(self):
        """Return pool info as dict."""
        return self.get_price_info()["pool_infos"][CURVE_BEAN_3CRV_ADDR]

    def curve_bean_3crv_bean_price(self):
        """Current float Bean price in the Curve Bean:3CRV pool."""
        return bean_to_float(self.curve_bean_3crv_pool_info()["price"])

    def curve_bean_3crv_lp_value(self):
        """Current float LP Token price of the Curve Bean:3CRV pool in USD."""
        return bean_to_float(self.curve_bean_3crv_pool_info()["lp_usd"])

    def well_bean_eth_pool_info(self):
        """Return pool info as dict."""
        return self.get_price_info()["pool_infos"][BEAN_ETH_WELL_ADDR]

    def well_bean_eth_bean_price(self):
        """Current float Bean price in the BEAN:ETH well."""
        return bean_to_float(self.well_bean_eth_pool_info()["price"])
    
    def well_bean_wsteth_pool_info(self):
        """Return pool info as dict."""
        return self.get_price_info()["pool_infos"][BEAN_WSTETH_WELL_ADDR]

    def well_bean_wsteth_bean_price(self):
        """Current float Bean price in the BEAN:wstETH well."""
        return bean_to_float(self.well_bean_wsteth_pool_info()["price"])


class WellClient(ChainClient):
    """Client for interacting with well contracts."""

    def __init__(self, address, web3=None):
        super().__init__(web3)
        self.address = address
        self.contract = get_well_contract(self._web3, address)

    def tokens(self, web3=None):
        """Returns a list of ERC20 tokens supported by the Well."""
        return call_contract_function_with_retry(self.contract.functions.tokens())


def get_tokens_sent(token, txn_hash, recipient, log_end_index):
    """Return the amount (as a float) of token sent in a transaction to the given recipient, prior to the provided log index"""
    logs = get_erc20_transfer_logs_in_txn(token, txn_hash, recipient, log_end_index)
    total_sum = 0
    for entry in logs:
        total_sum += int(entry.data, 16)
    return total_sum


def get_eth_sent(txn_hash, recipient, web3, log_end_index):
    """
    Return the amount (as a float) of ETH or WETH sent in a transaction to the given recipient, prior to the provided log index.
    If an aggregate value (ETH + WETH) is required, a specialized approach should be taken for the particular use case.
    This is because it is unclear who is the recipient of the ETH based on the .value property.
    """
    # Assumption is if WETH was sent, that any ETH from transaction.value would have already been wrapped and included
    logs = get_erc20_transfer_logs_in_txn(WRAPPED_ETH, txn_hash, recipient, log_end_index)
    total_sum = 0
    for entry in logs:
        total_sum += int(entry.data, 16)
    if total_sum != 0:
        return total_sum

    txn_value = web3.eth.get_transaction(txn_hash).value
    return txn_value


class CurveClient(ChainClient):
    """Client for interacting with standard curve pools."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_curve_3pool_contract(self._web3)

    # def get_3crv_price(self):
    #     return crv_to_float(call_contract_function_with_retry(self.contract.functions.get_virtual_price()))

    def get_3crv_price(self):
        """Current 3CRV price in USD as float."""
        return get_token_price(TOKEN_3CRV_ADDR)


class BarnRaiseClient(ChainClient):
    """Common functionality related to the Barn Raise Fertilizer contract."""

    def __init__(self, web3=None, beanstalk_client=None):
        super().__init__(web3)
        self.contract = get_fertilizer_contract(self._web3)
        # self.token_contract = get_fertilizer_token_contract(self._web3)
        # Set immutable variables.
        self.barn_raise_start = 1654516800  # seconds, epoch
        self.unpause_start = 1660564800  # seconds, epoch # August 15 2022, 12pm
        self.replant_season = 6074
        # self.pre_sale_humidity = 5000 / 10
        self.base_humidity = 2500 / 10
        self.step_size = 0.5  # %
        self.step_duration = 3600  # seconds
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
        return step_number + self.base_weather

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
class TxnPair:
    """The logs, in order, associated with a transaction."""

    txn_hash = ""
    logs = []

    def __init__(self, txn_hash, logs):
        self.txn_hash = txn_hash
        self.logs = logs


class EventClientType(IntEnum):
    BEANSTALK = 0
    SEASON = 1
    MARKET = 2
    BARN_RAISE = 3
    CURVE_BEAN_3CRV_POOL = 4
    WELL = 5
    AQUIFER = 6

class EthEventsClient:
    def __init__(self, event_client_type, address=""):
        # Track recently seen txns to avoid processing same txn multiple times.
        self._recent_processed_txns = OrderedDict()
        self._web3 = get_web3_instance()
        self._event_client_type = event_client_type
        if self._event_client_type == EventClientType.AQUIFER:
            self._contracts = [get_aquifer_contract(self._web3)]
            self._contract_addresses = [AQUIFER_ADDR]
            self._events_dict = AQUIFER_EVENT_MAP
            self._signature_list = AQUIFER_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.WELL:
            self._contracts = [get_well_contract(self._web3, address)]
            self._contract_addresses = [address]
            self._events_dict = WELL_EVENT_MAP
            self._signature_list = WELL_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.CURVE_BEAN_3CRV_POOL:
            self._contracts = [get_bean_3crv_pool_contract(self._web3)]
            self._contract_addresses = [CURVE_BEAN_3CRV_ADDR]
            self._events_dict = CURVE_POOL_EVENT_MAP
            self._signature_list = CURVE_POOL_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._contracts = [
                get_beanstalk_contract(self._web3),
                get_fertilizer_contract(self._web3),
            ]
            self._contract_addresses = [BEANSTALK_ADDR, FERTILIZER_ADDR]
            self._events_dict = BEANSTALK_EVENT_MAP
            self._signature_list = BEANSTALK_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.SEASON:
            self._contracts = [get_beanstalk_contract(self._web3)]
            self._contract_addresses = [BEANSTALK_ADDR]
            self._events_dict = SEASON_EVENT_MAP
            self._signature_list = SEASON_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.MARKET:
            self._contracts = [get_beanstalk_contract(self._web3)]
            self._contract_addresses = [BEANSTALK_ADDR]
            self._events_dict = MARKET_EVENT_MAP
            self._signature_list = MARKET_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.BARN_RAISE:
            self._contracts = [get_fertilizer_contract(self._web3)]
            self._contract_addresses = [FERTILIZER_ADDR]
            self._events_dict = FERTILIZER_EVENT_MAP
            self._signature_list = FERTILIZER_SIGNATURES_LIST
        else:
            raise ValueError("Unsupported event client type.")
        self._set_filters()

    def _set_filters(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filters = []
        for address in self._contract_addresses:
            self._event_filters.append(
                safe_create_filter(
                    self._web3,
                    address=address,
                    topics=[self._signature_list],
                    # from_block=10581687, # Use this to search for old events. # Rinkeby
                    # from_block=18722171,  # Use this to search for old events. # Mainnet
                    from_block="latest",
                    to_block="latest",
                )
            )

    def get_log_range(self, from_block, to_block="latest"):
        filters = []
        for address in self._contract_addresses:
            filters.append(
                safe_create_filter(
                    self._web3,
                    address=address,
                    topics=[self._signature_list],
                    from_block=from_block,
                    to_block=to_block,
                )
            )
        return self.get_new_logs(filters=filters, get_all=True)

    def get_new_logs(self, dry_run=None, filters=None, get_all=False):
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
        txn_hash_set = set()
        txn_logs_list = []

        if not dry_run:
            new_entries = []
            for filter in filters:
                new_entries.extend(self.safe_get_new_entries(filter, get_all=get_all))
        else:
            new_entries = get_test_entries(dry_run)
            time.sleep(3)

        # Track which unique logs have already been processed from this event batch.
        for entry in new_entries:
            # # This should only be triggered when pulling dry run test entries set directly since it
            # # will include entries from other contracts.
            # if entry.address != self._contract_address:
            #     continue
            # The event topic associated with this entry.
            if not dry_run:
                topic_hash = entry["topics"][0].hex()
                # Do not process topics outside of this classes topics of interest.
                if topic_hash not in self._events_dict:
                    logging.warning(
                        f"Unexpected topic ({topic_hash}) seen in "
                        f"{self._event_client_type.name} EthEventsClient"
                    )
                    continue

            # Print out entry.
            logging.info(f"{self._event_client_type.name} entry:\n{str(entry)}\n")

            # Do not process the same txn multiple times.
            txn_hash = entry["transactionHash"]
            if txn_hash in txn_hash_set:
                continue

            logging.info(f"{self._event_client_type.name} processing {txn_hash.hex()} logs.")

            # Retrieve the full txn and txn receipt.
            receipt = tools.util.get_txn_receipt_or_wait(self._web3, txn_hash)

            # If any removeDeposit events from Silo V2, ignore the entire txn. It is likely a migration.
            # This is a bit hacky, but none of this infrastructure was designed to manage implementations of
            # same event at same address.
            silo_v2_contract = get_beanstalk_v2_contract(self._web3)
            decoded_type_logs = silo_v2_contract.events["RemoveDeposit"]().processReceipt(
                receipt, errors=DISCARD
            )
            if len(decoded_type_logs) > 0:
                logging.warning("Skipping txn with Silo v2 RemoveDeposit")
                txn_hash_set.add(txn_hash)
                continue

            # Get and decode all logs of interest from the txn. There may be many logs.
            decoded_logs = []
            for signature in self._signature_list:
                for contract in self._contracts:
                    try:
                        decoded_type_logs = contract.events[
                            self._events_dict[signature]
                        ]().processReceipt(receipt, errors=DISCARD)
                    except web3_exceptions.ABIEventFunctionNotFound:
                        continue
                    decoded_logs.extend(decoded_type_logs)

            # Prune unrelated logs - logs that are of the same event types we watch, but are
            # not related to Beanstalk (i.e. swaps of non-Bean tokens).
            decoded_logs_copy = decoded_logs.copy()
            decoded_logs.clear()
            for log in decoded_logs_copy:
                # if log.event == 'Swap':
                #     # Only process uniswap swaps with the ETH:BEAN pool.
                #     if log.address != UNI_V2_BEAN_ETH_ADDR:
                #         continue
                if log.event == "TokenExchangeUnderlying" or log.event == "TokenExchange":
                    # Only process curve exchanges in supported BEAN pools.
                    if log.address not in [CURVE_BEAN_3CRV_ADDR]:
                        continue
                decoded_logs.append(log)

            # Add all remaining txn logs to log map.
            txn_hash_set.add(txn_hash)
            txn_logs_list.append(TxnPair(txn_hash, decoded_logs))
            logging.info(
                f"Transaction: {txn_hash}\nAll txn logs of interest:\n"
                f"{NEWLINE_CHAR.join([str(l) for l in decoded_logs])}"
            )

        return txn_logs_list

    def safe_get_new_entries(self, filter, get_all=False):
        """Retrieve all new entries that pass the filter.

        Returns one entry for every log that matches a filter. So if a single txn has multiple logs
        of interest this will return multiple entries.
        Catch any exceptions that may arise when attempting to connect to Infura.
        """
        logging.info(f"Checking for new {self._event_client_type.name} entries with " f"{filter}.")
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
                        logging.warning(
                            f"Ignoring txn that has already been processed ({entry.transactionHash})"
                        )
                # Add all new txn hashes to recent processed set/dict.
                for entry in new_unique_entries:
                    # Arbitrary value. Using this as a set.
                    self._recent_processed_txns[entry.transactionHash] = True
                # Keep the recent txn queue size within limit.
                for _ in range(max(0, len(self._recent_processed_txns) - TXN_MEMORY_SIZE_LIMIT)):
                    self._recent_processed_txns.popitem(last=False)
                return new_unique_entries
                # return filter.get_all_entries() # Use this to search for old events.
            except (
                ValueError,
                asyncio.TimeoutError,
                websockets.exceptions.ConnectionClosedError,
                Exception,
            ) as e:
                logging.warning(e, exc_info=True)
                logging.warning(
                    "filter.get_new_entries() (or .get_all_entries()) failed or timed out. Retrying..."
                )
                time.sleep(1)
                # Filters rely on server state and may be arbitrarily uninstalled by server.
                # https://github.com/ethereum/web3.py/issues/551
                # If we are failing too much recreate the filter.
                self._set_filters()
        logging.error("Failed to get new event entries. Passing.")
        return []


def safe_create_filter(web3, address, topics, from_block, to_block):
    """Create a filter but handle connection exceptions that web3 cannot manage."""
    max_tries = 15
    try_count = 0
    while try_count < max_tries:
        try:
            filter_params = {
                "topics": topics,
                "fromBlock": from_block,
                "toBlock": to_block
            }
            # Include the address in the filter params only if it is not None
            if address:
                filter_params["address"] = address
            return web3.eth.filter(filter_params)
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception("Failed to safely create filter")


def safe_get_block(web3, block_number="latest"):
    max_tries = 15
    try_count = 0
    while try_count < max_tries:
        try:
            return web3.eth.get_block(block_number)
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception("Failed to safely get block")


def get_erc20_total_supply(addr, decimals, web3=None):
    """Get the total supply of ERC-20 token in circulation as float."""
    if not web3:
        web3 = get_web3_instance()
    contract = get_erc20_contract(web3, address=addr)
    return token_to_float(
        call_contract_function_with_retry(contract.functions.totalSupply()), decimals
    )


class Erc20Info:
    def __init__(self, addr, name, symbol, decimals):
        self.addr = addr
        self.name = name
        self.symbol = symbol
        self.decimals = decimals

    def parse(self):
        return (self.addr, self.name, self.symbol, self.decimals)


# Global cache for erc20 info that is static.
erc20_info_cache = {}


def get_erc20_info(addr, web3=None):
    """Get the name, symbol, and decimals of an ERC-20 token."""
    addr = addr.lower()
    if addr not in erc20_info_cache:
        logging.info(f"Querying chain for erc20 token info of {addr}.")
        if not web3:
            web3 = get_web3_instance()
        # addr = web3.toChecksumAddress(addr)
        contract = get_erc20_contract(web3, address=addr)
        name = call_contract_function_with_retry(contract.functions.name())
        # Use custom in-house Beanstalk Symbol name, if set, otherwise default to on-chain symbol.
        symbol = TOKEN_SYMBOL_MAP.get(addr) or call_contract_function_with_retry(
            contract.functions.symbol()
        )
        decimals = call_contract_function_with_retry(contract.functions.decimals())
        erc20_info_cache[addr] = Erc20Info(addr, name, symbol, decimals)
    return erc20_info_cache[addr]


def get_constant_product_well_lp_bdv(addr, web3=None):
    """Get the float bdv of 1 LP token in constant product well at addr. Must contain Bean."""
    if not web3:
        web3 = get_web3_instance()
    well_contract = get_well_contract(web3, addr)
    total_supply = token_to_float(
        call_contract_function_with_retry(well_contract.functions.totalSupply()), WELL_LP_DECIMALS
    )
    bean_contract = get_bean_contract(web3)
    total_bdv = 2 * token_to_float(
        call_contract_function_with_retry(bean_contract.functions.balanceOf(addr)), BEAN_DECIMALS
    )
    return total_bdv / total_supply


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
    return entry["transactionHash"].hex() + entry["topics"][0].hex()


def call_contract_function_with_retry(function, max_tries=10, block_number='latest'):
    """Try to call a web3 contract object function and retry with exponential backoff."""
    try_count = 1
    while True:
        try:
            return function.call(block_identifier=block_number)
        except Exception as e:
            if try_count < max_tries:
                try_count += 1
                time.sleep(0.5)
                continue
            else:
                logging.error(
                    f'Failed to access "{function.fn_name}" function at contract address "{function.address}" after {max_tries} attempts. Raising exception...'
                )
                raise (e)


def get_erc20_transfer_logs_in_txn(token, txn_hash, recipient, log_end_index, web3=None):
    """Return all logs matching transfer signature to the recipient before the end index."""
    if not web3:
        web3 = get_web3_instance()
    receipt = tools.util.get_txn_receipt_or_wait(web3, txn_hash)
    retval = []
    for log in receipt.logs:
        if log.logIndex >= log_end_index:
            break
        try:
            if log.address == token and log.topics[0].hex() == ERC20_TRANSFER_EVENT_SIG and topic_is_address(log.topics[2], recipient):
                retval.append(log)
        # Ignore anonymous events (logs without topics).
        except IndexError:
            pass
    return retval


# Compares a topic (which has leading zeros) with an ethereum address
def topic_is_address(topic, address):
    return "0x" + topic.hex().lstrip("0x").zfill(40) == address.lower()


def token_to_float(token_long, decimals):
    if not token_long:
        return 0
    return int(token_long) / (10**decimals)


def eth_to_float(gwei):
    return token_to_float(gwei, ETH_DECIMALS)


def lp_to_float(lp_long):
    return token_to_float(lp_long, LP_DECIMALS)


def bean_to_float(bean_long):
    return token_to_float(bean_long, BEAN_DECIMALS)


def soil_to_float(soil_long):
    return token_to_float(soil_long, SOIL_DECIMALS)


def stalk_to_float(stalk_long):
    return token_to_float(stalk_long, STALK_DECIMALS)


def seeds_to_float(seeds_long):
    return token_to_float(seeds_long, SEED_DECIMALS)


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


def get_test_entries(dry_run=None):
    """Get a list of onchain transaction entries to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes

    time.sleep(1)

    if dry_run:
        if dry_run[0] == 'all':
            return dry_run_entries.entries
        else:
            entries = []
            for i in range(len(dry_run)):
                entries.append(AttributeDict({"transactionHash": HexBytes(dry_run[i])}))
            return entries



# For testing purposes.


def monitor_curve_pool_events():
    client = EthEventsClient(EventClientType.CURVE_BEAN_3CRV_POOL)
    while True:
        events = client.get_new_logs(dry_run=None)
        time.sleep(5)


# For testing purposes.


def monitor_beanstalk_events():
    client = EthEventsClient(EventClientType.BEANSTALK)
    while True:
        events = client.get_new_logs(dry_run=None)
        time.sleep(5)

if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)
    bs = BeanstalkClient()
    logging.info(f"bean seeds {bs.get_seeds(BEAN_ADDR)}")
    logging.info(f"season block {bs.get_season_block()}")
    client = EthEventsClient(EventClientType.SEASON)
    events = client.get_log_range(20566115, 20566115)
    logging.info(f"found txn: {events[0].txn_hash.hex()}")
    logging.info(f"lp bdv {bs.get_bdv(get_erc20_info(BEAN_WSTETH_WELL_ADDR), 20566115)}")

    # monitor_beanstalk_events()
    # monitor_curve_pool_events()
    # bean_client = BeanClient()
    # bean_client.avg_bean_price()
    # curve_client = CurveClient()
    # print(curve_client.get_3crv_price())

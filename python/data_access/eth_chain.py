import asyncio
import datetime
from enum import Enum
import logging
import json
import os
import time
from discord.ext.commands.errors import ArgumentParsingError

from web3 import Web3, WebsocketProvider
from web3.logs import DISCARD

API_KEY = os.environ['ETH_CHAIN_API_KEY']
URL = 'wss://mainnet.infura.io/ws/v3/' + API_KEY

# Decimals for conversion from chain int values to float decimal values.
ETH_DECIMALS = 18
LP_DECIMALS = 18
BEAN_DECIMALS = 6
DAI_DECIMALS = 18
USDC_DECIMALS = 6
USDT_DECIMALS = 6
CRV_DECIMALS = 18

POOL_FEE = 0.003 # %

# BEAN_TOKEN_ADDR = '0xDC59ac4FeFa32293A95889Dc396682858d52e5Db'
ETH_BEAN_POOL_ADDR = '0x87898263B6C5BABe34b4ec53F22d98430b91e371'
ETH_USDC_POOL_ADDR = '0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc'
BEANSTALK_ADDR = '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5'
BEAN_3CRV_POOL_ADDR = '0x3a70DfA7d2262988064A2D051dd47521E43c9BdD'

# Indices of tokens in Curve factory pool [bean, 3crv].
FACTORY_INDEX_BEAN = 0
FACTORY_INDEX_3CRV = 1

# Indices of underlying tokens in Curve factory pool [bean, dai, usdc, usdt].
FACTORY_UNDERLYING_INDEX_BEAN = 0
FACTORY_UNDERLYING_INDEX_DAI = 1
FACTORY_UNDERLYING_INDEX_USDC = 2
FACTORY_UNDERLYING_INDEX_USDT = 3


# Newline character to get around limits of f-strings.
NEWLINE_CHAR = '\n'

# NOTE(funderberker): Pretty lame that we cannot automatically parse these from the ABI files.
#   Technically it seems very straight forward, but it is not implemented in the web3 lib and
#   parsing it manually is not any better than just writing it out here.
def add_event_to_dict(signature, sig_dict, sig_list):
    """Add both signature_hash and event_name to the bidirectional dict.
    
    Configure as a bijective map. Both directions will be added for each event type:
        - signature_hash:event_name
        - event_name:signature_hash
    """
    event_name =  signature.split('(')[0]
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

# Method signatures. We handle some logs differently when derived from different methods.
# Silo conversion signatures.
silo_conversion_sigs = ['convertDepositedLP(uint256,uint256,uint32[],uint256[])',
                        'convertDepositedBeans(uint256,uint256,uint32[],uint256[])']
silo_conversion_sigs = {sig.split('(')[0]:Web3.keccak(text=sig).hex() for sig in silo_conversion_sigs}
# Signatures of methods with the explicit bean deposit (most txns include embedded deposit).
bean_deposit_sigs = ['depositBeans(uint256)',
                     'buyAndDepositBeans(uint256,uint256)',
                     'claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))',
                     'claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))']
bean_deposit_sigs = {sig.split('(')[0]:Web3.keccak(text=sig).hex() for sig in bean_deposit_sigs}

with open(os.path.join(os.path.dirname(__file__),
                       '../../contracts/ethereum/IUniswapV2Pair.json')) as uniswap_pool_abi_file:
    uniswap_pool_abi = json.load(uniswap_pool_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../../contracts/ethereum/curve_pool_abi.json')) as curve_pool_abi_file:
    curve_pool_abi = json.load(curve_pool_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../../contracts/ethereum/beanstalk_abi.json')) as beanstalk_abi_file:
    beanstalk_abi = json.load(beanstalk_abi_file)


def get_eth_bean_pool_contract(web3):
    """Get a web.eth.contract object for the ETH:BEAN pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=ETH_BEAN_POOL_ADDR, abi=uniswap_pool_abi)


def get_eth_usdc_pool_contract(web3):
    """Get a web.eth.contract object for the ETH:USDC pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=ETH_USDC_POOL_ADDR, abi=uniswap_pool_abi)


def get_bean_3crv_pool_contract(web3):
    """Get a web.eth.contract object for the curve BEAN:3CRV pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEAN_3CRV_POOL_ADDR, abi=curve_pool_abi)


def get_beanstalk_contract(web3):
    """Get a web.eth.contract object for the Beanstalk contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEANSTALK_ADDR, abi=beanstalk_abi)


class UniswapClient():
    def __init__(self):
        self._web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))
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

    def current_eth_and_bean_price(self):
        reserve0, reserve1, last_swap_block_time = self.eth_bean_pool_contract.functions.getReserves().call()
        eth_reserves = eth_to_float(reserve0)
        bean_reserves = bean_to_float(reserve1)
        eth_price = self.current_eth_price()
        bean_price = eth_price * eth_reserves / bean_reserves
        logging.info(f'Current bean price: {bean_price} (last ETH:BEAN txn block time: '
                     f'{datetime.datetime.fromtimestamp(last_swap_block_time).strftime("%c")})')
        return eth_price, bean_price

    def current_bean_price(self):
        _, bean_price = self.current_eth_and_bean_price()
        return bean_price

class CurveClient():
    def __init__(self):
        self._web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))
        self.bean_3crv_contract = get_bean_3crv_pool_contract(self._web3)

    def bean_twap(self):
        # NOTE(funderberker): These calcs do not work. Staying with Uniswap price for now.
        
        # Unknown time window for TWAP. This calculation shows bean price to be $0.55, so something must be off in calculation logic.
        bean_balance, crv_balance = self.bean_3crv_contract.functions.get_price_cumulative_last().call()
        bean_balance = bean_to_float(bean_balance)
        crv_balance = crv_to_float(crv_balance)
        # Balances are not held equal in curve factory pools, so cannot calculate direct from reserves.
        # bean_balance = bean_to_float(self.bean_3crv_contract.functions.balances(FACTORY_INDEX_BEAN).call())
        # crv_balance = crv_to_float(self.bean_3crv_contract.functions.balances(FACTORY_INDEX_3CRV).call())
        logging.info(f'crv bean price:   {crv_balance / bean_balance}')
        return bean_balance / crv_balance


def avg_eth_to_bean_swap_price(eth_in, bean_out, eth_price):
    """Returns the $/bean cost for a swap txn using the $/ETH price and approximate fee."""
    # Approximate fee by reducing input amount by pool fee %.
    eth_in = eth_in * (1 - POOL_FEE)
    return eth_price * (eth_in / bean_out)


def avg_bean_to_eth_swap_price(bean_in, eth_out, eth_price):
    """Returns the $/bean cost for a swap txn using the $/ETH price and approximate fee."""
    # Approximate fee by reducing input amount by pool fee %.
    bean_in = bean_in * (1 - POOL_FEE)
    return eth_price * (eth_out / bean_in)


def eth_to_float(gwei):
    if not gwei:
        return 0
    return int(gwei) / (10 ** ETH_DECIMALS)


def lp_to_float(lp_long):
    if not lp_long:
        return 0
    return int(lp_long) / (10 ** LP_DECIMALS)

def bean_to_float(bean_long):
    if not bean_long:
        return 0
    return int(bean_long) / (10 ** BEAN_DECIMALS)


def dai_to_float(dai_long):
    if not dai_long:
        return 0
    return int(dai_long) / (10 ** DAI_DECIMALS)


def usdc_to_float(usdc_long):
    if not usdc_long:
        return 0
    return int(usdc_long) / (10 ** USDC_DECIMALS)


def usdt_to_float(usdt_long):
    if not usdt_long:
        return 0
    return int(usdt_long) / (10 ** USDT_DECIMALS)

def crv_to_float(crv_long):
    if not crv_long:
        return 0
    return int(crv_long) / (10 ** CRV_DECIMALS)


class EventClientType(Enum):
    UNISWAP_POOL = 0
    CURVE_POOL = 1
    BEANSTALK = 2


class EthEventsClient():
    def __init__(self, event_client_type):
        self._web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))
        self._event_client_type = event_client_type
        if self._event_client_type == EventClientType.UNISWAP_POOL:
            self._contract = get_eth_bean_pool_contract(self._web3)
            self._contract_address = ETH_BEAN_POOL_ADDR
            self._events_dict = UNISWAP_POOL_EVENT_MAP
            self._signature_list = UNISWAP_POOL_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.CURVE_POOL:
            self._contract = get_bean_3crv_pool_contract(self._web3)
            self._contract_address = BEAN_3CRV_POOL_ADDR
            self._events_dict = CURVE_POOL_EVENT_MAP
            self._signature_list = CURVE_POOL_SIGNATURES_LIST
            self._set_filter()
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._contract = get_beanstalk_contract(self._web3)
            self._contract_address = BEANSTALK_ADDR
            self._events_dict = BEANSTALK_EVENT_MAP
            self._signature_list = BEANSTALK_SIGNATURES_LIST
            self._set_filter()
        else:
            raise ValueError("Illegal event client type.")

    def _set_filter(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filter = self._web3.eth.filter({
            "address": self._contract_address,
            "topics": [self._signature_list],
            # "fromBlock": 'latest',
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
            # The event topic associated with this entry.
            topic_hash = entry['topics'][0].hex()

            # Do not process topics outside of this classes topics of interest.
            if topic_hash not in self._events_dict:
                if not dry_run:
                    logging.warning(f'Unexpected topic ({topic_hash}) seen in '
                                    f'{self._event_client_type.name} EthEventsClient')
                else:
                    logging.info(f'Ignoring unexpected topic ({topic_hash}) from dry run data.')
                continue

            # Print out entry.
            logging.info(f'{self._event_client_type.name} entry:\n{str(entry)}\n')

            # Do not process the same txn multiple times.
            txn_hash = entry['transactionHash']
            if txn_hash in txn_logs_dict:
                continue

            logging.info(f'{self._event_client_type.name} processing {txn_hash.hex()} logs.')

            # Retrieve the full txn and txn receipt.
            receipt = self._web3.eth.get_transaction_receipt(txn_hash)
            
            # Get and decode all logs of interest from the txn. There may be many logs.
            decoded_logs = []
            for signature in self._signature_list:
                decoded_logs.extend(self._contract.events[
                    self._events_dict[signature]]().processReceipt(receipt, errors=DISCARD))
            print(decoded_logs)

            # Prune unrelated logs.
            decoded_logs_copy = decoded_logs.copy()
            decoded_logs.clear()
            for log in decoded_logs_copy:
                if log.event == 'Swap':
                    # Only process uniswap swaps with the ETH:BEAN pool.
                    if log.address != ETH_BEAN_POOL_ADDR:
                        continue
                elif log.event == 'TokenExchangeUnderlying' or log.event == 'TokenExchange':
                    # Only process curve exchanges in the BEAN:3CRV pool.
                    if log.address != BEAN_3CRV_POOL_ADDR:
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
            f'Checking for new {self._event_client_type.name} entries with ' \
            f'filter {self._event_filter}.')
        try_count = 0
        while try_count < 5:
            try_count += 1
            try:
                return filter.get_new_entries()
                # return filter.get_all_entries()
            except (ValueError, asyncio.TimeoutError, Exception) as e:
                logging.exception(e)
                logging.info(
                    'filter.get_new_entries() failed or timed out. Retrying...')
                time.sleep(1)
        # Filters rely on server state and may be arbitrarily uninstalled by server.
        # https://github.com/ethereum/web3.py/issues/551
        # If we are failing too much recreate the filter.
        self._set_filter()
        logging.error('Failed to get new event entries. Passing.')
        return []


def is_valid_wallet_address(address):
    """Return True is address is a valid ETH address. Else False."""
    if not Web3.isAddress(address):
        return False
    return True

def txn_topic_combo_id(entry):
    """Return a unique string identifying this transaction and topic combo."""
    return entry['transactionHash'].hex() + entry['topics'][0].hex()


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
        AttributeDict({'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x20162ea3724564603cb7d1f6d77f0f8760d10b1888f2b4f0a5817694f0aa4cd5'), 'blockNumber': 13817843, 'data': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000036d4669d00000000000000000000000000000000000000000000000002eeb669620f72bfe0000000000000000000000000000000000000000000000000000000000000000',
                      'logIndex': 66, 'removed': False, 'topics': [HexBytes('0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d'), HexBytes('0x0000000000000000000000007a250d5630b4cf539739df2c5dacb4c659f2488d')], 'transactionHash': HexBytes('0x3df8be86781d177f7a554bea6fdc79bfe5385f0a04f5a59255e65656093182d8'), 'transactionIndex': 57}),
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
                      'logIndex': 77, 'removed': False, 'topics': [HexBytes('0xd013ca23e77a65003c2c659c5442c00c805371b7fc1ebd4c206c41d1536bd90b'), HexBytes('0x0000000000000000000000000000000000007f150bd6f54c40a34d7c3d5e9f56')], 'transactionHash': HexBytes('0x2076ddf03449a024290c4123ad69bde5fb2629770ea76577fb59574b359859ba'), 'transactionIndex': 8})
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
    client = EthEventsClient(EventClientType.CURVE_POOL)
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
    logging.basicConfig(format='ETH Chain : %(levelname)s : %(asctime)s : %(message)s',
                        level=logging.INFO)
    # monitor_uni_v2_pair_events()
    # monitor_beanstalk_events()
    monitor_curve_pool_events()

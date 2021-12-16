import asyncio
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
USDC_DECIMALS = 6

# BEAN_TOKEN_ADDR = '0xDC59ac4FeFa32293A95889Dc396682858d52e5Db'
ETH_BEAN_POOL_ADDR = '0x87898263B6C5BABe34b4ec53F22d98430b91e371'
ETH_USDC_POOL_ADDR = '0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc'
BEANSTALK_ADDR = '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5'

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


POOL_EVENT_MAP = {}
POOL_SIGNATURES_LIST = []
add_event_to_dict('Mint(address,uint256,uint256)',
                  POOL_EVENT_MAP, POOL_SIGNATURES_LIST)
add_event_to_dict('Burn(address,uint256,uint256,address)',
                  POOL_EVENT_MAP, POOL_SIGNATURES_LIST)
add_event_to_dict('Swap(address,uint256,uint256,uint256,uint256,address)',
                  POOL_EVENT_MAP, POOL_SIGNATURES_LIST)

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
# add_event_to_dict('BeanRemove(address,uint32[],uint256[],uint256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# add_event_to_dict('LPRemove(address,uint32[],uint256[],uint256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('BeanWithdraw(address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict('LPWithdraw(address,uint256,uint256)',
                  BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)


with open(os.path.join(os.path.dirname(__file__),
                       '../../contracts/ethereum/IUniswapV2Pair.json')) as pool_abi_file:
    pool_abi = json.load(pool_abi_file)
with open(os.path.join(os.path.dirname(__file__),
                       '../../contracts/ethereum/beanstalk_abi.json')) as beanstalk_abi_file:
    beanstalk_abi = json.load(beanstalk_abi_file)


def get_eth_bean_pool_contract(web3):
    """Get a web.eth.contract object for the ETH:BEAN pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=ETH_BEAN_POOL_ADDR, abi=pool_abi)


def get_eth_usdc_pool_contract(web3):
    """Get a web.eth.contract object for the ETH:USDC pool. Contract is not thread safe."""
    return web3.eth.contract(
        address=ETH_USDC_POOL_ADDR, abi=pool_abi)


def get_beanstalk_contract(web3):
    """Get a web.eth.contract object for the Beanstalk contract. Contract is not thread safe."""
    return web3.eth.contract(
        address=BEANSTALK_ADDR, abi=beanstalk_abi)


class BlockchainClient():
    def __init__(self):
        self._web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))
        self.eth_usdc_pool_contract = get_eth_usdc_pool_contract(self._web3)
        self.eth_bean_pool_contract = get_eth_bean_pool_contract(self._web3)

    def current_eth_price(self):
        reserve0, reserve1, _ = self.eth_usdc_pool_contract.functions.getReserves().call()
        eth_reserves = eth_to_float(reserve1)
        usdc_reserves = usdc_to_float(reserve0)
        eth_price = usdc_reserves / eth_reserves
        logging.info('Current ETH Price: ' + str(eth_price))
        return eth_price

    def current_eth_and_bean_price(self):
        reserve0, reserve1, _ = self.eth_bean_pool_contract.functions.getReserves().call()
        eth_reserves = eth_to_float(reserve0)
        bean_reserves = bean_to_float(reserve1)
        eth_price = self.current_eth_price()
        bean_price = eth_price * eth_reserves / bean_reserves
        logging.info('Current bean price: ' + str(bean_price))
        return eth_price, bean_price

    def current_bean_price(self):
        _, bean_price = self.current_eth_and_bean_price()
        return bean_price

    def avg_swap_price(self, eth, beans, eth_price=None):
        """Returns the $/bean cost for a swap txn using the $/ETH price."""
        if not eth_price:
            eth_price = self.current_eth_price()
        return eth_price * (eth / beans)


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


def usdc_to_float(usdc_long):
    if not usdc_long:
        return 0
    return int(usdc_long) / (10 ** USDC_DECIMALS)



class EventClientType(Enum):
    POOL = 0
    BEANSTALK = 1


class EthEventsClient():
    def __init__(self, event_client_type):
        self._web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))
        self._event_client_type = event_client_type
        if self._event_client_type == EventClientType.POOL:
            self._contract = get_eth_bean_pool_contract(self._web3)
            self._events_dict = POOL_EVENT_MAP
            self._set_filter()
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._contract = get_beanstalk_contract(self._web3)
            self._events_dict = BEANSTALK_EVENT_MAP
            self._set_filter()
        else:
            raise ValueError("Illegal event client type.")

    def _set_filter(self):
        """This is located in a method so it can be reset on the fly."""
        if self._event_client_type == EventClientType.POOL:
            self._event_filter = self._web3.eth.filter({
                "address": ETH_BEAN_POOL_ADDR,
                "topics": [POOL_SIGNATURES_LIST],
                # "fromBlock": 'latest',
                "toBlock": 'latest'
                })
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._event_filter = self._web3.eth.filter({
                "address": BEANSTALK_ADDR,
                "topics": [BEANSTALK_SIGNATURES_LIST],
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
        # All decoded logs of interest from all txn+topic combos.
        logs_of_interest = []
        # Keep track of which txn/topic combos have already been processed. 
        seen_txn_topic_combos = set()

        if not dry_run:
            new_entries = self.safe_get_new_entries(self._event_filter)
        else:
            new_entries = get_test_entries()
            time.sleep(3)
            
        # Track which unique logs have already been processed from this event batch.
        for entry in new_entries:
            # The topic associated with this entry.
            topic_hash = entry['topics'][0].hex()

            # Do not process topics outside of this classes topics of interest.
            if topic_hash not in self._events_dict:
                logging.warning(f'Unexpected topic ({topic_hash}) seen in '
                                f'{self._event_client_type.name} EthEventsClient')
                continue

            logging.info(f'{self._event_client_type.name} entry:\n{str(entry)}\n')

            # Do not process the same txn + topic combo multiple times.
            if txn_topic_combo_id(entry) in seen_txn_topic_combos:
                continue
            seen_txn_topic_combos.add(txn_topic_combo_id(entry))

            # Retrieve the full txn receipt.
            receipt = self._web3.eth.get_transaction_receipt(entry['transactionHash'])
            
            # Get and decode all logs with given topic for the txn. There may be multiple logs
            # of interest in this txn+topic combo.
            decoded_logs = self._contract.events[self._events_dict[topic_hash]]().processReceipt(
                receipt, errors=DISCARD)
            
            logging.info(f'Decoded {self._events_dict[topic_hash]} logs from '
                         f'{entry["transactionHash"].hex()}:\n{str(decoded_logs)}\n')
            
            # Iterate through all txn+topic logs and add all logs that we are interested in.
            combo_logs_of_interest = []
            for log in decoded_logs:
                # Only process Swaps with the ETH:BEAN pool.
                if log.event == 'Swap' and log.address == ETH_BEAN_POOL_ADDR:
                    combo_logs_of_interest.append(log)
                elif log.event == self._events_dict[topic_hash]:
                    combo_logs_of_interest.append(log)
            # Expect at least one log of interest for each combo.
            if not combo_logs_of_interest:
                logging.error(f'No logs of interest found for:\n{txn_topic_combo_id(entry)}\n')
            logs_of_interest.extend(combo_logs_of_interest)

        return logs_of_interest

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

def txn_topic_combo_id(entry):
    """Return a unique string identifying this transaction and topic combo."""
    return entry['transactionHash'].hex() + entry['topics'][0].hex()

def maybe_get_test_logs(odds=1.0):
    """Get a list of old decoded logs to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes
    import random
    events = [
        AttributeDict({'args': AttributeDict({'sender': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'to': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'amount0In': 1461909585474928331, 'amount1In': 0, 'amount0Out': 0, 'amount1Out': 6603011113}), 'event': 'Swap', 'logIndex': 343, 'transactionIndex': 227,
                      'transactionHash': HexBytes('0xa23b6157fe6c16d31a486222e50c635d10c43db97c358869770adeeeb91fc3b5'), 'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x9d7072892b16e1c850ac1a6e32f7ae04579174e418c94e231d9b5d7b5f3b29aa'), 'blockNumber': 13722265}),
        AttributeDict({'args': AttributeDict({'sender': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'to': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'amount0In': 0, 'amount1In': 152620722880, 'amount0Out': 32933918030233354308, 'amount1Out': 0}), 'event': 'Swap', 'logIndex': 79, 'transactionIndex': 58,
                      'transactionHash': HexBytes('0x7a0cd2269e3a7c3def3cf3184dcdafcef9274078236ae840d20880cf79583b29'), 'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xb7447a69c5c193b046c0363cbf9898c424285a3ea0d3ebe1a1bc03776fda7b43'), 'blockNumber': 13722372}),
        AttributeDict({'args': AttributeDict({'sender': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'amount0': 32933918029946007630, 'amount1': 155379277120}), 'event': 'Mint', 'logIndex': 84, 'transactionIndex': 58, 'transactionHash': HexBytes(
            '0x7a0cd2269e3a7c3def3cf3184dcdafcef9274078236ae840d20880cf79583b29'), 'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xb7447a69c5c193b046c0363cbf9898c424285a3ea0d3ebe1a1bc03776fda7b43'), 'blockNumber': 13722372}),
        AttributeDict({'args': AttributeDict({'account': '0xBAe7A9B7Df36365Cb17004FD2372405773273a68', 'season': 2934, 'beans': 308825177}), 'event': 'BeanDeposit', 'logIndex': 111, 'transactionIndex': 104, 'transactionHash': HexBytes(
            '0xcf4cd0fbe114132da7006efbcf9a70c8df9751b73493a949561d78676cd21b3c'), 'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x1a1da81fe78ce946c333095eec9f52d18e67aae855d246843d2d09684e6a8b2b'), 'blockNumber': 13759594}),
        AttributeDict({'args': AttributeDict({'account': '0x25CFB95e1D64e271c1EdACc12B4C9032E2824905', 'crates': [2935, 2754], 'crateBeans': [818912179, 381087821], 'beans': 1200000000}), 'event': 'BeanRemove', 'logIndex': 360, 'transactionIndex': 248, 'transactionHash': HexBytes(
            '0xa6aeb32213fb61e4417622a4183584766abd5fc118e851eb506cd48b401e9e1e'), 'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x74e1a3d8fc1fda3b834e6b2e27c1d612520f7119d2f72be604494eac39800bd4'), 'blockNumber': 13759909}),
        AttributeDict({'args': AttributeDict({'account': '0x25CFB95e1D64e271c1EdACc12B4C9032E2824905', 'season': 2960, 'beans': 1200000000}), 'event': 'BeanWithdraw', 'logIndex': 361, 'transactionIndex': 248, 'transactionHash': HexBytes(
            '0xa6aeb32213fb61e4417622a4183584766abd5fc118e851eb506cd48b401e9e1e'), 'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x74e1a3d8fc1fda3b834e6b2e27c1d612520f7119d2f72be604494eac39800bd4'), 'blockNumber': 13759909}),
        AttributeDict({'args': AttributeDict({'account': '0x15884aBb6c5a8908294f25eDf22B723bAB36934F', 'withdrawals': [2983], 'lp': 343343500000000}), 'event': 'LPClaim', 'logIndex': 210, 'transactionIndex': 119, 'transactionHash': HexBytes(
            '0xf1ef8aeee45b44468393638356d9fccc0ff3b7cee169e6784969e7c0cdcf86a6'), 'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xa877eb7ab22366a8abcbf974da5069c4db03ec80df7f503435b42021877d9222'), 'blockNumber': 13772704}),
        AttributeDict({'args': AttributeDict({'account': '0x374E518f85aB75c116905Fc69f7e0dC9f0E2350C', 'crates': [1110], 'crateLP': [25560533590528], 'lp': 25560533590528}), 'event': 'LPRemove', 'logIndex': 472, 'transactionIndex': 208, 'transactionHash': HexBytes(
            '0xc35157e0ba17e7a3ea966f33f36a84dd14516e7542870add0061f377910d7533'), 'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x0a21f0179867a9d979b6654943dd88a0f92892b50ba927282c5127a09fc9bdb9'), 'blockNumber': 13777911})
    ]
    if random.randint(1, int(10/odds)) <= 10:
        return events
    else:
        return []

def get_test_entries():
    """Get a list of old encoded entries to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes
    time.sleep(1)
    entries = [
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0x9ec4bb0665ea05462c94c6482051d656f0d8d9f087acc9f835b4ee26f4944f9e'), 'blockNumber': 13816727, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c4c0000000000000000000000000000000000000000000000000000000000168678',
                      'logIndex': 698, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x000000000000000000000000821acf4602b9d57da21dee0c3db45e71143c0b45')], 'transactionHash': HexBytes('0xf9665147a5d4f518b71c6f1239a84b5db3aaac980d5992a075e45249959bf1de'), 'transactionIndex': 158}),
        AttributeDict({'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xe4a69dd4c21d6eb38328fe3e2bbf3df77e889489aceb53860809fbaa726e721c'), 'blockNumber': 13816750, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c4c0000000000000000000000000000000000000000000000000000000004f2ca26',
                      'logIndex': 25, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x000000000000000000000000414a26eaa23583715d71b3294f0bf5eabdd2eaa8')], 'transactionHash': HexBytes('0x39d1bc1325d27effed5092735861922443b269a1dfbe3f7d52e3cac8446a292e'), 'transactionIndex': 6})
    ]
    return entries

# For testing purposes.
# Verify at https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371.
def monitor_uni_v2_pair_events():
    client = EthEventsClient(EventClientType.POOL)
    while True:
        events = client.get_new_logs(dry_run=True)
        time.sleep(5)

# For testing purposes.
# Verify at https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371.


def monitor_beanstalk_events():
    client = EthEventsClient(EventClientType.BEANSTALK)
    while True:
        events = client.get_new_logs(dry_run=True)
        time.sleep(5)

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(format='ETH Chain : %(levelname)s : %(asctime)s : %(message)s',
                        level=logging.INFO)
    monitor_uni_v2_pair_events()
    # monitor_beanstalk_events()

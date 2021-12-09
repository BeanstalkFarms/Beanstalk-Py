import asyncio
import logging
import json
import os
import time
from discord.ext.commands.errors import ArgumentParsingError

from web3 import Web3, WebsocketProvider

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

with open(os.path.join(os.path.dirname(__file__), '../../contracts/ethereum/IUniswapV2Pair.json')) as pool_abi_file:
    pool_abi = json.load(pool_abi_file)
with open(os.path.join(os.path.dirname(__file__), '../../contracts/ethereum/beanstalk_abi.json')) as beanstalk_abi_file:
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
        self._web3 = Web3(WebsocketProvider(URL))
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

    def avg_swap_price(self, eth, beans):
        """Returns the $/bean cost for a swap txn using the $/ETH price."""
        return self.current_eth_price() * (eth / beans)


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


# For testing purposes.
# Verify at https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371.
def monitor_uni_v2_pair_events():
    client = EthEventsClient()
    client.set_event_log_filters_pool()
    while True:
        events = client.get_new_log_entries()
        logging.info(events)
        time.sleep(2)

# For testing purposes.
# Verify at https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371.


def monitor_beanstalk_events():
    client = EthEventsClient()
    client.set_event_log_filters_beanstalk()
    while True:
        events = client.get_new_log_entries()
        logging.info(events)
        time.sleep(2)


class EthEventsClient():
    def __init__(self):
        self._web3 = Web3(WebsocketProvider(URL))
        self._event_log_filters = None

    def get_new_log_entries(self, dry_run=False):
        """Iterate through all event log filters and return list of Event Log Objects."""
        assert self._event_log_filters
        event_logs = []
        if dry_run:
            return maybe_get_test_events()
        logging.info(
            f'Checking for new entries with filters {self._event_log_filters}.')
        for filter in self._event_log_filters:
            for event in self.safe_get_new_entries(filter):
                event_logs.append(event)
                logging.info(event)
        return event_logs

    def safe_get_new_entries(self, filter):
        try_count = 0
        while try_count < 5:
            try_count += 1
            try:
                return filter.get_new_entries()
                # return filter.get_all_entries()
            except (ValueError, asyncio.TimeoutError) as e:
                logging.warning(e)
                logging.info(
                    'filter.get_new_entries() failed or timed out. Retrying...')
                time.sleep(1)
        logging.error('Failed to get new event entries. Passing.')
        return []

    def set_event_log_filters_pool(self):
        """Create and return web3 filters for the uniswap pair logs.

        - Latest block only
        - Address == Uniswap V2 Pair Contract Address
        - Mint, Burn, and Swap interactions only (ignore sync).

        Returns:
            [swap filter, mint filter, burn filter]
        """
        # Creating an Event Log Filter this way will return Event Log Objects with arguments decoded.
        eth_bean_pool_contract = get_eth_bean_pool_contract(self._web3)
        self._event_log_filters = [eth_bean_pool_contract.events.Swap.createFilter(fromBlock='latest'),
                                   eth_bean_pool_contract.events.Mint.createFilter(
            fromBlock='latest'),
            eth_bean_pool_contract.events.Burn.createFilter(fromBlock='latest')]

    def set_event_log_filters_beanstalk(self):
        """Create and return web3 filters for the beanstalk contract logs.

        - Latest block only
        - Address == Beanstalk Contract Address

        Returns:
            []
        """
        # Creating Event Log Filters this way will return Event Log Objects with arguments decoded.
        beanstalk_contract = get_beanstalk_contract(self._web3)
        self._event_log_filters = [beanstalk_contract.events.LPDeposit.createFilter(fromBlock='latest'),
                                   beanstalk_contract.events.LPRemove.createFilter(
            fromBlock='latest'),
            beanstalk_contract.events.LPWithdraw.createFilter(
            fromBlock='latest'),
            beanstalk_contract.events.LPClaim.createFilter(fromBlock='latest'),
            beanstalk_contract.events.BeanDeposit.createFilter(
            fromBlock='latest'),
            beanstalk_contract.events.BeanRemove.createFilter(
            fromBlock='latest'),
            beanstalk_contract.events.BeanClaim.createFilter(
                fromBlock='latest'),
            beanstalk_contract.events.Sow.createFilter(fromBlock='latest')]

    # Creating a generic Filter this way will return Event Objects with data (arguments) encoded.
    # return web3.eth.filter({'fromBlock': 'latest', 'address': ETH_BEAN_POOL_ADDR, 'topic': [[MINT_TOPIC, BURN_TOPIC, SWAP_TOPIC]]})

    # Create one Event Log filter with all topics.
    # https://web3py.readthedocs.io/en/stable/filters.html
    # mint_event_signature_hash = web3.keccak(eth_bean_pool_contract.encode('Mint')).hex()
    # burn_event_signature_hash = web3.keccak(text="Burn(address,uint,uint,address)").hex()
    # swap_event_signature_hash = web3.keccak(text="Swap(address indexed sender,  uint amount0In,  uint amount1In,  uint amount0Out,  uint amount1Out,  address indexed to)").hex()

    # MINT_TOPIC = '0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f'
    # BURN_TOPIC = '0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496'
    # SWAP_TOPIC = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
    # SYNC_TOPIC = '0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'
    # Turns out this returns just a standard event type with the data encoded. :/.
    # return [web3.eth.filter({
    #     "address": ETH_BEAN_POOL_ADDR,
    #     "topics": [[mint_event_signature_hash, burn_event_signature_hash, swap_event_signature_hash]],
    #     "fromBlock": 13753729,
    #     "toBlock": 'latest'
    #     })]

    # return eth_bean_pool_contract.eventFilter('Swap', {'fromBlock': 0,'toBlock': 'latest'})
    # filter_builder = eth_bean_pool_contract.events.myEvent.build_filter()
    # swap_filter = eth_bean_pool_contract.events.Swap.createFilter(fromBlock='latest')
    # mint_filter = eth_bean_pool_contract.events.Mint.createFilter(fromBlock='latest')
    # burn_filter = eth_bean_pool_contract.events.Burn.createFilter(fromBlock='latest')
    # return swap_filter + mint_filter + burn_filter


def maybe_get_test_events(odds=1.0):
    """Get a list of old events to use for testing."""
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
            '0xf1ef8aeee45b44468393638356d9fccc0ff3b7cee169e6784969e7c0cdcf86a6'), 'address': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'blockHash': HexBytes('0xa877eb7ab22366a8abcbf974da5069c4db03ec80df7f503435b42021877d9222'), 'blockNumber': 13772704})
    ]
    if random.randint(1, int(10/odds)) <= 10:
        return events
    else:
        return []


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""

    # monitor_uni_v2_pair_events()
    monitor_beanstalk_events()

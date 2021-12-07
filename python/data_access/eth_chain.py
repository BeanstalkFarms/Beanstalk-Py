import asyncio
import logging
import json
import os
import time

from web3 import Web3, WebsocketProvider

API_KEY = os.environ['ETH_CHAIN_API_KEY']
URL = 'wss://mainnet.infura.io/ws/v3/' + API_KEY
web3 = Web3(WebsocketProvider(URL))

# Decimals for conversion from chain int values to float decimal values. 
ETH_DECIMALS = 18
BEAN_DECIMALS = 6
USDC_DECIMALS = 6

# BEAN_TOKEN_ADDR = '0xDC59ac4FeFa32293A95889Dc396682858d52e5Db'
ETH_BEAN_POOL_ADDR = '0x87898263B6C5BABe34b4ec53F22d98430b91e371'
ETH_USDC_POOL_ADDR = '0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc'

with open(os.path.join(os.path.dirname(__file__), '../../contracts/ethereum/IUniswapV2Pair.json')) as pool_abi_file:
    pool_abi = json.load(pool_abi_file)
eth_bean_pool_contract = web3.eth.contract(address=ETH_BEAN_POOL_ADDR, abi=pool_abi)
eth_usdc_pool_contract = web3.eth.contract(address=ETH_USDC_POOL_ADDR, abi=pool_abi)

def current_eth_price():
    reserve0, reserve1, _ = eth_usdc_pool_contract.functions.getReserves().call()
    eth_reserves = eth_to_float(reserve1)
    usdc_reserves = usdc_to_float(reserve0)
    eth_price = usdc_reserves / eth_reserves
    logging.info('Current ETH Price: ' + str(eth_price))
    return eth_price

def current_bean_price():
    reserve0, reserve1, _ = eth_bean_pool_contract.functions.getReserves().call()
    eth_reserves = eth_to_float(reserve0)
    bean_reserves = bean_to_float(reserve1)
    bean_price = current_eth_price() * eth_reserves / bean_reserves
    logging.info('Current bean price: ' + str(bean_price))
    return bean_price

def avg_swap_price(eth, beans):
    """Returns the $/bean cost for a swap txn using the $/ETH price."""
    return current_eth_price() * (eth / beans)

def eth_to_float(gwei):
    if not gwei:
        return 0
    return int(gwei) / (10 ** ETH_DECIMALS)

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
    client = EthEventClient()
    client.set_event_log_filters_pool_contract()
    while True:
        events = client.get_new_log_entries()
        logging.info(events)
        time.sleep(2)


class EthEventClient():

    def __init__(self):
        self.event_log_filters = []

    def set_event_log_filters_pool_contract(self):
        self.event_log_filters = self.get_event_log_filters_pool_contract()
    
    def get_event_log_filters_pool_contract(self):
        """Create and return web3 filters for the pool logs.

        - Latest block only
        - Address == Uniswap V2 Pair Contract Address
        - Mint, Burn, and Swap interactions only (ignore sync).

        amount0 parameters are ETH.
        amount1 parameters are BEAN.

        Returns:
            [swap filter, mint filter, burn filter]
        """
        # Creating an Event Log Filter this way will return Event Log Objects with arguments decoded.
        return [eth_bean_pool_contract.events.Swap.createFilter(fromBlock='latest'),
                eth_bean_pool_contract.events.Mint.createFilter(fromBlock='latest'),
                eth_bean_pool_contract.events.Burn.createFilter(fromBlock='latest')]
        # Creating a generic Filter this way will return Event Objects with data (arguments) encoded.
        # return web3.eth.filter({'fromBlock': 'latest', 'address': ETH_BEAN_POOL_ADDR, 'topic': [[MINT_TOPIC, BURN_TOPIC, SWAP_TOPIC]]})

    def get_new_log_entries(self, dry_run=False):
        """Iterate through all event log filters and return list of Event Log Objects."""
        assert self.event_log_filters
        event_logs = []
        if dry_run:
            return maybe_get_test_events()
        for filter in self.event_log_filters:
            for event in self.safe_get_new_entries(filter):
                event_logs.append(event)
                logging.info(event)
        return event_logs

    def safe_get_new_entries(self, filter):
        while True:
            try:
                logging.info(f'Checking for new entries on latest block with filter {filter.filter_id}.')
                return filter.get_new_entries()
            except (ValueError, asyncio.exceptions.TimeoutError):
                logging.info('filter.get_new_entries() failed or timed out. Retrying...')
                time.sleep(1)

def maybe_get_test_events(percent_chance=1.0):
    """Get a list of old events to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes
    import random
    events = [
    AttributeDict({'args': AttributeDict({'sender': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'to': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'amount0In': 1461909585474928331, 'amount1In': 0, 'amount0Out': 0, 'amount1Out': 6603011113}), 'event': 'Swap', 'logIndex': 343, 'transactionIndex': 227, 'transactionHash': HexBytes('0xa23b6157fe6c16d31a486222e50c635d10c43db97c358869770adeeeb91fc3b5'), 'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0x9d7072892b16e1c850ac1a6e32f7ae04579174e418c94e231d9b5d7b5f3b29aa'), 'blockNumber': 13722265}),
    AttributeDict({'args': AttributeDict({'sender': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'to': '0xC1E088fC1323b20BCBee9bd1B9fC9546db5624C5', 'amount0In': 0, 'amount1In': 152620722880, 'amount0Out': 32933918030233354308, 'amount1Out': 0}), 'event': 'Swap', 'logIndex': 79, 'transactionIndex': 58, 'transactionHash': HexBytes('0x7a0cd2269e3a7c3def3cf3184dcdafcef9274078236ae840d20880cf79583b29'), 'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xb7447a69c5c193b046c0363cbf9898c424285a3ea0d3ebe1a1bc03776fda7b43'), 'blockNumber': 13722372}),
    AttributeDict({'args': AttributeDict({'sender': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', 'amount0': 32933918029946007630, 'amount1': 155379277120}), 'event': 'Mint', 'logIndex': 84, 'transactionIndex': 58, 'transactionHash': HexBytes('0x7a0cd2269e3a7c3def3cf3184dcdafcef9274078236ae840d20880cf79583b29'), 'address': '0x87898263B6C5BABe34b4ec53F22d98430b91e371', 'blockHash': HexBytes('0xb7447a69c5c193b046c0363cbf9898c424285a3ea0d3ebe1a1bc03776fda7b43'), 'blockNumber': 13722372})
    ]
    if random.randint(1,int(10/percent_chance)) <= 10:
        return events
    else:
        return []

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""

    monitor_uni_v2_pair_events()

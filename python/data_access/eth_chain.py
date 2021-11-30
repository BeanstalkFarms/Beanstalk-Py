import logging
import json
import os
import time

from web3 import Web3, WebsocketProvider
from web3.types import FilterParams

API_KEY = os.environ['ETH_CHAIN_API_KEY']
URL = 'wss://mainnet.infura.io/ws/v3/' + API_KEY
web3 = Web3(WebsocketProvider(URL))

# Decimals for conversion from chain int values to float decimal values. 
ETH_DECIMALS = 18
BEAN_DECIMALS = 6

# BEAN_TOKEN_ADDR = '0xDC59ac4FeFa32293A95889Dc396682858d52e5Db'
UNI_V2_POOL_ADDR = '0x87898263B6C5BABe34b4ec53F22d98430b91e371'

with open(os.path.join(os.path.dirname(__file__), '../../contracts/ethereum/IUniswapV2Pair.json')) as pool_abi_file:
    # with open(os.path.expanduser('~/Programs/beanstalk_protocol/Beanstalk-Tooling/contracts/ethereum/univ2pool.json')) as pool_abi_file:
    pool_abi = json.load(pool_abi_file)
pool_contract = web3.eth.contract(address=UNI_V2_POOL_ADDR, abi=pool_abi)

def eth_to_float(gwei):
    if not gwei:
        return 0
    return int(gwei) / (10 ** ETH_DECIMALS)

def bean_to_float(bean_long):
    if not bean_long:
        return 0
    return int(bean_long) / (10** BEAN_DECIMALS)

def get_pool_contract_event_filters():
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
    return [pool_contract.events.Swap.createFilter(fromBlock='latest'),
            pool_contract.events.Mint.createFilter(fromBlock='latest'),
            pool_contract.events.Burn.createFilter(fromBlock='latest')]
    # Creating a generic Filter this way will return Event Objects with data (arguments) encoded.
    # return web3.eth.filter({'fromBlock': 'latest', 'address': UNI_V2_POOL_ADDR, 'topic': [[MINT_TOPIC, BURN_TOPIC, SWAP_TOPIC]]})


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

        Returns:
            [swap filter, mint filter, burn filter]
        """
        # Creating an Event Log Filter this way will return Event Log Objects with arguments decoded.
        return [pool_contract.events.Swap.createFilter(fromBlock='latest'),
                pool_contract.events.Mint.createFilter(fromBlock='latest'),
                pool_contract.events.Burn.createFilter(fromBlock='latest')]
        # Creating a generic Filter this way will return Event Objects with data (arguments) encoded.
        # return web3.eth.filter({'fromBlock': 'latest', 'address': UNI_V2_POOL_ADDR, 'topic': [[MINT_TOPIC, BURN_TOPIC, SWAP_TOPIC]]})

    def get_new_log_entries(self):
        """Iterate through all event log filters and return list of Event Log Objects."""
        assert self.event_log_filters
        event_logs = []
        for filter in self.event_log_filters:
            for event in self.safe_get_new_entries(filter):
                event_logs.append(event)
                print(event)
        return event_logs

    def safe_get_new_entries(self, filter):
        while True:
            try:
                return filter.get_new_entries()
            except ValueError:
                logging.info('get_new_entries() failed or timed out. Retrying...')

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""

    monitor_uni_v2_pair_events()




##### GRAVEYARD ####

# class PoolTxType(Enum):
#     SWAP = 0
#     MINT = 1
#     BURN = 2
#     SYNC = 3

# MINT_TOPIC = '0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f'
# BURN_TOPIC = '0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496'
# SWAP_TOPIC = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
# SYNC_TOPIC = '0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'

# TOPIC_TYPE_MAP = {
#     MINT_TOPIC : MINT_TOPIC,
#     BURN_TOPIC : BURN_TOPIC,
#     SWAP_TOPIC : SWAP_TOPIC,
#     SYNC_TOPIC : SYNC_TOPIC,
# }

# Retrieve contract details from global definitions.
# beanstalk_addr = ""
# with open(os.path.expanduser(os.environ.get('BEANSTALK_ADDR_PATH'))) as beanstalk_addr_path_file:
#     beanstalk_addr = beanstalk_addr_path_file.read().strip()
# beanstalk_abi = {}
# with open(os.path.expanduser(os.environ.get('BEANSTALK_ABI_PATH'))) as beanstalk_abi_file:
#     beanstalk_abi = json.load(beanstalk_abi_file)

# beanstalk_contract = web3.eth.contract(address=beanstalk_addr, abi=beanstalk_abi)

# soil = beanstalk_contract.functions.totalSoil().call()/1e6

# print('Total Soil: ' + str(soil))

# def decode_pool_tx_data(data):
#     pair_contract_filter = get_pool_contract_filter()
#     entry = pair_contract_filter.get_all_entries()
#     print(entry)
#     # decoded_data = pool_contract.decode_function_input(data)
#     logging.info(decoded_data)

# def get_lp_token_value():
#     """Get the value of 1.0 LP token for the pool."""
#     .totalSupply()
#     with open(os.path.expanduser('~/Programs/beanstalk_protocol/Beanstalk-Tooling/contracts/ethereum/IUniswapV2Pair.json')) as pool_abi_file:
#         pool_abi = json.load(pool_abi_file)
#     pool_contract = web3.eth.contract(address=UNI_V2_POOL_ADDR, abi=pool_abi)
#     pool_contract.functions.totalSupply().call()
#     return pool_value / circulating_supply

# event_filter = pool_contract.events.Swap.createFilter(fromBlock="latest", argument_filters={'arg1':10})
# event_filter.get_new_entries()
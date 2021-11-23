import json
import os
import time

from web3 import Web3, WebsocketProvider

API_KEY = os.environ.get('ETH_CHAIN_API_KEY')
URL = 'wss://mainnet.infura.io/ws/v3/' + API_KEY
web3 = Web3(WebsocketProvider(URL))

UNI_V2_PAIR_ADDR = '0xDC59ac4FeFa32293A95889Dc396682858d52e5Db'

MINT_TOPIC = '0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f'
BURN_TOPIC = '0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496'
SWAP_TOPIC = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
SYNC_TOPIC = '0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'

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


# with open(os.path.expanduser('~/Programs/beanstalk_protocol/Beanstalk-Tooling/contracts/ethereum/IUniswapV2Pair.json')) as pool_abi_file:
#     pool_abi = json.load(pool_abi_file)
# pool_contract = web3.eth.contract(address=UNI_V2_PAIR_ADDR, abi=pool_abi)


# event_filter = pool_contract.events.Swap.createFilter(fromBlock="latest", argument_filters={'arg1':10})
# event_filter.get_new_entries()


def get_pair_contract_filter():
    """Create and return a web3 filter for the pool logs.

    - Latest block only
    - Address == Uniswap V2 Pair Contract Address
    - Mint, Burn, and Swap interactions only (ignore sync).
    """
    return web3.eth.filter({'fromBlock': 'latest', 'address': UNI_V2_PAIR_ADDR, 'topic': [[MINT_TOPIC, BURN_TOPIC, SWAP_TOPIC]]})

# Verify at https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371.
def monitor_uni_v2_pair_events():
    pair_contract_filter = get_pair_contract_filter()
    while True:
        for event in pair_contract_filter.get_new_entries():
            print(event)
        time.sleep(2)

if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    monitor_uni_v2_pair_events()
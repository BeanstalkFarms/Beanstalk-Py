import logging
import json
import os
import time
import websockets

from web3 import HTTPProvider

from constants.addresses import *
from constants.config import *
import tools.util

from constants import dry_run_entries

with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/erc20_abi.json")
) as erc20_abi_file:
    erc20_abi = json.load(erc20_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/aquifer_abi.json")
) as aquifer_abi_file:
    aquifer_abi = json.load(aquifer_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/well_abi.json")
) as well_abi_file:
    well_abi = json.load(well_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/beanstalk_abi.json")
) as beanstalk_abi_file:
    beanstalk_abi = json.load(beanstalk_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/beanstalk_abi_silo_v2.json")
) as beanstalk_abi_file_silo_v2:
    beanstalk_v2_abi = json.load(beanstalk_abi_file_silo_v2)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/bean_price_abi.json")
) as bean_price_abi_file:
    bean_price_abi = json.load(bean_price_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/fertilizer_abi.json")
) as fertilizer_abi_file:
    fertilizer_abi = json.load(fertilizer_abi_file)
with open(
    os.path.join(os.path.dirname(__file__), "../../constants/abi/eth_usd_oracle_abi.json")
) as eth_usd_oracle_abi_file:
    eth_usd_oracle_abi = json.load(eth_usd_oracle_abi_file)

class ChainClient:
    """Base class for clients of Eth chain data."""

    def __init__(self, web3=None):
        self._web3 = web3 or get_web3_instance()
        

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


def usdc_to_float(usdc_long):
    return token_to_float(usdc_long, USDC_DECIMALS)


def usdt_to_float(usdt_long):
    return token_to_float(usdt_long, USDT_DECIMALS)


def get_test_entries(dry_run=None):
    """Get a list of onchain transaction entries to use for testing."""
    from attributedict.collections import AttributeDict
    from hexbytes import HexBytes

    time.sleep(1)

    if dry_run:
        if dry_run[0] == 'all':
            return dry_run_entries.entries
        elif dry_run[0] == 'seasons':
            return []
        else:
            entries = []
            for i in range(len(dry_run)):
                entries.append(AttributeDict({"transactionHash": HexBytes(dry_run[i])}))
            return entries

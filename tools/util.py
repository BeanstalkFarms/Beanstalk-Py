from hexbytes.main import HexBytes
import logging
import json
import os
import time
from web3 import Web3, WebsocketProvider
from web3.datastructures import AttributeDict
from web3.logs import DISCARD


URL = "wss://eth-mainnet.g.alchemy.com/v2/" + os.environ["ALCHEMY_ETH_API_KEY"]
web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))


def decode_logs(txn_receipt, event):
    """Returns all decoded logs of an event in a receipt."""
    return event.processReceipt(txn_receipt, errors=DISCARD)


def get_decoded_logs(txn_receipt, contract):
    """Get all decoded logs from a single contract in a receipt.

    Returns:
        List of AttributeDicts containing individual decoded logs.
    """
    decoded_logs = []
    for event in contract.events:
        decoded_logs.extend(decode_logs(txn_receipt, event()))
    return decoded_logs


def get_event(contract, event_name):
    """Get a single Event object from a contract by name."""
    return contract.events[event_name]()


def get_decoded_logs_by_event(txn_receipt, contract, event_name):
    """Get all decoded logs for a specific event in a single contract in a receipt.

    Returns:
        List of AttributeDicts containing individual decoded logs.
    """
    return decode_logs(txn_receipt, get_event(contract, event_name))


def format_log_str(log, indent=0):
    """Format decoded log AttributeDict as a nice str."""
    ret_str_list = []
    for key, value in log.items():
        if isinstance(value, AttributeDict):
            str_value = f"\n{format_log_str(value, 2)}"
        elif isinstance(value, HexBytes):
            str_value = value.hex()
        else:
            str_value = str(value)
        item_str = f'{" " * indent}{key}: {str_value}'
        if key == "event":
            ret_str_list.insert(0, item_str)
        else:
            ret_str_list.append(item_str)
    return "\n".join(ret_str_list)


def web3_call_with_retries(web3_function, max_retries=5):
    """Decorator to wrap web3 calls that could fail and gracefully handle retries."""

    def retry_wrapper(web3, txn_hash):
        try_count = 0
        while True:
            try_count += 1
            try:
                return web3_function(web3, txn_hash)
            except Exception as e:
                if try_count < max_retries:
                    logging.warning(f"Failed to get txn. Retrying...\n{e}")
                    time.sleep(15)
                    continue
                logging.error(
                    f"Failed to get txn after {try_count} retries. Was the block orphaned?"
                )
                raise (e)

    return retry_wrapper


@web3_call_with_retries
def get_txn_or_wait(web3, txn_hash):
    """Get the transaction and handle errors and block delays cleanly.

    Occasionally web3 will fail to pull the txn with "not found" error. This is likely
    because the txn has not been confirmed at the time of call, even though the logs may
    have already been seen. In this case, wait and hope it will confirm soon.

    Returns:
        AttributeDict containing a single txn receipt.
    """
    return web3.eth.get_transaction(txn_hash)


@web3_call_with_retries
def get_txn_receipt_or_wait(web3, txn_hash):
    """Get the transaction receipt and handle errors and block delays cleanly.

    Occasionally web3 will fail to pull the txn with "not found" error. This is likely
    because the txn has not been confirmed at the time of call, even though the logs may
    have already been seen. In this case, wait and hope it will confirm soon.

    Returns:
        AttributeDict containing a single txn receipt.
    """
    return web3.eth.get_transaction_receipt(txn_hash)


def load_contract_from_abi(abi_path):
    with open(abi_path) as abi_file:
        abi = json.load(abi_file)
    return web3.eth.contract(abi=abi)


def format_farm_call_str(decoded_txn, beanstalk_contract):
    """Break down a farm() call and return a list of the sub-method it calls.

    Args:
        txn: a decoded web3.transaction object.

    Return:
        str representing the farm call in human readable format.
    """
    ret_str = ""
    # Possible to have multiple items in this list, what do they represent?
    # [1] is args, ['data'] is data arg
    farm_data_arg_list = decoded_txn[1]["data"]
    # logging.info(f'farm_data_arg_list: {farm_data_arg_list}')

    for sub_method_call_bytes in farm_data_arg_list:
        sub_method_selector = sub_method_call_bytes[:4]
        logging.info(f"\nsub_method_selector: {sub_method_selector.hex()}")
        # sub_method_input = sub_method_call_bytes[4:]
        # logging.info(f'sub_method_input: {sub_method_input.hex()}')
        decoded_sub_method_call = beanstalk_contract.decode_function_input(sub_method_call_bytes)
        logging.info(f"decoded_sub_method_call: {decoded_sub_method_call}")
        ret_str += f"  sub-call: {decoded_sub_method_call[0].function_identifier}"
        ret_str += "\n  args:"
        for arg_name, value in decoded_sub_method_call[1].items():
            # Clean up bytes as strings for printing.
            if type(value) is bytes:
                value = value.hex()
            ret_str += f"\n    {arg_name}: {value}"
        ret_str += "\n\n"
    return ret_str

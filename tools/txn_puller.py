"""
Tool to extract all information about a transaction from chain.

Example use:
python3 -m tools.txn_puller 0x61ce4cfaf84ad70d83299c10e4dda09a6a593f8a328ac3db9e683088c2637f68
python3 txn_puller.py 0x34f24706cb3cbd26da893e8abf181e1868c11f95a7f39891baa842f19e61b72f -p ../constants/abi/beanstalk_abi.json

Web3 lib txn receipt structure:
TxReceipt = TypedDict("TxReceipt", {
    "blockHash": HexBytes,
    "blockNumber": BlockNumber,
    "contractAddress": Optional[ChecksumAddress],
    "cumulativeGasUsed": int,
    "effectiveGasPrice": int,
    "gasUsed": Wei,
    "from": ChecksumAddress,
    "logs": List[LogReceipt],
    "logsBloom": HexBytes,
    "root": HexStr,
    "status": int,
    "to": ChecksumAddress,
    "transactionHash": HexBytes,
    "transactionIndex": int,
})

"""

import argparse
from hexbytes.main import HexBytes
import json
import logging
import os
from pprint import pformat
import time
from web3 import Web3, WebsocketProvider
from web3.datastructures import AttributeDict
from web3.exceptions import TransactionNotFound
from web3.logs import DISCARD

URL = 'wss://eth-mainnet.g.alchemy.com/v2/' + os.environ['ALCHEMY_ETH_API_KEY']

logging.basicConfig(level=logging.INFO)


def decode_logs(txn_receipt, event):
    """Returns all decoded logs of an event in a receipt."""
    return event.processReceipt(txn_receipt, errors=DISCARD)

#  self.beanstalk_contract.events['PodOrderCancelled']().processReceipt(transaction_receipt, errors=eth_chain.DISCARD)


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


def get_txn_receipt_or_wait(web3, txn_hash, max_retries=5):
    """Get the transaction receipt and handle errors and block delays cleanly.

    Occasionally web3 will fail to pull the txn with "not found" error. This is likely
    because the txn has not been confirmed at the time of call, even though the logs may
    have already been seen. In this case, wait and hope it will confirm soon.

    Returns:
        AttributeDict containing a single txn receipt.
    """
    try_count = 0
    while True:
        try:
            return web3.eth.get_transaction_receipt(txn_hash)
        except TransactionNotFound as e:
            if try_count > max_retries:
                logging.error(
                    f'Failed to get txn after {try_count} retries. Was the block orphaned?')
                raise(e)
            logging.warning(f'Failed to get txn receipt. Retrying...\n{e}')
        # ~ 1 ETH block time.
        time.sleep(15)
        try_count += 1


def format_log_str(log, indent=0):
    """Format decoded log AttributeDict as a nice str."""
    ret_str_list = []
    for key, value in log.items():
        if isinstance(value, AttributeDict):
            str_value = f'\n{format_log_str(value, 4)}'
        elif isinstance(value, HexBytes):
            str_value = value.hex()
        else:
            str_value = str(value)
        item_str = f'{" " * indent}{key}: {str_value}'
        if key == 'event':
            ret_str_list.insert(0, item_str)
        else:
            ret_str_list.append(item_str)
    return '\n'.join(ret_str_list)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Pull transaction information.')
    parser.add_argument('txn_hash', type=str, help='the transaction hash')
    parser.add_argument('-p', '--abi_path', type=str,
                        help='path to contract abi (default: beanstalk)',
                        default=os.path.join(
                            os.path.dirname(__file__), '../constants/abi/beanstalk_abi.json'))
    parser.add_argument('-k', '--key', type=str,
                        help='alchemy key (default pulls env var ALCHEMY_ETH_API_KEY)',
                        default=os.environ['ALCHEMY_ETH_API_KEY'])
    args = parser.parse_args()

    URL = 'wss://eth-mainnet.g.alchemy.com/v2/' + args.key
    web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))

    # Get receipt from chain.
    receipt = get_txn_receipt_or_wait(web3, args.txn_hash)
    print('\nTxn receipt:\n' + pformat(dict(receipt)))

    # Decode logs if contract abi provided.
    if args.abi_path:
        with open(args.abi_path) as abi_file:
            abi = json.load(abi_file)
        contract = web3.eth.contract(abi=abi)

        # Use below line if you want decoded logs for all events in a contract.
        decoded_logs = get_decoded_logs(receipt, contract)
        # Use below line if you want decoded logs for a specific event only.
        # decoded_logs = get_decoded_logs_by_event(receipt, contract, 'AddDeposit')

        print('\nDecoded logs:\n' +
              '\n\n'.join([format_log_str(log) for log in decoded_logs]))
    else:
        print('\nNot decoding logs. Contract ABI required.')

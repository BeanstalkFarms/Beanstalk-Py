"""
Tool to extract all information about a transaction from chain.

Example use:
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
import json
import logging
import os
from pprint import pformat
import time
from web3 import Web3, WebsocketProvider
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
                logging.error(f'Failed to get txn after {try_count} retries. Was the block orphaned?')
                raise(e)
            logging.warning(f'Failed to get txn receipt. Retrying...\n{e}')
        # ~ 1 ETH block time.
        time.sleep(15)
        try_count += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pull transaction information.')
    parser.add_argument('txn_hash', type=str, help='the transaction hash')
    parser.add_argument('-p', '--abi_path', type=str, help='path to contract abi')
    args = parser.parse_args()

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

        print('\nDecoded logs:\n' + '\n\n'.join([pformat(dict(log)) for log in decoded_logs]))
    else:
        print('\nNot decoding logs. Contract ABI required.')

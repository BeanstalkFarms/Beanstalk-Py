"""
Tool to extract all information about a transaction from chain.

Example use:
python3 -m tools.txn_puller 0x61ce4cfaf84ad70d83299c10e4dda09a6a593f8a328ac3db9e683088c2637f68
python3 txn_puller.py 0x34f24706cb3cbd26da893e8abf181e1868c11f95a7f39891baa842f19e61b72f -p ../constants/abi/beanstalk_abi.json
"""

import argparse
import json
import logging
import os
from pprint import pformat
import time
from web3 import Web3, WebsocketProvider
from web3.datastructures import AttributeDict
from web3.exceptions import TransactionNotFound
from web3.logs import DISCARD

import constants.addresses
import tools.util

logging.basicConfig(level=logging.WARNING)


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
    receipt = tools.util.get_txn_receipt_or_wait(web3, args.txn_hash)
    print('\nTxn receipt:\n' + pformat(dict(receipt)))

    # Decode logs if contract abi provided.
    contract = tools.util.load_contract_from_abi(args.abi_path)

    # Use below line if you want decoded logs for all events in a contract.
    decoded_logs = tools.util.get_decoded_logs(receipt, contract)
    # Use below line if you want decoded logs for a specific event only.
    # decoded_logs = get_decoded_logs_by_event(receipt, contract, 'AddDeposit')

    print('\nDecoded logs:\n' +
          '\n\n'.join([tools.util.format_log_str(log) for log in decoded_logs]))

    # If a farm txn, decode the underlying farm method calls.
    txn = tools.util.get_txn_or_wait(web3, args.txn_hash)
    decoded_txn = None
    try:
        decoded_txn = contract.decode_function_input(txn.input)
    except ValueError as e:
        logging.warning(e)
    if decoded_txn is not None:
        print(f'\n\nfunction: {decoded_txn[0].function_identifier}')
        if decoded_txn[0].function_identifier == 'farm' and txn.to == constants.addresses.BEANSTALK_ADDR:
            print(tools.util.format_farm_call_str(decoded_txn, contract))
        else:
            print(f'args:')
            for arg_name, value in decoded_txn[1].items():
                print(f'    arg_name: {value}')

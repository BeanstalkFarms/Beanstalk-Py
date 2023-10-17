"""
Tools to inspect diamond contracts. Tailored to Beanstalk.

This doesn't do much more than txn_parse.py, but it is less about printing information and a 
clean example of how to parse farm() txns.
"""
import argparse
import logging
import json
import os
from web3 import Web3, WebsocketProvider

import tools.util
from constants.addresses import BEANSTALK_ADDR as BEANSTALK_DIAMOND

logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decode farm() transaction sub method calls.")
    parser.add_argument("txn_hash", type=str, help="the transaction hash")
    parser.add_argument(
        "-p",
        "--abi_path",
        type=str,
        help="path to contract abi (default: beanstalk)",
        default=os.path.join(os.path.dirname(__file__), "../constants/abi/beanstalk_abi.json"),
    )
    parser.add_argument(
        "-k",
        "--key",
        type=str,
        help="alchemy key (default pulls env var ALCHEMY_ETH_API_KEY)",
        default=os.environ["ALCHEMY_ETH_API_KEY"],
    )
    args = parser.parse_args()

    URL = "wss://eth-mainnet.g.alchemy.com/v2/" + args.key
    web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))

    # Load abi.
    with open(args.abi_path) as abi_file:
        abi = json.load(abi_file)
    contract = web3.eth.contract(abi=abi)

    # Get receipt from chain.
    txn = tools.util.get_txn_or_wait(web3, args.txn_hash)
    # logging.info('\ntxn:\n{txn}')

    decoded_txn = contract.decode_function_input(txn.input)  # returns tuple (function object, args)
    logging.info(f"decoded txn: {decoded_txn}")

    # If no args
    if not decoded_txn[1]:
        exit

    # Note that farm() calls only have 1 arg (data bytes[])
    for arg_name, arg_value in decoded_txn[1].items():
        logging.info(f"arg: {arg_name}")
        # logging.info(f'arg_value: {arg_value}')
        # If the data of a farm call parse it specially.
        if decoded_txn[0].function_identifier == "farm" and arg_name == "data":
            for sub_method_call_bytes in arg_value:
                sub_method_selector = sub_method_call_bytes[:4]
                logging.info(f"\n\nsub_method_selector: {sub_method_selector.hex()}")
                sub_method_input = sub_method_call_bytes[4:]
                # logging.info(f'sub_method_input: {sub_method_input.hex()}')
                decoded_sub_method_call = contract.decode_function_input(sub_method_call_bytes)
                logging.info(f"decoded_sub_method_call: {decoded_sub_method_call}")
        else:
            logging.info(f"arg value: {arg_value}")

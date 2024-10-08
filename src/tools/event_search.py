"""
Tool to search by recency through all transactions at address for an event and display txn hashes.

Example use:
python3 -m tools.event_search EVENT_DEFINITION
"""

import argparse
import logging
import os
from constants.addresses import BEANSTALK_ADDR
from web3 import Web3, WebsocketProvider


logging.basicConfig(level=logging.WARNING)

MAX_BLOCK_PULL_SIZE = 500

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search for event in recent transactions.")
    parser.add_argument(
        "event_definition",
        type=str,
        help="the str of the event contract definition. ex)  RemoveDeposit(address,address,uint32,uint256)",
    )
    # parser.add_argument('-l', '--list', action='store_true', help='list beanstalk event definitions')
    parser.add_argument("-e", "--show_entries", action="store_true", help="show event entries")
    parser.add_argument(
        "-n", "--num_txns", type=int, default=1, help="the max number of matching txns to return"
    )
    parser.add_argument(
        "-a",
        "--address",
        type=str,
        default=BEANSTALK_ADDR,
        help="the contract to check events at (default: Beanstalk addr)",
    )
    parser.add_argument(
        "-b",
        "--max_block",
        type=int,
        default=12974075,
        help="Oldest block to check (default: inception of Beanstalk)",
    )
    parser.add_argument(
        "-k",
        "--key",
        type=str,
        help="alchemy key"
    )
    args = parser.parse_args()

    # # List Beanstalk events, but does not include args necessary to build sig.
    # import tools.util
    # if args.list:
    #     contract = tools.util.load_contract_from_abi(os.path.join(os.path.dirname(__file__), '../constants/abi/beanstalk_abi.json'))
    #     for event in contract.events:
    #         print(event.event_name)
    #     exit(0)

    URL = "wss://eth-mainnet.g.alchemy.com/v2/" + args.key
    web3 = Web3(WebsocketProvider(URL, websocket_timeout=60))

    event_signature_hash = Web3.keccak(text=args.event_definition).hex()
    print(f"event signature: {event_signature_hash}")

    latest_searched_block = web3.eth.get_block("latest").number
    blocks_to_check = (
        MAX_BLOCK_PULL_SIZE
        if latest_searched_block - args.max_block > MAX_BLOCK_PULL_SIZE
        else latest_searched_block - args.max_block
    )
    entry_matches = []
    while len(entry_matches) < args.num_txns and latest_searched_block > args.max_block:
        from_block = latest_searched_block - blocks_to_check
        to_block = latest_searched_block - 1
        filter = web3.eth.filter(
            {
                "address": Web3.to_checksum_address(args.address),
                "topics": [event_signature_hash],
                "fromBlock": from_block,
                "toBlock": to_block,
            }
        )
        logging.info(f"Checking blocks {from_block} to {to_block} for {args.event_definition}")
        entries = filter.get_all_entries()
        for entry in reversed(entries):  # Newest to oldest.
            entry_matches.append(
                (entry["transactionHash"].hex(), entry["blockNumber"], entry)
            )  # txn hash
            if len(entry_matches) >= args.num_txns:
                break

        # Do not search blocks that have already been filtered against.
        latest_searched_block = latest_searched_block - blocks_to_check
        # Scale up size of search to keep things quick.
        blocks_to_check *= 2

    if len(entry_matches) == 0:
        print(f"No transactions found with matching event definition - {args.event_definition}")
    else:
        print(f"Transactions containing event definition:")
        for match in entry_matches:
            print(f"{match[0]}  (block: {match[1]})")
            if args.show_entries:
                print(f"entry:\n{match[2]}")

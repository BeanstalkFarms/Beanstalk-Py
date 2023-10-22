import logging
from data_access.util import get_with_retries
from data_access.eth_chain import get_chainlink_contract


CHAINLINK_ETH_USD = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
chainlink_contract = None


def get_eth_price(web3):
    # returns list [roundId, answer, startedAt, updatedAt, answeredInRound]
    try:
        response = chainlink_contract.functions.latestRoundData().call()
    except:
        chainlink_contract = get_chainlink_contract(web3, CHAINLINK_ETH_USD)
        response = chainlink_contract.functions.latestRoundData().call()
    return float(response[1] / 10**8)

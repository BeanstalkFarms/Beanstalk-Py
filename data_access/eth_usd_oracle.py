import logging
import constants.addresses
from data_access.eth_chain import get_web3_instance, get_eth_usd_oracle_contract


def get_twa_eth_price(web3, lookback_secs):
    """Returns the TWA price of ETH in USD as a float. In extreme cases will fallback to chainlink price."""
    contract = get_eth_usd_oracle_contract(web3)
    response = contract.functions.getEthUsdTwa(lookback_secs).call()
    return float(response / 10**6)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_twa_eth_price(get_web3_instance(), 3600))

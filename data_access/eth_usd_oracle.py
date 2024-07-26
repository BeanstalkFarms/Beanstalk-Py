import logging
from data_access.eth_chain import get_web3_instance, get_eth_usd_oracle_contract


def get_twa_eth_price(web3, lookback_secs):
    """Returns the TWA price of ETH in USD as a float."""
    contract = get_eth_usd_oracle_contract(web3)
    response = contract.functions.getEthUsdTwap(lookback_secs).call()
    return float(response / 10**6)

def get_twa_wsteth_price(web3, lookback_secs):
    """Returns the TWA price of wstETH in USD as a float."""
    contract = get_eth_usd_oracle_contract(web3)
    response = contract.functions.getWstethUsdTwap(lookback_secs).call()
    return float(response / 10**6)

def get_twa_wsteth_to_eth(web3, lookback_secs):
    """Returns the TWA price of wstETH in terms of ETH"""
    contract = get_eth_usd_oracle_contract(web3)
    response = contract.functions.getWstethEthTwap(lookback_secs).call()
    return float(response / 10**6)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_twa_eth_price(get_web3_instance(), 3600))
    print(get_twa_wsteth_price(get_web3_instance(), 3600))
    print(get_twa_wsteth_to_eth(get_web3_instance(), 3600))

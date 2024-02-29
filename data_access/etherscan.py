import logging
import os
from data_access.util import get_with_retries

ETHERSCAN_API_URL = (
    "https://api.etherscan.io/api?module={module}&action={action}&{payload}&apikey={key}"
)


def get_gas_base_fee():
    """Returns the base fee of the next block as a float. Retrieved from etherscan API."""
    request_url = ETHERSCAN_API_URL.format(
        module="gastracker", action="gasoracle", payload="", key=os.environ["ETHERSCAN_TOKEN"]
    )
    result = get_with_retries(request_url, timeout=15)
    if int(result["status"]) == 0:
        raise Exception(f'Request rejected by etherscan:\n{result["result"]}')
    return float(result["result"]["suggestBaseFee"])


# WARNING(funderberker): This API call requires expensive etherscan API pro.
def get_erc20_price(erc20_address):
    """Returns the price of an erc20 token in USD. Retrieved from etherscan API."""
    request_url = ETHERSCAN_API_URL.format(
        module="token",
        action="tokeninfo",
        payload=f"contractaddress={erc20_address}",
        key=os.environ["ETHERSCAN_TOKEN"],
    )
    result = get_with_retries(request_url)["result"]
    if int(result["status"]) == 0:
        raise Exception(f'Request rejected by etherscan:\n{result["result"]}')
    return float(result["result"]["tokenPriceUSD"])


def get_block_at_timestamp(timestamp):
    """Returns the block number at a timestamp. Retrieved from etherscan API."""
    request_url = ETHERSCAN_API_URL.format(
        module="block",
        action="getblocknobytime",
        payload="timestamp={timestamp}&closest=before",
        key=os.environ["ETHERSCAN_TOKEN"],
    )
    result = get_with_retries(request_url)
    if int(result["status"]) == 0:
        raise Exception(f'Request rejected by etherscan:\n{result["result"]}')
    return int(result["result"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_gas_base_fee())

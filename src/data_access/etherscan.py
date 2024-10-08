import logging
import os
from constants.chain import Chain
from data_access.util import get_with_retries

ETHERSCAN_API_URL = (
    "https://api.etherscan.io/api?module={module}&action={action}&{payload}&apikey={key}"
)
ARBISCAN_API_URL = (
    "https://api.arbiscan.io/api?module={module}&action={action}&{payload}&apikey={key}"
)

def get_gas_base_fee(chain):
    """Returns the base fee of the next block as a float. Retrieved from etherscan API."""
    if (chain == Chain.ETH):
        request_url = ETHERSCAN_API_URL.format(
            module="gastracker", action="gasoracle", payload="", key=os.environ["ETHERSCAN_TOKEN"]
        )
        result = get_with_retries(request_url, max_tries=4, timeout=10)
        if int(result["status"]) == 0:
            raise Exception(f'Request rejected by etherscan:\n{result["result"]}')
        return float(result["result"]["suggestBaseFee"])
    elif chain == Chain.ARB:
        request_url = ARBISCAN_API_URL.format(
            module="proxy", action="eth_gasPrice", payload="", key=os.environ["ARBISCAN_TOKEN"]
        )
        result = get_with_retries(request_url, max_tries=4, timeout=10)
        return float(int(result["result"], 16)) / 10 ** 9
    raise Exception("Unsupported chain")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_gas_base_fee(Chain.ARB))

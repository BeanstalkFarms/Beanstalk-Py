import logging
from constants.addresses import *
from data_access.util import get_with_retries
import time

USD_CG_ID = "usd"
ETHEREUM_CG_ID = "ethereum"

CG_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies={vs_id}"
CG_PRICE_ADDR_URL = "https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={address}&vs_currencies={vs_id}"


def get_eth_price():
    """Returns the price of a token in USD. Retrieved from Coin Gecko API. token_id is CG ID"""
    request_url = CG_PRICE_URL.format(token_id=ETHEREUM_CG_ID, vs_id=USD_CG_ID)
    return float(get_with_retries(request_url)[ETHEREUM_CG_ID][USD_CG_ID])


def get_token_price(address, retry = 5):
    """
    Returns the price of a token in USD. Retrieved from Coin Gecko API.
    Infers price when rate limit is hit, if possible. Otherwise, allow retrys if rate limit is hit.
    """
    address = str(address)
    if int(address, 16) == 0:
        return get_eth_price()
    request_url = CG_PRICE_ADDR_URL.format(address=address, vs_id=USD_CG_ID)
    response = get_with_retries(request_url)
    if address.lower() in response:
        return float(response[address.lower()][USD_CG_ID])
    elif address.lower() in [USDC.lower(), DAI.lower(), USDT.lower()]:
        # Infer price for common stables
        return 1
    elif retry > 0:
        # Retry if needed
        logging.warning(f"Retrying get_token_price for token {address} after 15 seconds... ({retry} attempts remaining)")
        time.sleep(15)
        return get_token_price(address, retry - 1)
    else:
        raise KeyError(f"Address '{address.lower()}' not found in response and a price could not be inferred.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(get_eth_price())

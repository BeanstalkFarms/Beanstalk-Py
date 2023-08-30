import logging
from data_access.util import get_with_retries

USD_CG_ID = 'usd'
ETHEREUM_CG_ID = 'ethereum'

CG_PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies={vs_id}'
CG_PRICE_ADDR_URL = 'https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={address}&vs_currencies={vs_id}'


def get_eth_price():
    """Returns the price of a token in USD. Retrieved from Coin Gecko API. token_id is CG ID"""
    request_url = CG_PRICE_URL.format(token_id=ETHEREUM_CG_ID, vs_id=USD_CG_ID)
    return float(get_with_retries(request_url)[ETHEREUM_CG_ID][USD_CG_ID])


def get_token_price(address):
    """Returns the price of a token in USD. Retrieved from Coin Gecko API."""
    address = str(address)
    if int(address,16) == 0: 
        return get_eth_price()
    request_url = CG_PRICE_ADDR_URL.format(address=address, vs_id=USD_CG_ID)
    return float(get_with_retries(request_url)[address][USD_CG_ID])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(get_eth_price())

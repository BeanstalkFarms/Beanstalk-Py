import logging
from data_access.util import get_with_retries

USD_CG_ID = 'usd'
ETHEREUM_CG_ID = 'ethereum'

CG_PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies={vs_id}'


def get_token_price(cg_token_id):
    """Returns the price of a token in USD. Retrieved from Coin Gecko API. token_id is CG ID"""
    request_url = CG_PRICE_URL.format(token_id=cg_token_id, vs_id=USD_CG_ID)
    return float(get_with_retries(request_url)[cg_token_id][USD_CG_ID])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(get_token_price(ETHEREUM_CG_ID))

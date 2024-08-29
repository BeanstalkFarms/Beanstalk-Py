from data_access.coin_gecko import get_token_price

from data_access.contracts.util import *

class CurveClient(ChainClient):
    """Client for interacting with standard curve pools."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_curve_3pool_contract(self._web3)

    # def get_3crv_price(self):
    #     return crv_to_float(call_contract_function_with_retry(self.contract.functions.get_virtual_price()))

    def get_3crv_price(self):
        """Current 3CRV price in USD as float."""
        return get_token_price(TOKEN_3CRV_ADDR)

from data_access.contracts.util import *

class WellClient(ChainClient):
    """Client for interacting with well contracts."""

    def __init__(self, address, web3=None):
        super().__init__(web3)
        self.address = address
        self.contract = get_well_contract(self._web3, address)

    def tokens(self, web3=None):
        """Returns a list of ERC20 tokens supported by the Well."""
        return call_contract_function_with_retry(self.contract.functions.tokens())

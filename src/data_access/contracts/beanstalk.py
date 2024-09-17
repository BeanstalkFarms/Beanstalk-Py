from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class BeanstalkClient(ChainClient):
    """Common functionality related to the Beanstalk contract."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_beanstalk_contract(self._web3)

    def get_season(self):
        """Get current season."""
        return call_contract_function_with_retry(self.contract.functions.season())

    def get_weather(self):
        """Get current weather (temperature) object."""
        return call_contract_function_with_retry(self.contract.functions.weather())

    def get_season_start_soil(self):
        """Amount of soil added/removed this season."""
        return soil_to_float(self.get_weather()[0])
    
    def get_season_block(self):
        """Get the block in which the latest season started"""
        return call_contract_function_with_retry(self.contract.functions.sunriseBlock())

    def get_total_deposited_beans(self):
        """Get current total deposited Beans in the Silo."""
        return bean_to_float(
            call_contract_function_with_retry(self.contract.functions.totalDepositedBeans())
        )

    def get_total_deposited(self, address, decimals):
        """Return the total deposited of the token at address as a float."""
        return token_to_float(
            call_contract_function_with_retry(self.contract.functions.getTotalDeposited(address)),
            decimals,
        )

    def get_underlying_token(self, unripe_token):
        """Return the address of the token that will be redeemed for a given unripe token."""
        return call_contract_function_with_retry(
            self.contract.functions.getUnderlyingToken(unripe_token)
        )

    def get_recap_funded_percent(self):
        """Return the % of target funds that have already been funded via fertilizer sales."""
        # Note that % recap is same for all unripe tokens.
        return token_to_float(
            call_contract_function_with_retry(
                self.contract.functions.getRecapFundedPercent(UNRIPE_LP_ADDR)
            ),
            6,
        )

    def get_seeds(self, token, block_number='latest'):
        """Returns the current amount of Seeds awarded for depositing `token` in the silo."""
        token = Web3.to_checksum_address(token)
        token_settings = call_contract_function_with_retry(self.contract.functions.tokenSettings(token), block_number=block_number)
        return (token_settings[1] * 10000) / 10 ** STALK_DECIMALS

    def get_bdv(self, erc20_info, block_number='latest'):
        """Returns the current bdv `token`."""
        token = Web3.to_checksum_address(erc20_info.addr)
        bdv = call_contract_function_with_retry(self.contract.functions.bdv(token, 10 ** erc20_info.decimals), block_number=block_number)
        return bean_to_float(bdv)
    
    def get_token_usd_price(self, token_addr, block_number='latest'):
        response = call_contract_function_with_retry(self.contract.functions.getTokenUsdPrice(token_addr), block_number=block_number)
        return float(response / 10**6)
    
    def get_token_usd_twap(self, token_addr, lookback, block_number='latest'):
        response = call_contract_function_with_retry(self.contract.functions.getTokenUsdTwap(token_addr, lookback), block_number=block_number)
        return float(response / 10**6)

class BarnRaiseClient(ChainClient):
    """Common functionality related to the Barn Raise Fertilizer contract."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_fertilizer_contract(self._web3)

    def remaining(self):
        """Amount of USD still needed to be raised as decimal float."""
        return token_to_float(call_contract_function_with_retry(self.contract.functions.remaining()), 6)

    # def purchased(self):
    #     """Amount of fertilizer that has been purchased.

    #     Note that this is not the same as amount 'raised', since forfeit silo assets contribute
    #     to the raised amount.
    #     """
    #     return self.token_contract


if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)
    bs = BeanstalkClient()
    logging.info(f"bean seeds {bs.get_seeds(BEAN_ADDR)}")
    logging.info(f"season block {bs.get_season_block()}")
    client = EthEventsClient(EventClientType.SEASON)
    events = client.get_log_range(20566115, 20566115)
    logging.info(f"found txn: {events[0].txn_hash.hex()}")
    logging.info(f"lp bdv {bs.get_bdv(get_erc20_info(BEAN_WSTETH_ADDR), 20566115)}")

from data_access.contracts.util import *
from data_access.contracts.eth_events import *

class BeanstalkClient(ChainClient):
    """Common functionality related to the Beanstalk contract."""

    def __init__(self, web3=None):
        super().__init__(web3)
        self.contract = get_beanstalk_contract(self._web3)
        self.replant_season = 6074
        self.base_humidity = 2500 / 10
        self.final_humidity = 200 / 10
        self.humidity_step_size = 0.5  # %
        # Number of seasons to min humidity.
        self.max_steps = (self.base_humidity - self.final_humidity) / self.humidity_step_size

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

    def get_total_deposited_uni_v2_bean_eth_lp(self):
        """Get current total deposited Uniswap V2 BEAN:ETH LP in the Silo."""
        return lp_to_float(
            call_contract_function_with_retry(self.contract.functions.totalDepositedLP())
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

    def get_remaining_recapitalization(self):
        """Return the USDC amount remaining to full capitalization."""
        return usdc_to_float(
            call_contract_function_with_retry(self.contract.functions.remainingRecapitalization())
        )

    def get_target_amount(self, remaining_recap, recap_funded_percent):
        return remaining_recap / (1 - recap_funded_percent)

    def get_amount_funded(self, remaining_recap, recap_funded_percent):
        """Return amount in USDC that has already been recapitalized.

        WARNING: This is imperfect. Will vary slightly based on unknown conditions of Beanstalk.
        Use graph to acquire supply when possible.
        """
        target = self.get_target_amount(remaining_recap, recap_funded_percent)
        return target - remaining_recap

    def get_humidity(self):
        """Calculate and return current humidity."""
        current_season = self.get_season()
        if current_season <= self.replant_season:
            return self.base_humidity
        elif current_season > self.replant_season + self.max_steps:
            return self.final_humidity
        return self.base_humidity - (current_season - self.replant_season) * self.humidity_step_size

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

class BarnRaiseClient(ChainClient):
    """Common functionality related to the Barn Raise Fertilizer contract."""

    def __init__(self, web3=None, beanstalk_client=None):
        super().__init__(web3)
        self.contract = get_fertilizer_contract(self._web3)
        # self.token_contract = get_fertilizer_token_contract(self._web3)
        # Set immutable variables.
        self.barn_raise_start = 1654516800  # seconds, epoch
        self.unpause_start = 1660564800  # seconds, epoch # August 15 2022, 12pm
        self.replant_season = 6074
        # self.pre_sale_humidity = 5000 / 10
        self.base_humidity = 2500 / 10
        self.step_size = 0.5  # %
        self.step_duration = 3600  # seconds
        if beanstalk_client is not None:
            self.beanstalk_client = beanstalk_client
        else:
            self.beanstalk_client = BeanstalkClient()

    def get_humidity(self):
        """Calculate and return current humidity."""
        # If unpause has not yet occurred, return 0.
        return self.beanstalk_client.get_humidity()

    def weather_at_step(self, step_number):
        """Return the weather at a given step."""
        return step_number + self.base_weather

    def seconds_until_step_end(self):
        """Calculate and return the seconds until the current humidity step ends."""
        unpaused_time = time.time() - self.unpause_start
        # If barn raise has not yet started, return time to unpause.
        if unpaused_time < 0:
            return abs(unpaused_time)
        return unpaused_time % self.step_duration

    def remaining(self):
        """Amount of USDC still needed to be raised as decimal float."""
        return usdc_to_float(call_contract_function_with_retry(self.contract.functions.remaining()))

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
    logging.info(f"lp bdv {bs.get_bdv(get_erc20_info(BEAN_WSTETH_WELL_ADDR), 20566115)}")

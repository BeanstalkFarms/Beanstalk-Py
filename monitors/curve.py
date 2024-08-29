from data_access.coin_gecko import get_token_price

from bots.util import *
from monitors.monitor import Monitor
from data_access.eth_chain import *
from data_access.graphs import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

class CurvePoolMonitor(Monitor):
    """Monitor a Curve pool for events."""

    def __init__(self, message_function, pool_type, prod=False, dry_run=None):
        if pool_type is EventClientType.CURVE_BEAN_3CRV_POOL:
            name = "Bean:3CRV Curve Pool"
        else:
            raise ValueError("Curve pool must be set to a supported pool.")
        super().__init__(name, message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_type = pool_type
        self._eth_event_client = EthEventsClient(self.pool_type)
        self.bean_client = BeanClient()
        self.three_pool_client = CurveClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + POOL_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the curve pool event logs for a single txn.

        Assumes that there are no non-Bean:3CRV TokenExchangeUnderlying events in logs.
        Note that Event Log Object is not the same as Event object.
        """
        # NOTE(funderberker): Using txn function to determine what is happening no longer works
        # because nearly everything is embedded into farm(bytes[] data) calls.
        # Ignore Silo Convert txns, which will be handled by the Beanstalk monitor.
        if event_sig_in_txn(BEANSTALK_EVENT_MAP["Convert"], txn_hash):
            logging.info("Ignoring pool txn, reporting as convert instead.")
            return

        if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
            bean_price = self.bean_client.curve_bean_3crv_bean_price()
        # No default since each pool must have support manually built in.
        for event_log in event_logs:
            event_str = self.any_event_str(event_log, bean_price)
            if event_str:
                self.message_function(event_str)

    def any_event_str(self, event_log, bean_price):
        event_str = ""
        # Parse possible values of interest from the event log. Not all will be populated.
        sold_id = event_log.args.get("sold_id")
        tokens_sold = event_log.args.get("tokens_sold")
        bought_id = event_log.args.get("bought_id")
        tokens_bought = event_log.args.get("tokens_bought")
        token_amounts = event_log.args.get("token_amounts")
        # Coin is a single ERC20 token, token is the pool token. So Coin can be Bean or 3CRV.
        token_amount = event_log.args.get("token_amount")
        coin_amount = event_log.args.get("coin_amount")

        value = None
        if token_amounts is not None:
            bean_amount = bean_to_float(token_amounts[FACTORY_3CRV_INDEX_BEAN])
            if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
                crv_amount = crv_to_float(token_amounts[FACTORY_3CRV_INDEX_3CRV])
                token_name = "3CRV"
                crv_value = self.three_pool_client.get_3crv_price()
            value = bean_amount * bean_price + crv_amount * crv_value
        # RemoveLiquidityOne.
        if coin_amount is not None:
            if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
                lp_value = self.bean_client.curve_bean_3crv_lp_value()
                lp_amount = token_to_float(token_amount, CRV_DECIMALS)
            value = lp_amount * lp_value

        if event_log.event == "TokenExchangeUnderlying" or event_log.event == "TokenExchange":
            # Set the variables of quantity and direction of exchange.
            bean_out = stable_in = bean_in = stable_out = None
            if bought_id in [FACTORY_3CRV_UNDERLYING_INDEX_BEAN]:
                bean_out = bean_to_float(tokens_bought)
                stable_in = tokens_sold
                stable_id = sold_id
            elif sold_id in [FACTORY_3CRV_UNDERLYING_INDEX_BEAN]:
                bean_in = bean_to_float(tokens_sold)
                stable_out = tokens_bought
                stable_id = bought_id
            else:
                logging.warning("Exchange detected between two non-Bean tokens. Ignoring.")
                return ""

            # Set the stable name string and convert value to float.
            if event_log.event == "TokenExchange":
                stable_name = "3CRV"
                stable_in = crv_to_float(stable_in)
                stable_out = crv_to_float(stable_out)
                stable_price = self.three_pool_client.get_3crv_price()
            elif stable_id == FACTORY_3CRV_UNDERLYING_INDEX_DAI:
                stable_name = "DAI"
                stable_in = dai_to_float(stable_in)
                stable_out = dai_to_float(stable_out)
                stable_price = get_token_price(DAI)
            elif stable_id == FACTORY_3CRV_UNDERLYING_INDEX_USDC:
                stable_name = "USDC"
                stable_in = usdc_to_float(stable_in)
                stable_out = usdc_to_float(stable_out)
                stable_price = get_token_price(USDC)
            elif stable_id == FACTORY_3CRV_UNDERLYING_INDEX_USDT:
                stable_name = "USDT"
                stable_in = usdt_to_float(stable_in)
                stable_out = usdt_to_float(stable_out)
                stable_price = get_token_price(USDT)
            else:
                logging.error(f"Unexpected stable_id seen ({stable_id}) in exchange. Ignoring.")
                return ""

            event_str += self.exchange_event_str(
                stable_name,
                stable_price,
                bean_out=bean_out,
                bean_in=bean_in,
                stable_in=stable_in,
                stable_out=stable_out,
            )
        elif event_log.event == "AddLiquidity":
            event_str += f"📥 LP added - {round_num(bean_amount, 0)} Beans and {round_num(crv_amount, 0)} {token_name} ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        elif event_log.event == "RemoveLiquidity" or event_log.event == "RemoveLiquidityImbalance":
            event_str += f"📤 LP removed - {round_num(bean_amount, 0)} Beans and {round_num(crv_amount, 0)} {token_name} ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        elif event_log.event == "RemoveLiquidityOne":
            event_str += f"📤 LP removed - "
            if self.pool_type == EventClientType.CURVE_BEAN_3CRV_POOL:
                # If 6 decimal then it must be Bean that was withdrawn. 18 decimal is 3CRV.
                if is_6_not_18_decimal_token_amount(coin_amount):
                    event_str += f"{round_num(bean_to_float(coin_amount), 0)} Beans"
                else:
                    event_str += f"{round_num(crv_to_float(coin_amount), 0)} 3CRV"
            event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
            event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        else:
            logging.warning(
                f"Unexpected event log seen in Curve Pool ({event_log.event}). Ignoring."
            )
            return ""

        if value is not None:
            event_str += f"\n{value_to_emojis(value)}"
        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def exchange_event_str(
        self,
        stable_name,
        stable_price,
        stable_in=None,
        bean_in=None,
        stable_out=None,
        bean_out=None,
    ):
        """Generate a standard token exchange string."""
        event_str = ""
        if (not stable_in and not bean_in) or (not stable_out and not bean_out):
            logging.error("Must set at least one input and one output of swap.")
            return ""
        if (stable_in and bean_in) or (stable_out and bean_out):
            logging.error("Cannot set two inputs or two outputs of swap.")
            return ""
        if stable_in:
            event_str += f"📗 {round_num(bean_out, 0)} {get_erc20_info(BEAN_ADDR).symbol} bought for {round_num(stable_in, 0)} {stable_name}"
            swap_value = stable_in * stable_price
            swap_price = swap_value / bean_out
        elif bean_in:
            event_str += f"📕 {round_num(bean_in, 0)} {get_erc20_info(BEAN_ADDR).symbol} sold for {round_num(stable_out, 0)} {stable_name}"
            # If this is a sale of Beans for a fertilizer purchase.
            swap_value = stable_out * stable_price
            swap_price = swap_value / bean_in
        event_str += f" @ ${round_num(swap_price, 4)} ({round_num(swap_value, 0, avoid_zero=True, incl_dollar=True)})"
        event_str += f"\n_{latest_pool_price_str(self.bean_client, CURVE_BEAN_3CRV_ADDR)}_ "
        event_str += f"\n{value_to_emojis(swap_value)}"
        return event_str

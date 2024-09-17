from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.well import WellClient
from data_access.subgraphs.basin import BasinGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class AllWellsMonitor(Monitor):
    def __init__(self, message_function, ignorelist, discord=False, prod=False, dry_run=None):
        super().__init__("wells", message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self._ignorelist = ignorelist
        self._discord = discord
        self._eth_aquifer = EthEventsClient(EventClientType.AQUIFER, AQUIFER_ADDR)
        # All addresses
        self._eth_all_wells = EthEventsClient(EventClientType.WELL, address=None)
        self.basin_graph_client = BasinGraphClient()
        self.bean_client = BeanClient()
    
    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_aquifer.get_new_logs(dry_run=self._dry_run):
                for event_log in txn_pair.logs:
                    event_str = self.aquifer_event_str(event_log)
                    if event_str:
                        self.message_function(event_str)
            for txn_pair in self._eth_all_wells.get_new_logs(dry_run=self._dry_run):
                for event_log in txn_pair.logs:
                    # Avoids double-reporting on whitelisted wells having a dedicated channel
                    if event_log.get("address") not in self._ignorelist:
                        event_str = well_event_str(event_log, False, self.basin_graph_client, self.bean_client, web3=self._web3)
                        if event_str:
                            self.message_function(event_str)

    def aquifer_event_str(self, event_log):
        if event_log.event == "BoreWell":
            well = event_log.args.get("well")
            tokens = event_log.args.get("tokens")

            erc20_info_0 = get_erc20_info(tokens[0])
            erc20_info_1 = get_erc20_info(tokens[1])

            def erc20_linkstr(info):
                result = f"[{info.symbol}](<https://etherscan.io/address/{info.addr.lower()}>)"
                # Embellish with discord emojis
                if self._discord:
                    if info.symbol == "BEAN":
                        result = '<:bean:1256384062340464750> ' + result
                return result

            event_str = (
                f"{'<:basin:1256383927610769478> ' if self._discord else ''} New Well created - {erc20_linkstr(erc20_info_0)} / {erc20_linkstr(erc20_info_1)}"
                f"\n<https://basin.exchange/#/wells/{well.lower()}>"
            )
            event_str += "\n_ _"
            return event_str

# Monitors a specific Well.
# NOTE arguments for doing 1 monitor for all wells and 1 monitor per well. In first pass wells will each get their
#      own discord channel, which will require human intervention in this code anyway, so going to go for 1 channel
#      per well for now.
class WellMonitor(Monitor):
    """Monitor Wells for events.

    This provides events in Beanstalk exchange channel as well as Basin per-well channels.

    NOTE assumption that all wells contain Bean. Valuation is done in BDV using the bean side of the trade to
         directly determine value.
    ^^ make this assumption less strict, instead only skip valuation if no BDV
    """

    def __init__(self, message_function, address, bean_reporting=False, prod=False, dry_run=None):
        super().__init__(f"specific well", message_function, POOL_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.pool_type = EventClientType.WELL
        self.pool_address = address
        self._eth_event_client = EthEventsClient(self.pool_type, self.pool_address)
        self.basin_graph_client = BasinGraphClient()
        self.bean_client = BeanClient()
        self.bean_reporting = bean_reporting

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the well event logs for a single txn."""
        # Sometimes ignore Silo Convert txns, which will be handled by the Beanstalk monitor.
        if self.bean_reporting is True and event_sig_in_txn(
            BEANSTALK_EVENT_MAP["Convert"], txn_hash
        ):
            logging.info("Ignoring well txn, reporting as convert instead.")
            return

        for event_log in event_logs:
            if event_log.get("address") == self.pool_address:
                event_str = well_event_str(event_log, self.bean_reporting, self.basin_graph_client, self.bean_client, web3=self._web3)
                if event_str:
                    self.message_function(event_str)
    
def well_event_str(event_log, bean_reporting, basin_graph_client, bean_client, web3=None):
    bdv = value = None
    event_str = ""
    address = event_log.get("address")
    # Parse possible values of interest from the event log. Not all will be populated.
    fromToken = event_log.args.get("fromToken")
    toToken = event_log.args.get("toToken")
    amountIn = event_log.args.get("amountIn")
    amountOut = event_log.args.get("amountOut")
    # recipient = event_log.args.get('recipient')
    tokenAmountsIn = event_log.args.get("tokenAmountsIn")  # int[]
    lpAmountOut = event_log.args.get("lpAmountOut")  # int
    lpAmountIn = event_log.args.get("lpAmountIn")
    tokenOut = event_log.args.get("tokenOut")
    tokenAmountOut = event_log.args.get("tokenAmountOut")
    tokenAmountsOut = event_log.args.get("tokenAmountsOut")
    #  = event_log.args.get('reserves')
    lpAmountOut = event_log.args.get("lpAmountOut")

    well_client = WellClient(address)
    tokens = well_client.tokens()

    is_swapish = False
    is_lpish = False

    if event_log.event == "AddLiquidity":
        is_lpish = True
        event_str += f"📥 LP added - "
        for i in range(len(tokens)):
            erc20_info = get_erc20_info(tokens[i])
            event_str += f"{round_token(tokenAmountsIn[i], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}"
            if i < len(tokens) - 1:
                event_str += " and"
            event_str += f" "
        bdv = token_to_float(lpAmountOut, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(
            address, web3=web3
        )
    elif event_log.event == "Sync":
        is_lpish = True
        event_str += f"📥 LP added - "
        # subgraph may be down, providing no deposit data.
        deposit = basin_graph_client.try_get_well_deposit_info(
            event_log.transactionHash, event_log.logIndex
        )
        if deposit:
            for i in range(len(tokens)):
                erc20_info = get_erc20_info(tokens[i])
                event_str += f'{round_token(deposit["reserves"][i], erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}'
                if i < len(tokens) - 1:
                    event_str += " and"
                event_str += f" "
            value = float(deposit["amountUSD"])
        else:
            bdv = token_to_float(
                lpAmountOut, WELL_LP_DECIMALS
            ) * get_constant_product_well_lp_bdv(address, web3=web3)
    elif event_log.event == "RemoveLiquidity" or event_log.event == "RemoveLiquidityOneToken":
        is_lpish = True
        event_str += f"📤 LP removed - "
        for i in range(len(tokens)):
            erc20_info = get_erc20_info(tokens[i])
            if event_log.event == "RemoveLiquidityOneToken":
                if tokenOut == tokens[i]:
                    out_amount = tokenAmountOut
                else:
                    out_amount = 0
            else:
                out_amount = tokenAmountsOut[i]
            event_str += f"{round_token(out_amount, erc20_info.decimals, erc20_info.addr)} {erc20_info.symbol}"

            if i < len(tokens) - 1:
                event_str += f" and"
            event_str += f" "
        bdv = token_to_float(lpAmountIn, WELL_LP_DECIMALS) * get_constant_product_well_lp_bdv(
            address, web3=web3
        )
    elif event_log.event == "Swap":
        is_swapish = True
        # value = lpAmountIn * lp_value
        erc20_info_in = get_erc20_info(fromToken)
        erc20_info_out = get_erc20_info(toToken)
        amount_in = amountIn
        amount_in_str = round_token(amount_in, erc20_info_in.decimals, erc20_info_in.addr)
        amount_out = amountOut
        amount_out_str = round_token(amount_out, erc20_info_out.decimals, erc20_info_out.addr)
        if fromToken == BEAN_ADDR:
            bdv = bean_to_float(amountIn)
        elif toToken == BEAN_ADDR:
            bdv = bean_to_float(amountOut)
    elif event_log.event == "Shift":
        shift_from_token = tokens[0] if tokens[1] == toToken else tokens[1]

        erc20_info_in = get_erc20_info(shift_from_token)
        erc20_info_out = get_erc20_info(toToken)

        amount_in = None

        if shift_from_token == WRAPPED_ETH:
            amount_in = get_eth_sent(event_log.transactionHash, address, web3, event_log.logIndex)
        else:
            amount_in = get_tokens_sent(shift_from_token, event_log.transactionHash, event_log.address, event_log.logIndex)

        if toToken == BEAN_ADDR:
            bdv = bean_to_float(amountOut)
        elif shift_from_token == BEAN_ADDR:
            bdv = bean_to_float(amount_in)

        erc20_info_in = get_erc20_info(shift_from_token)
        amount_in_str = round_token(amount_in, erc20_info_in.decimals, erc20_info_in.addr)

        amount_out = amountOut
        amount_out_str = round_token(amount_out, erc20_info_out.decimals, erc20_info_out.addr)
        if (
            amount_in is not None and amount_in > 0
        ):  # not None and not 0, then it is a pseudo swap
            is_swapish = True
        else:  # one sided shift
            event_str += f"🔀 {amount_out_str} {erc20_info_out.symbol} shifted out "
    else:
        logging.warning(f"Unexpected event log seen in Well ({event_log.event}). Ignoring.")
        return ""

    if bdv is not None:
        value = bdv * bean_client.avg_bean_price()

    if is_swapish:
        if bean_reporting and erc20_info_out.symbol == "BEAN":
            event_str += f"📗 {amount_out_str} {erc20_info_out.symbol} bought for {amount_in_str} {erc20_info_in.symbol} @ ${round_num(value/bean_to_float(amount_out), 4)} "
        elif bean_reporting and erc20_info_in.symbol == "BEAN":
            event_str += f"📕 {amount_in_str} {erc20_info_in.symbol} sold for {amount_out_str} {erc20_info_out.symbol} @ ${round_num(value/bean_to_float(amount_in), 4)} "
        else:
            event_str += (
                f"🔁 {amount_in_str} {erc20_info_in.symbol} swapped "
                f"for {amount_out_str} {erc20_info_out.symbol} "
            )

    if value is not None and value != 0:
        event_str += f"({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
        if (is_swapish or is_lpish) and bean_reporting:
            event_str += f"\n_{latest_pool_price_str(bean_client, address)}_ "
        if is_lpish and not bean_reporting:
            liqudity_usd = latest_well_lp_str(basin_graph_client, address)
            if liqudity_usd != 0:
                event_str += f"\n_{liqudity_usd}_ "
        event_str += f"\n{value_to_emojis(value)}"

    event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
    # Empty line that does not get stripped.
    event_str += "\n_ _"
    return event_str

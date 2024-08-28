class BeanstalkMonitor(Monitor):
    """Monitor the Beanstalk contract for events."""

    def __init__(self, message_function, prod=False, dry_run=False):
        super().__init__(
            "Beanstalk", message_function, BEANSTALK_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        self._eth_event_client = EthEventsClient(EventClientType.BEANSTALK)
        self.bean_client = BeanClient()
        self.beanstalk_client = BeanstalkClient()

    def _monitor_method(self):
        last_check_time = 0
        while self._thread_active:
            if time.time() < last_check_time + BEANSTALK_CHECK_RATE:
                time.sleep(0.5)
                continue
            last_check_time = time.time()
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                self._handle_txn_logs(txn_pair.txn_hash, txn_pair.logs)

    def _handle_txn_logs(self, txn_hash, event_logs):
        """Process the beanstalk event logs for a single txn.

        Note that Event Log Object is not the same as Event object.
        """
        # logging.warning(f'handling {txn_hash} logs...')
        # Prune *plant* deposit logs. They are uninteresting clutter.
        # Prune *pick* deposit logs. They are uninteresting clutter.
        # For each earn (plant/pick) event log remove a corresponding AddDeposit log.
        # for earn_event_log in get_logs_by_names(['Plant'], event_logs):
        for earn_event_log in get_logs_by_names(["Plant", "Pick"], event_logs):
            for deposit_event_log in get_logs_by_names("AddDeposit", event_logs):
                if deposit_event_log.args.get("token") == (
                    earn_event_log.args.get("token") or BEAN_ADDR
                ) and deposit_event_log.args.get("amount") == (
                    earn_event_log.args.get("beans") or earn_event_log.args.get("amount")
                ):
                    # Remove event log from event logs
                    event_logs.remove(deposit_event_log)
                    # At most allow 1 match.
                    logging.info(
                        f"Ignoring a {earn_event_log.event} AddDeposit event {txn_hash.hex()}"
                    )
                    break

        if event_in_logs("ClaimFertilizer", event_logs):
            event_str = self.rinse_str(event_logs)
            if event_str:
                self.message_function(event_str)
            remove_events_from_logs_by_name("ClaimFertilizer", event_logs)

        # Process conversion logs as a batch.
        if event_in_logs("Convert", event_logs):
            self.message_function(self.silo_conversion_str(event_logs))
            return
        # Else handle txn logs individually using default strings.

        # Prune *transfer* deposit logs. They are uninteresting clutter.
        # Note that this assumes that a transfer event never includes a novel deposit.
        remove_event_logs = get_logs_by_names(["RemoveDeposit", "RemoveDeposits"], event_logs)
        deposit_event_logs = get_logs_by_names("AddDeposit", event_logs)
        for remove_event_log in remove_event_logs:
            for deposit_event_log in deposit_event_logs:
                if deposit_event_log.args.get("token") == remove_event_log.args.get("token"):
                    # and deposit_event_log.args.get('amount') == \
                    # (remove_event_log.args.get('amount'))):
                    # Remove event log from event logs
                    try:
                        event_logs.remove(remove_event_log)
                    except ValueError:
                        pass
                    try:
                        event_logs.remove(deposit_event_log)
                    except ValueError:
                        pass
                    logging.info(
                        f"Ignoring a AddDeposit RemoveDeposit(s) pair {txn_hash.hex()}, possible transfer or silo migration"
                    )

        for event_log in event_logs:
            event_str = self.single_event_str(event_log)
            if event_str:
                self.message_function(event_str)

    def single_event_str(self, event_log):
        """Create a string representing a single event log.

        Events that are from a convert call should not be passed into this function as they
        should be processed in batch.
        """

        event_str = ""
        bean_price = self.bean_client.avg_bean_price()

        # Ignore these events. They are uninteresting clutter.
        if event_log.event in ["RemoveWithdrawal", "RemoveWithdrawals" "Plant", "Pick"]:
            return ""

        # Deposit & Withdraw events.
        elif event_log.event in ["AddDeposit", "RemoveDeposit", "RemoveDeposits"]:
            # Pull args from the event log.
            token_address = event_log.args.get("token")
            token_amount_long = event_log.args.get("amount")  # AddDeposit, AddWithdrawal

            _, _, token_symbol, decimals = get_erc20_info(token_address, web3=self._web3).parse()
            amount = token_to_float(token_amount_long, decimals)

            # Use current bdv rather than the deposited bdv reported in the event
            bdv = amount * self.beanstalk_client.get_bdv(get_erc20_info(token_address))

            value = None
            if bdv > 0:
                value = bdv * bean_price

            if event_log.event in ["AddDeposit"]:
                event_str += f"📥 Silo Deposit"
            elif event_log.event in ["RemoveDeposit", "RemoveDeposits"]:
                event_str += f"📭 Silo Withdrawal"
            else:
                return ""

            event_str += f" - {round_num_auto(amount, min_precision=0)} {token_symbol}"
            # Some legacy events may not set BDV, skip valuation. Also do not value unripe assets.
            if value is not None and not token_address.startswith(UNRIPE_TOKEN_PREFIX):
                event_str += f" ({round_num(value, 0, avoid_zero=True, incl_dollar=True)})"
                event_str += f"\n{value_to_emojis(value)}"

        # Sow event.
        elif event_log.event in ["Sow", "Harvest"]:
            # Pull args from the event log.
            beans_amount = bean_to_float(event_log.args.get("beans"))
            beans_value = beans_amount * bean_price
            pods_amount = bean_to_float(event_log.args.get("pods"))

            if event_log.event == "Sow":
                event_str += (
                    f"🚜 {round_num(beans_amount, 0, avoid_zero=True)} Beans Sown for "
                    f"{round_num(pods_amount, 0, avoid_zero=True)} Pods ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                )
                event_str += f"\n{value_to_emojis(beans_value)}"
            elif event_log.event == "Harvest":
                event_str += f"👩‍🌾 {round_num(beans_amount, 0, avoid_zero=True)} Pods Harvested for Beans ({round_num(beans_value, 0, avoid_zero=True, incl_dollar=True)})"
                event_str += f"\n{value_to_emojis(beans_value)}"

        # Chop event.
        elif event_log.event in ["Chop"]:
            token = event_log.args.get("token")
            underlying = self.beanstalk_client.get_underlying_token(token)
            _, _, chopped_symbol, chopped_decimals = get_erc20_info(token, self._web3).parse()
            chopped_amount = token_to_float(event_log.args.get("amount"), chopped_decimals)
            _, _, underlying_symbol, underlying_decimals = get_erc20_info(
                underlying, self._web3
            ).parse()
            underlying_amount = token_to_float(
                event_log.args.get("underlying"), underlying_decimals
            )
            if underlying == BEAN_ADDR:
                underlying_token_value = bean_price
            # If underlying assets are Bean-based LP represented in price aggregator.
            # If not in aggregator, will return none and not display value.
            else:
                underlying_token_value = self.bean_client.get_curve_lp_token_value(
                    underlying, underlying_decimals
                )
            event_str += f"⚰️ {round_num(chopped_amount, 0)} {chopped_symbol} Chopped for {round_num(underlying_amount, 0, avoid_zero=True)} {underlying_symbol}"
            if underlying_token_value is not None:
                underlying_value = underlying_amount * underlying_token_value
                event_str += (
                    f" ({round_num(underlying_value, 0, avoid_zero=True, incl_dollar=True)})"
                )
                event_str += f"\n{value_to_emojis(underlying_value)}"

        # Unknown event type.
        else:
            logging.warning(
                f"Unexpected event log from Beanstalk contract ({event_log}). Ignoring."
            )
            return ""

        event_str += f"\n<https://etherscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def silo_conversion_str(self, event_logs):
        """Create a human-readable string representing a silo position conversion.

        Assumes that there are no non-Bean swaps contained in the event logs.
        Assumes event_logs is not empty.
        Assumes embedded AddDeposit logs have been removed from logs.
        Uses events from Beanstalk contract.
        """
        bean_price = self.bean_client.avg_bean_price()
        # Find the relevant logs, should contain one RemoveDeposit and one AddDeposit.
        # print(event_logs)
        # in silo v3 AddDeposit event will always be present and these will always get set
        bdv_float = 0
        value = 0
        for event_log in event_logs:
            if event_log.event == "AddDeposit":
                bdv_float = bean_to_float(event_log.args.get("bdv"))
                value = bdv_float * bean_price
            elif event_log.event == "Convert":
                remove_token_addr = event_log.args.get("fromToken")
                _, _, remove_token_symbol, remove_decimals = get_erc20_info(
                    remove_token_addr, web3=self._web3
                ).parse()
                add_token_addr = event_log.args.get("toToken")
                _, _, add_token_symbol, add_decimals = get_erc20_info(
                    add_token_addr, web3=self._web3
                ).parse()
                remove_float = token_to_float(event_log.args.get("fromAmount"), remove_decimals)
                add_float = token_to_float(event_log.args.get("toAmount"), add_decimals)

        pool_token = BEAN_ADDR
        if remove_token_addr == CURVE_BEAN_3CRV_ADDR or add_token_addr == CURVE_BEAN_3CRV_ADDR:
            pool_token = CURVE_BEAN_3CRV_ADDR
        elif remove_token_addr == BEAN_ETH_WELL_ADDR or add_token_addr == BEAN_ETH_WELL_ADDR:
            pool_token = BEAN_ETH_WELL_ADDR
        elif remove_token_addr in [BEAN_WSTETH_WELL_ADDR, UNRIPE_LP_ADDR] or add_token_addr in [
            BEAN_WSTETH_WELL_ADDR,
            UNRIPE_LP_ADDR,
        ]:
            pool_token = BEAN_WSTETH_WELL_ADDR

        if remove_token_symbol.startswith("ur") and not add_token_symbol.startswith("ur"):
            # Chop convert
            event_str = (
                f"⚰️ {round_num_auto(remove_float, min_precision=0)} {remove_token_symbol} "
                f"Convert-Chopped to {round_num_auto(add_float, min_precision=0)} {add_token_symbol} "
            )
        else:
            # Normal convert
            event_str = (
                f"🔄 {round_num_auto(remove_float, min_precision=0)} {remove_token_symbol} "
                f"Converted to {round_num_auto(add_float, min_precision=0)} {add_token_symbol} "
            )
        # if (not remove_token_addr.startswith(UNRIPE_TOKEN_PREFIX)):
        event_str += f"({round_num(bdv_float, 0)} BDV)"
        pool_type_str = f""
        event_str += f"\n_{latest_pool_price_str(self.bean_client, pool_token)}_ "
        if not remove_token_addr.startswith(UNRIPE_TOKEN_PREFIX):
            event_str += f"\n{value_to_emojis(value)}"
        event_str += f"\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        return event_str

    def rinse_str(self, event_logs):
        bean_amount = 0.0
        for event_log in event_logs:
            if event_log.event == "ClaimFertilizer":
                bean_amount += bean_to_float(event_log.args.beans)
        # Ignore rinses with essentially no beans bc they are clutter, especially on transfers.
        if bean_amount < 1:
            return ""
        bean_price = self.bean_client.avg_bean_price()
        event_str = f"💦 Sprouts Rinsed - {round_num(bean_amount,0)} Sprouts ({round_num(bean_amount * bean_price, 0, avoid_zero=True, incl_dollar=True)})"
        event_str += f"\n{value_to_emojis(bean_amount * bean_price)}"
        event_str += f"\n<https://etherscan.io/tx/{event_logs[0].transactionHash.hex()}>"
        return event_str

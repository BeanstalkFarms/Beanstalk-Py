from bots.util import *
from monitors.monitor import Monitor
from data_access.contracts.util import *
from data_access.contracts.eth_events import *
from data_access.contracts.bean import BeanClient
from data_access.contracts.beanstalk import BarnRaiseClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class BarnRaiseMonitor(Monitor):
    def __init__(
        self,
        message_function,
        report_events=True,
        report_summaries=False,
        prod=False,
        dry_run=None,
    ):
        super().__init__(
            "BarnRaise", message_function, BARN_RAISE_CHECK_RATE, prod=prod, dry_run=dry_run
        )
        # Used for special init cases
        # self.SUMMARY_BLOCK_RANGE = self._web3.eth.get_block('latest').number - 14918083
        self.SUMMARY_BLOCK_RANGE = 1430  # ~ 6 hours
        # self.SUMMARY_BLOCK_RANGE = 5720 + 1192 # ~ 24 hours, offset by 5 hours
        self.EMOJI_RANKS = ["🥇", "🥈", "🥉"]
        self.report_events = report_events
        self.report_summaries = report_summaries
        self.bean_client = BeanClient()
        self.barn_raise_client = BarnRaiseClient()
        self._eth_event_client = EthEventsClient(EventClientType.BARN_RAISE)
        self.beanstalk_graph_client = BeanstalkGraphClient()
        self.last_total_bought = self.beanstalk_graph_client.get_fertilizer_bought()

    def _monitor_method(self):
        last_check_time = 0

        while self._thread_active:
            # Wait until check rate time has passed.
            if time.time() < last_check_time + self.query_rate:
                time.sleep(0.5)
                continue
            last_check_time = time.time()

            # If reporting summaries and a 6 hour block has passed.
            if self.report_summaries:
                current_block = safe_get_block(self._web3, "latest")
                if (current_block.number - 14915799) % self.SUMMARY_BLOCK_RANGE == 0:
                    # if True:
                    from_block = safe_get_block(
                        self._web3, current_block.number - self.SUMMARY_BLOCK_RANGE
                    )
                    time_range = current_block.timestamp - from_block.timestamp
                    all_events_in_time_range = []
                    for txn_pair in self._eth_event_client.get_log_range(
                        from_block=from_block.number, to_block=current_block.number
                    ):
                        event_logs = txn_pair.logs
                        all_events_in_time_range.extend(event_logs)
                    # Do not report a summary if nothing happened.
                    if len(all_events_in_time_range) == 0:
                        logging.info("No events detected to summarize. Skipping summary.")
                        continue
                    # Sort events based on size.
                    all_events_in_time_range = sorted(
                        all_events_in_time_range,
                        key=lambda event: event.args.get("value") or sum(event.args.get("values")),
                        reverse=True,
                    )
                    # all_events_in_time_range = sorted(all_events_in_time_range, lambda(event: int(event.args.value)))
                    total_raised = 0
                    for event in all_events_in_time_range:
                        usdc_amount = int(event.args.value)
                        total_raised += usdc_amount
                    msg_str = f"🚛 In the past {round_num(time_range/3600, 1)} hours, ${round_num(total_raised, 0)} was raised from {len(all_events_in_time_range)} txns"
                    remaining = self.barn_raise_client.remaining()
                    msg_str += f"\n🪴 {round_num(remaining, 0)} Fertilizer remaining"
                    msg_str += f"\n"
                    for i in range(3):
                        try:
                            event = all_events_in_time_range[i]
                        # There may not be 3 events in a time block.
                        except IndexError:
                            break
                        # msg_str += f'\n{self.EMOJI_RANKS[i]} ${round_num(event.args.value, 0)} ({event.args["to"]})' # {event.transactionHash.hex()}
                        msg_str += f"\n{self.EMOJI_RANKS[i]} ${round_num(event.args.value, 0)} (https://arbiscan.io/tx/{event.transactionHash.hex()})"

                    self.message_function(msg_str)

            # If reporting events.
            if self.report_events:
                # Check for new Bids, Bid updates, and Sows.
                all_events = []
                for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                    all_events.extend(txn_pair.logs)
                for event_log in all_events:
                    self._handle_event_log(event_log)

    def _handle_event_log(self, event_log):
        """Process a single event log for the Barn Raise."""
        # Mint single.
        if (
            event_log.address == FERTILIZER_ADDR
            and event_log.event in ["TransferSingle", "TransferBatch"]
            and event_log.args["from"] == NULL_ADDR
        ):
            if event_log.event == "TransferSingle":
                amount = int(event_log.args.value)
            # Mint batch.   <- is this even possible???
            elif event_log.event == "TransferBatch":
                amount = sum([int(value) for value in event_log.args.values])

            wsteth_amount = token_to_float(
                get_tokens_sent(WSTETH, event_log.transactionHash, event_log.address, event_log.logIndex), 18
            )

            event_str = f"🚛 Fertilizer Purchased - {round_num(amount, 0)} Fert for {round_num(wsteth_amount, 3)} wstETH @ 20% Humidity"
            total_bought = self.beanstalk_graph_client.get_fertilizer_bought()

            # The subgraph is slower to update, so may need to calculate total bought here.
            if total_bought <= self.last_total_bought + 1:
                self.last_total_bought = total_bought + amount
            else:
                self.last_total_bought = total_bought

            event_str += f" - Total sold: {round_num(self.last_total_bought, 0)}"
            # event_str += f' ({round_num(self.barn_raise_client.remaining(), 0)} Available Fertilizer)'
            event_str += f"\n{value_to_emojis(amount)}"
        # Transfer or some other uninteresting transaction.
        else:
            return

        event_str += f"\n<https://arbiscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        self.message_function(event_str)
        logging.info(f"\n\n\nfull barn message here {event_str}\n\n\n")

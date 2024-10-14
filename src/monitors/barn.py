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
        prod=False,
        dry_run=None,
    ):
        super().__init__(
            "BarnRaise", message_function, BARN_RAISE_CHECK_RATE, prod=prod, dry_run=dry_run
        )
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

            all_events = []
            for txn_pair in self._eth_event_client.get_new_logs(dry_run=self._dry_run):
                event_logs = txn_pair.logs
                if event_in_logs("L1FertilizerMigrated", event_logs):
                    # Ignore fertilizer mint as a result of contract migrating barn
                    remove_events_from_logs_by_name("TransferSingle", event_logs)
                all_events.extend(event_logs)
            for event_log in all_events:
                self._handle_event_log(event_log)

    def _handle_event_log(self, event_log):
        """Process a single event log for the Barn Raise."""
        # Mint single.
        if (
            event_log.address == FERTILIZER_ADDR
            and event_log.event in ["TransferSingle"]
            and event_log.args["from"] == NULL_ADDR
        ):
            amount = int(event_log.args.value)
            self.last_total_bought += amount

            wsteth_amount = token_to_float(
                get_tokens_sent(WSTETH, event_log.transactionHash, event_log.address, event_log.logIndex), 18
            )

            event_str = f"🚛 Fertilizer Purchased - {round_num(amount, 0)} Fert for {round_num(wsteth_amount, 3)} wstETH @ 20% Humidity"
            event_str += f" - Total sold: {round_num(self.last_total_bought, 0)}"
            event_str += f"\n{value_to_emojis(amount)}"
        else:
            # Transfer or some other uninteresting transaction.
            return

        event_str += f"\n<https://arbiscan.io/tx/{event_log.transactionHash.hex()}>"
        # Empty line that does not get stripped.
        event_str += "\n_ _"
        self.message_function(event_str)

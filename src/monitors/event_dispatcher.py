import logging
import time
from collections import Counter

from constants.addresses import *
from constants.config import *
from data_access.contracts.eth_events import *
from data_access.contracts.util import get_rpc_request_counts
from monitors.monitor import Monitor


class EventRoute:
    def __init__(self, name, monitor, event_names, handler, addresses=None):
        self.name = name
        self.monitor = monitor
        self.event_names = set(event_names)
        self.handler = handler
        self.addresses = {addr.lower() for addr in addresses} if addresses else None

    def logs_for_txn(self, txn_pair):
        route_logs = []
        for log in txn_pair.logs:
            if log.event not in self.event_names:
                continue
            if self.addresses is not None and log.address.lower() not in self.addresses:
                continue
            route_logs.append(log)
        return route_logs


class EventDispatcher(Monitor):
    """Poll one shared event client and route decoded transaction logs to monitors."""

    def __init__(self, routes, well_addresses, prod=False, dry_run=None):
        super().__init__("EventDispatcher", lambda _: None, EVENT_DISPATCHER_CHECK_RATE, prod=prod, dry_run=dry_run)
        self.routes = routes
        self._eth_event_client = EthEventsClient(
            [
                EventClientType.WELL,
                EventClientType.BEANSTALK,
                EventClientType.MARKET,
            ],
            well_addresses,
            combine_filters=True,
        )

    def _monitor_method(self):
        self.last_check_time = 0
        self.last_heartbeat_time = time.time()
        logging.info(
            "EventDispatcher started with "
            f"{len(self._eth_event_client._event_filters)} shared filter(s)"
        )
        while self._thread_active:
            if time.time() - self.last_heartbeat_time > 15 * 60:
                logging.info("EventDispatcher heartbeat")
                self.last_heartbeat_time = time.time()
            if time.time() < self.last_check_time + self.query_rate:
                time.sleep(0.5)
                continue

            self.last_check_time = time.time()
            for route in self.routes:
                route.monitor.last_check_time = self.last_check_time

            rpc_counts_before = get_rpc_request_counts()
            txn_pairs = self._eth_event_client.get_new_logs(dry_run=self._dry_run)
            route_counts = self._dispatch(txn_pairs)
            rpc_counts_after = get_rpc_request_counts()
            self._log_cycle_counts(txn_pairs, route_counts, rpc_counts_before, rpc_counts_after)

    def _dispatch(self, txn_pairs):
        route_counts = {
            route.name: {
                "txns": 0,
                "logs": 0,
                "errors": 0,
            }
            for route in self.routes
        }

        for txn_pair in txn_pairs:
            for route in self.routes:
                route_logs = route.logs_for_txn(txn_pair)
                if not route_logs:
                    continue

                route_counts[route.name]["txns"] += 1
                route_counts[route.name]["logs"] += len(route_logs)
                try:
                    route.handler(txn_pair.txn_hash, list(route_logs))
                except Exception:
                    route_counts[route.name]["errors"] += 1
                    logging.error(
                        f"EventDispatcher route {route.name} failed for txn "
                        f"{txn_pair.txn_hash.hex()}",
                        exc_info=True,
                    )

        return route_counts

    def _log_cycle_counts(self, txn_pairs, route_counts, rpc_counts_before, rpc_counts_after):
        decoded_log_count = sum(len(txn_pair.logs) for txn_pair in txn_pairs)
        method_counts_before = Counter(rpc_counts_before["methods"])
        method_counts_after = Counter(rpc_counts_after["methods"])
        rpc_method_counts = method_counts_after - method_counts_before
        route_counts_str = ", ".join(
            f"{route_name}=txns:{counts['txns']}/logs:{counts['logs']}/errors:{counts['errors']}"
            for route_name, counts in route_counts.items()
        )
        logging.info(
            "EventDispatcher cycle: "
            f"filters={len(self._eth_event_client._event_filters)}, "
            f"rpc_methods=[{self._format_counts(rpc_method_counts)}], "
            f"decoded_txns={len(txn_pairs)}, decoded_logs={decoded_log_count}, "
            f"routes=[{route_counts_str}]"
        )

    def _format_counts(self, method_counts):
        if not method_counts:
            return "none"
        return ", ".join(f"{method}={count}" for method, count in method_counts.most_common())


def event_names_from_map(event_map):
    return {key for key in event_map if isinstance(key, str) and not key.startswith("0x")}


def main_event_routes(wells_monitor, beanstalk_monitor, market_monitor):
    return [
        EventRoute(
            "Well",
            wells_monitor,
            event_names_from_map(WELL_EVENT_MAP),
            lambda txn_hash, logs: wells_monitor._handle_txn_logs(txn_hash, logs),
            addresses=wells_monitor.pool_addresses,
        ),
        EventRoute(
            "Beanstalk",
            beanstalk_monitor,
            event_names_from_map(BEANSTALK_EVENT_MAP),
            lambda txn_hash, logs: beanstalk_monitor._handle_txn_logs(txn_hash, logs),
            addresses=[BEANSTALK_ADDR, FERTILIZER_ADDR],
        ),
        EventRoute(
            "Market",
            market_monitor,
            event_names_from_map(MARKET_EVENT_MAP),
            lambda txn_hash, logs: market_monitor._handle_txn_logs(txn_hash, logs),
            addresses=[BEANSTALK_ADDR],
        ),
    ]

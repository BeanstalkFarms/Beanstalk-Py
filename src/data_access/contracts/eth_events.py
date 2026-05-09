import asyncio
import os
from collections import OrderedDict
from enum import IntEnum

from web3 import Web3
from web3 import exceptions as web3_exceptions
from web3.logs import DISCARD
from web3.datastructures import AttributeDict

from data_access.contracts.util import *

from constants.addresses import *

# NOTE(funderberker): Pretty lame that we cannot automatically parse these from the ABI files.
#   Technically it seems very straight forward, but it is not implemented in the web3 lib and
#   parsing it manually is not any better than just writing it out here.


def add_event_to_dict(signature, sig_dict, sig_list):
    """Add both signature_hash and event_name to the bidirectional dict.

    Configure as a bijective map. Both directions will be added for each event type:
        - signature_hash:event_name
        - event_name:signature_hash
    """
    event_name = signature.split("(")[0]
    event_signature_hash = Web3.keccak(text=signature).hex()
    sig_dict[event_name] = event_signature_hash
    sig_dict[event_signature_hash] = event_name
    sig_list.append(event_signature_hash)
    # NOTE Must config prior to logs otherwise all logging breaks
    # logging.basicConfig(level=logging.INFO)
    # logging.info(f'event signature: {signature}  -  hash: {event_signature_hash}')

AQUIFER_EVENT_MAP = {}
AQUIFER_SIGNATURES_LIST = []
# IERC20 types will just be addresses.
add_event_to_dict(
    "BoreWell(address,address,address[],(address,bytes),(address,bytes)[],bytes)",  # IERC == address
    AQUIFER_EVENT_MAP,
    AQUIFER_SIGNATURES_LIST,
)


WELL_EVENT_MAP = {}
WELL_SIGNATURES_LIST = []
# IERC20 types will just be addresses.
add_event_to_dict(
    "Swap(address,address,uint256,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict("AddLiquidity(uint256[],uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)
add_event_to_dict(
    "RemoveLiquidity(uint256,uint256[],address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict(
    "RemoveLiquidityOneToken(uint256,address,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST
)
add_event_to_dict("Shift(uint256[],address,uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)
add_event_to_dict("Sync(uint256[],uint256,address)", WELL_EVENT_MAP, WELL_SIGNATURES_LIST)


BEANSTALK_EVENT_MAP = {}
BEANSTALK_SIGNATURES_LIST = []
add_event_to_dict(
    "Sow(address,uint256,uint256,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict(
    "Harvest(address,uint256,uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict(
    "AddDeposit(address,address,int96,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveDeposit(address,address,int96,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveDeposits(address,address,int96[],uint256[],uint256,uint256[])",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Convert(address,address,address,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Chop(address,address,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict("Plant(address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict("Pick(address,address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# On Fertilizer contract.
add_event_to_dict(
    "ClaimFertilizer(uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
# Needed to identify cases where AddDeposit should be ignored
add_event_to_dict(
    "L1DepositsMigrated(address,address,uint256[],uint256[],uint256[])",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)

# Season/sunrise events
SEASON_EVENT_MAP = {}
SEASON_SIGNATURES_LIST = []
add_event_to_dict(
    "Incentivization(address,uint256)",
    SEASON_EVENT_MAP,
    SEASON_SIGNATURES_LIST,
)

# Farmer's market events.
MARKET_EVENT_MAP = {}
MARKET_SIGNATURES_LIST = []
add_event_to_dict(
    "PodListingCreated(address,uint256,uint256,uint256,uint256,uint24,uint256,uint256,uint8)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodListingFilled(address,address,uint256,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodListingCancelled(address,uint256,uint256)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict(
    "PodOrderCreated(address,bytes32,uint256,uint256,uint24,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodOrderFilled(address,address,bytes32,uint256,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodOrderCancelled(address,bytes32)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)

# Barn Raise events.
FERTILIZER_EVENT_MAP = {}
FERTILIZER_SIGNATURES_LIST = []
add_event_to_dict(
    "TransferSingle(address,address,address,uint256,uint256)",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)
add_event_to_dict(
    "TransferBatch(address,address,address,uint256[],uint256[])",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)
# Needed to identify when fert mints should be ignored
add_event_to_dict(
    "L1FertilizerMigrated(address,address,uint256[],uint128[],uint128)",
    FERTILIZER_EVENT_MAP,
    FERTILIZER_SIGNATURES_LIST,
)

# L2 Migration events
CONTRACTS_MIGRATED_EVENT_MAP = {}
CONTRACTS_MIGRATED_SIGNATURES_LIST = []
add_event_to_dict(
    "L1BeansMigrated(address,uint256,uint8)",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1DepositsMigrated(address,address,uint256[],uint256[],uint256[])",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1PlotsMigrated(address,address,uint256[],uint256[])",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1InternalBalancesMigrated(address,address,address[],uint256[])",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "L1FertilizerMigrated(address,address,uint256[],uint128[],uint128)",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)
add_event_to_dict(
    "ReceiverApproved(address,address)",
    CONTRACTS_MIGRATED_EVENT_MAP,
    CONTRACTS_MIGRATED_SIGNATURES_LIST,
)

class EventClientType(IntEnum):
    BEANSTALK = 0
    SEASON = 1
    MARKET = 2
    BARN_RAISE = 3
    WELL = 4
    AQUIFER = 5
    CONTRACT_MIGRATED = 6

class TxnPair:
    """The logs, in order, associated with a transaction."""

    txn_hash = ""
    logs = []

    def __init__(self, txn_hash, logs):
        self.txn_hash = txn_hash
        self.logs = logs

class EthEventsClient:
    def __init__(self, client_types, addresses=None, combine_filters=False, install_filters=True):
        if isinstance(client_types, EventClientType):
            client_types = [client_types]
        if not client_types:
            raise ValueError("Must specify at least one client type")
        if addresses is None:
            addresses = []
        elif isinstance(addresses, str):
            addresses = [addresses]

        # Track recently seen txns to avoid processing same txn multiple times.
        self._recent_processed_txns = OrderedDict()
        self._web3 = get_web3_instance()
        self._client_types = client_types
        self._combine_filters = combine_filters

        self._contracts = []
        self._contracts_by_key = {}
        self._contract_keys = set()
        self._contract_event_sources = OrderedDict()
        self._contract_addresses = []
        self._signature_list = []
        self._events_dict = {}
        self._filter_specs = []

        for client_type in client_types:
            if client_type == EventClientType.AQUIFER:
                contract = self._add_contract("aquifer", get_aquifer_contract(self._web3))
                self._add_contract_event_names("aquifer", contract, AQUIFER_EVENT_MAP)
                self._add_filter_spec(client_type, [AQUIFER_ADDR], AQUIFER_SIGNATURES_LIST)
                self._signature_list.extend(AQUIFER_SIGNATURES_LIST)
                self._events_dict.update(AQUIFER_EVENT_MAP)
            elif client_type == EventClientType.WELL:
                contract = self._add_contract("well", get_well_contract(self._web3, None))
                self._add_contract_event_names("well", contract, WELL_EVENT_MAP)
                self._add_filter_spec(client_type, addresses, WELL_SIGNATURES_LIST)
                self._signature_list.extend(WELL_SIGNATURES_LIST)
                self._events_dict.update(WELL_EVENT_MAP)
            elif client_type == EventClientType.BEANSTALK:
                beanstalk_contract = self._add_contract("beanstalk", get_beanstalk_contract(self._web3))
                fertilizer_contract = self._add_contract("fertilizer", get_fertilizer_contract(self._web3))
                self._add_contract_event_names("beanstalk", beanstalk_contract, BEANSTALK_EVENT_MAP)
                self._add_contract_event_names("fertilizer", fertilizer_contract, BEANSTALK_EVENT_MAP)
                self._add_filter_spec(client_type, [BEANSTALK_ADDR, FERTILIZER_ADDR], BEANSTALK_SIGNATURES_LIST)
                self._signature_list.extend(BEANSTALK_SIGNATURES_LIST)
                self._events_dict.update(BEANSTALK_EVENT_MAP)
            elif client_type == EventClientType.SEASON:
                contract = self._add_contract("beanstalk", get_beanstalk_contract(self._web3))
                self._add_contract_event_names("beanstalk", contract, SEASON_EVENT_MAP)
                self._add_filter_spec(client_type, [BEANSTALK_ADDR], SEASON_SIGNATURES_LIST)
                self._signature_list.extend(SEASON_SIGNATURES_LIST)
                self._events_dict.update(SEASON_EVENT_MAP)
            elif client_type == EventClientType.MARKET:
                contract = self._add_contract("beanstalk", get_beanstalk_contract(self._web3))
                self._add_contract_event_names("beanstalk", contract, MARKET_EVENT_MAP)
                self._add_filter_spec(client_type, [BEANSTALK_ADDR], MARKET_SIGNATURES_LIST)
                self._signature_list.extend(MARKET_SIGNATURES_LIST)
                self._events_dict.update(MARKET_EVENT_MAP)
            elif client_type == EventClientType.BARN_RAISE:
                fertilizer_contract = self._add_contract("fertilizer", get_fertilizer_contract(self._web3))
                beanstalk_contract = self._add_contract("beanstalk", get_beanstalk_contract(self._web3))
                self._add_contract_event_names("fertilizer", fertilizer_contract, FERTILIZER_EVENT_MAP)
                self._add_contract_event_names("beanstalk", beanstalk_contract, FERTILIZER_EVENT_MAP)
                self._add_filter_spec(client_type, [FERTILIZER_ADDR, BEANSTALK_ADDR], FERTILIZER_SIGNATURES_LIST)
                self._signature_list.extend(FERTILIZER_SIGNATURES_LIST)
                self._events_dict.update(FERTILIZER_EVENT_MAP)
            elif client_type == EventClientType.CONTRACT_MIGRATED:
                contract = self._add_contract("beanstalk", get_beanstalk_contract(self._web3))
                self._add_contract_event_names("beanstalk", contract, CONTRACTS_MIGRATED_EVENT_MAP)
                self._add_filter_spec(client_type, [BEANSTALK_ADDR], CONTRACTS_MIGRATED_SIGNATURES_LIST)
                self._signature_list.extend(CONTRACTS_MIGRATED_SIGNATURES_LIST)
                self._events_dict.update(CONTRACTS_MIGRATED_EVENT_MAP)
            else:
                raise ValueError("Unsupported event client type.")

        if install_filters:
            self._set_filters()
        else:
            self._event_filters = []
            logging.info(
                f"{', '.join(ct.name for ct in self._client_types)} EthEventsClient "
                "initialized without realtime filters"
            )

    def _add_contract(self, key, contract):
        if key in self._contract_keys:
            return self._contracts_by_key[key]
        self._contracts.append(contract)
        self._contracts_by_key[key] = contract
        self._contract_keys.add(key)
        return contract

    def _add_contract_event_names(self, contract_key, contract, event_map):
        for event_name in self._event_names_from_map(event_map):
            self._contract_event_sources[(contract_key, event_name)] = contract

    def _event_names_from_map(self, event_map):
        return [key for key in event_map if isinstance(key, str) and not key.startswith("0x")]

    def _add_filter_spec(self, client_type, addresses, signatures):
        addresses = list(OrderedDict.fromkeys(addresses))
        self._contract_addresses.extend(addresses)
        self._filter_specs.append(
            {
                "client_type": client_type,
                "addresses": addresses,
                "signatures": signatures,
            }
        )

    def _filter_address_param(self, addresses):
        if len(addresses) == 0:
            return None
        if len(addresses) == 1:
            return addresses[0]
        return addresses

    def _create_filters(self, from_block, to_block):
        if self._combine_filters:
            addresses = []
            signatures = []
            for spec in self._filter_specs:
                addresses.extend(spec["addresses"])
                signatures.extend(spec["signatures"])
            addresses = list(OrderedDict.fromkeys(addresses))
            signatures = list(OrderedDict.fromkeys(signatures))
            if not signatures:
                return []
            return [
                safe_create_filter(
                    self._web3,
                    address=self._filter_address_param(addresses),
                    topics=[signatures],
                    from_block=from_block,
                    to_block=to_block,
                )
            ]

        filters = []
        for spec in self._filter_specs:
            filters.append(
                safe_create_filter(
                    self._web3,
                    address=self._filter_address_param(spec["addresses"]),
                    topics=[spec["signatures"]],
                    from_block=from_block,
                    to_block=to_block,
                )
            )
        return filters

    def _set_filters(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filters = self._create_filters(
            from_block=os.environ.get("DRY_RUN_FROM_BLOCK", "latest"),
            to_block=os.environ.get("DRY_RUN_TO_BLOCK", "latest"),
        )
        logging.info(
            f"{', '.join(ct.name for ct in self._client_types)} EthEventsClient "
            f"configured {len(self._event_filters)} filter(s) across "
            f"{sum(len(spec['addresses']) or 1 for spec in self._filter_specs)} address group(s)"
        )

    def get_log_range(self, from_block, to_block="latest"):
        filters = self._create_filters(from_block=from_block, to_block=to_block)
        return self.get_new_logs(filters=filters, get_all=True)

    def get_new_logs(self, dry_run=None, filters=None, get_all=False):
        """Iterate through all entries passing filter and return list of decoded Log Objects.

        Each on-chain event triggered creates one log, which is associated with one entry. We
        assume that an entry here will contain only one log of interest. It is
        possible to have multiple entries on the same block though, with each entry
        representing a unique txn.

        Note that there may be multiple unique entries with the same topic. Though we assume
        each entry indicates one log of interest.
        """
        self_filters = filters is None
        if self_filters:
            filters = self._event_filters
        # All decoded logs of interest from each txn.
        txn_hash_set = set()
        txn_logs_list = []

        if not dry_run:
            new_entries = []
            for i in range(len(filters)):
                try_count = 0
                while try_count < 3:
                    try_count += 1
                    try:
                        new_entries.extend(self.safe_get_new_entries(filters[i], get_all=get_all))
                        break
                    except (
                        ValueError,
                        asyncio.TimeoutError,
                        websockets.exceptions.ConnectionClosedError,
                        Exception,
                    ) as e:
                        logging.warning(e, exc_info=True)
                        logging.warning("filter.safe_get_new_entries() failed or timed out. Retrying...")
                        time.sleep(1)
                        if self_filters:
                            self._set_filters()
                            filters = self._event_filters
        else:
            new_entries = get_test_entries(dry_run)
            time.sleep(3)

        # Track which unique logs have already been processed from this event batch.
        for entry in new_entries:
            # There can be zero topics for dry run
            if len(entry.get("topics", [])) > 0:
                topic_hash = entry["topics"][0].hex()
                # Do not process topics outside of this classes topics of interest.
                if topic_hash not in self._events_dict:
                    logging.warning(
                        f"Unexpected topic ({topic_hash}) seen in "
                        f"{', '.join(ct.name for ct in self._client_types)} EthEventsClient"
                    )
                    continue

            # Do not process the same txn multiple times.
            txn_hash = entry["transactionHash"]
            if txn_hash in txn_hash_set:
                continue

            # Retrieve and decode all logs of interest from the txn. There may be many logs.
            receipt = tools.util.get_txn_receipt_or_wait(self._web3, txn_hash)
            decoded_logs = self.logs_from_receipt(receipt)
            decoded_logs.sort(key=lambda log: getattr(log, "logIndex", float("inf")))

            # Add all remaining txn logs to log map.
            txn_hash_set.add(txn_hash)
            txn_logs_list.append(TxnPair(txn_hash, decoded_logs))

        txn_logs_list.sort(
            key=lambda entry: (
                entry.logs[0].receipt.blockNumber if entry.logs else float("inf"),
                entry.logs[0].logIndex if entry.logs else float("inf"),
            )
        )
        return txn_logs_list

    def safe_get_new_entries(self, filter, get_all=False):
        """Retrieve all new entries that pass the filter.

        Returns one entry for every log that matches a filter. So if a single txn has multiple logs
        of interest this will return multiple entries.
        Catch any exceptions that may arise when attempting to connect to Infura.
        """
        if get_all or "DRY_RUN_FROM_BLOCK" in os.environ:
            return filter.get_all_entries()

        # We must verify new_entries because get_new_entries() will occasionally pull
        # entries that are not actually new. May be a bug with web3 or may just be a relic
        # of the way block confirmations work.
        new_entries = filter.get_new_entries()
        new_unique_entries = []
        # Remove entries w txn hashes that already processed on past get_new_entries calls.
        for i in range(len(new_entries)):
            entry = new_entries[i]
            # If we have not already processed this txn hash.
            if entry.transactionHash not in self._recent_processed_txns:
                new_unique_entries.append(entry)

        # Add all new txn hashes to recent processed set/dict.
        for entry in new_unique_entries:
            # Arbitrary value. Using this as a set.
            self._recent_processed_txns[entry.transactionHash] = True
        # Keep the recent txn queue size within limit.
        for _ in range(max(0, len(self._recent_processed_txns) - TXN_MEMORY_SIZE_LIMIT)):
            self._recent_processed_txns.popitem(last=False)
        return new_unique_entries

    def logs_from_receipt(self, receipt):
        """Decode and return all logs of interest from the given receipt."""
        decoded_logs = []
        for (_, event_name), contract in self._contract_event_sources.items():
            try:
                decoded_type_logs = contract.events[event_name]().processReceipt(receipt, errors=DISCARD)
            except web3_exceptions.ABIEventFunctionNotFound:
                continue
            for log in decoded_type_logs:
                # Attach the full receipt so downstream monitors do not fetch it again.
                decoded_logs.append(AttributeDict({**dict(log), "receipt": receipt}))
        return decoded_logs

def safe_create_filter(web3, address, topics, from_block, to_block):
    """Create a filter but handle connection exceptions that web3 cannot manage."""
    max_tries = 15
    try_count = 0
    while try_count < max_tries:
        try:
            filter_params = {
                "topics": topics,
                "fromBlock": from_block,
                "toBlock": to_block
            }
            # Include the address in the filter params only if it is not None
            if address:
                filter_params["address"] = address
            return web3.eth.filter(filter_params)
        except websockets.exceptions.ConnectionClosedError as e:
            logging.warning(e, exc_info=True)
            time.sleep(2)
            try_count += 1
    raise Exception("Failed to safely create filter")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    filter = safe_create_filter(
        get_web3_instance(),
        address=BEANSTALK_ADDR,
        topics=[BEANSTALK_SIGNATURES_LIST],
        from_block="256715188",
        to_block="256715781",
    )
    entries = filter.get_new_entries()
    logging.info(f"found {len(entries)} entries")

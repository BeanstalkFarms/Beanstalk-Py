import asyncio
from collections import OrderedDict
from enum import IntEnum

from web3 import Web3
from web3 import exceptions as web3_exceptions
from web3.logs import DISCARD

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
    # NOTE ERROR logging here silently breaks all logging. very cool python feature.
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


CURVE_POOL_EVENT_MAP = {}
CURVE_POOL_SIGNATURES_LIST = []
add_event_to_dict(
    "TokenExchange(address,int128,uint256,int128,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "TokenExchangeUnderlying(address,int128,uint256,int128,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "AddLiquidity(address,uint256[2],uint256[2],uint256,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidity(address,uint256[2],uint256[2],uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidityOne(address,uint256,uint256,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveLiquidityImbalance(address,uint256[2],uint256[2],uint256,uint256)",
    CURVE_POOL_EVENT_MAP,
    CURVE_POOL_SIGNATURES_LIST,
)

BEANSTALK_EVENT_MAP = {}
BEANSTALK_SIGNATURES_LIST = []
add_event_to_dict(
    "Sow(address,uint256,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict(
    "Harvest(address,uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
# Depositing an asset => AddDeposit()
# Withdrawing an asset => RemoveDeposit()
# Claiming an asset => RemoveWithdrawal()
# add_event_to_dict('RemoveDeposit(address,address,uint32,uint256)', # SILO V2
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict(
    "RemoveDeposit(address,address,int96,uint256,uint256)",  # SILO v3
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveDeposits(address,address,int96[],uint256[],uint256,uint256[])",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "AddDeposit(address,address,int96,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveWithdrawal(address,address,uint32,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "RemoveWithdrawals(address,address,uint32[],uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
add_event_to_dict(
    "Convert(address,address,address,uint256,uint256)",
    BEANSTALK_EVENT_MAP,
    BEANSTALK_SIGNATURES_LIST,
)
# add_event_to_dict('StalkBalanceChanged(address,int256,int256)',
#                   BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict(
    "Chop(address,address,uint256,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
)
add_event_to_dict("Plant(address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
add_event_to_dict("Pick(address,address,uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST)
# On Fertilizer contract.
add_event_to_dict(
    "ClaimFertilizer(uint256[],uint256)", BEANSTALK_EVENT_MAP, BEANSTALK_SIGNATURES_LIST
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
    "PodListingCreated(address,uint256,uint256,uint256,uint24,uint256,uint256,bytes,uint8,uint8)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodListingFilled(address,address,uint256,uint256,uint256,uint256)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict("PodListingCancelled(address,uint256)", MARKET_EVENT_MAP, MARKET_SIGNATURES_LIST)
add_event_to_dict(
    "PodOrderCreated(address,bytes32,uint256,uint24,uint256,uint256,bytes,uint8)",
    MARKET_EVENT_MAP,
    MARKET_SIGNATURES_LIST,
)
add_event_to_dict(
    "PodOrderFilled(address,address,bytes32,uint256,uint256,uint256,uint256)",
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


def generate_sig_hash_map(sig_str_list):
    return {sig.split("(")[0]: Web3.keccak(text=sig).hex() for sig in sig_str_list}


# Silo Convert signature.
convert_function_sig_strs = ["convert(bytes,uint32[],uint256[])"]
convert_sigs = generate_sig_hash_map(convert_function_sig_strs)

# Method signatures. We handle some logs differently when derived from different methods.
# Silo conversion signatures.
silo_conversion_sig_strs = [
    "convertDepositedLP(uint256,uint256,uint32[],uint256[])",
    "convertDepositedBeans(uint256,uint256,uint32[],uint256[])",
]
silo_conversion_sigs = generate_sig_hash_map(silo_conversion_sig_strs)
# Signatures of methods with the explicit bean deposit (most txns include embedded deposit).
bean_deposit_sig_strs = [
    "depositBeans(uint256)",
    "buyAndDepositBeans(uint256,uint256)",
    "claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))",
    "claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256))",
]
bean_deposit_sigs = generate_sig_hash_map(bean_deposit_sig_strs)
# Buy Fertilizer signature.
buy_fert_function_sig_strs = [
    "buyAndMint(uint256)",
    "mint(uint256)",
    "mintFertilizer(uint128,uint256,uint8)",
    "farm(bytes[])",
]
buy_fert_sigs = generate_sig_hash_map(buy_fert_function_sig_strs)

# Claim type signatures.
# claim_sigs = ['claim', 'claimAndUnwrapBeans', 'claimConvertAddAndDepositLP', 'claimAndSowBeans', 'claimBuyAndSowBeans', 'claimAndCreatePodOrder', 'claimAndFillPodListing', 'claimBuyBeansAndCreatePodOrder', 'claimBuyBeansAndFillPodListing', 'claimAddAndDepositLP', 'claimAndDepositBeans', 'claimAndDepositLP', 'claimAndWithdrawBeans', 'claimAndWithdrawLP', 'claimBuyAndDepositBeans']
claim_deposit_beans_sig_strs = [
    "claimAndDepositBeans(uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool))",
    "claimBuyAndDepositBeans(uint256,uint256,(uint32[],uint32[],uint256[],bool,bool,uint256,uint256,bool)))",
]
claim_deposit_beans_sigs = generate_sig_hash_map(claim_deposit_beans_sig_strs)

# Signatures of methods of interest for testing.
test_deposit_sig_strs = ["harvest(uint256[])", "updateSilo(address)"]
test_deposit_sigs = generate_sig_hash_map(test_deposit_sig_strs)

class EventClientType(IntEnum):
    BEANSTALK = 0
    SEASON = 1
    MARKET = 2
    BARN_RAISE = 3
    CURVE_BEAN_3CRV_POOL = 4
    WELL = 5
    AQUIFER = 6

class TxnPair:
    """The logs, in order, associated with a transaction."""

    txn_hash = ""
    logs = []

    def __init__(self, txn_hash, logs):
        self.txn_hash = txn_hash
        self.logs = logs

class EthEventsClient:
    def __init__(self, event_client_type, address=""):
        # Track recently seen txns to avoid processing same txn multiple times.
        self._recent_processed_txns = OrderedDict()
        self._web3 = get_web3_instance()
        self._event_client_type = event_client_type
        if self._event_client_type == EventClientType.AQUIFER:
            self._contracts = [get_aquifer_contract(self._web3)]
            self._contract_addresses = [AQUIFER_ADDR]
            self._events_dict = AQUIFER_EVENT_MAP
            self._signature_list = AQUIFER_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.WELL:
            self._contracts = [get_well_contract(self._web3, address)]
            self._contract_addresses = [address]
            self._events_dict = WELL_EVENT_MAP
            self._signature_list = WELL_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.CURVE_BEAN_3CRV_POOL:
            self._contracts = [get_bean_3crv_pool_contract(self._web3)]
            self._contract_addresses = [CURVE_BEAN_3CRV_ADDR]
            self._events_dict = CURVE_POOL_EVENT_MAP
            self._signature_list = CURVE_POOL_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.BEANSTALK:
            self._contracts = [
                get_beanstalk_contract(self._web3),
                get_fertilizer_contract(self._web3),
            ]
            self._contract_addresses = [BEANSTALK_ADDR, FERTILIZER_ADDR]
            self._events_dict = BEANSTALK_EVENT_MAP
            self._signature_list = BEANSTALK_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.SEASON:
            self._contracts = [get_beanstalk_contract(self._web3)]
            self._contract_addresses = [BEANSTALK_ADDR]
            self._events_dict = SEASON_EVENT_MAP
            self._signature_list = SEASON_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.MARKET:
            self._contracts = [get_beanstalk_contract(self._web3)]
            self._contract_addresses = [BEANSTALK_ADDR]
            self._events_dict = MARKET_EVENT_MAP
            self._signature_list = MARKET_SIGNATURES_LIST
        elif self._event_client_type == EventClientType.BARN_RAISE:
            self._contracts = [get_fertilizer_contract(self._web3)]
            self._contract_addresses = [FERTILIZER_ADDR]
            self._events_dict = FERTILIZER_EVENT_MAP
            self._signature_list = FERTILIZER_SIGNATURES_LIST
        else:
            raise ValueError("Unsupported event client type.")
        self._set_filters()

    def _set_filters(self):
        """This is located in a method so it can be reset on the fly."""
        self._event_filters = []
        for address in self._contract_addresses:
            self._event_filters.append(
                safe_create_filter(
                    self._web3,
                    address=address,
                    topics=[self._signature_list],
                    # from_block=10581687, # Use this to search for old events. # Rinkeby
                    # from_block=18722171,  # Use this to search for old events. # Mainnet
                    from_block="latest",
                    to_block="latest",
                )
            )

    def get_log_range(self, from_block, to_block="latest"):
        filters = []
        for address in self._contract_addresses:
            filters.append(
                safe_create_filter(
                    self._web3,
                    address=address,
                    topics=[self._signature_list],
                    from_block=from_block,
                    to_block=to_block,
                )
            )
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
        if filters is None:
            filters = self._event_filters
        # All decoded logs of interest from each txn.
        txn_hash_set = set()
        txn_logs_list = []

        if not dry_run:
            new_entries = []
            for filter in filters:
                new_entries.extend(self.safe_get_new_entries(filter, get_all=get_all))
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
                        f"{self._event_client_type.name} EthEventsClient"
                    )
                    continue

            # Print out entry.
            # logging.info(f"{self._event_client_type.name} entry:\n{str(entry)}\n")

            # Do not process the same txn multiple times.
            txn_hash = entry["transactionHash"]
            if txn_hash in txn_hash_set:
                continue

            # logging.info(f"{self._event_client_type.name} processing {txn_hash.hex()} logs.")

            # Retrieve the full txn and txn receipt.
            receipt = tools.util.get_txn_receipt_or_wait(self._web3, txn_hash)

            # If any removeDeposit events from Silo V2, ignore the entire txn. It is likely a migration.
            # This is a bit hacky, but none of this infrastructure was designed to manage implementations of
            # same event at same address.
            silo_v2_contract = get_beanstalk_v2_contract(self._web3)
            decoded_type_logs = silo_v2_contract.events["RemoveDeposit"]().processReceipt(
                receipt, errors=DISCARD
            )
            if len(decoded_type_logs) > 0:
                logging.warning("Skipping txn with Silo v2 RemoveDeposit")
                txn_hash_set.add(txn_hash)
                continue

            # Get and decode all logs of interest from the txn. There may be many logs.
            decoded_logs = []
            for signature in self._signature_list:
                for contract in self._contracts:
                    try:
                        decoded_type_logs = contract.events[
                            self._events_dict[signature]
                        ]().processReceipt(receipt, errors=DISCARD)
                    except web3_exceptions.ABIEventFunctionNotFound:
                        continue
                    decoded_logs.extend(decoded_type_logs)

            # Prune unrelated logs - logs that are of the same event types we watch, but are
            # not related to Beanstalk (i.e. swaps of non-Bean tokens).
            decoded_logs_copy = decoded_logs.copy()
            decoded_logs.clear()
            for log in decoded_logs_copy:
                # if log.event == 'Swap':
                #     # Only process uniswap swaps with the ETH:BEAN pool.
                #     if log.address != UNI_V2_BEAN_ETH_ADDR:
                #         continue
                if log.event == "TokenExchangeUnderlying" or log.event == "TokenExchange":
                    # Only process curve exchanges in supported BEAN pools.
                    if log.address not in [CURVE_BEAN_3CRV_ADDR]:
                        continue
                decoded_logs.append(log)

            # Add all remaining txn logs to log map.
            txn_hash_set.add(txn_hash)
            txn_logs_list.append(TxnPair(txn_hash, decoded_logs))
            # logging.info(
            #     f"Transaction: {txn_hash}\nAll txn logs of interest:\n"
            #     f"{NEWLINE_CHAR.join([str(l) for l in decoded_logs])}"
            # )

        return txn_logs_list

    def safe_get_new_entries(self, filter, get_all=False):
        """Retrieve all new entries that pass the filter.

        Returns one entry for every log that matches a filter. So if a single txn has multiple logs
        of interest this will return multiple entries.
        Catch any exceptions that may arise when attempting to connect to Infura.
        """
        logging.info(f"Checking for new {self._event_client_type.name} entries with " f"{filter}.")
        try_count = 0
        while try_count < 5:
            try_count += 1
            try:
                if get_all:
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
                    else:
                        logging.warning(
                            f"Ignoring txn that has already been processed ({entry.transactionHash})"
                        )
                # Add all new txn hashes to recent processed set/dict.
                for entry in new_unique_entries:
                    # Arbitrary value. Using this as a set.
                    self._recent_processed_txns[entry.transactionHash] = True
                # Keep the recent txn queue size within limit.
                for _ in range(max(0, len(self._recent_processed_txns) - TXN_MEMORY_SIZE_LIMIT)):
                    self._recent_processed_txns.popitem(last=False)
                return new_unique_entries
                # return filter.get_all_entries() # Use this to search for old events.
            except (
                ValueError,
                asyncio.TimeoutError,
                websockets.exceptions.ConnectionClosedError,
                Exception,
            ) as e:
                logging.warning(e, exc_info=True)
                logging.warning(
                    "filter.get_new_entries() (or .get_all_entries()) failed or timed out. Retrying..."
                )
                time.sleep(1)
                # Filters rely on server state and may be arbitrarily uninstalled by server.
                # https://github.com/ethereum/web3.py/issues/551
                # If we are failing too much recreate the filter.
                self._set_filters()
        logging.error("Failed to get new event entries. Passing.")
        return []

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
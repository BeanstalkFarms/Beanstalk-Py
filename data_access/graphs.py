import asyncio
import logging
import os
import sys
import time

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from constants.addresses import BEANSTALK_ADDR
from data_access.eth_chain import bean_to_float, pods_to_float, soil_to_float, token_to_float

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger

requests_logger.setLevel(logging.WARNING)


FIELDS_PLACEHOLDER = "FIELDS"

# Names of common graph fields.
PRICE_FIELD = "price"
TIMESTAMP_FIELD = "timestamp"
LAST_PEG_CROSS_FIELD = "lastCross"

# Somewhat arbitrary prediction of number of assets that have to be pulled to be sure that all
# assets of interest across 1 most recent season are retrieved. This is a function of number of
# assets. User will need to consider potential early leading seasons from withdrawals, and
# bypassing ongoing season season. So should be
# at least current # of assets * 3 (with 1 season withdraw delay). This is used to
# pull down graph data that is not properly grouped by season due to implementation issues with
# subgraph. Will probably need to be increased someday. Would be better to find it
# programmatically, but regularly checking the subgraph creates an inefficiency and I am tired
# of compensating for subgraph implementation problems here.
# SeeBeanstalkSqlClient.get_num_silo_assets().
MAX_ASSET_SNAPSHOTS_PER_SEASON = 10

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = "\n"

# DAO_SNAPSHOT_NAME = 'beanstalkfarmscommittee.eth'
DAO_SNAPSHOT_NAME = "beanstalkdao.eth"
FARMS_SNAPSHOT_NAME = "beanstalkfarms.eth"

# BEAN_GRAPH_ENDPOINT = f'https://api.thegraph.com/subgraphs/name/cujowolf/bean'
BEAN_GRAPH_ENDPOINT = "https://graph.node.bean.money/subgraphs/name/bean"
# BEANSTALK_GRAPH_ENDPOINT = 'https://api.thegraph.com/subgraphs/name/cujowolf/beanstalk'
# BEANSTALK_GRAPH_ENDPOINT = 'https://graph.node.bean.money/subgraphs/name/beanstalk'
BEANSTALK_GRAPH_ENDPOINT = "https://graph.node.bean.money/subgraphs/name/beanstalk"
# BEANSTALK_GRAPH_ENDPOINT = 'https://graph.node.bean.money/subgraphs/name/beanstalk-testing'
SNAPSHOT_GRAPH_ENDPOINT = "https://hub.snapshot.org/graphql"
BASIN_GRAPH_ENDPOINT = "https://graph.node.bean.money/subgraphs/name/basin"


class BeanSqlClient(object):
    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    def bean_price(self):
        """Returns float representing the most recent cost of a BEAN in USD."""
        return float(self.get_bean_field(PRICE_FIELD))

    def get_bean_field(self, field):
        """Get a single field from the bean object."""
        return self.get_bean_fields(fields=[field])[field]

    def get_bean_fields(self, fields=[PRICE_FIELD]):
        """Retrieve the specified fields for the bean token.

        Args:
            fields: an array of strings specifying which fields should be retried.

        Returns:
            dict containing all request field:value pairs (fields and values are strings).

        Raises:
            gql.transport.exceptions.TransportQueryError: Invalid field name provided.
        """
        # General query string with bean sub fields placeholder.
        query_str = (
            """
            query get_bean_fields {
                beans(first: 1)
                { """
            + FIELDS_PLACEHOLDER
            + """ }
            }
        """
        )
        # Stringify array and inject fields into query string.
        query_str = string_inject_fields(query_str, fields)

        # Create gql query and execute.
        # Note that there is always only 1 bean item returned.
        return execute(self._client, query_str)["beans"][0]

    def last_cross(self):
        """Returns a dict containing timestamp and direction of most recent peg cross."""
        return self.get_last_crosses(n=1)[0]

    def get_last_crosses(self, n=1):
        """Retrieve the last n peg crosses, including timestamp and cross direction.

        Args:
            n: number of recent crosses to retrieve.

        Returns:
            array of dicts containing timestamp and cross direction for each cross.
        """
        query_str = (
            """
            query get_last_bean_crosses {
                beanCrosses(first: """
            + str(n)
            + """, orderBy:timestamp, orderDirection: desc)
                {timestamp, above, id}
            }
            """
        )
        # Create gql query and execute.
        return execute(self._client, query_str)["beanCrosses"]


class BeanstalkSqlClient(object):
    def __init__(self):
        transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    def get_pod_listing(self, id):
        """Get a single pod listing based on id.

        id is "{lister_address}-{listing_index}"
        """
        query_str = f"""
            query {{
                podListing(id: "{id}") {{
                    id
                    status
                    pricePerPod
                    amount
                    originalAmount
                    filled
                    index
                    start
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str)["podListing"]

    def get_pod_order(self, id):
        """Get a single pod order based on id.

        id is arbitrary?
        """
        # Market order subgraph IDs are strings that must begin with 0x.
        if not id.startswith("0x"):
            id = "0x" + id
        query_str = f"""
            query {{
                podOrder(id: "{id}") {{
                    maxPlaceInLine
                    id
                    pricePerPod
                    podAmount
                    podAmountFilled
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str)["podOrder"]

    def get_fertilizer_bought(self):
        query_str = """
            query {
                fertilizers {
                    supply
                }
            }
        """
        # Create gql query and execute.
        return float(execute(self._client, query_str)["fertilizers"][0]["supply"])

    def get_start_stalk_by_season(self, season):
        if season <= 1:
            return 0
        query_str = f"""
        query MyQuery {{
            siloHourlySnapshots(
                orderDirection: desc
                first: 1
                where: {{season: {season - 1}  silo: "{BEANSTALK_ADDR.lower()}"}}
            ) {{
                season
                stalk
            }}
        }}
        """
        # Create gql query and execute.
        return float(execute(self._client, query_str)["siloHourlySnapshots"][0]["stalk"])

    def silo_assets_seasonal_changes(self, current_silo_assets=None, previous_silo_assets=None):
        """Get address, delta balance, and delta BDV of all silo assets across last season.

        parameters are same shape as SeasonStats.pre_assets - lists of dicts.

        Note that season snapshots are created at the beginning of each season and updated throughout season.

        Returns:
            Map of asset deltas with keys [token, delta_amount, delta_bdv].
        """
        if current_silo_assets is None or previous_silo_assets is None:
            current_silo_assets, previous_silo_assets = [
                season_stats.pre_assets
                for season_stats in self.seasons_stats(
                    seasons=False, siloHourlySnapshots=True, fieldHourlySnapshots=False
                )
            ]

        # If there are a different number of assets between seasons, do not associate, just accept it is edge case and display less data.
        if len(current_silo_assets) != len(previous_silo_assets):
            logging.warning("Number of assets in this season changed. Was a new asset added?")
            return []

        assets_changes = []
        for i in range(len(previous_silo_assets)):
            assets_changes.append(AssetChanges(previous_silo_assets[i], current_silo_assets[i]))
        logging.info(f"assets_changes: {assets_changes}")
        return assets_changes

    def seasons_stats(
        self, num_seasons=2, seasons=True, siloHourlySnapshots=True, fieldHourlySnapshots=True
    ):
        """Get a standard set of data corresponding to current season.

        Returns array of last 2 season in descending order, each value a graphql map structure of all requested data.
        """
        query_str = "query seasons_stats {"
        if seasons:
            query_str += f"""
                seasons(first: {num_seasons}, skip: 0, orderBy: season, orderDirection: desc) {{
                    season
                    createdAt
                    price
                    deltaBeans
                    deltaB
                    beans
                    rewardBeans
                    incentiveBeans
                }}
            """
        if siloHourlySnapshots:
            query_str += f"""
                siloHourlySnapshots(
                    where: {{silo: "0xc1e088fc1323b20bcbee9bd1b9fc9546db5624c5"}}
                    orderBy: season
                    orderDirection: desc
                    first: {num_seasons}
                ){{
                    season
                    deltaBeanMints
                    depositedBDV
                }}
                siloAssetHourlySnapshots(
                    orderBy: season
                    orderDirection: desc
                    first: {(num_seasons + 2) * MAX_ASSET_SNAPSHOTS_PER_SEASON}
                    where: {{depositedAmount_gt: "0",
                             siloAsset_: {{silo: "0xc1e088fc1323b20bcbee9bd1b9fc9546db5624c5"}}
                           }}
                ) {{
                    depositedAmount
                    depositedBDV
                    season
                    siloAsset {{
                        token
                    }}
                }}
            """
        if fieldHourlySnapshots:
            query_str += f"""
                fieldHourlySnapshots(
                    where: {{field: "0xc1e088fc1323b20bcbee9bd1b9fc9546db5624c5"}}
                    orderBy: season
                    orderDirection: desc
                    first: {num_seasons}
                ) {{
                    id
                    season
                    temperature
                    podRate
                    issuedSoil
                    deltaSownBeans
                }}
            """
        query_str += "}"

        # Create gql query and execute.
        result = execute(self._client, query_str)

        # Return list of SeasonStats class instances
        return [SeasonStats(result, i) for i in range(num_seasons)]

    def get_num_silo_assets(self):
        """
        The Beanstalk graph silo entities contain a lot of irrelevant 'assets'. This function will
        return the number of assets we are actually interested in, deduced programmatically from
        the subgraph.

        NOTE(funderberker): UNTESTED
        """
        query_str = """
            silo(id: "0xc1e088fc1323b20bcbee9bd1b9fc9546db5624c5") {
                assets(first: 100, where: {depositedAmount_gt: "0"}) {
                    token
                    depositedAmount
                }
            }
        """

        # Create gql query and execute.
        result = execute(self._client, query_str)

        # Return number of assets matching filters.
        return len(result["silo"]["assets"])

    # NOTE(funderberker): Hour to season conversion is imperfect. Unsure why.
    # Perhaps due to paused hours. Or subgraph data is different than expectations.
    # WARNING(funderberker): This is a very slow call on non-recent seasons.
    def get_season_id_by_timestamp(self, timestamp):
        pull_size = 500
        pulled_seasons = 0
        while True:
            query_str = f"""
                query {{
                    seasons(first: {pull_size}, skip: {pulled_seasons}, orderBy: season, orderDirection: desc) {{
                        id
                        createdAt
                    }}
                }}
            """
            seasons = execute(self._client, query_str)["seasons"]
            pulled_seasons += pull_size
            if timestamp < int(seasons[-1]["createdAt"]):
                continue
            # Assumes pulling in descending order.
            if timestamp > int(seasons[0]["createdAt"]):
                return int(seasons[0]["id"])
            for i in range(len(seasons) - 1):
                if timestamp < int(seasons[i]["createdAt"]) and timestamp >= int(
                    seasons[i + 1]["createdAt"]
                ):
                    return int(seasons[i + 1]["id"])


class BasinSqlClient(object):
    def __init__(self):
        transport = AIOHTTPTransport(url=BASIN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    def get_latest_well_snapshots(self, num_snapshots):
        """Get a single well snapshot."""
        query_str = f"""
            query {{
                wells(orderBy: totalLiquidityUSD, orderDirection: desc, where: {{totalLiquidityUSD_gt: 1000}}) {{
                    id
                    name
                    symbol
                        dailySnapshots(first: {num_snapshots}, orderBy: day, orderDirection: desc) {{
                            totalLiquidityUSD
                            deltaVolumeUSD
                    }}
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str)["wells"]

    def get_wells_stats(self):
        """Get high level stats of all wells."""
        query_str = f"""
            query {{
                wells(orderBy: totalLiquidityUSD, orderDirection: desc, where: {{totalLiquidityUSD_gt: 1000}}) {{
                    id
                    cumulativeVolumeUSD
                    totalLiquidityUSD
                }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str)["wells"]

    def try_get_well_deposit_info(self, txn_hash, log_index):
        """Get deposit tokens. Retry if data not available. Return {} if it does not become available.

        This is expected to be used for realtime data retrieval, which means the subgraph may not yet have populated
        the data. Repeated queries give the subgraph a chance to catch up.
        """
        query_str = f"""
            query {{
                deposit(id: "{txn_hash.hex()}-{str(log_index)}") {{
                    tokens {{
                        id
                    }}
                    reserves
                    amountUSD
                }}
            }}
        """
        return try_execute_with_wait("deposit", self._client, query_str)


class SnapshotClient:
    def __init__(self):
        transport = AIOHTTPTransport(url=SNAPSHOT_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7
        )

    # def _get_proposal_quorum(start_time, quorum_ratio):

    def get_active_proposals(self):
        """Returns list of active proposals for Beanstalk DAO."""
        query_str = f"""  
            query get_active_proposals {{
            proposals(
                first: 20,
                skip: 0,
                where: {{
                    space_in: ["{DAO_SNAPSHOT_NAME}", "{FARMS_SNAPSHOT_NAME}"],
                    state: "active"
                }},
                orderBy: "created",
                orderDirection: desc
            ) {{
                title
                choices
                scores
                scores_total
                start
                end
                space {{
                    id
                }}
            }}
            }}
        """
        # Create gql query and execute.
        return execute(self._client, query_str)["proposals"]


class SeasonStats:
    """Standard object containing fields for all fields of interest for a single season.

    Populated from subgraph data.
    """

    def __init__(self, graph_seasons_response, season_index=0, season=None):
        """Create a SeasonStats object directly from the response of a graphql request.

        If the response contains multiple seasons use the season_index to pull desired season.
        """
        season_index = int(season_index)
        if season is None and "seasons" not in graph_seasons_response:
            raise ValueError(
                "Must specify season or include season data to create SeasonStats object."
            )
        self.season = season or graph_seasons_response["seasons"][season_index]["season"]
        if "seasons" in graph_seasons_response:
            self.created_at = graph_seasons_response["seasons"][season_index]["createdAt"]
            self.price = float(graph_seasons_response["seasons"][season_index]["price"])
            # deltaB at beginning of season
            self.delta_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["deltaBeans"]
            )
            # time weighted deltaB based from previous 2 seasons - same as from oracle - used to determine mints and soil
            self.delta_b = bean_to_float(graph_seasons_response["seasons"][season_index]["deltaB"])
            self.total_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["beans"]
            )  # Bean supply
            # silo rewards + fert rewards + pods harvestable
            self.reward_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["rewardBeans"]
            )
            self.incentive_beans = bean_to_float(
                graph_seasons_response["seasons"][season_index]["incentiveBeans"]
            )
        if "siloHourlySnapshots" in graph_seasons_response:
            # Beans minted this season # newFarmableBeans
            self.silo_hourly_bean_mints = bean_to_float(
                graph_seasons_response["siloHourlySnapshots"][season_index]["deltaBeanMints"]
            )
            self.deposited_bdv = bean_to_float(
                graph_seasons_response["siloHourlySnapshots"][season_index]["depositedBDV"]
            )
            # List of each asset at the start of the season. Note that this is offset by 1 from subgraph data.
            self.pre_assets = []
            logging.info(
                f'siloAssetHourlySnapshots: {graph_seasons_response["siloAssetHourlySnapshots"]}'
            )
            for asset_season_snapshot in graph_seasons_response["siloAssetHourlySnapshots"]:
                # Shift back by one season since asset amounts represent current/end of season values.
                if int(asset_season_snapshot["season"]) == self.season - 1:
                    self.pre_assets.append(asset_season_snapshot)
            logging.info(f"self.pre_assets: {self.pre_assets}")
        if "fieldHourlySnapshots" in graph_seasons_response:
            self.temperature = float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["temperature"]
            )
            self.pod_rate = float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["podRate"]
            )
            self.issued_soil = soil_to_float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["issuedSoil"]
            )
            self.sown_beans = bean_to_float(
                graph_seasons_response["fieldHourlySnapshots"][season_index]["deltaSownBeans"]
            )


class AssetChanges:
    """Class representing change in state of an asset across seasons."""

    def __init__(self, init_season_asset, final_season_asset):
        self.init_season_asset = init_season_asset
        self.final_season_asset = final_season_asset
        self.token = init_season_asset["siloAsset"]["token"]
        self.delta_asset = int(final_season_asset["depositedAmount"]) - int(
            init_season_asset["depositedAmount"]
        )
        # self.delta_asset_percent = (
        #     int(final_season_asset['depositedAmount']) /
        #     int(init_season_asset['depositedAmount']) - 1) * 100
        self.delta_bdv = int(final_season_asset["depositedBDV"]) - int(
            init_season_asset["depositedBDV"]
        )
        # self.delta_bdv_percent = (
        #     int(final_season_asset['depositedBDV']) /
        #     int(init_season_asset['depositedBDV']) - 1) * 100


class GraphAccessException(Exception):
    """Sustained failure to access the graph."""


def string_inject_fields(string, fields):
    """Modify string by replacing fields placeholder with stringified array of fields."""
    # Index where desired fields should be injected.
    fields_index_start = string.find(FIELDS_PLACEHOLDER)
    fields_index_end = string.find(FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

    # Stringify array and inject it into query string.
    return string[:fields_index_start] + " ".join(fields) + string[fields_index_end:]


def execute(client, query_str, max_tries=10):
    """Convert query string into a gql query and execute query."""
    query = gql(query_str)

    try_count = 0
    retry_delay = 1  # seconds
    while not max_tries or try_count < max_tries:
        logging.info(f"GraphQL query:" f'{query_str.replace(NEWLINE_CHAR, "").replace("    ", "")}')
        try:
            result = client.execute(query)
            logging.info(f"GraphQL result:{result}")
            return result
        except asyncio.TimeoutError:
            logging.warning(
                f"Timeout error on {client_subgraph_name(client)} subgraph access. Retrying..."
            )
        except RuntimeError as e:
            # This is a bad state. It means the underlying thread exiting without properly
            # stopping these threads. This state is never expected.
            logging.error(e)
            logging.error("Main thread no longer running. Exiting.")
            exit(1)
        except Exception as e:
            logging.warning(e, exc_info=True)
            logging.warning(
                f"Unexpected error on {client_subgraph_name(client)} subgraph access."
                f"\nRetrying..."
            )
        # Exponential backoff to prevent eating up all subgraph API calls.
        time.sleep(retry_delay)
        retry_delay *= 2
        try_count += 1
    logging.error("Unable to access subgraph data")
    raise GraphAccessException


def try_execute_with_wait(check_key, client, query_str, max_tries=2, max_wait_blocks=5):
    """Perform execute. Wait a block and try again if return data is empty. Eventually return None if no data.

    Also do not raise exception on failure, log warning and proceed.
    """
    result = None
    for _ in range(max_wait_blocks):
        try:
            result = execute(client, query_str, max_tries=max_tries)[check_key]
        except GraphAccessException:
            pass
        if result is not None:  # null
            break
        logging.info("Data not found. Waiting a block, retrying...")
        time.sleep(15)
    return result


def client_subgraph_name(client):
    """Return a plain string name of the subgraph for the given gql.Client object."""
    url = client.transport.url
    if url == BEAN_GRAPH_ENDPOINT:
        return "Bean"
    if url == BEANSTALK_GRAPH_ENDPOINT:
        return "Beanstalk"
    else:
        return "unknown"


if __name__ == "__main__":
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    bean_sql_client = BeanSqlClient()
    print(f"Last peg cross: {bean_sql_client.last_cross()}")
    print(f"Last peg crosses: {bean_sql_client.get_last_crosses(4)}")

    # beanstalk_client = BeanstalkSqlClient()
    # print(
    #     f'\nCurrent and previous Season Stats:\n{beanstalk_client.seasons_stats()}')
    # timestamp = 1628299400
    # print(
    #     f'season at time {timestamp} = {beanstalk_client.get_season_id_by_timestamp(timestamp)}')

    basin_client = BasinSqlClient()
    print(
        f'\nDeposit: {basin_client.try_get_well_deposit_info("0x002a57c802e6125455e1d05ff8c6c2a2db8248cc5ef0bc19c7d979752251450d", 360)}'
    )

    # snapshot_sql_client = SnapshotClient()
    # print(f'Voted: {snapshot_sql_client.percent_of_stalk_voted()}%')

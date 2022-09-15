import asyncio
import logging
import os
import sys
import time

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from data_access.eth_chain import bean_to_float, token_to_float

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger
requests_logger.setLevel(logging.WARNING)


FIELDS_PLACEHOLDER = 'FIELDS'
DEFAULT_SEASON_FIELDS = ['id', 'timestamp', 'price', 'weather', 'newFarmableBeans',
                         'newHarvestablePods', 'newPods', 'lp', 'pods', 'beans'
                        ]

# Names of common graph fields.
PRICE_FIELD = 'price'
TIMESTAMP_FIELD = 'timestamp'
LAST_PEG_CROSS_FIELD = 'lastCross'

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = '\n'

SUBGRAPH_API_KEY = os.environ["SUBGRAPH_API_KEY"]

# BEAN_GRAPH_ENDPOINT = f'https://gateway.thegraph.com/api/{SUBGRAPH_API_KEY}/' \
#     'subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-1'
BEAN_GRAPH_ENDPOINT = f'https://api.thegraph.com/subgraphs/name/cujowolf/bean'
# BEANSTALK_GRAPH_ENDPOINT = f'https://gateway.thegraph.com/api/{SUBGRAPH_API_KEY}/' \
#     'subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-0'
BEANSTALK_GRAPH_ENDPOINT = 'https://api.thegraph.com/subgraphs/name/cujowolf/beanstalk'


class BeanSqlClient(object):

    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7)

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
        query_str = """
            query get_bean_fields {
                beans(first: 1)
                { """ + FIELDS_PLACEHOLDER + """ }
            }
        """
        # Stringify array and inject fields into query string.
        query_str = string_inject_fields(query_str, fields)

        # Create gql query and execute.
        # Note that there is always only 1 bean item returned.
        return execute(self._client, query_str)['beans'][0]

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
        query_str = """
            query get_last_crosses {
                crosses(first: """ + str(n) + """, orderBy:timestamp, orderDirection: desc)
                {timestamp, above, id}
            }
        """
        # Create gql query and execute.
        try:
            return execute(self._client, query_str)['crosses']
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Bean subgraph...')
            sys.exit(0)


class BeanstalkSqlClient(object):

    def __init__(self):
        transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7)

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
                    totalAmount
                    filledAmount
                    index
                    start
                }}
            }}
        """
        # Create gql query and execute.
        try:
            return execute(self._client, query_str)['podListing']
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            sys.exit(0)

    def get_pod_order(self, id):
        """Get a single pod order based on id.
        
        id is arbitrary?
        """
        # Market order subgraph IDs are strings that must begin with 0x.
        if not id.startswith('0x'):
            id = '0x' + id
        query_str = f"""
            query {{
                podOrder(id: "{id}") {{
                    maxPlaceInLine
                    id
                    pricePerPod
                    amount
                    filledAmount
                }}
            }}
        """
        # Create gql query and execute.
        try:
            return execute(self._client, query_str)['podOrder']
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            sys.exit(0)

    def get_fertilizer_bought(self):
        query_str = """
            query {
                fertilizers {
                    totalSupply
                }
            }
        """
        # Create gql query and execute.
        try:
            return float(execute(self._client, query_str)['fertilizers'][0]['totalSupply'])
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            sys.exit(0)

    def silo_assets_seasonal_changes(self, current_silo_assets=None, previous_silo_assets=None):
        """Get address, delta balance, and delta BDV of all silo assets across last season.
        
        Note that season snapshots are created at the beginning of each season and updated throughout season.

        Returns:
            Map of asset deltas with keys [token, delta_amount, delta_bdv].
        """
        if current_silo_assets is None or previous_silo_assets is None:
            current_silo_assets, previous_silo_assets = [season_stats.assets for season_stats in self.seasons_stats(
                seasons=False, siloHourlySnapshots=True, fieldHourlySnapshots=False)]

        assets_changes = []
        for i in range(len(previous_silo_assets)):
            assets_changes.append(AssetChanges(previous_silo_assets[i], current_silo_assets[i]))
        return assets_changes

    def seasons_stats(self, num_seasons=2, seasons=True, siloHourlySnapshots=True, fieldHourlySnapshots=True):
        """Get a standard set of data corresponding to current season.
        
        Returns array of last 2 season in descending order, each value a graphql map structure of all requested data.
        """
        query_str = 'query seasons_stats {'
        if seasons:
            query_str += f"""
                seasons(first: {num_seasons}, skip: 0, orderBy: season, orderDirection: desc) {{
                    season
                    timestamp
                    price
                    deltaBeans
                    deltaB
                    beans
                    rewardBeans
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
                    hourlyBeanMints #newFarmableBeans
                    totalDepositedBDV
                    silo {{
                        assets(first: 100, orderBy: totalDepositedBDV, orderDirection: desc,
                               where: {{totalDepositedAmount_gt: "0"}}) {{
                            token
                            totalDepositedAmount
                            totalDepositedBDV
                        }}
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
                    weather
                    newPods
                    totalPods #pods
                    newSoil
                    sownBeans
                }}
            """
        query_str += '}'

        # Create gql query and execute.
        try:
            result = execute(self._client, query_str)
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            sys.exit(0)

        # Return list of SeasnStat class instances
        return [SeasonStats(result, i) for i in range(num_seasons)]

### DEPRECATED VIA SUBGRAPH IMPL CHANGES ###
'''
    def current_season_stat(self, field):
        return self.current_season_stats([field])[field]

    def current_season_stats(self, fields=DEFAULT_SEASON_FIELDS):
        return self.seasons_stats(season_ages=[0], fields=fields)[0]

    def last_completed_season_stat(self, field):
        return self.last_completed_season_stats([field])[field]

    def last_completed_season_stats(self, fields=DEFAULT_SEASON_FIELDS):
        return self.seasons_stats(season_ages=[1], fields=fields)[0]

    def seasons_stats(self, season_ages=[0, 1], fields=DEFAULT_SEASON_FIELDS):
        """Retrieve the specified data for a season.

        Args:
            season_ages: list of ascending order int of season age relative to current season.
            fields: list of strings specifying which fields should be retried.

        Raises:
            gql.transport.exceptions.TransportQueryError: Invalid field name provided.
        """
        # General query string with season sub fields placeholder.
        query_str = """
            query last_season_stats {
                seasons(first: """ + str(len(season_ages)) + """,
                        skip: """ + str(season_ages[0]) + """,
                        orderBy: timestamp, orderDirection: desc)
                { """ + FIELDS_PLACEHOLDER + """ }
            }
        """

        # Stringify array and inject fields into query string.
        query_str = string_inject_fields(query_str, fields)

        # Create gql query and execute.
        try:
            return execute(self._client, query_str)['seasons']
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            sys.exit(0)

    def wallet_stats(self, account_id):
        return self.wallets_stats([account_id])[0]

    def wallets_stats(self, account_ids):
        """Returns list of maps, where each map represents a single account."""
        # General query string.
        query_str = """
            query wallets_stats {
                accounts(subgraphError:deny, first: """ + str(len(account_ids)) + """ 
                    where: {
                        id_in: [ """ + ','.join([f'"{id}"' for id in account_ids]) + """ ]
                    }
                ) {
                    id, depositedLP, depositedBeans, pods
                }
            }
        """

        # Create gql query and execute.
        try:
            return execute(self._client, query_str)['accounts']
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            sys.exit(0)
'''

class SeasonStats():
    """Standard object containing fields for all fields of interest for a single season.

    Populated from subgraph data.
    """
    def __init__(self, graph_seasons_response, season_index=0):
        """Create a SeasonStats object directly from the response of a graphql request.

        If the response contains multiple seasons use the season_index to pull desired season.
        """
        if 'seasons' in graph_seasons_response:
            self.season = graph_seasons_response['seasons'][season_index]['season']
            self.timestamp = graph_seasons_response['seasons'][season_index]['timestamp']
            self.price = float(graph_seasons_response['seasons'][season_index]['price'])
            self.delta_beans = bean_to_float(graph_seasons_response['seasons'][season_index]['deltaBeans']) # deltaB at beginning of season
            self.delta_b = bean_to_float(graph_seasons_response['seasons'][season_index]['deltaB']) # time weighted deltaB based from previous 2 seasons - same as from oracle - used to determine mints and soil
            self.total_beans = bean_to_float(graph_seasons_response['seasons'][season_index]['beans']) # Bean supply
            self.reward_beans = bean_to_float(graph_seasons_response['seasons'][season_index]['rewardBeans']) # silo rewards + fert rewards + pods harvestable
        if 'siloHourlySnapshots' in graph_seasons_response:
            self.silo_hourly_bean_mints = bean_to_float(graph_seasons_response['siloHourlySnapshots'][season_index]['hourlyBeanMints']) # Beans minted this season # newFarmableBeans
            self.total_deposited_bdv = bean_to_float(graph_seasons_response['siloHourlySnapshots'][season_index]['totalDepositedBDV'])
            self.assets = graph_seasons_response['siloHourlySnapshots'][season_index]['silo']['assets'] # Beans minted this season # newFarmableBeans
        if 'fieldHourlySnapshots' in graph_seasons_response:
            self.weather = float(graph_seasons_response['fieldHourlySnapshots'][season_index]['weather'])
            self.newPods = bean_to_float(graph_seasons_response['fieldHourlySnapshots'][season_index]['newPods'])
            self.total_pods = bean_to_float(graph_seasons_response['fieldHourlySnapshots'][season_index]['totalPods'])  # pods
            self.new_soil = bean_to_float(graph_seasons_response['fieldHourlySnapshots'][season_index]['newSoil'])
            self.sown_beans = bean_to_float(graph_seasons_response['fieldHourlySnapshots'][season_index]['sownBeans'])

class AssetChanges():
    """Class representing change in state of an asset across seasons."""
    def __init__(self, init_season_asset, final_season_asset):
        self.init_season_asset = init_season_asset
        self.final_season_asset = final_season_asset
        self.token = init_season_asset['token']
        self.delta_asset = int(
            final_season_asset['totalDepositedAmount']) - int(init_season_asset['totalDepositedAmount'])
        self.delta_bdv = int(
            final_season_asset['totalDepositedBDV']) - int(init_season_asset['totalDepositedBDV'])
        

class GraphAccessException(Exception):
    """Failed to access the graph."""

def string_inject_fields(string, fields):
    """Modify string by replacing fields placeholder with stringified array of fields."""
    # Index where desired fields should be injected.
    fields_index_start = string.find(FIELDS_PLACEHOLDER)
    fields_index_end = string.find(
        FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

    # Stringify array and inject it into query string.
    return string[:fields_index_start] + \
        ' '.join(fields) + string[fields_index_end:]


def execute(client, query_str, max_tries=10):
    """Convert query string into a gql query and execute query."""
    query = gql(query_str)

    try_count = 0
    retry_delay = 1 # seconds
    while not max_tries or try_count < max_tries:
        logging.info(f'GraphQL query:'
                     f'{query_str.replace(NEWLINE_CHAR, "").replace("    ", "")}')
        try:
            result = client.execute(query)
            logging.info(f'GraphQL result:{result}')
            return result
        except asyncio.TimeoutError:
            logging.warning(
                f'Timeout error on {client_subgraph_name(client)} subgraph access. Retrying...')
        except RuntimeError as e:
            # This is a bad state. It means the underlying thread exiting without properly
            # stopping these threads. This state is never expected.
            logging.error(e)
            logging.error('Main thread no longer running. Exiting.')
            exit(1)
        except Exception as e:
            logging.warning(e, exc_info=True)
            logging.warning(f'Unexpected error on {client_subgraph_name(client)} subgraph access.'
                            f'\nRetrying...')
        # Exponential backoff to prevent eating up all subgraph API calls.
        time.sleep(retry_delay)
        retry_delay *= 2
        try_count += 1
    raise GraphAccessException


def client_subgraph_name(client):
    """Return a plain string name of the subgraph for the given gql.Client object."""
    url = client.transport.url
    if url == BEAN_GRAPH_ENDPOINT:
        return 'Bean'
    if url == BEANSTALK_GRAPH_ENDPOINT:
        return 'Beanstalk'
    else:
        return 'unknown'


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    bean_sql_client = BeanSqlClient()
    print(f'Last peg cross: {bean_sql_client.last_cross()}')
    print(f'Last peg crosses: {bean_sql_client.get_last_crosses(4)}')
    print(bean_sql_client.get_bean_fields(['id', 'totalCrosses']))

    beanstalk_client = BeanstalkSqlClient()
    print(
        f'\nCurrent and previous Season Stats:\n{beanstalk_client.seasons_stats()}')

    snapshot_sql_client = SnapshotSqlClient()
    print(f'Voted: {snapshot_sql_client.percent_of_stalk_voted()}%')

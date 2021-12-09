import asyncio
import logging
import os
import time

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger
requests_logger.setLevel(logging.WARNING)


FIELDS_PLACEHOLDER = 'FIELDS'
DEFAULT_SEASON_FIELDS = ['id', 'timestamp', 'price', 'weather', 'newFarmableBeans', 'newHarvestablePods',
                         'newDepositedBeans', 'newWithdrawnBeans', 'newDepositedLP',
                         'newWithdrawnLP', 'newPods', 'pooledBeans', 'pooledEth', 'lp'
                         # , 'soil', 'newSoil'
                         ]

# Names of common graph fields.
PRICE_FIELD = 'price'
TIMESTAMP_FIELD = 'timestamp'
LAST_PEG_CROSS_FIELD = 'lastCross'

# Newline character to get around limits of f-strings.
NEWLINE_CHAR = '\n'

SUBGRAPH_API_KEY = os.environ["SUBGRAPH_API_KEY"]
BEAN_GRAPH_ENDPOINT = f'https://gateway.thegraph.com/api/{SUBGRAPH_API_KEY}/' \
    'subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-1'
BEANSTALK_GRAPH_ENDPOINT = f'https://gateway.thegraph.com/api/{SUBGRAPH_API_KEY}/' \
    'subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-0'


class BeanSqlClient(object):

    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7)

    def current_bean_price(self):
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

        # Index where desired fields should be injected.
        fields_index_start = query_str.find(FIELDS_PLACEHOLDER)
        fields_index_end = query_str.find(
            FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

        # Stringify array and inject it into query string.
        query_str = query_str[:fields_index_start] + \
            ' '.join(fields) + query_str[fields_index_end:]

        # Create gql query and execute.
        # Note that there is always only 1 bean item returned.
        return execute(self._client, query_str)['beans'][0]

    def last_cross(self):
        """Returns a dict containing timestamp and direction of most recent peg cross."""
        return self.get_last_crosses()[0]

    def get_last_crosses(self, n=1):
        """Retrive the last n peg crosses, including timestamp and cross direction.

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
            os._exit(os.EX_UNAVAILABLE)


class BeanstalkSqlClient(object):

    def __init__(self):
        transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7)

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

        # Index where desired fields should be injected.
        fields_index_start = query_str.find(FIELDS_PLACEHOLDER)
        fields_index_end = query_str.find(
            FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

        # Stringify array and inject it into query string.
        query_str = query_str[:fields_index_start] + \
            ' '.join(fields) + query_str[fields_index_end:]

        # Create gql query and execute.
        try:
            return execute(self._client, query_str)['seasons']
        except GraphAccessException as e:
            logging.exception(e)
            logging.error(
                'Killing all processes due to inability to access Beanstalk subgraph...')
            os._exit(os.EX_UNAVAILABLE)


class GraphAccessException(Exception):
    """Failed to access the graph."""


def execute(client, query_str, max_tries=0):
    """Convert query string into a gql query and execute query."""
    query = gql(query_str)

    try_count = 0
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
            logging.warning(f'Unexpected error on {client_subgraph_name(client)} subgraph access:'
                            f'\n{e}\n Retrying...')
        time.sleep(1)
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

    bean_client = BeanSqlClient()
    print(f'Price: {bean_client.current_bean_price()}')
    print(f'Last peg cross: {bean_client.last_cross()}')
    print(
        f'Total Supply (USD): {bean_client.get_bean_field("totalSupplyUSD")}')
    print(bean_client.get_bean_fields(['id', 'totalCrosses']))

    beanstalk_client = BeanstalkSqlClient()
    print(
        f'\nCurrent and previous Season Stats:\n{beanstalk_client.seasons_stats()}')
    print(
        f'\nPrevious Season Start Price:\n{beanstalk_client.last_completed_season_stat(PRICE_FIELD)}')
    print(
        f'\nCurrent Season Start Price:\n{beanstalk_client.current_season_stat(PRICE_FIELD)}')

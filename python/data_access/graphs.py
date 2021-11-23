import asyncio
import logging
import time

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger
requests_logger.setLevel(logging.WARNING)

BEAN_GRAPH_ENDPOINT= 'https://api.studio.thegraph.com/query/6727/bean/v0.0.11'
BEANSTALK_GRAPH_ENDPOINT = 'https://gateway.thegraph.com/api/[API_KEY]/' \
                          'subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-0'

FIELDS_PLACEHOLDER = 'FIELDS'
DEFAULT_SEASON_FIELDS = ['id', 'timestamp', 'price', 'weather', 'newFarmableBeans', 'newHarvestablePods',
                         'newDepositedBeans', 'newWithdrawnBeans', 'newDepositedLP',
                         'newWithdrawnLP', 'newPods'
                         # , 'soil', 'newSoil'
                         ]

# Names of common graph fields.
PRICE_FIELD = 'price'
TIMESTAMP_FIELD = 'timestamp'
LAST_PEG_CROSS_FIELD = 'lastCross'


class BeanSqlClient(object):

    # TODO(funderberker): Configurable timeout. Also for beanstalk subgraph.
    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=10)

    def current_bean_price(self):
        """Returns float representing the most recent cost of a BEAN in USD."""
        return float(self.get_bean_field(PRICE_FIELD))

    def last_peg_cross(self):
        """Returns a timestamp of the last time the peg was crossed."""
        return int(self.get_bean_field(LAST_PEG_CROSS_FIELD))

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
        fields_index_end = query_str.find(FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

        # Stringify array and inject it into query string.
        query_str = query_str[:fields_index_start] + ' '.join(fields) + query_str[fields_index_end:]

        # Create gql query and execute.
        # Note that there is always only 1 bean item returned.
        return execute(self._client, query_str)['beans'][0]

class BeanstalkSqlClient(object):

    def __init__(self):
        transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=10)

    def current_season_stat(self, field):
        return self.current_season_stats([field])[field]

    def current_season_stats(self, fields=DEFAULT_SEASON_FIELDS):
        return self.seasons_stats(season_ages=[0], fields=fields)[0]

    def last_completed_season_stat(self, field):
        return self.last_completed_season_stats([field])[field]

    def last_completed_season_stats(self, fields=DEFAULT_SEASON_FIELDS):
        return self.seasons_stats(season_ages=[1], fields=fields)[0]

    def seasons_stats(self, season_ages=[0,1], fields=DEFAULT_SEASON_FIELDS):
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
        fields_index_end = query_str.find(FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

        # Stringify array and inject it into query string.
        query_str = query_str[:fields_index_start] + ' '.join(fields) + query_str[fields_index_end:]

        # Create gql query and execute.
        return execute(self._client, query_str)['seasons']
        
class GraphAccessException(Exception):
    """Failed to access the graph."""

def execute(client, query_str):
    """Convert query string into a gql query and execute query."""
    max_tries = 10
    query = gql(query_str)

    try_count = 0
    while try_count < max_tries:
        logging.info(f'GraphQL query:\n{query_str}')
        try:
            result = client.execute(query)
            logging.info(f'GraphQL result:\n{result}')
            return result
        except asyncio.exceptions.TimeoutError:
            logging.warning('Timeout error on Bean GraphQL access. Retrying...')
        except Exception as e:
            logging.warning(f'Unexpected error on Bean GraphQL access:\n{e}\n Retrying...')
        time.sleep(0.5)
        try_count += 1
    raise GraphAccessException


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    bean_client = BeanSqlClient()
    print(f'Price: {bean_client.current_bean_price()}')
    print(f'Last peg cross: {bean_client.last_peg_cross()}')
    print(f'Total Supply (USD): {bean_client.get_bean_field("totalSupplyUSD")}')
    print(bean_client.get_bean_fields(['id', 'totalCrosses']))


    beanstalk_client = BeanstalkSqlClient()
    print(f'\nCurrent and previous Season Stats:\n{beanstalk_client.seasons_stats()}')
    print(f'\nPrevious Season Start Price:\n{beanstalk_client.last_completed_season_stat(PRICE_FIELD)}')
    print(f'\nCurrent Season Start Price:\n{beanstalk_client.current_season_stat(PRICE_FIELD)}')

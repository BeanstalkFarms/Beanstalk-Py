import asyncio
import logging
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

# Reduce log spam from the gql package
from gql.transport.aiohttp import log as requests_logger
requests_logger.setLevel(logging.WARNING)

BEANSTALK_GRAPH_ENDPOINT = 'https://gateway.thegraph.com/api/[API_KEY]/' \
                          'subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-0'

FIELDS_PLACEHOLDER = 'FIELDS'

class BeanstalkSqlClient(object):

    def __init__(self):
        transport = AIOHTTPTransport(url=BEANSTALK_GRAPH_ENDPOINT)
        self._client = Client(transport=transport, fetch_schema_from_transport=False)
        
    def last_season_stats(self, fields=['id', 'price']):
        """Retrieve the specified data for the most recently completed season.

        Args:
            fields: an array of strings specifying which fields should be retried.

        Raises:
            gql.transport.exceptions.TransportQueryError: Invalid field name provided.
        """
        # General query string with season sub fields placeholder.
        query_str = """
            query last_season_stats {
                seasons(first: 1, skip: 1 orderBy: timestamp, orderDirection: desc)
                { """ + FIELDS_PLACEHOLDER + """ }
            }
        """

        # Index where desired fields should be injected.
        fields_index_start = query_str.find(FIELDS_PLACEHOLDER)
        fields_index_end = query_str.find(FIELDS_PLACEHOLDER) + len(FIELDS_PLACEHOLDER)

        # Stringify array and inject it into query string.
        query_str = query_str[:fields_index_start] + ' '.join(fields) + query_str[fields_index_end:]

        # Create gql query and execute.
        return self._execute(query_str)['seasons'][0]


    def _execute(self, query_str):
        """Convert query string into a gql query and execute query."""
        query = gql(query_str)
        while True:
            logging.info(f'Beanstalk GraphQL query:\n{str(query)}')
            try:
                result = self._client.execute(query)
                break
            except asyncio.exceptions.TimeoutError:
                logging.warning('Timeout error on Beanstalk GraphQL access. Retrying...')
        logging.info(f'GraphQL result:\n{result}')
        return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    client = BeanstalkSqlClient()
    print(client.last_season_stats())



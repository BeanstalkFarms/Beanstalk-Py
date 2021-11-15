import asyncio
import logging

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

# Reduce log spam from the gql package
from gql.transport.aiohttp import log as requests_logger
requests_logger.setLevel(logging.WARNING)

BEAN_GRAPH_ENDPOINT= 'https://api.studio.thegraph.com/query/6727/bean/v0.0.10'

FIELDS_PLACEHOLDER = 'FIELDS'

# Names of common graph fields.
PRICE_FIELD = 'price'
LAST_PEG_CROSS_FIELD = 'lastCross'

# NOTE(funderberker): Delete this before merege.
"""
I came up with three approaches to implement graph calls in python. All are kind of lame.
1. Write the query strings directly into the methods
    - ugly maintaining of plain string blocks in code
    - will be hard to maintain / update with changes to graphql interface
2. Write the query strings into graphql files
    - sourcing the files when importing this module does not appear possible
    - kind of ugly because so many files and also method intention name duplication all the way through
3. Use the DSL lib https://github.com/graphql-python/gql/commit/44803d436d0cca7972acf999eccaed61ced820ae#diff-864bb4222a8ae3d7ebab9d62686f86721c29c9fe8f883d42c70e0875f66e213f
    - Makes the code less readable, obscures the graphql syntax, heavy handed, seems intended for complex calls
"""


class BeanSqlClient(object):

    # TODO(funderberker): Configurable timeout. Also for beanstalk subgraph.
    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=10)

    async def current_bean_price(self):
        """Returns float representing the most recent cost of a BEAN in USD."""
        return await self.get_bean_field(PRICE_FIELD)

    async def last_peg_cross(self):
        """Returns a timestamp of the last time the peg was crossed."""
        return int(await self.get_bean_field(LAST_PEG_CROSS_FIELD))

    async def get_bean_field(self, field):
        """Get a single field from the bean object."""
        return (await self.get_bean_fields(fields=[field]))[field]

    async def get_bean_fields(self, fields=[PRICE_FIELD]):
        """Retrieve the specified fields for the bean token.

        Args:
            fields: an array of strings specifying which fields should be retried.
        
        Returns:
            dict containing all request field:value pairs.

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
        return (await self._execute(query_str))['beans'][0]

    async def _execute(self, query_str):
        """Convert query string into a gql query and execute query."""
        query = gql(query_str)

        # TODO(funderberker): Configure max # of retries and raise custom exception on fail.  Also for beanstalk subgraph.
        while True:
            logging.info(f'Bean GraphQL query:\n{query_str}')
            try:
                result = await self._client.execute_async(query)
                break
            except asyncio.exceptions.TimeoutError:
                logging.warning('Timeout error on Bean GraphQL access. Retrying...')
        logging.info(f'GraphQL result:\n{result}')
        return result


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    client = BeanSqlClient()
    print(client.current_bean_price())
    print(client.last_peg_cross())

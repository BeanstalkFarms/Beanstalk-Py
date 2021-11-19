import asyncio
import logging

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from subgraphs import util

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger
requests_logger.setLevel(logging.WARNING)

BEAN_GRAPH_ENDPOINT= 'https://api.studio.thegraph.com/query/6727/bean/v0.0.10'

FIELDS_PLACEHOLDER = 'FIELDS'

# Names of common graph fields.
PRICE_FIELD = 'price'
LAST_PEG_CROSS_FIELD = 'lastCross'


class BeanSqlClient(object):

    # TODO(funderberker): Configurable timeout. Also for beanstalk subgraph.
    def __init__(self):
        transport = AIOHTTPTransport(url=BEAN_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=10)

    async def current_bean_price(self):
        """Returns float representing the most recent cost of a BEAN in USD."""
        return float(await self.get_bean_field(PRICE_FIELD))

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
        return (await util.execute(self._client, query_str))['beans'][0]


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    client = BeanSqlClient()
    print(f'Price: {asyncio.run(client.current_bean_price())}')
    print(f'Last peg cross: {asyncio.run(client.last_peg_cross())}')
    print(f'Total Supply (USD): {asyncio.run(client.get_bean_field("totalSupplyUSD"))}')
    print(asyncio.run(client.get_bean_fields(['id', 'totalCrosses'])))

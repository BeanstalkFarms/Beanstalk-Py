from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
import logging

from graphs import execute

SNAPSHOT_GRAPH_ENDPOINT = f'https://hub.snapshot.org/graphql'

class SnapshotSqlClient(object):
    """Lazy programming because this is intended for one time use for BIP-21.
    
    Get the % voted
    """
    PRE_EXPLOIT_STALK_COUNT = 213329318.46 # inferred from snapshot
    def __init__(self):
        transport = AIOHTTPTransport(url=SNAPSHOT_GRAPH_ENDPOINT)
        self._client = Client(
            transport=transport, fetch_schema_from_transport=False, execute_timeout=7)

    def percent_of_stalk_voted(self):
        query_str = """
            query Proposal {
                proposal(id:"0xbe30bc43d7185ef77cd6af0e5c85da7d7c06caad4c0de3a73493ed48eae32d71") {
                    id
                    title
                    choices
                    start
                    end
                    snapshot
                    state
                    scores
                    scores_total
                    scores_updated
                }
            }
            """
        result = execute(self._client, query_str)
        votes_yes = result['proposal']['scores'][0] + result['proposal']['scores'][1]
        percent_of_stalk_voted = votes_yes / self.PRE_EXPLOIT_STALK_COUNT
        return percent_of_stalk_voted * 100


if __name__ == '__main__':
    """Quick test and demonstrate functionality."""
    logging.basicConfig(level=logging.INFO)

    snapshot_sql_client = SnapshotSqlClient()
    print(f'Voted: {snapshot_sql_client.percent_of_stalk_voted()}%')
from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from data_access.subgraphs.util import *
from data_access.contracts.util import *
from constants.addresses import *
from constants.config import *

class SnapshotGraphClient:
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

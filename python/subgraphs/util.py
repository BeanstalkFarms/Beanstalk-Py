# Utils for subgraph access.
import asyncio
import logging
import time

from gql import gql

def execute(client, query_str):
    """Convert query string into a gql query and execute query."""
    query = gql(query_str)

    # TODO(funderberker): Configure max # of retries and raise custom exception on fail.  Also for beanstalk subgraph.
    while True:
        logging.info(f'GraphQL query:\n{query_str}')
        try:
            result = client.execute(query)
            break
        except asyncio.exceptions.TimeoutError:
            logging.warning('Timeout error on Bean GraphQL access. Retrying...')
        except Exception as e:
            logging.warning(f'Unexpected error on Bean GraphQL access:\n{e}\n Retrying...')
        time.sleep(0.5)
    logging.info(f'GraphQL result:\n{result}')
    return result

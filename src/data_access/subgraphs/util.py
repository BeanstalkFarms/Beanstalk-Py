import asyncio
import logging
import time

from gql import gql

from constants.config import *

# Reduce log spam from the gql package.
from gql.transport.aiohttp import log as requests_logger

requests_logger.setLevel(logging.WARNING)


class GraphAccessException(Exception):
    """Sustained failure to access the graph."""


def string_inject_fields(string, fields):
    """Modify string by replacing fields placeholder with stringified array of fields."""
    # Index where desired fields should be injected.
    fields_index_start = string.find(GRAPH_FIELDS_PLACEHOLDER)
    fields_index_end = string.find(GRAPH_FIELDS_PLACEHOLDER) + len(GRAPH_FIELDS_PLACEHOLDER)

    # Stringify array and inject it into query string.
    return string[:fields_index_start] + " ".join(fields) + string[fields_index_end:]


def execute(client, query_str, max_tries=10):
    """Convert query string into a gql query and execute query."""
    query = gql(query_str)

    try_count = 0
    retry_delay = 1  # seconds
    while not max_tries or try_count < max_tries:
        # logging.info(f"GraphQL query:" f'{query_str.replace(NEWLINE_CHAR, "").replace("    ", "")}')
        try:
            result = client.execute(query)
            # logging.info(f"GraphQL result:{result}")
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
    """Perform execute. Wait a 5s and try again if return data is empty. Eventually return None if no data.

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
        logging.info("Data not found. Waiting 5s, retrying...")
        time.sleep(5)
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

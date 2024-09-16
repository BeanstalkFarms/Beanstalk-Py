import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import time
import requests


def get_with_retries(request_url, max_tries=10, timeout=6):
    """Attempt a get call with error handling."""
    # logging.info(f"Attempting GET to {request_url}")
    try_count = 0
    while True:
        try:
            response = requests.get(request_url, timeout=timeout)
            logging.info(f"Response: {response.json()}")
            return response.json()

        except Exception as e:
            if try_count < max_tries:
                logging.error(f"Failed GET request ({request_url}). Retrying...", exc_info=True)
                time.sleep(1)
            else:
                raise e
        try_count += 1

### Functions to execute multiple calls in parallel using asyncio
# Function to execute a lambda function synchronously
def _execute_lambda(lambda_func):
    return lambda_func()

# Asynchronous function to run synchronous calls in a thread pool
async def _async_execute_lambda(executor, lambda_func):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _execute_lambda, lambda_func)

# Main function to parallelize lambda function calls
async def _execute_lambdas_async(*lambda_funcs):
    # Create a ThreadPoolExecutor
    with ThreadPoolExecutor() as executor:
        # Schedule all lambda function calls to run in parallel
        tasks = [_async_execute_lambda(executor, lambda_func) for lambda_func in lambda_funcs]
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
    return results

# Synchronous wrapper function
def execute_lambdas(*lambda_funcs):
    return asyncio.run(_execute_lambdas_async(*lambda_funcs))

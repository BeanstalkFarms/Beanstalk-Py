import logging
import time
import requests


def get_with_retries(request_url, max_tries=10):
    """Attempt a get call with error handling."""
    logging.info(f"Attempting GET to {request_url}")
    try_count = 0
    while True:
        try:
            response = requests.get(request_url, timeout=6)
            logging.info(f"Response: {response.json()}")
            return response.json()

        except Exception as e:
            if try_count < max_tries:
                logging.error(f"Failed GET request ({request_url}). Retrying...", exc_info=True)
                time.sleep(1)
            else:
                raise e
        try_count += 1

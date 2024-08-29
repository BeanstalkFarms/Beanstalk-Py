from abc import abstractmethod
import asyncio.exceptions

from bots.util import *

class Monitor:
    """Base class for monitors. Do not use directly.

    Args:
        name: simple human readable name string to use for logging.
        message_function: fun(str) style function to send application messages.
        query_rate: int representing rate monitored data should be queried (in seconds).
        prod: bool indicating if this is a production instance or not.
    """

    def __init__(self, name, message_function, query_rate, prod=False, dry_run=None):
        self.name = name
        self.message_function = message_function
        self.query_rate = query_rate
        self.prod = prod
        self._dry_run = dry_run
        # Time to wait before restarting monitor after an unhandled exception. Exponential backoff.
        self.monitor_reset_delay = RESET_MONITOR_DELAY_INIT
        self._thread_active = False
        self._thread_wrapper = threading.Thread(target=self._thread_wrapper_method)
        self._web3 = get_web3_instance()

    @abstractmethod
    def _monitor_method(self):
        pass

    def start(self):
        logging.info(f"Starting {self.name} monitoring thread...")
        if self._dry_run:
            self.message_function(f"{self.name} monitoring started (with simulated data).")
        elif not self.prod:
            self.message_function(f"{self.name} monitoring started.")
        self._thread_active = True
        self._thread_wrapper.start()

    def stop(self):
        logging.info(f"Stopping {self.name} monitoring thread...")
        if not self.prod:
            self.message_function(f"{self.name} monitoring stopped.")
        self._thread_active = False
        self._thread_wrapper.join(3 * self.query_rate)

    def _thread_wrapper_method(self):
        """
        If an unhandled exception occurred in the monitor and it is killed, log the exception here
        and restart the monitor.
        """
        retry_time = 0
        while self._thread_active:
            if time.time() < retry_time:
                logging.info(
                    f"Waiting {retry_time - time.time()} more seconds before restarting "
                    f" monitor on {self.name} thread."
                )
                time.sleep(1)
                continue
            logging.info(f"Starting monitor on {self.name} thread.")
            self._web3 = get_web3_instance()
            try:
                self._monitor_method()
            # Websocket disconnects are expected occasionally.
            except websockets.exceptions.ConnectionClosedError as e:
                logging.error(f"Websocket connection closed error\n{e}\n**restarting the monitor**")
                logging.warning(e, exc_info=True)
            # Timeouts on data access are expected occasionally.
            except asyncio.exceptions.TimeoutError as e:
                logging.error(f"Asyncio timeout error:\n{e}\n**restarting the monitor**")
                logging.warning(e, exc_info=True)
            except Exception as e:
                logging.error(
                    f"Unhandled exception in the {self.name} thread."
                    f"\n**restarting the monitor**."
                )
                logging.warning(e, exc_info=True)
            # Reset the restart delay after a stretch of successful running.
            if time.time() > retry_time + 3600:
                self.monitor_reset_delay = RESET_MONITOR_DELAY_INIT
            else:
                self.monitor_reset_delay *= 2
            retry_time = time.time() + self.monitor_reset_delay
        logging.warning("Thread wrapper returned.")

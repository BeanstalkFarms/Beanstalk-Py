from opensea import OpenseaAPI

from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.contracts.util import *
from data_access.util import *
from constants.addresses import *
from constants.config import *

GENESIS_SLUG = "beanft-genesis"
WINTER_SLUG = "beanft-winter"
BARN_RAISE_SLUG = "beanft-barn-raise"

class NFTPreviewMonitor(PreviewMonitor):
    """Monitor data that offers a view into BeaNFT collections."""

    def __init__(self, name_function, status_function):
        super().__init__("NFT", name_function, status_function, check_period=8)
        self.opensea_api = None

    def _monitor_method(self):
        api_key = os.environ["OPEN_SEA_KEY"]
        self.opensea_api = OpenseaAPI(apikey=api_key)
        while self._thread_active:
            self.wait_for_next_cycle()
            self.iterate_display_index()

            # Rotate data and update status.
            name_str = ""
            status_str = ""

            # Set collection slug and name.
            if self.display_index == 0:
                slug = GENESIS_SLUG
                name = "Genesis BeaNFT"
            elif self.display_index == 1:
                slug = WINTER_SLUG
                name = "Winter BeaNFT"
            elif self.display_index == 2:
                slug = BARN_RAISE_SLUG
                name = "Barn Raise BeaNFT"
            else:
                logging.exception("Invalid status index for NFT Preview Bot.")
                continue

            # Set bot name and status.
            # Floor price preview.
            if self.display_index in [0, 1, 2]:
                logging.info(f"Retrieving OpenSea data for {slug} slug...")
                collection = self.opensea_api.collection_stats(collection_slug=slug)
                logging.info(f"OpenSea data for {slug} slug:\n{collection}")
                collection_stats = collection["stats"]
                name_str = f'{holiday_emoji()}Floor: {collection_stats["floor_price"]}Ξ'
                status_str = f"{name}"

            self.name_function(name_str)
            self.status_function(status_str)

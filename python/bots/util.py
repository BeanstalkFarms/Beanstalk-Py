from enum import Enum
import logging

from subgraphs.bean_subgraph import (
    BeanSqlClient, PRICE_FIELD, LAST_PEG_CROSS_FIELD)

# There is a built in assumption that we will update at least once per
# Ethereum block (~13.5 seconds), so frequency should not be set too low.
PEG_UPDATE_FREQUENCY = 0.1  # hz


class PegCrossType(Enum):
    NO_CROSS = 0
    CROSS_ABOVE = 1
    CROSS_BELOW = 2


def peg_cross_string(cross_type):
    """Return peg cross string used for bot messages."""
    # NOTE(funderberker): Have to compare enum values here because method of import of caller
    # can change the enum id.
    if cross_type.value == PegCrossType.CROSS_ABOVE.value:
        return 'BEAN crossed above peg! 🟩↗'
    elif cross_type.value == PegCrossType.CROSS_BELOW.value:
        return 'BEAN crossed below peg! 🟥↘'
    else:
        return 'Peg not crossed.'


class PegCrossMonitor():

    def __init__(self):
        self.last_known_cross = 0
        self.bean_subgraph_client = BeanSqlClient()

    async def check_for_peg_cross(self):
        """
        Check to see if the peg has been crossed since the last known timestamp of the caller.
        Assumes that block time > period of subgraph checks.

        Note that this call can take over 10 seconds due to graph access delays. If an access
        takes longer than two blocks it is possible to miss a cross (only the latest cross)
        will be reported.

        Returns:
            PegCrossType
        """
        cross_type = PegCrossType.NO_CROSS

        # Get latest data from subgraph. May take 10+ seconds.
        result = await self.bean_subgraph_client.get_bean_fields([LAST_PEG_CROSS_FIELD, PRICE_FIELD])
        last_cross = int(result[LAST_PEG_CROSS_FIELD])
        price = float(result[PRICE_FIELD])

        # # For testing.
        # import random
        # self.last_known_cross = 1
        # price = random.uniform(0.5, 1.5)

        if not self.last_known_cross:
            logging.info('Peg cross timestamp initialized with last peg cross = '
                         f'{last_cross}')
            self.last_known_cross = last_cross
            return cross_type

        if last_cross > self.last_known_cross:
            if price >= 1.0:
                logging.info('Price crossed above peg.')
                cross_type = PegCrossType.CROSS_ABOVE
            else:
                logging.info('Price crossed below peg.')
                cross_type = PegCrossType.CROSS_BELOW
        self.last_known_cross = last_cross
        return cross_type

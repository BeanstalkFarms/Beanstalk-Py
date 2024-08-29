from bots.util import *
from monitors.preview.preview import PreviewMonitor
from data_access.contracts.util import *
from data_access.subgraphs.snapshot import SnapshotGraphClient
from data_access.subgraphs.beanstalk import BeanstalkGraphClient
from data_access.util import *
from constants.addresses import *
from constants.config import *

class SnapshotPreviewMonitor(PreviewMonitor):
    """Monitor active Snapshots and display via discord nickname/status."""

    def __init__(self, name_function, status_function):
        super().__init__(
            "Snapshot", name_function, status_function, 1, check_period=PREVIEW_CHECK_PERIOD
        )
        self.last_name = ""
        self.last_status = ""

    def _monitor_method(self):
        self.snapshot_client = SnapshotGraphClient()
        self.beanstalk_graph_client = BeanstalkGraphClient()
        while self._thread_active:
            active_proposals = self.snapshot_client.get_active_proposals()
            if len(active_proposals) == 0:
                self.name_function("DAO: 0 active")
                self.status_function(f"snapshot.org/#/" + DAO_SNAPSHOT_NAME)
                time.sleep(60)
                continue

            # Rotate data and update status.
            for proposal in active_proposals:
                votable_stalk = stalk_to_float(
                    self.beanstalk_graph_client.get_start_stalk_by_season(
                        self.beanstalk_graph_client.get_season_id_by_timestamp(proposal["start"])
                    )
                )
                logging.info(f"votable_stalk = {votable_stalk}")

                # self.status_function(proposal['title'])

                self.name_function(f'DAO: {proposal["title"]}')
                self.status_function(f'Votes: {round_num(proposal["scores_total"], 0)}')
                self.wait_for_next_cycle()
                for i in range(len(proposal["choices"])):
                    try:
                        self.status_function(
                            f'{round_num(100 * proposal["scores"][i] / votable_stalk,2)}% - {proposal["choices"][i]}'
                        )
                    except IndexError:
                        # Unkown if Snapshot guarantees parity between these arrays.
                        break
                    self.wait_for_next_cycle()

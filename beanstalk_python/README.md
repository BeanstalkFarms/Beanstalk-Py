# Python Tooling
This is the Beanstalk Python tooling library. Initially motivated by the desire to set up a series of communication channel bots.

## Hosting
Some of the planned bots will require running continuous processes and/or maintaining state. In order to allow this some amount of compute resources will be necessary to host the bots logic on.
This host will collect data from the subgraphs, manipulate and store it locally, then forward it through bots or API responses.

Initial implementation will use GCP with the intention of migrating to a decentralized service in the future.

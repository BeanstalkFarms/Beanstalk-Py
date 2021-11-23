# Graphs
This package includes Python modules for interacting with Beanstalk subgraphs. There are two subgraphs: _beanstalk_ and _bean_.

https://gql.readthedocs.io/en/v3.0.0b0/

## Beanstalk Subgraph
The beanstalk subgraph tracks the complete state of Beanstalk as well as time series data for the Beanstalk Protocol.

This is very fast because it is published (decentralized) and has plenty of signal.

https://github.com/BeanstalkFarms/Beanstalk-Subgraph/blob/master/schema.graphql

https://gateway.thegraph.com/api/[API_KEY]/subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-0


## Bean Subgraph
The bean subgraph tracks time series data for the Bean token. It includes all events in the Uniswap pool, which takes a significant amount of time to fully index.

Bean subgraph is not yet published, so it is rate limited and will take longer to return requests. Will be published soon.

https://github.com/BeanstalkFarms/Bean-Subgraph/blob/master/schema.graphql (GitHub not set up yet)

https://api.studio.thegraph.com/query/6727/bean/v0.0.10 (centralized)


## Python Client Configuration
The client is built on top of [GQL 3](https://gql.readthedocs.io/en/v3.0.0b0/). Underlying connections are made using HTTP through the [aiohttp](https://docs.aiohttp.org/en/stable/) library. Each subgraph has its own module.

## Graph Data
To see what data is available through the subgraphs go to https://lucasconstantino.github.io/graphiql-online/ and enter the API URLs above.

# Ethereum Chain
https://infura.io/docs/ethereum

https://web3py.readthedocs.io/en/stable/

https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371


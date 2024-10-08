# Graphs
This package includes Python modules for interacting with Beanstalk subgraphs. There are two subgraphs: _beanstalk_ and _bean_.

https://gql.readthedocs.io/en/v3.0.0b0/

## Beanstalk Subgraph
The beanstalk subgraph tracks the complete state of Beanstalk as well as time series data for the Beanstalk Protocol.

This is very fast because it is published (decentralized) and has plenty of signal.

https://github.com/BeanstalkFarms/Beanstalk-Subgraph/blob/master/schema.graphql

https://gateway.thegraph.com/api/[api-key]/subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-0


## Bean Subgraph
The bean subgraph tracks time series data for the Bean token. It includes all events in the Uniswap pool, which takes a significant amount of time to fully index.

Bean subgraph is not yet published, so it is rate limited and will take longer to return requests. Will be published soon.

https://github.com/BeanstalkFarms/Bean-Subgraph/blob/master/schema.graphql (GitHub not set up yet)

https://api.studio.thegraph.com/query/6727/bean/v1.1.11 (centralized)
https://gateway.thegraph.com/api/[api-key]/subgraphs/id/0x925753106fcdb6d2f30c3db295328a0a1c5fd1d1-1

## Python Client Configuration
The client is built on top of [GQL 3](https://gql.readthedocs.io/en/v3.0.0b0/). Underlying connections are made using HTTP through the [aiohttp](https://docs.aiohttp.org/en/stable/) library. Each subgraph has its own module.

## Graph Data
To see what data is available through the subgraphs go to https://lucasconstantino.github.io/graphiql-online/ and enter the API URLs above.

# Ethereum Chain
https://infura.io/docs/ethereum

https://web3py.readthedocs.io/en/stable/

https://v2.info.uniswap.org/pair/0x87898263b6c5babe34b4ec53f22d98430b91e371

## Chain Data Access with the Web3 Library
The Web3 library documentation leaves a lot to be desired. Here is some useful information about how
it is used in these libraries and what the different classes look like.

### Signature string derived from ABI.
`sig = 'updateSilo(address)'`

### Signature hash derived from ABI.
`sig_hash = Web3.keccak(text=sig).hex()`

### The first characters of the signature hash match the input hash of the txn if the txn is calling the method the signature was derived from.

`sig_hash  == '0x8bee54996fc63a60b4064e74faf3927ea904b1dba603e61fd889ffaaee0a68c5'`

`txn_input == '0x8bee54990000000000000000000000003c5aac016ef2f178e8699d6208796a2d67557fe2'`

https://arbiscan.io/tx/0x7f6b1c80301461b743a7b8137963b4e91f4015d8b3a3398f2dbebc4f5e6538d2

### Transaction
`AttributeDict({'accessList': [], 'blockHash': HexBytes('0x5ed9d97812da3e8ec8d6a4bc3d7191d5ddb319d4fe28ca3315e256b56e04a353'), 'blockNumber': 13819425, 'chainId': '0x1', 'from': '0xC81635aBBF6EC73d0271F237a78b6456D6766132', 'gas': 134557, 'gasPrice': 109766341103,'hash': HexBytes('0x3ee69e0eba363b93fb0f27c81126c1082e41d4d64bcfaa96b5e7b4a4b5438ba4'), 'input': '0x8bee5499000000000000000000000000c81635abbf6ec73d0271f237a78b6456d6766132','maxFeePerGas': 126976614339, 'maxPriorityFeePerGas': 1500000000, 'nonce': 59, 'r': HexBytes('0x404cc33dff15b14eacb9cc47b9fc46c02b6153533eac5d49698c00660e34b96f'), 's': HexBytes('0x73e97b3a43767f9a8bcdc081af5fa201e92809c8215c06b923a994cde9e0ef3b'), 'to': '0xD1A0060ba708BC4BCD3DA6C37EFa8deDF015FB70', 'transactionIndex': 426, 'type': '0x2', 'v': 0, 'value': 0})`

### Receipt

`AttributeDict({'blockHash': HexBytes('0x5ed9d97812da3e8ec8d6a4bc3d7191d5ddb319d4fe28ca3315e256b56e04a353'),'blockNumber': 13819425, 'contractAddress': None, 'cumulativeGasUsed': 20483913, 'effectiveGasPrice': 109766341103, 'from': '0xC81635aBBF6EC73d0271F237a78b6456D6766132', 'gasUsed': 130717, 'logs': [AttributeDict({'address': '0xD1A0060ba708BC4BCD3DA6C37EFa8deDF015FB70', 'blockHash': HexByte('0x5ed9d97812da3e8ec8d6a4bc3d7191d5ddb319d4fe28ca3315e256b56e04a353'), 'blockNumber': 13819425, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c560000000000000000000000000000000000000000000000000000000305a3d0d8', 'logIndex': 422, 'removed': False, 'topics': [HexByte('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x000000000000000000000000c81635abbf6ec73d0271f237a78b6456d6766132')], 'transactionHash': HexBytes('0x3ee69e0eba363b93fb0f27c81126c1082e41d4d64bcfaa96b5e7b4a4b5438ba4'), 'transactionIndex': 426}), AttributeDict({'address': '0xD1A0060ba708BC4BCD3DA6C37EFa8deDF015FB70', 'blockHash': HexBytes('0x5ed9d97812da3e8ec8d6a4bc3d7191d5ddb319d4fe28ca3315e256b56e04a353'), 'blockNumber': 13819425, 'data': '0x0000000000000000000000000000000000000000000000000000000000000c56000000000000000000000000000000000000000000000000000000041fe9edf2', 'logIndex': 423, 'removed': False, 'topics': [HexBytes('0x916fd954accea6bad98fd6d8dda65058a5a16511534ebb14b2380f24aa61cc3a'), HexBytes('0x000000000000000000000000c81635abbf6ec73d0271f237a78b6456d6766132')], 'transactionHash': HexBytes('0x3ee69e0eba363b93fb0f27c81126c1082e41d4d64bcfaa96b5e7b4a4b5438ba4'), 'transactionIndex': 426})], 'logsBloom': HexByte('0x00000000000000040000000000000000000000000000000004000000000000000000000000000000201000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'), 'status': 1, 'to': '0xD1A0060ba708BC4BCD3DA6C37EFa8deDF015FB70', 'transactionHash': HexBytes('0x3ee69e0eba363b93fb0f27c81126c1082e41d4d64bcfaa96b5e7b4a4b5438ba4'), 'transactionIndex': 426, 'type': '0x2'})`
from datetime import datetime
from subgrounds.subgraph import SyntheticField, FieldPath
from subgrounds.subgrounds import Subgrounds

sg = Subgrounds()
#bean = sg.load_subgraph('https://gateway.thegraph.com/api/e34fb57b214a5d092654d30c465b7e51/subgraphs/id/CsmWTbztr1EQcRYmgqUYpSaVc8exTnVmhUxsaswvkbjG')

bean = sg.load_subgraph('https://api.studio.thegraph.com/query/25536/bean/1.1.12')

#bean = sg.load_subgraph('http://3.17.129.41:8000/subgraphs/name/bean-dev')


# Let's convert the timestamp to humanreadable date tie format
bean.PoolDayData.dayDatetime = SyntheticField(
  lambda timestamp: str(datetime.fromtimestamp(timestamp)),
  SyntheticField.STRING,
  bean.PoolDayData.dayTimestamp,
)

bean.PoolHourData.hourDatetime = SyntheticField(
  lambda timestamp: str(datetime.fromtimestamp(timestamp)),
  SyntheticField.STRING,
  bean.PoolHourData.hourTimestamp,
)

# Let's pull the last 100 days by day price data from the Price/liquidity fields
pricesETH_100daysD = bean.Query.poolDayDatas(
      first=100,
      orderBy=bean.PoolDayData.dayTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
      where={
     'pool': '0x87898263b6c5babe34b4ec53f22d98430b91e371'
      }
)

sg.query_df([
  pricesETH_100daysD.id,
  pricesETH_100daysD.dayDatetime,
  pricesETH_100daysD.price,
  pricesETH_100daysD.liquidityUSD,
  pricesETH_100daysD.volumeUSD,
  pricesETH_100daysD.delta,
  pricesETH_100daysD.newCrosses,
  pricesETH_100daysD.totalCrosses,
])

prices3CRV_100daysD = bean.Query.poolDayDatas(
      first=100,
      orderBy=bean.PoolDayData.dayTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
      where={
     'pool': '0x3a70dfa7d2262988064a2d051dd47521e43c9bdd'
      }
)

sg.query_df([
  prices3CRV_100daysD.id,
  prices3CRV_100daysD.dayDatetime,
  prices3CRV_100daysD.price,
  prices3CRV_100daysD.liquidityUSD,
  prices3CRV_100daysD.volumeUSD,
  prices3CRV_100daysD.delta,
  prices3CRV_100daysD.newCrosses,
  prices3CRV_100daysD.totalCrosses,
])

pricesLUSD_100daysD = bean.Query.poolDayDatas(
      first=100,
      orderBy=bean.PoolDayData.dayTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
      where={
     'pool': '0xd652c40fbb3f06d6b58cb9aa9cff063ee63d465d'
      }
)

sg.query_df([
  pricesLUSD_100daysD.id,
  pricesLUSD_100daysD.dayDatetime,
  pricesLUSD_100daysD.price,
  pricesLUSD_100daysD.liquidityUSD,
  pricesLUSD_100daysD.volumeUSD,
  pricesLUSD_100daysD.delta,
  pricesLUSD_100daysD.newCrosses,
  pricesLUSD_100daysD.totalCrosses,
])

# Let's pull the last 30 days by hour price data from the Price/liquidity fields
pricesETH_30daysH = bean.Query.poolHourDatas(
      first=720,
      orderBy=bean.PoolHourData.hourTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
      where={
     'pool': '0x87898263b6c5babe34b4ec53f22d98430b91e371'
      }
)

sg.query_df([
  pricesETH_30daysH.id,
  pricesETH_30daysH.hourDatetime,
  pricesETH_30daysH.price,
  pricesETH_30daysH.liquidityUSD,
  pricesETH_30daysH.volumeUSD,
  pricesETH_30daysH.delta,
  pricesETH_30daysH.newCrosses,
  pricesETH_30daysH.totalCrosses,
])

prices3CRV_30daysH = bean.Query.poolHourDatas(
      first=720,
      orderBy=bean.PoolHourData.hourTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
      where={
     'pool': '0x3a70dfa7d2262988064a2d051dd47521e43c9bdd'
      }
)

sg.query_df([
  prices3CRV_30daysH.id,
  prices3CRV_30daysH.hourDatetime,
  prices3CRV_30daysH.price,
  prices3CRV_30daysH.liquidityUSD,
  prices3CRV_30daysH.volumeUSD,
  prices3CRV_30daysH.delta,
  prices3CRV_30daysH.newCrosses,
  prices3CRV_30daysH.totalCrosses,
])

pricesLUSD_30daysH = bean.Query.poolHourDatas(
      first=720,
      orderBy=bean.PoolHourData.hourTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
      where={
     'pool': '0xd652c40fbb3f06d6b58cb9aa9cff063ee63d465d'
      }
)

sg.query_df([
  pricesLUSD_30daysH.id,
  pricesLUSD_30daysH.hourDatetime,
  pricesLUSD_30daysH.price,
  pricesLUSD_30daysH.liquidityUSD,
  pricesLUSD_30daysH.volumeUSD,
  pricesLUSD_30daysH.delta,
  pricesLUSD_30daysH.newCrosses,
  pricesLUSD_30daysH.totalCrosses,
])

# Let's convert the timestamp to humanreadable date tie format
bean.BeanDayData.dayDatetime = SyntheticField(
  lambda timestamp: str(datetime.fromtimestamp(timestamp)),
  SyntheticField.STRING,
  bean.BeanDayData.dayTimestamp,
)

bean.BeanHourData.hourDatetime = SyntheticField(
  lambda timestamp: str(datetime.fromtimestamp(timestamp)),
  SyntheticField.STRING,
  bean.BeanHourData.hourTimestamp,
)

# Let's pull the last 100 days by day bean data from the Bean fields
bean_100daysD = bean.Query.beanDayDatas(
      first=100,
      orderBy=bean.BeanDayData.dayTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
)

sg.query_df([
  bean_100daysD.id,
  bean_100daysD.dayDatetime,
  bean_100daysD.totalVolumeUSD,
  bean_100daysD.totalLiquidityUSD,
  bean_100daysD.averagePrice,
])

# Let's pull the last 30 days by hour bean data from the Bean fields
bean_30daysH = bean.Query.beanHourDatas(
      first=100,
      orderBy=bean.BeanHourData.hourTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
)

sg.query_df([
  bean_30daysH.id,
  bean_30daysH.hourDatetime,
  bean_30daysH.totalVolumeUSD,
  bean_30daysH.totalLiquidityUSD,
  bean_30daysH.averagePrice,
])
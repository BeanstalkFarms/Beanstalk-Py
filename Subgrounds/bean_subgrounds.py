from datetime import datetime
from subgrounds.subgraph import SyntheticField, FieldPath
from subgrounds.subgrounds import Subgrounds

sg = Subgrounds()
#bean = sg.load_subgraph('https://gateway.thegraph.com/api/e34fb57b214a5d092654d30c465b7e51/subgraphs/id/CsmWTbztr1EQcRYmgqUYpSaVc8exTnVmhUxsaswvkbjG')

#bean = sg.load_subgraph('https://api.studio.thegraph.com/query/23084/beandev/0.0.4')

bean = sg.load_subgraph('http://18.118.165.15:8000/subgraphs/name/bean-dev')


# Let's convert the timestamp to humanreadable date tie format
bean.DayData.dayDatetime = SyntheticField(
  lambda timestamp: str(datetime.fromtimestamp(timestamp)),
  SyntheticField.STRING,
  bean.DayData.dayTimestamp,
)

bean.HourData.hourDatetime = SyntheticField(
  lambda timestamp: str(datetime.fromtimestamp(timestamp)),
  SyntheticField.STRING,
  bean.HourData.hourTimestamp,
)

# Let's pull the last 100 days by day price data from the Price fields
prices_100daysD = bean.Query.dayDatas(
      first=100,
      orderBy=bean.DayData.dayTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
)

sg.query_df([
  prices_100daysD.id,
  prices_100daysD.dayDatetime,
  prices_100daysD.price,
  prices_100daysD.curveSwapPrice3CRV,
  prices_100daysD.curveSwapPriceLUSD,
  prices_100daysD.curveUSDCPrice,
  prices_100daysD.curveUSDTPrice,
  prices_100daysD.curveDAIPrice,
  prices_100daysD.curveLUSDPrice,
  prices_100daysD.curveVirtualPrice3CRV,
  prices_100daysD.uniswapLPUSD,
  prices_100daysD.curve3CRVLPUSD,
  prices_100daysD.curveLUSDLPUSD,
  prices_100daysD.curveTotalLPUSD,
  prices_100daysD.curve3CRVLpUsage,
  prices_100daysD.curveLUSDLpUsage,
  prices_100daysD.curve3CRVVolumeUSD,
  prices_100daysD.curveLUSDVolumeUSD,
])

# Let's pull the last 100 days by day price data from the Price fields
prices_30daysH = bean.Query.hourDatas(
      first=720,
      orderBy=bean.HourData.hourTimestamp,
      orderDirection='desc',
  		subgraphError='deny',
)

sg.query_df([
  prices_30daysH.id,
  prices_30daysH.hourDatetime,
  prices_30daysH.price,
  prices_30daysH.curveSwapPrice3CRV,
  prices_30daysH.curveSwapPriceLUSD,
  prices_30daysH.curveUSDCPrice,
  prices_30daysH.curveUSDTPrice,
  prices_30daysH.curveDAIPrice,
  prices_30daysH.curveLUSDPrice,
  prices_30daysH.curveVirtualPrice3CRV,
  prices_30daysH.uniswapLPUSD,
  prices_30daysH.curve3CRVLPUSD,
  prices_30daysH.curveLUSDLPUSD,
  prices_30daysH.curveTotalLPUSD,
  prices_30daysH.curve3CRVLpUsage,
  prices_30daysH.curveLUSDLpUsage,
  prices_30daysH.curve3CRVVolumeUSD,
  prices_30daysH.curveLUSDVolumeUSD,
])
import dash
import dash_bootstrap_components as dbc
from dash import html
from subgrounds.dash_wrappers import Graph
from subgrounds.plotly_wrappers import Figure, Scatter
from bean_subgrounds import (
    sg,
    bean_100daysD,
    bean_30daysH,
    pricesETH_100daysD,
    prices3CRV_100daysD,
    pricesLUSD_100daysD,
    pricesETH_30daysH,
    prices3CRV_30daysH,
    pricesLUSD_30daysH,
)

# This is a simple demonstration on how to build a dashboard powered by Subgrounds and Dash
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SLATE])
server = app.server
# This is where you start constructing your dashboard components
# Everything is built inside a container, but you can use HTML div if you prefer
app.layout = dbc.Container(
    [
        # Rows and Columns help with building a grid layout system
        # First row for some simple dashboard label
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label(
                            "BEAN Subgraph Metrics",
                            style={
                                "font-style": "normal",
                                "font-weight": "600",
                                "font-size": "64px",
                                "line-height": "96px",
                                "color": "#FFFFFF",
                            },
                            xs=12,
                            sm=12,
                            md=12,
                            lg=6,
                            xl=6,
                        )
                    ]
                ),
            ]
        ),
        # Second row for to contain the price charts cards
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # BEAN pool prices for the last 100 days
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_100daysD.dayDatetime,
                                                                        y=pricesETH_100daysD.price,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV pool",
                                                                        x=prices3CRV_100daysD.dayDatetime,
                                                                        y=prices3CRV_100daysD.price,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD pool",
                                                                        x=pricesLUSD_100daysD.dayDatetime,
                                                                        y=pricesLUSD_100daysD.price,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "100 days - Daily BEAN Prices",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # BEAN pool prices for the last 30 days hourly
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_30daysH.hourDatetime,
                                                                        y=pricesETH_30daysH.price,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV pool",
                                                                        x=prices3CRV_30daysH.hourDatetime,
                                                                        y=prices3CRV_30daysH.price,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD pool",
                                                                        x=pricesLUSD_30daysH.hourDatetime,
                                                                        y=pricesLUSD_30daysH.price,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - hourly BEAN Prices",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # BEAN pool delta newCrosses for the last 100 days
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_100daysD.dayDatetime,
                                                                        y=pricesETH_100daysD.newCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV pool",
                                                                        x=prices3CRV_100daysD.dayDatetime,
                                                                        y=prices3CRV_100daysD.newCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD pool",
                                                                        x=pricesLUSD_100daysD.dayDatetime,
                                                                        y=pricesLUSD_100daysD.newCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - hourly BEAN Delta newCrosses",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # BEAN pool delta newCrosses for the last 30 days hourly
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_30daysH.hourDatetime,
                                                                        y=pricesETH_30daysH.newCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV pool",
                                                                        x=prices3CRV_30daysH.hourDatetime,
                                                                        y=prices3CRV_30daysH.newCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD pool",
                                                                        x=pricesLUSD_30daysH.hourDatetime,
                                                                        y=pricesLUSD_30daysH.newCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - hourly BEAN delta newCrosses",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # BEAN pool delta totalCrosses for the last 100 days
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_100daysD.dayDatetime,
                                                                        y=pricesETH_100daysD.totalCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV pool",
                                                                        x=prices3CRV_100daysD.dayDatetime,
                                                                        y=prices3CRV_100daysD.totalCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD pool",
                                                                        x=pricesLUSD_100daysD.dayDatetime,
                                                                        y=pricesLUSD_100daysD.totalCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - hourly BEAN Delta totalCrosses",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # BEAN pool delta crototalCrossessses for the last 30 days hourly
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_30daysH.hourDatetime,
                                                                        y=pricesETH_30daysH.totalCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV pool",
                                                                        x=prices3CRV_30daysH.hourDatetime,
                                                                        y=prices3CRV_30daysH.totalCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD pool",
                                                                        x=pricesLUSD_30daysH.hourDatetime,
                                                                        y=pricesLUSD_30daysH.totalCrosses,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - hourly BEAN delta totalCrosses",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                            ]
                        ),
                    ]
                ),
            ]
        ),
        # Second row for to contain the Volume/liquidity charts cards
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Uniswap and Curve USD Liquidity for the last 100 days
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_100daysD.dayDatetime,
                                                                        y=pricesETH_100daysD.liquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV Factory",
                                                                        x=prices3CRV_100daysD.dayDatetime,
                                                                        y=prices3CRV_100daysD.liquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD Factory",
                                                                        x=pricesLUSD_100daysD.dayDatetime,
                                                                        y=pricesLUSD_100daysD.liquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="Bean Total liquidity",
                                                                        x=bean_100daysD.dayDatetime,
                                                                        y=bean_100daysD.totalLiquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "yellow",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "100 days - Daily BEAN Liquidity",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Uniswap and Curve USD Liquidity for the last 30 days hourly
                                                                    Scatter(
                                                                        name="BEAN/ETH Uniswap",
                                                                        x=pricesETH_30daysH.hourDatetime,
                                                                        y=pricesETH_30daysH.liquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/3CRV Factory",
                                                                        x=prices3CRV_30daysH.hourDatetime,
                                                                        y=prices3CRV_30daysH.liquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="BEAN/LUSD Factory",
                                                                        x=pricesLUSD_30daysH.hourDatetime,
                                                                        y=pricesLUSD_30daysH.liquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="Bean Total liquidity",
                                                                        x=bean_30daysH.hourDatetime,
                                                                        y=bean_30daysH.totalLiquidityUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "yellow",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - Hourly BEAN Total Liquidity",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Bean Average DEX price for the last 100 days
                                                                    Scatter(
                                                                        name="BEAN average Price",
                                                                        x=bean_100daysD.dayDatetime,
                                                                        y=bean_100daysD.averagePrice,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "yellow",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "100 days - Daily Bean Average DEX Price",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Bean Average DEX price for the last 30 days hourly
                                                                    Scatter(
                                                                        name="BEAN average Price",
                                                                        x=bean_30daysH.hourDatetime,
                                                                        y=bean_30daysH.averagePrice,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "yellow",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - Daily Bean Average DEX Price",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Pool Delta for the last 100 days
                                                                    Scatter(
                                                                        name="ETH Pool Delta",
                                                                        x=pricesETH_100daysD.dayDatetime,
                                                                        y=pricesETH_100daysD.delta,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="3CRV Pool Delta",
                                                                        x=prices3CRV_100daysD.dayDatetime,
                                                                        y=prices3CRV_100daysD.delta,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="LUSD Pool Delta",
                                                                        x=pricesLUSD_100daysD.dayDatetime,
                                                                        y=pricesLUSD_100daysD.delta,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "100 days - Daily Pool Delta",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Pool Delta for the last 30 days by hour
                                                                    Scatter(
                                                                        name="ETH Pool Delta",
                                                                        x=pricesETH_30daysH.hourDatetime,
                                                                        y=pricesETH_30daysH.delta,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="3CRV Pool Delta",
                                                                        x=prices3CRV_30daysH.hourDatetime,
                                                                        y=prices3CRV_30daysH.delta,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="LUSD Pool Delta",
                                                                        x=pricesLUSD_30daysH.hourDatetime,
                                                                        y=pricesLUSD_30daysH.delta,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - Hourly Pool Delta",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Pool Volume for the last 100 days
                                                                    Scatter(
                                                                        name="ETH Pool Delta",
                                                                        x=pricesETH_100daysD.dayDatetime,
                                                                        y=pricesETH_100daysD.volumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="3CRV Pool Delta",
                                                                        x=prices3CRV_100daysD.dayDatetime,
                                                                        y=prices3CRV_100daysD.volumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="LUSD Pool Delta",
                                                                        x=pricesLUSD_100daysD.dayDatetime,
                                                                        y=pricesLUSD_100daysD.volumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "100 days - Daily Pools Volume",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Pool Volume for the last 30 days hourly
                                                                    Scatter(
                                                                        name="ETH Pool Delta",
                                                                        x=pricesETH_30daysH.hourDatetime,
                                                                        y=pricesETH_30daysH.volumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "blue",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="3CRV Pool Delta",
                                                                        x=prices3CRV_30daysH.hourDatetime,
                                                                        y=prices3CRV_30daysH.volumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "green",
                                                                        },
                                                                    ),
                                                                    Scatter(
                                                                        name="LUSD Pool Delta",
                                                                        x=pricesLUSD_30daysH.hourDatetime,
                                                                        y=pricesLUSD_30daysH.volumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "red",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - Daily Pools Volume",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Bean total USD Volume for the last 100 days
                                                                    Scatter(
                                                                        name="BEAN USD Volume",
                                                                        x=bean_100daysD.dayDatetime,
                                                                        y=bean_100daysD.totalVolumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "yellow",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "100 days - Daily Bean Total Volume",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        Graph(
                                                            Figure(
                                                                subgrounds=sg,
                                                                traces=[
                                                                    # Bean total USD Volume for the last 30 days hourly
                                                                    Scatter(
                                                                        name="BEAN USD Volume",
                                                                        x=bean_30daysH.hourDatetime,
                                                                        y=bean_30daysH.totalVolumeUSD,
                                                                        mode="lines",
                                                                        line={
                                                                            "width": 2,
                                                                            "color": "yellow",
                                                                        },
                                                                    ),
                                                                ],
                                                                layout={
                                                                    "showlegend": True,
                                                                    "xaxis": {
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "showgrid": False,
                                                                    },
                                                                    "yaxis": {
                                                                        "type": "linear",
                                                                        "linewidth": 0.1,
                                                                        "linecolor": "#31333F",
                                                                        "color": "white",
                                                                        "title": "30 days - Daily Bean Total Volume",
                                                                        "showgrid": False,
                                                                    },
                                                                    "legend.font.color": "white",
                                                                    "paper_bgcolor": "#000000",
                                                                    "plot_bgcolor": "rgba(0,0,0,0)",
                                                                },
                                                            )
                                                        )
                                                    ]
                                                ),
                                            ],
                                            className="analytics_card_metric",
                                            style={"text-align": "center"},
                                        ),
                                    ]
                                ),
                            ]
                        )
                    ]
                ),
            ]
        ),
        html.Footer(
            "Powered by Playgrounds",
            style={
                "backgrounds-color": "#2e343e",
                "color": "white",
                "font-size": "20px",
                "padding": "10px",
            },
        ),
    ],
    style={"backgroundColor": "#2a3847"},
    fluid=True,
)

if __name__ == "__main__":
    app.run_server(debug=True, host="localhost", port=8052)

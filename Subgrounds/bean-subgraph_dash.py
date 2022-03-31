import dash
import dash_bootstrap_components as dbc
from dash import html
from subgrounds.dash_wrappers import Graph
from subgrounds.plotly_wrappers import Figure, Scatter
from bean_subgrounds import sg, prices_100daysD, prices_30daysH

# This is a simple demonstration on how to build a dashboard powered by Subgrounds and Dash
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SLATE])
server = app.server
# This is where you start constructing your dashboard components
# Everything is built inside a container, but you can use HTML div if you prefer
app.layout = dbc.Container([
    # Rows and Columns help with building a grid layout system
    # First row for some simple dashboard label
    dbc.Row([
        dbc.Col([
            dbc.Label('BEAN Subgraph Prices',
                      style={'font-style': 'normal',
                             'font-weight': '600',
                             'font-size': '64px',
                             'line-height': '96px',
                             'color': '#FFFFFF'
                             }, xs=12, sm=12, md=12, lg=6, xl=6)
        ]),
    ]),
    # Second row for to contain the price charts cards
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # BEAN pool prices for the last 100 days
                                    Scatter(
                                        name='BEAN/ETH Uniswap',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.price,
                                        mode='lines',
                                        line={'width': 2, 'color': 'blue'},
                                    ),
                                    Scatter(
                                        name='BEAN/3CRV pool',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveSwapPrice3CRV,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD pool',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveSwapPriceLUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                    Scatter(
                                        name='PEG Line',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveVirtualPrice3CRV,
                                        mode='lines',
                                        line={'width': 0.5, 'color': 'white'},
                                    ),                                     
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '100 days - Daily BEAN Prices',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # BEAN pool prices for the last 30 days hourly
                                    Scatter(
                                        name='BEAN/ETH Uniswap',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.price,
                                        mode='lines',
                                        line={'width': 2, 'color': 'blue'},
                                    ),
                                    Scatter(
                                        name='BEAN/3CRV pool',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveSwapPrice3CRV,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD pool',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveSwapPriceLUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                    Scatter(
                                        name='PEG Line',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveVirtualPrice3CRV,
                                        mode='lines',
                                        line={'width': 0.5, 'color': 'white'},
                                    ),                                     
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '30 days - hourly BEAN Prices',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # DAI/USDC/USDT curve Pool price last 5 days
                                   Scatter(
                                        name='LUSD / DAI-USDC-USDT Curve Pool',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveLUSDPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                   Scatter(
                                        name='DAI / USDC-USDT Curve Pool',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveDAIPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'blue'},
                                    ),
                                    Scatter(
                                        name='USDC / DAI-USDT Curve Pool',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveUSDCPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'yellow'},
                                    ),
                                    Scatter(
                                        name='USDT / DAI-USDC Curve Pool',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveUSDTPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'pink'},
                                    ),
                                    Scatter(
                                        name='PEG Line',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveVirtualPrice3CRV,
                                        mode='lines',
                                        line={'width': 2, 'color': 'white'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.01, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '100 days - Daily LUSD / DAI / USDC / USDT Curve Pool Prices',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # DAI/USDC/USDT curve Pool price last 5 days
                                   Scatter(
                                        name='LUSD / DAI-USDC-USDT Curve Pool',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveLUSDPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                   Scatter(
                                        name='DAI / USDC-USDT Curve Pool',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveDAIPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'blue'},
                                    ),
                                    Scatter(
                                        name='USDC / DAI-USDT Curve Pool',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveUSDCPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'yellow'},
                                    ),
                                    Scatter(
                                        name='USDT / DAI-USDC Curve Pool',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveUSDTPrice,
                                        mode='lines',
                                        line={'width': 2, 'color': 'pink'},
                                    ),
                                    Scatter(
                                        name='PEG Line',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveVirtualPrice3CRV,
                                        mode='lines',
                                        line={'width': 2, 'color': 'white'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.01, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '30 days - hourly LUSD / DAI / USDC / USDT Curve Pool Prices',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
            ]),
        ])
    ]),
     # Rows and Columns help with building a grid layout system
    # First row for some simple dashboard label
    dbc.Row([
        dbc.Col([
            dbc.Label('Curve Subgraph metrics',
                      style={'font-style': 'normal',
                             'font-weight': '600',
                             'font-size': '64px',
                             'line-height': '96px',
                             'color': '#FFFFFF'
                             }, xs=12, sm=12, md=12, lg=6, xl=6)
        ]),
    ]),
# Second row for to contain the Volume/liquidity charts cards
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # Uniswap and Curve USD Liquidity for the last 100 days
                                    Scatter(
                                        name='BEAN/ETH Uniswap',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.uniswapLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'blue'},
                                    ),
                                    Scatter(
                                        name='BEAN/3CRV Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curve3CRVLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveLUSDLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                    Scatter(
                                        name='Total liquidity Curve Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveTotalLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'yellow'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '100 days - Daily BEAN Liquidity',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # Uniswap and Curve USD Liquidity for the last 30 days hourly
                                    Scatter(
                                        name='BEAN/ETH Uniswap',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.uniswapLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'blue'},
                                    ),
                                    Scatter(
                                        name='BEAN/3CRV Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curve3CRVLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveLUSDLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                    Scatter(
                                        name='Total liquidity Curve Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveTotalLPUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'yellow'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '30 days - Hourly BEAN Liquidity',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # Curve % Liquidity Usage for the last 100 days
                                    Scatter(
                                        name='BEAN/3CRV Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curve3CRVLpUsage,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveLUSDLpUsage,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '100 days - Daily Curve % Liquidity',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # Curve % Liquidity Usage for the last 30 days hourly
                                    Scatter(
                                        name='BEAN/3CRV Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curve3CRVLpUsage,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveLUSDLpUsage,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '30 days - Hourly Curve % Liquidity',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # Curve USD Volume for the last 100 days
                                    Scatter(
                                        name='BEAN/3CRV Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curve3CRVVolumeUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD Factory',
                                        x=prices_100daysD.dayDatetime,
                                        y=prices_100daysD.curveLUSDVolumeUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '100 days - Daily Curve Volume',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            Graph(Figure(
                                subgrounds=sg,
                                traces=[
                                    # Curve USD Volume for the last 30 days hourly
                                    Scatter(
                                        name='BEAN/3CRV Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curve3CRVVolumeUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'green'},
                                    ),
                                    Scatter(
                                        name='BEAN/LUSD Factory',
                                        x=prices_30daysH.hourDatetime,
                                        y=prices_30daysH.curveLUSDVolumeUSD,
                                        mode='lines',
                                        line={'width': 2, 'color': 'red'},
                                    ),
                                ],
                                layout={
                                    'showlegend': True,
                                    'xaxis': {'linewidth': 0.1, 'linecolor': '#31333F', 'color': 'white',
                                              'showgrid': False},
                                    'yaxis': {'type': 'linear', 'linewidth': 0.1, 'linecolor': '#31333F',
                                              'color': 'white',
                                              'title': '30 days - Hourly Curve Volume',
                                              'showgrid': False},
                                    'legend.font.color': 'white',
                                    'paper_bgcolor': '#000000',
                                    'plot_bgcolor': 'rgba(0,0,0,0)',
                                }
                            ))
                        ]),
                    ], className="analytics_card_metric", style={'text-align': 'center'}),
                ]),
      ])
    ]),
]),
    html.Footer('Powered by Playgrounds',
                style={'backgrounds-color': '#2e343e',
                       'color': 'white',
                       'font-size': '20px',
                       'padding': '10px'
                       }),
], style={'backgroundColor': '#2a3847'}, fluid=True)

if __name__ == '__main__':
    app.run_server(debug=True,host="localhost", port=8052)
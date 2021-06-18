import logging
import numpy as np
import pandas as pd

import matplotlib.figure
import plotly.graph_objects as go

from .logging import LOGGER_NAME


logger = logging.getLogger(LOGGER_NAME)


def _create_fig_and_ax():
    fig = matplotlib.figure.Figure()
    fig.set_size_inches(18.5, 10.5)
    ax = fig.subplots()
    return fig, ax


def _get_data_extrema(x: pd.Series, y: pd.Series, overflow=19) -> (float, float):
    data_min = min(x)
    if min(y) < data_min:
        data_min = min(y)

    data_max = max(x)
    if max(y) > data_max:
        data_max = max(y)

    data_range = data_max - data_min
    plot_min = data_min - data_range / overflow
    plot_max = data_max + data_range / overflow

    return plot_min, plot_max


def heatmap(df, annotate_values=False, cbar_kw=None, cbarlabel=""):
    if cbar_kw is None:
        cbar_kw = {}

    fig, ax = _create_fig_and_ax()
    n_rows, n_cols = df.shape
    ax.set_aspect(.9 * n_rows / n_cols)

    im = ax.imshow(df)
    ax.set_xticks(np.arange(n_cols))
    ax.set_yticks(np.arange(n_rows))

    # Rotate the tick labels and set their alignment.
    ax.set_xticklabels(df.columns, rotation=45, ha="right", rotation_mode="anchor")
    ax.set_yticklabels(df.index)

    # Create colorbar
    cbar = ax.figure.colorbar(im, ax=ax, **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    # Loop over data dimensions and create text annotations.
    if annotate_values:
        for i in range(n_cols):
            for j in range(n_rows):
                _ = ax.text(j, i, df.iloc[i, j], ha="center", va="center", color="w")

    # ax.set_title("Correlation plot", fontsize=24)
    fig.tight_layout()

    return fig


def heatmap_plotly(df):
    fig = go.Figure(data=go.Heatmap(
        z=df,
        x=df.columns,
        y=df.index,
        hoverongaps=False)
    )
    return fig


def r2_plot(y, y_hat, title=None):
    from sklearn.metrics import r2_score

    fig, ax = _create_fig_and_ax()

    ax.set_aspect(.9)
    ax.scatter(y_hat, y)
    ax.plot([y.min(), y.max()], [y.min(), y.max()], 'k-', color='r')

    r2 = r2_score(y, y_hat)

    r2_annotation = r'$r^2 = {:.2f}\%$'.format(r2 * 100)
    ax.text(0.1, 2.5, r2_annotation, color='r', fontsize=24)
    xlabel = y_hat.name.replace('->', '$\\rightarrow$')
    ylabel = y.name.replace('->', '$\\rightarrow$')
    ax.set_xlabel(xlabel, fontsize=20)
    ax.set_ylabel(ylabel, fontsize=20)
    ax.grid(which='major')

    if title is not None:
        ax.set_title(title, fontsize=24)

    return fig


def r2_plotly(x, y, title=None):
    logger.debug(f'{x = }')
    logger.debug(f'{y = }')
    from sklearn.metrics import r2_score
    r2 = r2_score(y, x)

    plot_min, plot_max = _get_data_extrema(x, y)
    data_range = plot_max - plot_min

    fig = go.Figure()
    # Line
    fig.add_trace(
        go.Scatter(
            x=[y.min(), y.max()],
            y=[y.min(), y.max()],
            showlegend=False,
            mode='lines',
            line_color='#FF8E26',
            line_width=3,
            hoverinfo='skip'
        )
    )

    # Data
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            showlegend=False,
            mode='markers',
            marker_color='#3B97D3', marker_size=10,
            hoverlabel={'bordercolor': '#FFF', 'font_size': 16},
            hovertemplate=' <b>Patient ID: %{text}</b> ' +
                          '<br><br>' +
                          ' Predicted: %{x:.2f} <br>' +
                          ' Measured: %{y:.2f} ' +
                          '<extra></extra>',
            text=x.index
        )
    )

    fig.update_layout(
        width=700,
        height=700,
        xaxis=dict(
            title_text=x.name.replace('->', '\u2192'),
            title_font_size=18, title_font_color='#222222',
            tickfont_size=15, tickfont_color='#222222',
            zerolinecolor='#222222',
            gridcolor='#ccc'
        ),
        yaxis=dict(
            title_text=y.name.replace('->', '\u2192'),
            title_font_size=18, title_font_color='#222222',
            tickfont_size=15, tickfont_color='#222222',
            zerolinecolor='#222222',
            gridcolor='#ccc',
            scaleanchor="x",
            scaleratio=1
        ),
        hoverlabel_align='right'
    )

    fig.update_layout(
        showlegend=False,
        annotations=[
            dict(
                x=min(y) + data_range / 3,
                y=max(y) - data_range / 12,
                text='Variance explained: {:.2f}%'.format(r2 * 100),
                font=dict(family='Arial', size=25, color='#DB307D'),
                showarrow=False
            )
        ]
    )

    fig.update_xaxes(range=[plot_min, plot_max])
    fig.update_yaxes(range=[plot_min, plot_max])

    fig.update_layout(
        paper_bgcolor='#fff',
        plot_bgcolor='#fff'
    )

    if title is not None:
        fig.update_layout(title_text=title)

    return fig

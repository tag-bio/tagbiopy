import numpy as np

import matplotlib.figure
import plotly.graph_objects as go


def _create_fig_and_ax():
    fig = matplotlib.figure.Figure()
    fig.set_size_inches(18.5, 10.5)
    ax = fig.subplots()
    return fig, ax


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
    from sklearn.metrics import r2_score
    r2 = r2_score(x, y)

    fig = go.Figure()
    # Line
    fig.add_trace(
        go.Scatter(
            x=[y.min(), y.max()],
            y=[y.min(), y.max()],
            showlegend=False,
            mode='lines',
            line=dict(color='red')
        )

    )

    # Data
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            showlegend=False,
            mode='markers',
            marker=dict(
                color='blue'
            )
        )
    )

    fig.update_layout(
        width=800,
        height=720,
        xaxis=dict(
            title_text=x.name.replace('->', '\u2192'),
            title_font={'size': 18}
        ),
        yaxis=dict(
            title_text=y.name.replace('->', '\u2192'),
            title_font={'size': 18},
            tickfont={'size': 15},
            scaleanchor="x",
            scaleratio=1
        )
    )

    fig.update_layout(
        showlegend=False,
        annotations=[
            dict(
                x=0.5,
                y=2.8,
                text='Variance explained: {:.2f}%'.format(r2 * 100),
                font=dict(family='Arial, bold', size=25),
                showarrow=False
            )
        ]
    )

    return fig

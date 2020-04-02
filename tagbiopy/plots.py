import matplotlib.pyplot as plt
import numpy as np


def _create_fig_and_ax():
    fig, ax = plt.subplots()
    fig.set_size_inches(18.5, 10.5)
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

    ax.set_xticklabels(df.columns)
    ax.set_yticklabels(df.index)

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # Create colorbar
    cbar = ax.figure.colorbar(im, ax=ax, **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    # Loop over data dimensions and create text annotations.
    if annotate_values:
        for i in range(n_cols):
            for j in range(n_rows):
                text = ax.text(j, i, df.iloc[i, j], ha="center", va="center", color="w")

    #ax.set_title("Correlation plot", fontsize=24)
    fig.tight_layout()

    return fig
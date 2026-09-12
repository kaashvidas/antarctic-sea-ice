"""
Shared plotting helpers.

Keep quick sanity-check plots (used constantly during Phase 1-3 while
debugging data pulls and model outputs) separate from the polished
figures anyone builds for the pitch deck — put deck-quality figure code
in notebooks/ instead, since it'll need one-off tweaking per figure.
"""

import matplotlib.pyplot as plt


def quicklook(data_array, title="", save_path=None):
    """
    Plot a single 2-D xarray DataArray (e.g. one day's sea-ice
    concentration, cropped to the domain) and optionally save it.

    This is intentionally dumb/fast — it's for "does this look like ice
    or noise" checks while building the data pipeline, not for the
    dashboard or the deck.
    """
    fig, ax = plt.subplots(figsize=(6, 6))
    data_array.plot(ax=ax)
    ax.set_title(title)
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved {save_path}")
    return fig, ax


def plot_route_comparison(optimized_route, naive_route, background=None, save_path=None):
    """
    Overlay the optimized route against the naive shortest-distance route
    on the same axes.

    Per the README, this comparison is called out as the single best demo
    moment (Phase 4) — the point isn't just "here's a good route", it's
    "here's what the naive approach would have done instead, and why ours
    avoids the risk." Fill in once Layer 3 (routing/isochrone.py) exists.

    Parameters
    ----------
    optimized_route, naive_route : array-like of (lon, lat) points
    background : optional 2-D DataArray (e.g. ice concentration or the
        route cost grid) to show underneath the two paths for context
    """
    fig, ax = plt.subplots(figsize=(8, 8))
    if background is not None:
        background.plot(ax=ax, add_colorbar=True)

    opt_lon, opt_lat = zip(*optimized_route)
    nav_lon, nav_lat = zip(*naive_route)
    ax.plot(opt_lon, opt_lat, "-", color="tab:green", linewidth=2, label="Optimized route")
    ax.plot(nav_lon, nav_lat, "--", color="tab:red", linewidth=2, label="Naive shortest path")
    ax.legend()
    ax.set_title("Route comparison: optimized vs. naive")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved {save_path}")
    return fig, ax

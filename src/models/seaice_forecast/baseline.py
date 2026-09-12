"""
Module 1, step 1 — sea-ice forecast baselines.

Build these BEFORE the ConvLSTM. They're not throwaway: they're what you
report the trained model's skill *against*, and per the README/Master
Guide, "report model skill honestly against baselines" is explicitly
called out as a credibility signal to the jury, not busywork.

Two standard baselines for short-term sea-ice forecasting:
  - Persistence: tomorrow's concentration = today's concentration.
  - Climatology: tomorrow's concentration = the historical mean for that
    day-of-year at each grid cell.

A model that can't beat persistence at short lead times is not
uncommon in this literature (see the "Should Sea-Ice Modeling Tools..."
paper in the README) — so don't be alarmed if the ConvLSTM's edge over
persistence is modest; report it honestly either way.
"""

import xarray as xr
import pandas as pd


def persistence_forecast(history: xr.DataArray, horizon_days: int) -> xr.DataArray:
    """
    Naive baseline: repeat the last observed day's concentration for
    every day of the forecast horizon.

    Parameters
    ----------
    history : DataArray with a 'time' dimension, most recent day last
    horizon_days : how many days ahead to forecast
    """
    last_day = history.isel(time=-1)
    forecast = xr.concat([last_day] * horizon_days, dim="time")
    # NOTE: `history.time.values[-1] + i` looks right but silently adds `i`
    # NANOSECONDS to a numpy.datetime64, not `i` days (numpy treats a bare
    # int added to datetime64 as the array's native unit) -- producing
    # forecast timestamps that are a few nanoseconds after the last
    # observed day instead of days ahead, which then fail to align at all
    # against real daily-cadence truth data. Use pd.Timedelta explicitly.
    last_time = pd.Timestamp(history.time.values[-1])
    forecast = forecast.assign_coords(
        time=[last_time + pd.Timedelta(days=i) for i in range(1, horizon_days + 1)]
    )
    return forecast


def climatology_forecast(history: xr.DataArray, target_dates, day_of_year_mean=None) -> xr.DataArray:
    """
    Baseline: for each target date, use the historical mean concentration
    for that day-of-year, computed from `history` (ideally several years
    of daily data, not just the current forecast window).

    Precompute day_of_year_mean once (e.g. history.groupby("time.dayofyear").mean())
    and pass it in on repeat calls rather than recomputing it per forecast —
    it only needs to be built once from the full training history.
    """
    import pandas as pd

    if day_of_year_mean is None:
        day_of_year_mean = history.groupby("time.dayofyear").mean()

    forecasts = []
    for date in target_dates:
        # xarray's .time.values yields numpy.datetime64, not a Python
        # datetime — it has no .timetuple(); go through pandas.Timestamp
        # instead, which accepts both.
        doy = pd.Timestamp(date).dayofyear
        # method="nearest" so a short training window (this build's modest
        # real-data pull is a few months, not several years) still returns
        # something for every target date instead of a bare KeyError on a
        # day-of-year that window never observed.
        forecasts.append(day_of_year_mean.sel(dayofyear=doy, method="nearest"))
    return xr.concat(forecasts, dim="time").assign_coords(time=target_dates)


def evaluate(forecast: xr.DataArray, truth: xr.DataArray) -> dict:
    """
    Standard error metrics for comparing any forecast (baseline or
    ConvLSTM) against held-out real observations. Report these for every
    model, at every lead time, not just an aggregate — skill typically
    degrades with lead time and that curve is itself worth showing.
    """
    diff = forecast - truth
    return {
        "mae": float(abs(diff).mean()),
        "rmse": float((diff ** 2).mean() ** 0.5),
        "bias": float(diff.mean()),
    }

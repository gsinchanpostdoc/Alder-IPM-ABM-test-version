"""AlderIPM v2 - stage 1: climate drivers per site and on a European grid.

Baseline: WeatherBench 2 ERA5 climatology 1990-2019 (0.25 deg, 6-hourly by day of year;
          Rasp et al. 2024), reduced to daily-mean 2 m temperature and daily precipitation.
Future:   delta method. Monthly change in each CMIP6 GCM between 1985-2014 and 2041-2070
          (difference for temperature, ratio for precipitation), ensemble mean over the
          ISIMIP3b primary models, added to / multiplied into the ERA5 daily climatology.
Indices (per site and per grid cell, per scenario):
  winter_T   mean daily T, Dec-Feb (deg C)          frost_days  days with daily mean T < 0
  gsl5       days with daily mean T > 5 deg C       gsl10       days with daily mean T > 10 deg C
  gdd10      sum of max(T-10, 0) over the year      T_MJJ       mean T May-Jul (larval window)
  T_AMJ      mean T Apr-Jun (spring)                precip_annual, precip_MJJA (mm)
Output: data/climate_sites.csv, data/climate_grid.nc, results/provenance/climate_provenance.json
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd, xarray as xr, yaml

WB2 = "https://storage.googleapis.com/weatherbench2/datasets/era5-hourly-climatology/1990-2019_6h_1440x721.zarr"
WB2_STATIC = "https://storage.googleapis.com/weatherbench2/datasets/era5/1959-2023_01_10-wb13-6h-1440x721_with_derived_variables.zarr"
PANGEO_CAT = "https://storage.googleapis.com/cmip6/pangeo-cmip6.csv"
_CAT = None
DOY_MONTH = pd.to_datetime(np.arange(365), unit="D", origin="2001-01-01").month.values  # 365-day year


def era5_daily(box):
    """Daily-mean T (deg C) and daily precipitation (mm) by day of year over the box."""
    ds = xr.open_zarr(WB2, consolidated=True, chunks={}).rename({"latitude": "lat", "longitude": "lon"})
    ds = ds.assign_coords(lon=((ds.lon + 180) % 360) - 180).sortby("lon").sortby("lat")
    ds = ds.sel(lat=slice(box["ymin"], box["ymax"]), lon=slice(box["xmin"], box["xmax"]))
    ds = ds.isel(dayofyear=slice(0, 365))
    t = (ds["2m_temperature"].mean("hour") - 273.15).compute().astype("float32")
    p = (ds["total_precipitation_24hr"].sel(hour=0) * 1000.0).compute().astype("float32")
    lsm = xr.open_zarr(WB2_STATIC, consolidated=True)["land_sea_mask"].rename({"latitude": "lat", "longitude": "lon"})
    lsm = lsm.assign_coords(lon=((lsm.lon + 180) % 360) - 180).sortby("lon").sortby("lat")
    lsm = lsm.sel(lat=slice(box["ymin"], box["ymax"]), lon=slice(box["xmin"], box["xmax"])).compute()
    return xr.Dataset({"t2m": t, "pr": p, "lsm": lsm})


def cmip6_monthly(model, experiment, variable, years, member, box):
    cache = Path(f"data/cmip6/{model}_{experiment}_{variable}_{years[0]}-{years[1]}.nc")
    if cache.exists():
        ds = xr.open_dataset(cache).load()
        return ds[variable], json.loads(ds.attrs["meta"])
    clim, meta = _cmip6_monthly(model, experiment, variable, years, member, box)
    cache.parent.mkdir(exist_ok=True)
    out = clim.to_dataset(name=variable); out.attrs["meta"] = json.dumps(meta); out.to_netcdf(cache)
    return clim, meta


def _cmip6_monthly(model, experiment, variable, years, member, box):
    global _CAT
    if _CAT is None:
        _CAT = pd.read_csv(PANGEO_CAT)
    c = _CAT[(_CAT.source_id == model) & (_CAT.experiment_id == experiment) & (_CAT.table_id == "Amon") & (_CAT.variable_id == variable)]
    if c.empty:
        raise SystemExit(f"CMIP6 {model} {experiment} {variable} not in the Pangeo catalogue")
    c = c[c.member_id == member] if (c.member_id == member).any() else c.sort_values("member_id").head(1)
    url = c.iloc[0].zstore.replace("gs://", "https://storage.googleapis.com/")
    ds = xr.open_zarr(url, consolidated=True, use_cftime=True)
    ds = ds.drop_vars([v for v in ("height",) if v in ds.coords])
    if float(ds.lon.max()) > 180:
        ds = ds.assign_coords(lon=((ds.lon + 180) % 360) - 180).sortby("lon")
    ds = ds.sortby("lat").sel(lat=slice(box["ymin"] - 3, box["ymax"] + 3), lon=slice(box["xmin"] - 3, box["xmax"] + 3))
    da = ds[variable].sel(time=ds.time.dt.year.isin(range(years[0], years[1] + 1)))
    clim = da.groupby("time.month").mean("time").compute()
    meta = {"model": model, "experiment": experiment, "variable": variable, "member": str(c.iloc[0].member_id),
            "grid": str(c.iloc[0].grid_label), "zstore": str(c.iloc[0].zstore), "years": list(years)}
    return clim, meta


def indices(t, p):
    """Climate indices from daily series along dim 'dayofyear' (365)."""
    m = xr.DataArray(DOY_MONTH, dims="dayofyear", coords={"dayofyear": t.dayofyear})
    win = t.where(m.isin([12, 1, 2]))
    return xr.Dataset({
        "winter_T": win.mean("dayofyear"),
        "frost_days": (t < 0).sum("dayofyear"),
        "gsl5": (t > 5).sum("dayofyear"),
        "gsl10": (t > 10).sum("dayofyear"),
        "gdd10": (t - 10).clip(min=0).sum("dayofyear"),
        "T_MJJ": t.where(m.isin([5, 6, 7])).mean("dayofyear"),
        "T_AMJ": t.where(m.isin([4, 5, 6])).mean("dayofyear"),
        "T_annual": t.mean("dayofyear"),
        "precip_annual": p.sum("dayofyear"),
        "precip_MJJA": p.where(m.isin([5, 6, 7, 8])).sum("dayofyear"),
    })


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path))
    box, c6 = cfg["europe_box"], cfg["climate"]["cmip6"]
    sites = json.load(open(cfg["sites_file"]))["sites"]
    Path("data").mkdir(exist_ok=True); Path("results/provenance").mkdir(parents=True, exist_ok=True)
    prov = {"baseline": {"dataset": cfg["climate"]["baseline"]["dataset"], "url": WB2, "years": [1990, 2019]},
            "gcms": [], "retrieved_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}

    t0 = time.time(); print("ERA5 daily climatology ...", flush=True)
    cache = Path("data/era5_daily_europe.nc")
    if cache.exists():
        base = xr.open_dataset(cache).load()
    else:
        base = era5_daily(box); base.to_netcdf(cache)
    print(f"  done in {time.time()-t0:.0f} s; grid {base.t2m.shape}", flush=True)

    futures = [s for s in cfg["scenarios"] if s != "baseline"]
    dT = {s: [] for s in futures}; rP = {s: [] for s in futures}; change = []
    for mdl in c6["models"]:
        print(f"CMIP6 {mdl} ...", flush=True)
        th, mt = cmip6_monthly(mdl, "historical", "tas", c6["historical_years"], c6["member"], box)
        ph, mp = cmip6_monthly(mdl, "historical", "pr", c6["historical_years"], c6["member"], box)
        prov["gcms"] += [mt, mp]
        for s in futures:
            tf, mtf = cmip6_monthly(mdl, c6["experiments"][s], "tas", c6["future_years"], c6["member"], box)
            pf, mpf = cmip6_monthly(mdl, c6["experiments"][s], "pr", c6["future_years"], c6["member"], box)
            prov["gcms"] += [mtf, mpf]
            d = (tf - th).interp(lat=base.lat, lon=base.lon, method="linear")
            q = (pf / ph.where(ph > 0)).interp(lat=base.lat, lon=base.lon, method="linear").clip(0.3, 3).fillna(1)
            dT[s].append(d); rP[s].append(q)
            change.append({"model": mdl, "scenario": s, "dT_annual_mean_C": round(float(d.mean()), 2),
                           "dP_annual_pct": round(float(q.mean()) * 100 - 100, 1)})
    prov["regional_change"] = change

    mcoord = xr.DataArray(DOY_MONTH, dims="dayofyear", coords={"dayofyear": base.dayofyear})
    daily = {"baseline": (base.t2m, base.pr)}; spread = {}; grids = {}
    for s in futures:
        dm = xr.concat(dT[s], "gcm"); qm = xr.concat(rP[s], "gcm")
        daily[s] = (base.t2m + dm.mean("gcm").sel(month=mcoord), base.pr * qm.mean("gcm").sel(month=mcoord))
        spread[s] = {"dT_annual_mean": dm.mean("month").mean("gcm"), "dT_annual_sd": dm.mean("month").std("gcm"),
                     "dT_winter_mean": dm.sel(month=[12, 1, 2]).mean("month").mean("gcm"),
                     "dT_winter_sd": dm.sel(month=[12, 1, 2]).mean("month").std("gcm"),
                     "dT_MJJ_mean": dm.sel(month=[5, 6, 7]).mean("month").mean("gcm"),
                     "dT_MJJ_sd": dm.sel(month=[5, 6, 7]).mean("month").std("gcm")}
    for s, (t, p) in daily.items():
        g = indices(t, p); g["lsm"] = base.lsm
        for k, v in spread.get(s, {}).items():
            g[k] = v
        grids[s] = g
    grid = xr.concat([grids[s].assign_coords(scenario=s) for s in daily], "scenario")
    grid.attrs = {"source": "ERA5 (WB2 climatology 1990-2019) + ensemble-mean CMIP6 delta " + ", ".join(c6["models"]),
                  "future_period": str(c6["future_years"]), "historical_period": str(c6["historical_years"])}
    grid.to_netcdf("data/climate_grid.nc")

    rows = []
    for st in sites:
        for s in daily:
            g = grids[s].sel(lat=st["lat"], lon=st["lon"], method="nearest")
            row = {"site": st["id"], "name": st["name"], "country": st["country"], "lat": st["lat"], "lon": st["lon"],
                   "scenario": s, "era5_lat": float(g.lat), "era5_lon": float(g.lon)}
            for v in g.data_vars:
                row[v] = float(g[v])
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv("data/climate_sites.csv", index=False)
    json.dump(prov, open("results/provenance/climate_provenance.json", "w"), indent=1)
    print(pd.DataFrame(change).to_string(index=False))
    print(df[df.scenario == "baseline"][["site", "winter_T", "gsl5", "gsl10", "gdd10", "T_MJJ", "precip_annual"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

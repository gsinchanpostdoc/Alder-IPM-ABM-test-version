"""AlderIPM v2 - stage 3b: apply the climate -> parameter mapping to every alder-domain grid cell.
Output: data/grid_params.json (cell lists per scenario; same mapping and reference anchoring as the sites).
"""
from __future__ import annotations
import json, sys, importlib.util
import numpy as np, xarray as xr, yaml

spec = importlib.util.spec_from_file_location("pm", "pipeline/param_map.py"); pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path)); mp = {k: v for k, v in cfg["mapping"].items() if v.get("enabled", True)}
    reg = json.load(open("data/param_registry.json")); defaults = json.load(open("web/data/default_params.json"))
    dref = json.load(open("data/site_params.json"))["reference_drivers"]
    grid = xr.open_dataset("data/climate_grid.nc"); dom = xr.open_dataset("data/gbif_grid.nc")
    ii, jj = np.where(dom["alder_domain"].values == 1)
    out = {"reference_site": cfg["reference_site"], "mapping": mp, "n_cells": int(len(ii)),
           "lat": grid.lat.values[ii].round(3).tolist(), "lon": grid.lon.values[jj].round(3).tolist(),
           "n_alder": dom["n_alder"].values[ii, jj].astype(int).tolist(), "n_beetle": dom["n_beetle"].values[ii, jj].astype(int).tolist(),
           "scenarios": {}}
    for s in cfg["scenarios"]:
        g = grid.sel(scenario=s)
        drivers = {k: g[k].values[ii, jj] for k in ("gsl10", "winter_T", "T_MJJ", "precip_annual", "gdd10")}
        sc = {"climate": {k: np.round(v, 2).tolist() for k, v in drivers.items()}}
        for k, m in mp.items():
            d = drivers[m["driver"]]
            sc[k] = [round(pm.map_param(k, m, reg, defaults[k], float(x), dref[m["driver"]]), 4) for x in d]
        out["scenarios"][s] = sc
    json.dump(out, open("data/grid_params.json", "w"))
    print(f"{len(ii)} domain cells x {len(cfg['scenarios'])} scenarios written")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

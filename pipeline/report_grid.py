"""AlderIPM v2 - stage 5b: gridded atlas products.
Reads results/grid_results.json; writes results/grid_atlas.nc, results/grid_summary.csv, figures and the
web overlays (web/data/grid/*.png + web/data/grid_cells.json) for web/v2.
"""
from __future__ import annotations
import json, sys, time
import numpy as np, pandas as pd, xarray as xr, yaml
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm

CLS_NAMES = ["coexistence", "parasitoid_free", "canopy_only", "trivial", "numerical_failure"]
CLS_COL = ["#1f8a44", "#cf9418", "#0a7fb0", "#8a8f86", "#000000"]
SCN_LABEL = {"baseline": "Baseline (ERA5 1990–2019)", "ssp245": "SSP2-4.5 (2041–2070)", "ssp585": "SSP5-8.5 (2041–2070)"}


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path)); scen = cfg["scenarios"]
    R = json.load(open("results/grid_results.json")); G = json.load(open("data/grid_params.json"))
    grid = xr.open_dataset("data/climate_grid.nc"); dom = xr.open_dataset("data/gbif_grid.nc")
    lat, lon = np.array(R["lat"]), np.array(R["lon"])
    ii = np.round((lat - grid.lat.values[0]) / 0.25).astype(int); jj = np.round((lon - grid.lon.values[0]) / 0.25).astype(int)
    ds = xr.Dataset(coords={"scenario": scen, "lat": grid.lat, "lon": grid.lon})
    for v in ["cls", "rho", "RP", "D", "K", "A"]:
        arr = np.full((len(scen), len(grid.lat), len(grid.lon)), np.nan)
        for si, s in enumerate(scen):
            arr[si, ii, jj] = np.array(R["scenarios"][s][v], float)
        ds[v] = (("scenario", "lat", "lon"), arr)
    for k in G["mapping"]:
        arr = np.full((len(scen), len(grid.lat), len(grid.lon)), np.nan)
        for si, s in enumerate(scen):
            arr[si, ii, jj] = np.array(G["scenarios"][s][k], float)
        ds["p_" + k] = (("scenario", "lat", "lon"), arr)
    ds["n_alder"] = dom["n_alder"]; ds["alder_domain"] = dom["alder_domain"]
    ds.attrs = {"engine": "AlderIPM-Sim web engine, central run from (1, 0.5, K0, 0)", "classes": json.dumps(dict(enumerate(CLS_NAMES))), "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ds.to_netcdf("results/grid_atlas.nc")

    # area-weighted summary
    w = np.cos(np.radians(lat)); rows = []
    for s in scen:
        c = np.array(R["scenarios"][s]["cls"]); rho = np.array(R["scenarios"][s]["rho"]); rp = np.array(R["scenarios"][s]["RP"]); D = np.array(R["scenarios"][s]["D"])
        pf = c == 1
        row = {"scenario": s, "cells": len(c)}
        for k, name in enumerate(CLS_NAMES[:4]):
            row[f"area_pct_{name}"] = round(100 * w[c == k].sum() / w.sum(), 1)
        row.update({"cells_RP_gt_1": int((rp > 1).sum()), "mean_rho_pf": round(float(rho[pf].mean()), 3), "pct_pf_rho_gt_0.95": round(100 * float((rho[pf] > 0.95).mean()), 1),
                    "mean_RP": round(float(rp.mean()), 3), "mean_D_pf": round(float(D[pf].mean()), 3)})
        rows.append(row)
    summ = pd.DataFrame(rows); summ.to_csv("results/grid_summary.csv", index=False)
    # transitions baseline -> futures
    cb = np.array(R["scenarios"]["baseline"]["cls"]); trans = []
    for s in scen[1:]:
        cs = np.array(R["scenarios"][s]["cls"])
        for a in range(4):
            for b in range(4):
                m = (cb == a) & (cs == b)
                if m.sum():
                    trans.append({"scenario": s, "from": CLS_NAMES[a], "to": CLS_NAMES[b], "cells": int(m.sum()), "area_pct": round(100 * w[m].sum() / w.sum(), 1)})
    pd.DataFrame(trans).to_csv("results/grid_transitions.csv", index=False)

    # --- figures
    cmap = ListedColormap(CLS_COL[:4]); norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4)
    lsm = grid.sel(scenario="baseline")["lsm"].values
    def bg(ax):
        ax.pcolormesh(grid.lon, grid.lat, np.where(lsm >= 0.5, 1, np.nan), cmap="Greys", vmin=0, vmax=5, shading="auto")
        ax.set_aspect(1.6); ax.set_xticks([]); ax.set_yticks([])
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6))
    for ax, s in zip(axes, scen):
        bg(ax); ax.pcolormesh(grid.lon, grid.lat, ds["cls"].sel(scenario=s).values, cmap=cmap, norm=norm, shading="auto"); ax.set_title(SCN_LABEL[s])
    from matplotlib.patches import Patch
    axes[0].legend(handles=[Patch(color=c, label=n.replace("_", " ")) for n, c in zip(CLS_NAMES[:4], CLS_COL)], loc="upper left", fontsize=8, title="attractor")
    fig.suptitle(f"Alder presence domain ({len(lat)} ERA5 cells with ≥{cfg['gbif'].get('domain_min_records', 3)} GBIF A. glutinosa records): regime of the unmanaged system")
    fig.savefig("results/figures/grid_attractor.png", dpi=140, bbox_inches="tight"); plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9.5))
    for j, s in enumerate(scen):
        bg(axes[0, j]); im = axes[0, j].pcolormesh(grid.lon, grid.lat, ds["rho"].sel(scenario=s).values, cmap="magma_r", vmin=0.3, vmax=1.0, shading="auto"); axes[0, j].set_title(f"ρ* — {SCN_LABEL[s]}")
        bg(axes[1, j]); im2 = axes[1, j].pcolormesh(grid.lon, grid.lat, ds["RP"].sel(scenario=s).values, cmap="viridis", vmin=0, vmax=0.5, shading="auto"); axes[1, j].set_title(f"R_P — {SCN_LABEL[s]}")
    fig.colorbar(im, ax=axes[0, :], shrink=0.8, label="spectral radius ρ* at the attractor (1 = loss of stability)"); fig.colorbar(im2, ax=axes[1, :], shrink=0.8, label="parasitoid invasion threshold R_P (1 = coexistence possible)")
    fig.savefig("results/figures/grid_rho_RP.png", dpi=140, bbox_inches="tight"); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, s in zip(axes, scen[1:]):
        bg(ax); d = ds["rho"].sel(scenario=s).values - ds["rho"].sel(scenario="baseline").values
        im = ax.pcolormesh(grid.lon, grid.lat, d, cmap="RdBu_r", vmin=-0.15, vmax=0.15, shading="auto"); ax.set_title(f"Δρ* — {SCN_LABEL[s]} minus baseline")
    fig.colorbar(im, ax=axes, shrink=0.8, label="Δρ* (positive = lower resilience)")
    fig.savefig("results/figures/grid_delta_rho.png", dpi=140, bbox_inches="tight"); plt.close(fig)

    # --- web overlays (transparent PNG per scenario, north-up) + compact cell table
    from pathlib import Path
    Path("web/data/grid").mkdir(parents=True, exist_ok=True)
    from PIL import Image
    rgba_cls = np.array([[31, 138, 68], [207, 148, 24], [10, 127, 176], [138, 143, 134], [0, 0, 0]])
    bounds = [float(grid.lat.min()) - 0.125, float(grid.lon.min()) - 0.125, float(grid.lat.max()) + 0.125, float(grid.lon.max()) + 0.125]
    for s in scen:
        c = ds["cls"].sel(scenario=s).values
        img = np.zeros((len(grid.lat), len(grid.lon), 4), np.uint8)
        ok = ~np.isnan(c)
        img[ok, :3] = rgba_cls[c[ok].astype(int)]; img[ok, 3] = 190
        Image.fromarray(img[::-1]).save(f"web/data/grid/attractor_{s}.png")
        r = ds["rho"].sel(scenario=s).values
        img = np.zeros((len(grid.lat), len(grid.lon), 4), np.uint8)
        v = np.clip((r - 0.3) / 0.7, 0, 1); cm = plt.get_cmap("magma_r")(v)
        img[ok, :3] = (cm[ok, :3] * 255).astype(np.uint8); img[ok, 3] = 190
        Image.fromarray(img[::-1]).save(f"web/data/grid/rho_{s}.png")
    cells = {"bounds": bounds, "res": 0.25, "lat": [round(float(x), 3) for x in lat], "lon": [round(float(x), 3) for x in lon], "classes": CLS_NAMES,
             "n_alder": R["n_alder"], "n_beetle": R["n_beetle"], "scenarios": {s: {k: R["scenarios"][s][k] for k in ("cls", "rho", "RP", "D", "K")} | {"params": {k: G["scenarios"][s][k] for k in G["mapping"]}, "climate": {k: G["scenarios"][s]["climate"][k] for k in ("winter_T", "gsl10", "T_MJJ")}} for s in scen},
             "summary": rows, "domain_rule": dom.attrs.get("domain_rule", "")}
    json.dump(cells, open("web/data/grid_cells.json", "w"), separators=(",", ":"))
    print(summ.to_string(index=False)); print(pd.DataFrame(trans).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

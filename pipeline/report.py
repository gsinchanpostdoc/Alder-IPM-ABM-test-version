"""AlderIPM v2 - stage 5: tables, maps and the web data file.
Reads results/site_results.json (+ data/*.csv) and writes
  results/report.md, results/summary.csv, results/figures/*.png, web/data/alder_sites_v2.json
"""
from __future__ import annotations
import json, sys, time
import numpy as np, pandas as pd, yaml
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import xarray as xr

CLS_COLOR = {"coexistence": "#1f8a44", "parasitoid_free": "#cf9418", "canopy_only": "#0a7fb0", "trivial": "#8a8f86", "numerical_failure": "#000"}
SCN_LABEL = {"baseline": "Baseline (ERA5 1990–2019)", "ssp245": "SSP2-4.5 (2041–2070)", "ssp585": "SSP5-8.5 (2041–2070)"}


def land_background(ax, grid):
    lsm = grid["lsm"].values
    ax.pcolormesh(grid.lon, grid.lat, np.where(lsm >= 0.5, 1, np.nan), cmap="Greys", vmin=0, vmax=4, shading="auto", zorder=0)
    ax.set_xlim(float(grid.lon.min()), float(grid.lon.max())); ax.set_ylim(float(grid.lat.min()), float(grid.lat.max()))
    ax.set_aspect(1.6); ax.set_xticks([]); ax.set_yticks([])


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path))
    res = json.load(open("results/site_results.json"))
    df = pd.DataFrame([{k: v for k, v in r.items() if not isinstance(v, (dict, list))} | {f"p_{k}": v for k, v in r["params"].items()}
                       | {f"c_{k}": v for k, v in r["climate"].items()} | {"bird_ratio": r["drivers"]["bird_ratio"]}
                       | {k: r["gbif"][k] for k in ["n_alder", "n_beetle", "n_parasitoid"]}
                       | ({f"J_{x['name'][-1]}": x["J"] for x in r.get("control", [])} if r.get("control") else {})
                       | ({f"feas_{x['name'][-1]}": x["feasible"] for x in r.get("control", [])} if r.get("control") else {})
                       for r in res["sites"]])
    df.to_csv("results/summary.csv", index=False)
    grid = xr.open_dataset("data/climate_grid.nc")
    prov_c = json.load(open("results/provenance/climate_provenance.json")); prov_g = json.load(open("results/provenance/gbif_provenance.json"))
    scen = cfg["scenarios"]

    # --- Figure 1: P_shift maps per scenario
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
    for ax, s in zip(axes, scen):
        land_background(ax, grid.sel(scenario="baseline"))
        d = df[df.scenario == s]
        sc = ax.scatter(d.lon, d.lat, c=d.P_shift, cmap="RdYlGn_r", vmin=0, vmax=1, s=55, edgecolor="k", linewidth=0.5, zorder=3)
        ax.set_title(SCN_LABEL[s], fontsize=11)
    cb = fig.colorbar(sc, ax=axes, shrink=0.8, pad=0.02); cb.set_label("Climate-conditional regime-shift probability P_shift")
    fig.suptitle("AlderIPM v2 — probability that the unmanaged system leaves the coexistence regime", y=0.98)
    fig.savefig("results/figures/map_P_shift.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    # --- Figure 2: attractor class maps
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
    for ax, s in zip(axes, scen):
        land_background(ax, grid.sel(scenario="baseline"))
        d = df[df.scenario == s]
        for cls, col in CLS_COLOR.items():
            dd = d[d.attractor == cls]
            if len(dd):
                ax.scatter(dd.lon, dd.lat, c=col, s=55, edgecolor="k", linewidth=0.5, label=cls.replace("_", " "), zorder=3)
        ax.set_title(SCN_LABEL[s], fontsize=11)
    axes[0].legend(loc="upper left", fontsize=8, title="attractor (central run)")
    fig.suptitle("Attractor reached from the coexistence reference state (A, F, K, D) = (1, 0.5, K0, 0)", y=0.98)
    fig.savefig("results/figures/map_attractor.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    # --- Figure 3: drivers and parameters vs scenario
    base = df[df.scenario == "baseline"].set_index("site")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, (col, lab) in zip(axes.ravel(), [("c_winter_T", "winter mean T (°C)"), ("c_gsl10", "days > 10 °C"), ("c_T_MJJ", "May–Jul mean T (°C)"),
                                             ("p_sigma_A", "σ_A (beetle overwinter survival)"), ("p_T", "T (season length, d)"), ("p_delta", "δ (parasitoid emergence rate)")]):
        for s, c in zip(scen, ["#1f8a44", "#cf9418", "#b01722"]):
            d = df[df.scenario == s].set_index("site").loc[base.index]
            ax.scatter(base.lat, d[col], s=18, c=c, label=SCN_LABEL[s])
        ax.set_xlabel("site latitude (°N)"); ax.set_ylabel(lab)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Climate drivers and mapped phenological parameters across the 41 alder sites")
    fig.tight_layout(); fig.savefig("results/figures/drivers_and_parameters.png", dpi=150); plt.close(fig)

    # --- Figure 4: rho* and R_P shifts
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for s, c in zip(scen[1:], ["#cf9418", "#b01722"]):
        d = df[df.scenario == s].set_index("site").loc[base.index]
        axes[0].scatter(base.rho_star, d.rho_star, s=20, c=c, label=SCN_LABEL[s])
        axes[1].scatter(base.R_P, d.R_P, s=20, c=c, label=SCN_LABEL[s])
    for ax, lab in zip(axes, ["ρ* (spectral radius of annual map at attractor)", "R_P (parasitoid invasion threshold)"]):
        lim = [min(ax.get_xlim()[0], ax.get_ylim()[0]), max(ax.get_xlim()[1], ax.get_ylim()[1])]
        ax.plot(lim, lim, "k--", lw=0.8); ax.set_xlabel(f"baseline {lab}"); ax.set_ylabel(f"future {lab}")
        ax.axhline(1, color="grey", lw=0.6); ax.axvline(1, color="grey", lw=0.6)
    axes[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig("results/figures/rho_RP_shift.png", dpi=150); plt.close(fig)

    # --- Figure 5: GBIF beetle phenology (pooled monthly histogram, all sites, 100 km)
    gb = pd.read_csv("data/gbif_sites.csv")
    hist = np.sum([json.loads(h) for h in gb.beetle_month_hist_100km], axis=0)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(np.arange(1, 13), hist, color="#2f6b4f"); ax.set_xticks(np.arange(1, 13)); ax.set_xticklabels(list("JFMAMJJASOND"))
    ax.set_ylabel("A. alni GBIF records (pooled, 100 km of each site)"); ax.set_title("Adult activity: spring (overwintered) and late-summer (new generation) peaks bracket the larval window")
    fig.tight_layout(); fig.savefig("results/figures/gbif_beetle_phenology.png", dpi=150); plt.close(fig)

    # --- Figure 6: gridded parameter atlas (mapping applied to every 0.25 deg land cell; no model run)
    import importlib.util
    spec = importlib.util.spec_from_file_location("pm", "pipeline/param_map.py"); pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
    reg = json.load(open("data/param_registry.json")); defaults = json.load(open("web/data/default_params.json"))
    sp = json.load(open("data/site_params.json")); dref = sp["reference_drivers"]
    drv = {"gsl10": "gsl10", "winter_T": "winter_T", "T_MJJ": "T_MJJ"}
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    for j, k in enumerate(["T", "sigma_A", "sigma_F", "delta"]):
        m = cfg["mapping"][k]; vf = np.vectorize(lambda d: pm.map_param(k, m, reg, defaults[k], d, dref[m["driver"]]))
        gb_ = grid.sel(scenario="baseline"); gf_ = grid.sel(scenario="ssp585")
        land = gb_["lsm"].values >= 0.5
        vb = np.where(land, vf(gb_[drv[m["driver"]]].values), np.nan); vfut = np.where(land, vf(gf_[drv[m["driver"]]].values), np.nan)
        im = axes[0, j].pcolormesh(grid.lon, grid.lat, vb, shading="auto", cmap="viridis"); axes[0, j].set_title(f"{k} — baseline"); fig.colorbar(im, ax=axes[0, j], shrink=0.8)
        dm = np.nanmax(np.abs(vfut - vb)); im = axes[1, j].pcolormesh(grid.lon, grid.lat, vfut - vb, shading="auto", cmap="RdBu_r", vmin=-dm, vmax=dm); axes[1, j].set_title(f"Δ{k} — SSP5-8.5 minus baseline"); fig.colorbar(im, ax=axes[1, j], shrink=0.8)
        for ax in axes[:, j]:
            ax.set_aspect(1.6); ax.set_xticks([]); ax.set_yticks([]); ax.scatter(base.lon, base.lat, s=6, c="k", zorder=3)
    fig.suptitle("Gridded parameter atlas: the climate→parameter mapping applied to every ERA5 land cell (dots = the 41 sites)")
    fig.tight_layout(); fig.savefig("results/figures/parameter_atlas_grid.png", dpi=130); plt.close(fig)

    # --- Markdown report
    L = ["# AlderIPM v2 — climate-driven, site-specific stability atlas", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Engine: unchanged AlderIPM-Sim web model (model.js/control.js). "
         f"Reference site for the calibrated parameter set: **{res['meta']['reference_site']}**. Initial condition {res['meta']['initial_condition']}; "
         f"{res['meta']['years']} annual-map iterations (central), {res['meta']['sample_years']} for the {res['meta']['lhs_samples']} LHS samples per site × scenario.", "",
         "## Data sources", "",
         f"- Climate baseline: {prov_c['baseline']['dataset']} ({prov_c['baseline']['url']}).",
         f"- Climate change: ensemble-mean delta of {', '.join(cfg['climate']['cmip6']['models'])} ({cfg['climate']['cmip6']['future_years']} vs {cfg['climate']['cmip6']['historical_years']}), Pangeo CMIP6 (Google Cloud). Regional mean changes:", ""]
    L += ["| GCM | scenario | ΔT annual (°C) | ΔP annual (%) |", "|---|---|---|---|"]
    L += [f"| {c['model']} | {c['scenario']} | {c['dT_annual_mean_C']:.2f} | {c['dP_annual_pct']:+.1f} |" for c in prov_c["regional_change"]]
    L += ["", f"- Occurrences: GBIF occurrence search API, {prov_g['years'][0]}–{prov_g['years'][1]}, retrieved {prov_g['retrieved_utc']} UTC; keys: " +
          ", ".join(f"{k} = {v}" for k, v in prov_g["keys"].items() if k in ("Alnus glutinosa", "Agelastica alni", "Meigenia mutabilis")) +
          " (GBIF Backbone). No download DOI — register a derived dataset before publication.", "",
          "## Climate → parameter mapping", "", "| parameter | driver | form | assumption |", "|---|---|---|---|"]
    for k, m in cfg["mapping"].items():
        L.append(f"| {k} | {m['driver']} | {m['mode']} | " + ", ".join(f"{a}={b}" for a, b in m.items() if a not in ("driver", "mode", "source")) + " |")
    L += ["", "All other parameters stay at the calibrated AlderIPM-Sim values. Mapped values are clipped to the PARAM_REGISTRY ranges.", "",
          "## Site results (central run)", ""]
    cols = ["site", "country", "scenario", "attractor", "rho_star", "R_P", "D_star", "K_star", "P_shift", "P_parasitoid_free", "cheapest_feasible", "p_T", "p_sigma_A", "p_sigma_F", "p_delta", "p_B_index", "c_winter_T", "c_gsl10"]
    cols = [c for c in cols if c in df.columns]
    L += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.sort_values(["site", "scenario"]).iterrows():
        L.append("| " + " | ".join(f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c]) for c in cols) + " |")
    L += ["", "## Summary by scenario", "", "| scenario | n sites | coexistence | parasitoid-free | canopy-only | trivial | mean P_shift | mean ρ* | mean R_P | sites with R_P > 1 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for s in scen:
        d = df[df.scenario == s]; vc = d.attractor.value_counts()
        L.append(f"| {s} | {len(d)} | {vc.get('coexistence', 0)} | {vc.get('parasitoid_free', 0)} | {vc.get('canopy_only', 0)} | {vc.get('trivial', 0)} | "
                 f"{d.P_shift.mean():.3f} | {d.rho_star.mean():.3f} | {d.R_P.mean():.3f} | {(d.R_P > 1).sum()} |")
    if "J_C" in df.columns:
        L += ["", "## Management (grid-searched strategies A, B, C; app's ControlComparator, 50-year horizon)", "", "| scenario | A feasible | B feasible | C feasible | mean J_A | mean J_B | mean J_C | cheapest feasible = C |", "|---|---|---|---|---|---|---|---|"]
        for s in scen:
            d = df[df.scenario == s]
            L.append(f"| {s} | {int(d.feas_A.sum())}/{len(d)} | {int(d.feas_B.sum())}/{len(d)} | {int(d.feas_C.sum())}/{len(d)} | {d.J_A.mean():.1f} | {d.J_B.mean():.1f} | {d.J_C.mean():.1f} | {(d.cheapest_feasible == 'Strategy C').sum()}/{len(d)} |")
    L += ["", "## Figures", "", "![P_shift](figures/map_P_shift.png)", "![attractor](figures/map_attractor.png)", "![drivers](figures/drivers_and_parameters.png)",
          "![rho](figures/rho_RP_shift.png)", "![phenology](figures/gbif_beetle_phenology.png)", "![atlas](figures/parameter_atlas_grid.png)", "",
          "## Interpretation", "", "_Write by hand after inspecting the tables; the pipeline does not draft interpretation._"]
    open("results/report.md", "w").write("\n".join(L))

    # --- web data
    sites_v1 = json.load(open(cfg["sites_file"]))
    out = {"schema_version": "2.0", "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "description": "AlderIPM v2 site layer: ERA5/CMIP6 climate drivers, climate-mapped phenological parameters and precomputed stability metrics per site and scenario. Produced by pipeline/ (see README).",
           "reference_site": res["meta"]["reference_site"], "scenarios": {s: SCN_LABEL[s] for s in scen}, "mapping": cfg["mapping"],
           "provenance": {"climate": prov_c["baseline"], "cmip6_models": cfg["climate"]["cmip6"]["models"], "gbif": {k: prov_g[k] for k in ("api", "taxonomy", "years", "retrieved_utc")}},
           "sites": []}
    byid = {}
    for r in res["sites"]:
        e = byid.setdefault(r["site"], {"id": r["site"], "name": r["name"], "country": r["country"], "lat": r["lat"], "lon": r["lon"],
                                        "region": next((x.get("region", "") for x in sites_v1["sites"] if x["id"] == r["site"]), ""), "gbif": r["gbif"], "scenarios": {}})
        e["scenarios"][r["scenario"]] = {"climate": r["climate"], "drivers": r["drivers"], "params": r["params"],
                                         "metrics": {k: r[k] for k in ("attractor", "converged", "A_star", "F_star", "K_star", "D_star", "rho_star", "R_P", "R1", "R2", "P_shift", "P_parasitoid_free", "P_canopy_only", "P_trivial", "rho_star_mean")},
                                         "control": r.get("control"), "cheapest_feasible": r.get("cheapest_feasible")}
    out["sites"] = list(byid.values())
    json.dump(out, open("web/data/alder_sites_v2.json", "w"), indent=0)
    print("\n".join(L[L.index("## Summary by scenario"):L.index("## Figures")]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

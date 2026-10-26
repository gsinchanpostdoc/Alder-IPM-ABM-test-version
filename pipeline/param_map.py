"""AlderIPM v2 - stage 3: climate (and GBIF) drivers -> phenological parameters, with uncertainty.

Every climate-driven parameter x is a monotone function of one driver d, anchored so that
x(d_ref) equals the calibrated AlderIPM-Sim value at the reference site's ERA5 baseline climate,
and clipped to the PARAM_REGISTRY range used by the app:
  proportional : x = x_ref * (d / d_ref) ** elasticity              (T <- gsl10; B_index <- bird_ratio)
  logit_linear : logit((x-lo)/(hi-lo)) = logit((x_ref-lo)/(hi-lo)) + k (d - d_ref)   (sigma_A, sigma_F <- winter_T)
  degree_day   : x = x_ref * (d - T0) / (d_ref - T0)                (delta <- T_MJJ; linear development rate above T0)
Uncertainty: Latin hypercube samples over (i) the mapping slopes (multiplier ~ N(1, slope_cv), truncated
to [0.2, 2]) and (ii) for future scenarios the GCM spread of the temperature change at the site
(winter and May-July changes ~ N(mean, sd across GCMs)); the bird ratio gets its binomial error.
Only these parameters vary; all others stay at their calibrated values, so differences between
scenarios are attributable to climate ("climate-conditional" regime-shift probability).
Output: data/site_params.json
"""
from __future__ import annotations
import json, sys
import numpy as np, pandas as pd, yaml
from scipy.stats import qmc, norm


def logit(p): return np.log(p / (1 - p))
def logistic(z): return 1 / (1 + np.exp(-z))


def map_param(name, spec, reg, x_ref, d, d_ref, slope_mult=1.0):
    lo, hi = reg[name]["min"], reg[name]["max"]
    mode = spec["mode"]
    if mode == "proportional":
        x = x_ref * (d / d_ref) ** (spec["elasticity"] * slope_mult)
    elif mode == "logit_linear":
        z = logit((x_ref - lo) / (hi - lo)) + spec["slope_per_C"] * slope_mult * (d - d_ref)
        x = lo + (hi - lo) * logistic(z)
    elif mode == "degree_day":
        T0 = spec["T0_C"]
        x = x_ref * (max(d - T0, 0.1) / (d_ref - T0)) ** slope_mult
    else:
        raise ValueError(mode)
    return float(np.clip(x, lo, hi))


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path)); mp = cfg["mapping"]
    reg = json.load(open("data/param_registry.json"))
    defaults = json.load(open("web/data/default_params.json"))
    clim = pd.read_csv("data/climate_sites.csv")
    gb = pd.read_csv("data/gbif_sites.csv").set_index("site")
    ref = cfg["reference_site"]
    refrow = clim[(clim.site == ref) & (clim.scenario == "baseline")].iloc[0]
    d_ref = {"gsl10": refrow.gsl10, "winter_T": refrow.winter_T, "T_MJJ": refrow.T_MJJ, "bird_ratio": gb.loc[ref, "bird_ratio"]}
    names = [k for k, v in mp.items() if v.get("enabled", True)]; n = cfg["stability"]["lhs_samples"]
    sampler = qmc.LatinHypercube(d=len(names) + 3, seed=cfg["seed"])  # slopes + 3 driver perturbations
    out = {"reference_site": ref, "reference_drivers": {k: float(v) for k, v in d_ref.items()},
           "mapping": {k: mp[k] for k in names}, "calibrated": {k: defaults[k] for k in names}, "sites": []}
    for _, r in clim.iterrows():
        g = gb.loc[r.site]
        drivers = {"gsl10": r.gsl10, "winter_T": r.winter_T, "T_MJJ": r.T_MJJ, "bird_ratio": g.bird_ratio}
        central = {k: map_param(k, mp[k], reg, defaults[k], drivers[mp[k]["driver"]], d_ref[mp[k]["driver"]]) for k in names}
        u = sampler.random(n)
        samples = []
        base = clim[(clim.site == r.site) & (clim.scenario == "baseline")].iloc[0]
        for i in range(n):
            mult = {k: float(np.clip(norm.ppf(u[i, j], 1.0, mp[k]["slope_cv"]), 0.2, 2.0)) for j, k in enumerate(names)}
            dd = dict(drivers)
            if r.scenario != "baseline":
                zw, zs, za = norm.ppf(u[i, len(names)]), norm.ppf(u[i, len(names) + 1]), norm.ppf(u[i, len(names) + 2])
                dd["winter_T"] = r.winter_T + zw * r.dT_winter_sd
                dd["T_MJJ"] = r.T_MJJ + zs * r.dT_MJJ_sd
                scale = (r.dT_annual_mean + za * r.dT_annual_sd) / r.dT_annual_mean if r.dT_annual_mean else 1.0
                dd["gsl10"] = base.gsl10 + (r.gsl10 - base.gsl10) * scale
            else:
                zb = norm.ppf(u[i, len(names)])
            if g.n_aves and g.n_aves > 0:
                se = np.sqrt(g.bird_ratio * (1 - g.bird_ratio) / g.n_aves)
                dd["bird_ratio"] = float(np.clip(g.bird_ratio + norm.ppf(u[i, len(names) + 2]) * se, 1e-3, 0.999))
            samples.append([map_param(k, mp[k], reg, defaults[k], dd[mp[k]["driver"]], d_ref[mp[k]["driver"]], mult[k]) for k in names])
        out["sites"].append({"site": r.site, "name": r["name"], "country": r.country, "lat": r.lat, "lon": r.lon, "scenario": r.scenario,
                             "drivers": {k: (None if pd.isna(v) else float(v)) for k, v in drivers.items()},
                             "climate": {k: float(r[k]) for k in ["winter_T", "frost_days", "gsl5", "gsl10", "gdd10", "T_MJJ", "T_annual", "precip_annual", "precip_MJJA"]},
                             "gbif": {k: (None if pd.isna(g[k]) else float(g[k])) for k in ["n_alder", "n_beetle", "n_parasitoid", "n_passerines", "n_aves", "beetle_peak_interval_months"]},
                             "params": central, "param_names": names, "samples": samples})
    json.dump(out, open("data/site_params.json", "w"))
    df = pd.DataFrame([{"site": s["site"], "scenario": s["scenario"], **s["params"]} for s in out["sites"]])
    print(df.pivot(index="site", columns="scenario", values=names).round(3).to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

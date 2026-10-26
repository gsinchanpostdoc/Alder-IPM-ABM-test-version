"""AlderIPM v2 - stage 2: GBIF occurrence context per site (occurrence search API, no account).

Per site (within gbif.radius_km): record counts of Alnus glutinosa, Agelastica alni, Meigenia
mutabilis, the configured generalist passerines and all birds (class Aves), 2000-2026, with
coordinates. The effort-normalised bird index is
    bird_ratio = passerine records / Aves records,
a reporting-rate proxy for generalist insectivore pressure (used only to scale B_index).
Per site (within gbif.phenology_radius_km): monthly histogram of A. alni records. A. alni
adults show two activity peaks (overwintered adults in spring, new generation in late summer);
the interval between the two peaks brackets the egg-larva-pupa period and is reported as an
empirical check on the climate-derived season length T.
Taxon keys are GBIF Backbone keys from /species/match (rgbif >= 3.9.0 returns COL XR keys;
record which is used before joining to other data).
Output: data/gbif_sites.csv, results/provenance/gbif_provenance.json
"""
from __future__ import annotations
import json, sys, time
import numpy as np, pandas as pd, requests, yaml
from pathlib import Path

BASE = "https://api.gbif.org/v1"
S = requests.Session()


def match(name):
    r = S.get(f"{BASE}/species/match", params={"name": name}, timeout=60).json()
    return r.get("usageKey"), r.get("matchType")


def count(params):
    for attempt in range(4):
        try:
            r = S.get(f"{BASE}/occurrence/search", params={**params, "limit": 0}, timeout=90)
            return r.json()["count"]
        except Exception:
            time.sleep(2 * (attempt + 1))
    return np.nan


def facet_month(params):
    r = S.get(f"{BASE}/occurrence/search", params={**params, "limit": 0, "facet": "month", "facetLimit": 12}, timeout=90).json()
    f = {int(c["name"]): c["count"] for c in r["facets"][0]["counts"]} if r.get("facets") else {}
    return [f.get(m, 0) for m in range(1, 13)]


def bbox(lat, lon, km):
    dlat = km / 111.0
    dlon = km / (111.0 * np.cos(np.radians(lat)))
    return {"decimalLatitude": f"{lat-dlat},{lat+dlat}", "decimalLongitude": f"{lon-dlon},{lon+dlon}"}


def peak_interval(hist):
    """Months between the spring and late-summer activity peaks of A. alni adults (nan if unclear)."""
    h = np.array(hist, float)
    if h.sum() < 50:
        return np.nan, np.nan
    spring = 3 + int(np.argmax(h[3:7]))          # Apr-Jul window (index 3..6)
    late = 6 + int(np.argmax(h[6:10]))           # Jul-Oct window
    trough = h[spring:late + 1].min() if late > spring else np.nan
    if late <= spring or trough >= 0.8 * min(h[spring], h[late]):
        return np.nan, np.nan
    return float(late - spring), float(h[spring] + h[late])


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path)); g = cfg["gbif"]
    sites = json.load(open(cfg["sites_file"]))["sites"]
    years = f"{g['years'][0]},{g['years'][1]}"
    keys = {n: match(n) for n in ["Alnus glutinosa", "Agelastica alni", "Meigenia mutabilis"] + g["generalist_passerines"]}
    pass_keys = [keys[n][0] for n in g["generalist_passerines"]]
    common = {"hasCoordinate": "true", "year": years, "occurrenceStatus": "PRESENT"}
    part = Path("data/gbif_sites_partial.csv")
    done = pd.read_csv(part) if part.exists() else pd.DataFrame()
    rows = done.to_dict("records") if len(done) else []
    for i, st in enumerate(sites):
        if len(done) and st["id"] in set(done.site):
            continue
        b = bbox(st["lat"], st["lon"], g["radius_km"]); bp = bbox(st["lat"], st["lon"], g["phenology_radius_km"])
        row = {"site": st["id"],
               "n_alder": count({**common, **b, "taxonKey": keys["Alnus glutinosa"][0]}),
               "n_beetle": count({**common, **b, "taxonKey": keys["Agelastica alni"][0]}),
               "n_parasitoid": count({**common, **b, "taxonKey": keys["Meigenia mutabilis"][0]}),
               "n_passerines": count({**common, **b, "taxonKey": pass_keys}),
               "n_aves": count({**common, **b, "classKey": 212})}
        row["bird_ratio"] = row["n_passerines"] / row["n_aves"] if row["n_aves"] else np.nan
        hist = facet_month({**common, **bp, "taxonKey": keys["Agelastica alni"][0]})
        row["beetle_month_hist_100km"] = json.dumps(hist)
        row["beetle_peak_interval_months"], row["beetle_peak_n"] = peak_interval(hist)
        rows.append(row)
        pd.DataFrame(rows).to_csv(part, index=False)
        print(f"{i+1:2d}/{len(sites)} {st['id']:<20} alder {row['n_alder']:>6} beetle {row['n_beetle']:>5} "
              f"parasitoid {row['n_parasitoid']:>3} bird_ratio {row['bird_ratio']:.3f} peakint {row['beetle_peak_interval_months']}", flush=True)
    df = pd.DataFrame(rows); df.to_csv("data/gbif_sites.csv", index=False)
    json.dump({"api": "GBIF occurrence search API (no download DOI; register a derived dataset before publication)",
               "taxonomy": "GBIF Backbone keys via /species/match", "keys": {k: v[0] for k, v in keys.items()},
               "match_types": {k: v[1] for k, v in keys.items()}, "years": g["years"], "radius_km": g["radius_km"],
               "phenology_radius_km": g["phenology_radius_km"], "retrieved_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())},
              open("results/provenance/gbif_provenance.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

"""AlderIPM v2 - stage 2b: gridded GBIF occurrence density for the alder presence domain.

Uses the GBIF maps API (vector tiles, zoom 2, EPSG:4326, ~0.088 deg pixels; records 2000-2026 with
coordinates) and aggregates record totals to the 0.25 deg ERA5 grid of data/climate_grid.nc.
The alder presence domain is every cell with >= domain_min_records Alnus glutinosa records.
Output: data/gbif_grid.nc (n_alder, n_beetle per cell), results/provenance/gbif_grid_provenance.json
"""
from __future__ import annotations
import json, sys, time
import numpy as np, requests, xarray as xr, yaml
import mapbox_vector_tile as mvt

TILE_DEG, Z, EXTENT = 45.0, 2, 512


def tile_counts(taxon_key, years, box):
    """Return (lon, lat, total) arrays for all occupied pixels inside the box."""
    lons, lats, tots = [], [], []
    x0, x1 = int((box["xmin"] + 180) // TILE_DEG), int((box["xmax"] + 180) // TILE_DEG)
    y0, y1 = int((90 - box["ymax"]) // TILE_DEG), int((90 - box["ymin"]) // TILE_DEG)
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            url = f"https://api.gbif.org/v2/map/occurrence/density/{Z}/{tx}/{ty}.mvt?srs=EPSG:4326&taxonKey={taxon_key}&year={years[0]},{years[1]}"
            r = requests.get(url, timeout=120); r.raise_for_status()
            if not r.content:
                continue
            layer = mvt.decode(r.content, default_options={"y_coord_down": True}).get("occurrence")
            if not layer:
                continue
            lon0, lat0 = -180 + tx * TILE_DEG, 90 - ty * TILE_DEG
            for f in layer["features"]:
                px, py = f["geometry"]["coordinates"]
                if not (0 <= px < EXTENT and 0 <= py < EXTENT):
                    continue  # buffer pixels belong to neighbouring tiles
                lons.append(lon0 + (px + 0.5) / EXTENT * TILE_DEG); lats.append(lat0 - (py + 0.5) / EXTENT * TILE_DEG)
                tots.append(f["properties"].get("total", 0))
    return np.array(lons), np.array(lats), np.array(tots)


def to_grid(lon, lat, tot, grid):
    glon, glat = grid.lon.values, grid.lat.values
    out = np.zeros((len(glat), len(glon)))
    i = np.round((lat - glat[0]) / 0.25).astype(int); j = np.round((lon - glon[0]) / 0.25).astype(int)
    ok = (i >= 0) & (i < len(glat)) & (j >= 0) & (j < len(glon))
    np.add.at(out, (i[ok], j[ok]), tot[ok])
    return out


def main(cfg_path):
    cfg = yaml.safe_load(open(cfg_path)); g = cfg["gbif"]
    keys = json.load(open("results/provenance/gbif_provenance.json"))["keys"]
    grid = xr.open_dataset("data/climate_grid.nc").sel(scenario="baseline")
    ds = xr.Dataset(coords={"lat": grid.lat, "lon": grid.lon})
    prov = {"api": "GBIF maps API v2, occurrence density vector tiles (zoom 2, EPSG:4326)", "years": g["years"], "taxa": {}}
    for name, var in [("Alnus glutinosa", "n_alder"), ("Agelastica alni", "n_beetle")]:
        lon, lat, tot = tile_counts(keys[name], g["years"], cfg["europe_box"])
        ds[var] = (("lat", "lon"), to_grid(lon, lat, tot, grid))
        prov["taxa"][name] = {"key": keys[name], "records_in_box": int(tot.sum()), "occupied_pixels": int(len(tot))}
        print(f"{name}: {int(tot.sum())} records, {int((ds[var] > 0).sum())} occupied 0.25-deg cells", flush=True)
    land = grid["lsm"].values >= 0.5
    dom = (ds["n_alder"].values >= g.get("domain_min_records", 3)) & land
    ds["alder_domain"] = (("lat", "lon"), dom.astype("int8"))
    ds.attrs["domain_rule"] = f"n_alder >= {g.get('domain_min_records', 3)} GBIF records (2000-2026) and ERA5 land fraction >= 0.5"
    ds.to_netcdf("data/gbif_grid.nc")
    prov["domain_cells"] = int(dom.sum()); prov["retrieved_utc"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    json.dump(prov, open("results/provenance/gbif_grid_provenance.json", "w"), indent=1)
    w = np.cos(np.radians(grid.lat.values))[:, None] * np.ones_like(dom)
    print(f"alder domain: {int(dom.sum())} cells of {int(land.sum())} land cells ({100*(w*dom).sum()/(w*land).sum():.1f} % of land area)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/v2.yaml")

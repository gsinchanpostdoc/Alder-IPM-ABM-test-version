"""Use the v2 site layer from Python, e.g. with the alder_ipm_sim package:

    from site_params_api import site_params
    from alder_ipm_sim.model import AlderIPMSimModel
    m = AlderIPMSimModel(site_params("neusiedler", "ssp585"))
"""
import json
from pathlib import Path


def site_params(site_id: str, scenario: str = "baseline", layer: str = str(Path(__file__).parent.parent / "web/data/alder_sites_v2.json")) -> dict:
    data = json.load(open(layer))
    site = next(s for s in data["sites"] if s["id"] == site_id)
    defaults = json.load(open(Path(layer).parent / "default_params.json"))
    return {**defaults, **site["scenarios"][scenario]["params"]}


def site_metrics(site_id: str, scenario: str = "baseline", layer: str = str(Path(__file__).parent.parent / "web/data/alder_sites_v2.json")) -> dict:
    data = json.load(open(layer))
    site = next(s for s in data["sites"] if s["id"] == site_id)
    return site["scenarios"][scenario]["metrics"]

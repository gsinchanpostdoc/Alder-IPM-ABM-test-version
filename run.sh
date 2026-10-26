#!/usr/bin/env bash
# AlderIPM v2 — full pipeline (about 45 min on one core; stages 1-2 are cached/resumable).
set -euo pipefail
pip install -r pipeline/requirements.txt && npm install
python3 pipeline/climate_sites.py config/v2.yaml          # 1. ERA5 daily climatology + CMIP6 deltas -> site/grid indices
python3 pipeline/gbif_sites.py    config/v2.yaml          # 2. GBIF context per site (counts, bird ratio, beetle phenology)
python3 pipeline/gbif_grid.py     config/v2.yaml          # 2b. gridded alder presence domain (GBIF maps API)
node    -e "const E=require('./pipeline/engine.js');const o={};for(const [k,m] of Object.entries(E.PARAM_REGISTRY))o[k]={default:m.default,min:m.min,max:m.max,unit:m.unit,symbol:m.symbol};require('fs').writeFileSync('data/param_registry.json',JSON.stringify(o,null,1))"
python3 pipeline/param_map.py     config/v2.yaml          # 3. climate -> phenological parameters (+ LHS samples)
node    pipeline/run_sites.js     config/v2.yaml --control # 4. stability atlas with the unchanged AlderIPM-Sim engine
python3 pipeline/report.py        config/v2.yaml          # 5. tables, figures, web/data/alder_sites_v2.json
python3 pipeline/param_map_grid.py config/v2.yaml         # 3b. mapping on the grid
node    pipeline/run_grid.js      config/v2.yaml          # 4b. central run on all 5,308 domain cells (~25 min; resumable)
python3 pipeline/report_grid.py   config/v2.yaml          # 5b. gridded atlas products
echo "open web/v2/index.html (serve web/ with: python3 web/serve.py)"

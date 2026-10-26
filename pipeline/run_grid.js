// AlderIPM v2 - stage 4b: run the unchanged engine on every alder-domain grid cell (central run only;
// LHS uncertainty and strategy comparison are site-level products). Resumable: --max N cells per call.
//   node pipeline/run_grid.js config/v2.yaml [--max N]
const fs = require('fs'), yaml = require('js-yaml');
const E = require('./engine.js');
const cfg = yaml.load(fs.readFileSync(process.argv[2] || 'config/v2.yaml', 'utf8'));
const maxArg = process.argv.indexOf('--max'); const MAX = maxArg > 0 ? parseInt(process.argv[maxArg + 1]) : Infinity;
const secArg = process.argv.indexOf('--seconds'); const SECONDS = secArg > 0 ? parseFloat(process.argv[secArg + 1]) : Infinity;
const YEARS = cfg.stability.years, TOL = 1e-6;
const G = JSON.parse(fs.readFileSync('data/grid_params.json', 'utf8'));
const defaults = E.getDefaults();
const PART = 'results/grid_results.partial.json';
const out = fs.existsSync(PART) ? JSON.parse(fs.readFileSync(PART, 'utf8')) : { meta: { years: YEARS, early_stop_tol: 1e-7, initial_condition: [1, 0.5, 'K_0', 0] }, lat: G.lat, lon: G.lon, n_alder: G.n_alder, n_beetle: G.n_beetle, scenarios: {} };
const CLS = { coexistence: 0, parasitoid_free: 1, canopy_only: 2, trivial: 3, numerical_failure: 4 };

function runCell(params) {
  const p = Object.assign({}, defaults, params);
  const m = new E.AlderIPMSimModel(p);
  let A = 1.0, F = 0.5, K = p.K_0, D = 0.0, t = 0, converged = false;
  for (; t < YEARS; t++) {
    const r = m.annualMap(A, F, K, D);
    const dA = Math.abs(r.A_next - A) / Math.max(A, 1e-3), dF = Math.abs(r.F_next - F) / Math.max(F, 1e-3);
    A = r.A_next; F = r.F_next; K = r.K_next; D = r.D_next;
    if (!isFinite(A) || !isFinite(F)) break;
    if (t > 20 && dA < 1e-7 && dF < 1e-7) { converged = true; break; }
  }
  let cls;
  if (!isFinite(A) || !isFinite(F)) cls = 'numerical_failure';
  else if (A < TOL) cls = 'trivial'; else if (F < TOL && D < TOL) cls = 'canopy_only'; else if (F < TOL) cls = 'parasitoid_free'; else cls = 'coexistence';
  const rho = cls === 'numerical_failure' ? NaN : m.spectralRadius(A, F, K, D);
  return { cls: CLS[cls], A, F, K, D, rho, RP: m.computeRP(), years: t, converged };
}

let done = 0, t0 = Date.now();
for (const s of cfg.scenarios) {
  const sc = G.scenarios[s];
  const res = out.scenarios[s] || (out.scenarios[s] = { cls: [], A: [], F: [], K: [], D: [], rho: [], RP: [], years: [] });
  for (let i = res.cls.length; i < G.n_cells; i++) {
    if (done >= MAX || (Date.now() - t0) / 1000 > SECONDS) break;
    const params = {}; Object.keys(G.mapping).forEach(k => params[k] = sc[k][i]);
    const r = runCell(params);
    res.cls.push(r.cls); res.A.push(+r.A.toFixed(5)); res.F.push(+r.F.toFixed(6)); res.K.push(+r.K.toFixed(4)); res.D.push(+r.D.toFixed(4)); res.rho.push(+r.rho.toFixed(4)); res.RP.push(+r.RP.toFixed(4)); res.years.push(r.years);
    done++;
    if (done % 200 === 0) { fs.writeFileSync(PART, JSON.stringify(out)); console.log(`${s} ${i + 1}/${G.n_cells} ${((Date.now() - t0) / 1000).toFixed(0)}s`); }
  }
  if (done >= MAX || (Date.now() - t0) / 1000 > SECONDS) break;
}
fs.writeFileSync(PART, JSON.stringify(out));
const total = cfg.scenarios.reduce((a, s) => a + ((out.scenarios[s] || { cls: [] }).cls.length), 0);
if (total < G.n_cells * cfg.scenarios.length) { console.log(`chunk done: ${total}/${G.n_cells * cfg.scenarios.length}; rerun to continue`); process.exit(0); }
fs.writeFileSync('results/grid_results.json', JSON.stringify(out)); console.log('wrote results/grid_results.json');

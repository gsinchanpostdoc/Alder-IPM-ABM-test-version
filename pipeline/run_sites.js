// AlderIPM v2 - stage 4: stability atlas. Runs the unchanged AlderIPM-Sim engine for every
// site x scenario parameter set produced by param_map.py.
//   node pipeline/run_sites.js config/v2.yaml            central + LHS samples -> results/site_results.json
//   node pipeline/run_sites.js config/v2.yaml --control  adds the three management strategies (A, B, C)
// Reference initial condition (A, F, K, D) = (1.0, 0.5, K_0, 0): the coexistence reference state used
// by the app (science.js) and the paper's dominant-attractor analysis.
const fs = require('fs'), yaml = require('js-yaml');
const E = require('./engine.js');
const cfg = yaml.load(fs.readFileSync(process.argv[2] || 'config/v2.yaml', 'utf8'));
const doControl = process.argv.includes('--control');
const maxArg = process.argv.indexOf('--max'); const MAX = maxArg > 0 ? parseInt(process.argv[maxArg + 1]) : Infinity;
const YEARS = cfg.stability.years, YEARS_S = Math.min(YEARS, 120), TOL = 1e-6;
const data = JSON.parse(fs.readFileSync('data/site_params.json', 'utf8'));
const defaults = E.getDefaults();

function classify(sim, n) {
  const A = sim.A[n], F = sim.F[n], K = sim.K[n], D = sim.D[n];
  let dev = 0;
  for (let i = n - 10; i < n; i++) dev = Math.max(dev, Math.abs(sim.A[i + 1] - sim.A[i]) / Math.max(sim.A[n], 1e-3), Math.abs(sim.F[i + 1] - sim.F[i]) / Math.max(sim.F[n], 1e-3));
  let cls;
  if (!isFinite(A) || !isFinite(F)) cls = 'numerical_failure';
  else if (A < TOL) cls = 'trivial';
  else if (F < TOL && D < TOL) cls = 'canopy_only';
  else if (F < TOL) cls = 'parasitoid_free';
  else cls = 'coexistence';
  return { cls, A, F, K, D, converged: dev < 1e-4 };
}

function run(params, years) {
  const p = Object.assign({}, defaults, params);
  const m = new E.AlderIPMSimModel(p);
  const sim = m.simulate(1.0, 0.5, p.K_0, 0.0, years, false);
  return { m, p, sim, c: classify(sim, years) };
}

const out = { meta: { years: YEARS, sample_years: YEARS_S, lhs_samples: cfg.stability.lhs_samples, reference_site: data.reference_site,
                      initial_condition: [1.0, 0.5, 'K_0', 0.0], engine: 'AlderIPM-Sim web engine (model.js, control.js) unchanged' }, sites: [] };
const prev = fs.existsSync('results/site_results.json') ? JSON.parse(fs.readFileSync('results/site_results.json', 'utf8')) : null;
const partial = fs.existsSync('results/site_results.partial.json') ? JSON.parse(fs.readFileSync('results/site_results.partial.json', 'utf8')) : null;
if (partial) { out.sites = partial.sites.filter(r => !doControl || r.control); console.log(`resuming: ${out.sites.length} entries already done`); }
let done = 0;
let t0 = Date.now();
data.sites.forEach((s, idx) => {
  if (out.sites.some(x => x.site === s.site && x.scenario === s.scenario)) return;
  if (done >= MAX) return;
  done++;
  const r = run(s.params, YEARS);
  const { m, sim, c } = r;
  const rho = m.spectralRadius(c.A, c.F, c.K, c.D);
  const rec = { site: s.site, name: s.name, country: s.country, lat: s.lat, lon: s.lon, scenario: s.scenario,
    drivers: s.drivers, climate: s.climate, gbif: s.gbif, params: s.params,
    attractor: c.cls, converged: c.converged, A_star: c.A, F_star: c.F, K_star: c.K, D_star: c.D,
    rho_star: rho, R_P: m.computeRP(), R1: m.computeR1(c.A, c.F, c.K, c.D), R2: m.computeR2(c.A, c.F, c.K, c.D),
    D_crit_exceeded: c.D > r.p.D_crit, K_below_min: c.K < r.p.K_min };
  const counts = {}; let rhoSum = 0, nRho = 0;
  s.samples.forEach(v => {
    const ps = {}; s.param_names.forEach((k, j) => ps[k] = v[j]);
    const rs = run(ps, YEARS_S);
    counts[rs.c.cls] = (counts[rs.c.cls] || 0) + 1;
    const rr = rs.m.spectralRadius(rs.c.A, rs.c.F, rs.c.K, rs.c.D); if (isFinite(rr)) { rhoSum += rr; nRho++; }
  });
  const n = s.samples.length;
  rec.sample_classes = counts; rec.n_samples = n;
  rec.P_shift = n ? 1 - (counts.coexistence || 0) / n : null;          // probability of a non-coexistence attractor
  rec.P_parasitoid_free = n ? (counts.parasitoid_free || 0) / n : null;
  rec.P_canopy_only = n ? (counts.canopy_only || 0) / n : null;
  rec.P_trivial = n ? (counts.trivial || 0) / n : null;
  rec.rho_star_mean = nRho ? rhoSum / nRho : null;
  if (doControl) {
    const cc = new E.ControlComparator(r.p);
    const res = cc.compareStrategies({ A0: 1.0, F0: 0.5, K0: r.p.K_0, D0: 0.0, nYears: 50 });
    rec.control = res.map(x => ({ name: x.name, J: x.J, rho_star: x.rhoStar, feasible: x.feasible, finalD: x.finalD, finalK: x.finalK, peakD: x.peakD, controls: x.controls }));
    const feas = rec.control.filter(x => x.feasible).sort((a, b) => a.J - b.J);
    rec.cheapest_feasible = feas.length ? feas[0].name : 'none';
  } else if (prev) {
    const old = prev.sites.find(x => x.site === s.site && x.scenario === s.scenario);
    if (old && old.control) { rec.control = old.control; rec.cheapest_feasible = old.cheapest_feasible; }
  }
  out.sites.push(rec);
  fs.writeFileSync('results/site_results.partial.json', JSON.stringify(out));
  if (idx % 6 === 0 || idx === data.sites.length - 1)
    console.log(`${idx + 1}/${data.sites.length} ${s.site} ${s.scenario} ${c.cls} rho*=${rho.toFixed(3)} R_P=${rec.R_P.toFixed(3)} P_shift=${rec.P_shift} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
});
if (out.sites.length < data.sites.length) { console.log(`chunk done: ${out.sites.length}/${data.sites.length}; rerun to continue`); process.exit(0); }
out.sites.sort((a, b) => data.sites.findIndex(x => x.site === a.site && x.scenario === a.scenario) - data.sites.findIndex(x => x.site === b.site && x.scenario === b.scenario));
fs.writeFileSync('results/site_results.json', JSON.stringify(out));
const cols = ['site', 'name', 'country', 'lat', 'lon', 'scenario', 'attractor', 'converged', 'A_star', 'F_star', 'K_star', 'D_star', 'rho_star', 'R_P', 'R1', 'R2', 'P_shift', 'P_parasitoid_free', 'P_canopy_only', 'P_trivial', 'rho_star_mean', 'cheapest_feasible'];
const pcols = Object.keys(out.sites[0].params), ccols = ['winter_T', 'gsl10', 'T_MJJ', 'gdd10', 'precip_annual'];
const lines = [cols.concat(pcols, ccols, ['bird_ratio', 'n_beetle', 'n_alder']).join(',')];
out.sites.forEach(r => lines.push(cols.map(k => r[k] === undefined ? '' : r[k]).concat(pcols.map(k => r.params[k]), ccols.map(k => r.climate[k]), [r.drivers.bird_ratio, r.gbif.n_beetle, r.gbif.n_alder]).join(',')));
fs.writeFileSync('results/site_results.csv', lines.join('\n'));
console.log('wrote results/site_results.json and .csv');

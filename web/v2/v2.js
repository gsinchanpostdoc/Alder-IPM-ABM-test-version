/* AlderIPM-Sim v2 — climate-scenario site layer (reads data/alder_sites_v2.json produced by pipeline/). */
(function () {
  'use strict';
  const DATA_URL = '../data/alder_sites_v2.json';
  const CLS = { coexistence: '#1f8a44', parasitoid_free: '#cf9418', canopy_only: '#0a7fb0', trivial: '#8a8f86' };
  const PARAM_LABEL = { T: 'T · season length (d)', sigma_A: 'σ_A · beetle overwinter survival', sigma_F: 'σ_F · parasitoid overwinter survival', delta: 'δ · parasitoid emergence rate (/d)', B_index: 'B_index · bird pressure' };
  let DATA = null, GRID = null, scenario = 'baseline', map = null, markers = [], current = null, overlay = null, layer = 'attractor', popup = null;

  function pColor(p) {            // green -> yellow -> red
    if (p == null || isNaN(p)) return '#999';
    const stops = [[0, [26, 152, 80]], [0.5, [254, 224, 139]], [1, [215, 48, 39]]];
    let i = 0; while (i < stops.length - 2 && p > stops[i + 1][0]) i++;
    const [a, ca] = stops[i], [b, cb] = stops[i + 1], t = Math.min(1, Math.max(0, (p - a) / (b - a)));
    return 'rgb(' + ca.map((v, k) => Math.round(v + (cb[k] - v) * t)).join(',') + ')';
  }
  const f = (x, d = 3) => (x == null || isNaN(x)) ? '—' : Number(x).toFixed(d);
  const sgn = (x, d = 2) => (x > 0 ? '+' : '') + Number(x).toFixed(d);

  function buildScenarioBar() {
    const bar = document.getElementById('scn');
    Object.entries(DATA.scenarios).forEach(([k, label]) => {
      const b = document.createElement('button'); b.textContent = label; b.dataset.s = k; if (k === scenario) b.classList.add('active');
      b.addEventListener('click', () => { scenario = k; document.querySelectorAll('#scn button').forEach(x => x.classList.toggle('active', x.dataset.s === k)); drawMarkers(); if (current) renderSite(current); });
      bar.appendChild(b);
    });
  }

  function drawOverlay() {
    if (overlay) { map.removeLayer(overlay); overlay = null; }
    if (!GRID || layer === 'none') return;
    const b = GRID.bounds;
    overlay = L.imageOverlay(`../data/grid/${layer}_${scenario}.png`, [[b[0], b[1]], [b[2], b[3]]], { opacity: 0.75, interactive: false }).addTo(map);
  }

  function nearestCell(lat, lon) {
    let best = -1, bd = 1e9;
    for (let i = 0; i < GRID.lat.length; i++) { const d = Math.abs(GRID.lat[i] - lat) + Math.abs(GRID.lon[i] - lon); if (d < bd) { bd = d; best = i; } }
    return bd <= 0.26 ? best : -1;
  }

  function showCell(e) {
    if (!GRID) return;
    const i = nearestCell(e.latlng.lat, e.latlng.lng); if (i < 0) { if (popup) map.closePopup(popup); return; }
    const s = GRID.scenarios[scenario], b = GRID.scenarios.baseline;
    const html = `<b>Grid cell</b> ${GRID.lat[i].toFixed(2)}°N ${GRID.lon[i].toFixed(2)}°E · ${DATA.scenarios[scenario]}<br>
      attractor: <b>${GRID.classes[s.cls[i]].replace('_', ' ')}</b>${scenario !== 'baseline' && s.cls[i] !== b.cls[i] ? ` (baseline: ${GRID.classes[b.cls[i]].replace('_', ' ')})` : ''}<br>
      ρ* = ${f(s.rho[i])}${scenario !== 'baseline' ? ` (${sgn(s.rho[i] - b.rho[i], 3)})` : ''} · R<sub>P</sub> = ${f(s.RP[i])} · D* = ${f(s.D[i])} · K* = ${f(s.K[i], 2)}<br>
      T = ${f(s.params.T[i], 1)} d · σ<sub>A</sub> = ${f(s.params.sigma_A[i])} · σ<sub>F</sub> = ${f(s.params.sigma_F[i])} · δ = ${f(s.params.delta[i])}<br>
      winter T ${f(s.climate.winter_T[i], 1)} °C · days > 10 °C ${Math.round(s.climate.gsl10[i])} · May–Jul ${f(s.climate.T_MJJ[i], 1)} °C<br>
      <span class="muted">GBIF 2000–2026: alder ${GRID.n_alder[i]}, beetle ${GRID.n_beetle[i]} records</span>`;
    popup = L.popup({ maxWidth: 360 }).setLatLng(e.latlng).setContent(html).openOn(map);
  }

  function drawMarkers() {
    drawOverlay();
    markers.forEach(m => map.removeLayer(m)); markers = [];
    DATA.sites.forEach(site => {
      const s = site.scenarios[scenario]; if (!s) return;
      const m = L.circleMarker([site.lat, site.lon], { radius: 9, fillColor: pColor(s.metrics.P_shift), color: CLS[s.metrics.attractor] || '#333', weight: 3, fillOpacity: 0.9 }).addTo(map);
      m.bindTooltip(`<b>${site.name}</b> (${site.country})<br>attractor: ${s.metrics.attractor.replace('_', ' ')} · ρ* = ${f(s.metrics.rho_star)} · R<sub>P</sub> = ${f(s.metrics.R_P)}<br>P<sub>shift</sub> = ${f(s.metrics.P_shift, 2)}`, { sticky: true });
      m.on('click', () => { current = site; renderSite(site); });
      markers.push(m);
    });
  }

  function renderSite(site) {
    const s = site.scenarios[scenario], b = site.scenarios.baseline, c = s.climate, cb = b.climate, m = s.metrics;
    const chip = (v, lab, dv) => `<div class="chip"><b>${v}</b><span>${lab}</span>${dv !== undefined ? `<div class="delta">${dv} vs baseline</div>` : ''}</div>`;
    const isB = scenario === 'baseline';
    let html = `<h2>${site.name} <span class="muted">· ${site.country}${site.region ? ' · ' + site.region : ''} · ${site.lat.toFixed(2)}°N ${site.lon.toFixed(2)}°E</span></h2>
      <div class="muted">${DATA.scenarios[scenario]}</div>
      <div class="chips">
        ${chip(f(c.winter_T, 1) + ' °C', 'Dec–Feb mean', isB ? undefined : sgn(c.winter_T - cb.winter_T, 1) + ' °C')}
        ${chip(Math.round(c.gsl10) + ' d', 'days > 10 °C', isB ? undefined : sgn(c.gsl10 - cb.gsl10, 0) + ' d')}
        ${chip(f(c.T_MJJ, 1) + ' °C', 'May–Jul mean', isB ? undefined : sgn(c.T_MJJ - cb.T_MJJ, 1) + ' °C')}
        ${chip(Math.round(c.precip_annual) + ' mm', 'precipitation / yr', isB ? undefined : sgn(100 * (c.precip_annual / cb.precip_annual - 1), 0) + ' %')}
      </div>
      <h3>Stability of the unmanaged system (central run)</h3>
      <div class="chips">
        <div class="chip"><b><span class="badge" style="background:${CLS[m.attractor] || '#333'}">${m.attractor.replace('_', ' ')}</span></b><span>attractor</span></div>
        ${chip(f(m.rho_star), 'ρ* (spectral radius)')}${chip(f(m.R_P), 'R_P (parasitoid invasion)')}${chip(f(m.D_star), 'D* (defoliation)')}${chip(f(m.K_star, 2), 'K* (canopy capacity)')}
        <div class="chip" style="background:${pColor(m.P_shift)}33"><b>${f(m.P_shift, 2)}</b><span>P_shift (LHS)</span></div>
      </div>
      <h3>Climate-mapped parameters</h3>
      <table><thead><tr><th>parameter</th><th class="num">calibrated</th><th class="num">baseline</th><th class="num">${isB ? '' : 'scenario'}</th></tr></thead><tbody>`;
    const cal = getDefaults();
    Object.keys(s.params).forEach(k => {
      html += `<tr><td>${PARAM_LABEL[k] || k}</td><td class="num">${f(cal[k])}</td><td class="num">${f(b.params[k])}</td><td class="num">${isB ? '' : f(s.params[k])}</td></tr>`;
    });
    html += `</tbody></table>`;
    if (s.control) {
      html += `<h3>Management strategies (50-year horizon, app cost functional)</h3><table><thead><tr><th>strategy</th><th class="num">J</th><th class="num">ρ*</th><th>feasible</th><th>controls</th></tr></thead><tbody>`;
      s.control.forEach(x => { html += `<tr${x.name === s.cheapest_feasible ? ' style="background:rgba(31,138,68,.12)"' : ''}><td>${x.name}</td><td class="num">${f(x.J, 1)}</td><td class="num">${f(x.rho_star)}</td><td>${x.feasible ? 'yes' : 'no'}</td><td class="muted">u_P ${f(x.controls.u_P, 2)} · u_C ${f(x.controls.u_C, 2)} · u_B ${f(x.controls.u_B, 2)}</td></tr>`; });
      html += `</tbody></table><div class="muted">Cheapest feasible: <b>${s.cheapest_feasible}</b></div>`;
    }
    html += `<div class="muted" style="margin-top:8px">GBIF records within 25 km (2000–2026): alder ${site.gbif.n_alder ?? '—'}, beetle ${site.gbif.n_beetle ?? '—'}, parasitoid ${site.gbif.n_parasitoid ?? '—'}; bird reporting ratio ${f(s.drivers.bird_ratio, 3)}.</div>
      <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap">
        <button class="btn primary" id="btn-live">Run live (100 yr)</button>
        <button class="btn" id="btn-copy">Copy parameter set (JSON)</button>
      </div>`;
    document.getElementById('site').innerHTML = html;
    document.getElementById('btn-live').addEventListener('click', () => runLive(site));
    document.getElementById('btn-copy').addEventListener('click', () => {
      const p = Object.assign(getDefaults(), s.params);
      navigator.clipboard.writeText(JSON.stringify(p, null, 2)).then(() => { document.getElementById('btn-copy').textContent = 'Copied'; });
    });
  }

  function runLive(site) {
    const s = site.scenarios[scenario];
    const p = Object.assign(getDefaults(), s.params);
    const model = new AlderIPMSimModel(p);
    const sim = model.simulate(1.0, 0.5, p.K_0, 0.0, 100, false);
    const yrs = sim.A.map((_, i) => i);
    const box = document.getElementById('live'); box.hidden = false;
    document.getElementById('live-title').textContent = `Live simulation — ${site.name}, ${DATA.scenarios[scenario]} (same engine as the main app)`;
    const lay = (t, y) => ({ title: { text: t, font: { size: 13 } }, margin: { l: 45, r: 10, t: 30, b: 35 }, xaxis: { title: 'year' }, yaxis: { title: y } });
    Plotly.newPlot('cA', [{ x: yrs, y: sim.A, mode: 'lines', line: { color: '#2f3a55' } }], lay('Adult beetles A', 'A'), { responsive: true, displayModeBar: false });
    Plotly.newPlot('cF', [{ x: yrs, y: sim.F, mode: 'lines', line: { color: '#7a5ea8' } }], lay('Parasitoids F', 'F'), { responsive: true, displayModeBar: false });
    Plotly.newPlot('cK', [{ x: yrs, y: sim.K, mode: 'lines', line: { color: '#3f7a2e' } }], lay('Canopy capacity K', 'K'), { responsive: true, displayModeBar: false });
    Plotly.newPlot('cD', [{ x: yrs, y: sim.D, mode: 'lines', line: { color: '#c0392b' } }, { x: yrs, y: yrs.map(() => p.D_crit), mode: 'lines', line: { dash: 'dash', color: '#999' }, name: 'D_crit' }], lay('Defoliation D', 'D'), { responsive: true, displayModeBar: false, showlegend: false });
    box.scrollIntoView({ behavior: 'smooth' });
  }

  async function init() {
    DATA = await fetch(DATA_URL).then(r => r.json());
    buildScenarioBar();
    map = L.map('map', { scrollWheelZoom: false }).setView([50.5, 10], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 10 }).addTo(map);
    try { GRID = await fetch('../data/grid_cells.json').then(r => r.json()); } catch (e) { GRID = null; }
    if (GRID) {
      const bar = document.getElementById('layers');
      [['attractor', 'Grid: regime'], ['rho', 'Grid: ρ*'], ['none', 'Sites only']].forEach(([k, label]) => {
        const b = document.createElement('button'); b.textContent = label; b.dataset.l = k; if (k === layer) b.classList.add('active');
        b.addEventListener('click', () => { layer = k; document.querySelectorAll('#layers button').forEach(x => x.classList.toggle('active', x.dataset.l === k)); drawOverlay(); });
        bar.appendChild(b);
      });
      map.on('click', showCell);
      const sm = GRID.summary.map(r => `${r.scenario}: parasitoid-free ${r.area_pct_parasitoid_free} %, beetle-free ${r.area_pct_trivial} %, coexistence ${r.area_pct_coexistence} % of alder area`).join(' · ');
      document.getElementById('gridnote').innerHTML = `<b>Gridded domain</b> — ${GRID.lat.length} ERA5 cells (0.25°) with ≥ 3 GBIF <i>A. glutinosa</i> records, 2000–2026; central run per cell (no LHS / strategy costs at grid level). Click any coloured cell for its values. ${sm}.`;
    }
    drawMarkers();
    const pv = DATA.provenance;
    document.getElementById('foot').innerHTML = `<p><b>Provenance.</b> Climate baseline: ${pv.climate.dataset}. Change signal: ensemble-mean delta of ${pv.cmip6_models.join(', ')} (Pangeo CMIP6). Occurrence context: ${pv.gbif.api} (${pv.gbif.taxonomy}; retrieved ${pv.gbif.retrieved_utc} UTC). Layer generated ${DATA.generated_utc}; reference site for the calibrated parameter set: ${DATA.reference_site}.</p>
      <p><b>Read with care.</b> Only T, σ<sub>A</sub>, σ<sub>F</sub>, δ and B<sub>index</sub> vary between sites and scenarios; the mapping slopes are literature-informed assumptions, not fitted relations, and P<sub>shift</sub> propagates their uncertainty together with the CMIP6 inter-model spread. The engine is the published AlderIPM-Sim model; no site-specific field time series were used, so these are structural scenario projections, not stand-level forecasts.</p>`;
  }
  document.addEventListener('DOMContentLoaded', init);
})();

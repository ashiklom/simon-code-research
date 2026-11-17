import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { asyncBufferFromUrl, parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'

// Adapted from climate-product-compare/site/src/main.js.
// Site data base URL: local ./data by default; production builds may read it from elsewhere
// at a pinned commit (site/.env.production, VITE_DATA_BASE).
const DATA = (import.meta.env.VITE_DATA_BASE || './data').replace(/\/$/, '')

// ---- fixed product styling (color follows the product, never its rank) -------------------
// 8 validated categorical slots; products 9-16 reuse the hues with a dashed line.
const PRODUCTS = [
  'geoscf_v1', 'merra2', 'merra2_cnn', 'cams_eac4', 'acag', 'ghap', 'hrrr_smoke', 'naqfc',
  'geoscf_v2', 'geosfp_aer', 'cams_fcst', 'ghap_m', 'naqfc_bc', 'haqes', 'merra2_gmi',
]
const css = (v) => getComputedStyle(document.querySelector('.viz-root')).getPropertyValue(v).trim()
function productStyle(p) {
  let i = PRODUCTS.indexOf(p)
  if (i < 0) i = 15
  return { color: css(`--s${(i % 8) + 1}`), dash: i >= 8 ? [6, 4] : null }
}
const TIERS = {
  1: ['US reference (AQS, IMPROVE, CSN)', '--s1'], 2: ['Global reference (embassies, SPARTAN)', '--s2'],
  3: ['Low-cost sensors (Sensor.Community)', '--s3'], 4: ['Station-remote points', '--s7'],
}
const OBS_SOURCES = ['AQS', 'AQS-FRM', 'CSN', 'IMPROVE', 'Embassy', 'SPARTAN', 'SensorCommunity']
const UG = 'µg m⁻³'
const VARS = [
  { key: 'pm25', label: 'PM2.5', units: UG, obs: ['pm25', 'pm25_frm'], prod: ['pm25'], hourly: 'pm25' },
  { key: 'pm10', label: 'PM10', units: UG, obs: ['pm10'], prod: ['pm10'], hourly: 'pm10' },
  { key: 'o3', label: 'O3 (daily max 8-h mean; hourly O3 below)', units: 'ppb', obs: ['o3_mda8'], prod: ['o3_mda8'], hourly: 'o3' },
  { key: 'no2', label: 'NO2', units: 'ppb', obs: ['no2'], prod: ['no2'], hourly: 'no2' },
  { key: 'smoke', label: 'Smoke PM2.5 (HRRR-Smoke) vs total PM2.5', units: UG, obs: ['pm25'], prod: ['pm25_smoke'], hourly: 'pm25_smoke' },
  { key: 'so4', label: 'PM2.5 sulfate', units: UG, obs: ['spec_so4'], prod: ['spec_so4'] },
  { key: 'no3', label: 'PM2.5 nitrate', units: UG, obs: ['spec_no3'], prod: ['spec_no3'] },
  { key: 'nh4', label: 'PM2.5 ammonium', units: UG, obs: ['spec_nh4'], prod: ['spec_nh4'] },
  { key: 'om', label: 'PM2.5 organic matter (obs 1.8 × OC)', units: UG, obs: ['spec_om'], prod: ['spec_om'] },
  { key: 'bc', label: 'PM2.5 black / elemental carbon', units: UG, obs: ['spec_bc'], prod: ['spec_bc'] },
  { key: 'dust', label: 'PM2.5 dust / fine soil', units: UG, obs: ['spec_dust'], prod: ['spec_dust'] },
  { key: 'ss', label: 'PM2.5 sea salt', units: UG, obs: ['spec_ss'], prod: ['spec_ss'] },
]
const METRIC_VARS = { pm25: ['pm25', 'pm25_frm'], pm10: ['pm10'], o3: ['o3', 'o3_mda8'], no2: ['no2'], smoke: [],
  so4: ['spec_so4'], no3: ['spec_no3'], nh4: ['spec_nh4'], om: ['spec_om'], bc: ['spec_bc'], dust: ['spec_dust'], ss: ['spec_ss'] }

let SITES = [], PRODMETA = {}, SUMMARY = [], SCALES = {}
const state = { site: null, data: {}, varKey: 'pm25', agg: 'daily', hidden: new Set(), hourly: null, hourlyYear: null, metrics: [] }

// ---- data loading ------------------------------------------------------------------------
async function readParquet(url) {
  const file = await asyncBufferFromUrl({ url })
  return parquetReadObjects({ file, compressors })
}
function toColumns(rows, timeKey) {
  const cols = {}
  if (!rows.length) return { t: [], cols }
  const keys = Object.keys(rows[0]).filter((k) => k !== timeKey)
  const t = new Float64Array(rows.length)
  const sc = Object.fromEntries(keys.map((k) => [k, SCALES[k.split('|')[1]] || 1]))
  for (const k of keys) cols[k] = new Array(rows.length)
  rows.forEach((r, i) => {
    t[i] = Number(r[timeKey])
    for (const k of keys) { const v = r[k]; cols[k][i] = v == null ? null : Number(v) / sc[k] }
  })
  return { t, cols }
}

// ---- map --------------------------------------------------------------------------------
let map, markers = []
const tierOn = new Set([1, 2, 3, 4])
function initMap() {
  map = L.map('map', { preferCanvas: true, worldCopyJump: true }).setView([25, -30], 2)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 12, attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map)
  const f = document.getElementById('tier-filters')
  for (const [k, [label, v]] of Object.entries(TIERS)) {
    const n = SITES.filter((s) => s.tier === +k).length
    if (!n) continue
    const b = document.createElement('button')
    b.className = 'chip on'
    b.innerHTML = `<span class="dot" style="background:${css(v)}"></span>${label} (${n})`
    b.onclick = () => { tierOn.has(+k) ? tierOn.delete(+k) : tierOn.add(+k); b.classList.toggle('on'); drawMarkers() }
    f.appendChild(b)
  }
  drawMarkers()
}
function drawMarkers() {
  markers.forEach((m) => m.remove())
  markers = []
  for (const s of SITES) {
    if (!tierOn.has(s.tier)) continue
    const m = L.circleMarker([s.lat, s.lon], {
      radius: s.tier === 1 ? 4 : 6, color: css('--surface-1'), weight: 1.5, fillColor: css(TIERS[s.tier][1]), fillOpacity: 1,
    }).addTo(map)
    m.bindTooltip(`<b>${s.name}</b><br>${s.network} · ${s.site_id}`)
    m.on('click', () => selectSite(s))
    markers.push(m)
  }
}

// ---- site panel -------------------------------------------------------------------------
function header(s) {
  return `<h2>${s.name}</h2><p class="secondary">${s.site_id} · ${s.network} · ${s.region}${s.setting ? ' · ' + s.setting : ''} ·
    ${s.lat.toFixed(3)}, ${s.lon.toFixed(3)}</p>${s.note ? `<p class="note">${s.note}</p>` : ''}
    ${s.tier === 4 ? '<p class="note">Station-remote point: no observations, so products are compared with each other.</p>' : ''}`
}
async function selectSite(s) {
  state.site = s; state.hourly = null; state.hourlyYear = null; state.data = {}
  const panel = document.getElementById('panel')
  panel.innerHTML = header(s) + '<p class="muted">Loading…</p>'
  if (!s.daily) state.agg = 'monthly'
  await loadAgg()
  state.metrics = await (await fetch(`${DATA}/site/${s.id}/metrics.json`)).json().catch(() => [])
  renderPanel()
}
async function loadAgg() {
  const s = state.site
  if (state.data[state.agg]) return
  const file = state.agg === 'daily' ? 'daily' : 'monthly'
  try { state.data[state.agg] = toColumns(await readParquet(`${DATA}/site/${s.id}/${file}.parquet`), 'day') }
  catch { state.data[state.agg] = { t: [], cols: {} } }
}

function sourcesFor(v, cols) {
  const out = []
  const bySrc = {}
  for (const c of Object.keys(cols)) { const [src, name] = c.split('|'); (bySrc[src] ||= []).push(name) }
  for (const [src, names] of Object.entries(bySrc)) {
    const isObs = OBS_SOURCES.includes(src)
    for (const w of (isObs ? v.obs : v.prod)) if (names.includes(w)) out.push({ src, col: `${src}|${w}`, isObs, label: isObs ? `${src} (obs${w.endsWith('_frm') ? ', 24-h filter' : ''})` : (PRODMETA[src]?.title || src) })
  }
  out.sort((a, b) => (b.isObs - a.isObs) || PRODUCTS.indexOf(a.src) - PRODUCTS.indexOf(b.src))
  return out
}

let plot = null, hplot = null
function renderPanel() {
  const s = state.site, panel = document.getElementById('panel')
  const cur = state.data[state.agg]
  const avail = VARS.filter((v) => sourcesFor(v, cur.cols).length)
  if (!avail.find((v) => v.key === state.varKey)) state.varKey = avail[0]?.key
  const v = VARS.find((x) => x.key === state.varKey)
  if (!v) { panel.innerHTML = header(s) + '<p class="muted">No series for this site.</p>'; return }
  const srcs = sourcesFor(v, cur.cols)
  panel.innerHTML = header(s) + `
    <div class="row">
      <select id="var">${avail.map((x) => `<option value="${x.key}" ${x.key === v.key ? 'selected' : ''}>${x.label}</option>`).join('')}</select>
      <select id="agg">${['daily', 'monthly'].filter((a) => a === 'monthly' || s.daily).map((a) => `<option ${a === state.agg ? 'selected' : ''}>${a}</option>`).join('')}</select>
      ${s.hourly_years?.length && v.hourly ? `<span class="secondary">Hourly:</span>${s.hourly_years.map((y) => `<button class="btn" data-year="${y}">${y}</button>`).join('')}` : ''}
    </div>
    <div class="legend" id="legend"></div>
    <div class="chart" id="chart"></div>
    <p class="note">Daily values are local-standard-time days (GHAP daily: UTC days). O3 daily = MDA8 (CAMS 3-hourly: daily max of instants).
      Products are bilinear from the 4 surrounding pixels. ${state.agg === 'daily' ? 'The chart opens on the last three years: drag to zoom, double-click for the full record.' : 'Monthly means need ≥ 75 % of days; ACAG and GHAP-monthly are monthly products.'}</p>
    <div id="hourly"></div>
    <h3>Skill for this variable</h3>
    <div id="metrics"></div>`
  panel.querySelector('#var').onchange = (e) => { state.varKey = e.target.value; renderPanel() }
  panel.querySelector('#agg').onchange = async (e) => { state.agg = e.target.value; await loadAgg(); renderPanel() }
  panel.querySelectorAll('[data-year]').forEach((b) => (b.onclick = () => loadHourly(+b.dataset.year)))
  drawLegend(srcs)
  const el = document.getElementById('chart')
  if (plot) plot.destroy()
  plot = makePlot(el, Array.from(cur.t, (d) => d * 86400), srcs.map(({ col }) => cur.cols[col]), srcs, v.units, false,
    state.agg === 'daily' ? 3 * 365 : null)
  drawMetrics(v)
  if (state.hourly) drawHourly(v)
}

function drawLegend(srcs) {
  const el = document.getElementById('legend')
  el.innerHTML = ''
  for (const { src, isObs, label } of srcs) {
    const st = isObs ? { color: css('--obs'), dash: null } : productStyle(src)
    const b = document.createElement('button')
    b.className = 'chip' + (state.hidden.has(src) ? ' off' : '')
    b.innerHTML = `<span class="swatch ${st.dash ? 'dashed' : ''}" style="border-color:${st.color}"></span>${label}`
    b.title = isObs ? 'Observations' : `${PRODMETA[src]?.source || ''}\nUses surface obs: ${PRODMETA[src]?.dependence || ''}`
    b.onclick = () => { state.hidden.has(src) ? state.hidden.delete(src) : state.hidden.add(src); renderPanel() }
    el.appendChild(b)
  }
}

function tooltipPlugin(units) {
  let tt
  return {
    hooks: {
      init: (u) => { tt = document.createElement('div'); tt.className = 'tt'; tt.style.display = 'none'; u.over.appendChild(tt) },
      setCursor: (u) => {
        const i = u.cursor.idx
        if (i == null) { tt.style.display = 'none'; return }
        const d = new Date(u.data[0][i] * 1000)
        const rows = u.series.slice(1).map((s, k) => {
          const val = u.data[k + 1][i]
          return s.show && val != null ? `<div><span class="swatch" style="border-color:${s._color}"></span>${s.label}: <span class="v">${val.toFixed(1)} ${units}</span></div>` : ''
        }).join('')
        tt.innerHTML = `<div class="secondary">${d.toISOString().slice(0, u._hourly ? 16 : 10).replace('T', ' ')}${u._hourly ? ' UTC' : ''}</div>${rows}`
        tt.style.display = rows ? 'block' : 'none'
        const left = Math.min(u.cursor.left + 12, u.over.clientWidth - tt.offsetWidth - 4)
        tt.style.left = left + 'px'; tt.style.top = Math.max(0, u.cursor.top - tt.offsetHeight - 8) + 'px'
      },
    },
  }
}

function makePlot(el, t, series, srcs, units, hourly, initialDays = null) {
  const order = srcs.map((_, i) => i).sort((a, b) => srcs[a].isObs - srcs[b].isObs)
  srcs = order.map((i) => srcs[i]); series = order.map((i) => series[i])
  const width = Math.max(320, el.clientWidth || 600)
  const opts = {
    width, height: 300,
    scales: { x: { time: true } },
    axes: [
      { stroke: css('--text-secondary'), grid: { stroke: css('--grid'), width: 1 }, ticks: { stroke: css('--grid') } },
      { stroke: css('--text-secondary'), grid: { stroke: css('--grid'), width: 1 }, ticks: { stroke: css('--grid') }, label: units, size: 56 },
    ],
    cursor: { drag: { x: true, y: false }, points: { size: 8 } },
    legend: { show: false },
    series: [{}, ...srcs.map(({ src, isObs, label }) => {
      const st = isObs ? { color: css('--obs'), dash: null } : productStyle(src)
      const filt = isObs && label.includes('filter')
      return { label, stroke: st.color, dash: st.dash || undefined, width: isObs ? 2 : 1.5, show: !state.hidden.has(src),
        spanGaps: false, _color: st.color, points: { show: filt, size: 5, fill: st.color }, paths: filt ? () => null : undefined }
    })],
    plugins: [tooltipPlugin(units)],
  }
  const tt = Array.from(t)
  const u = new uPlot(opts, [tt, ...series], el)
  u._hourly = hourly
  if (initialDays && tt.length) u.setScale('x', { min: tt[tt.length - 1] - initialDays * 86400, max: tt[tt.length - 1] })
  return u
}

async function loadHourly(year) {
  const s = state.site
  state.hourly = toColumns(await readParquet(`${DATA}/site/${s.id}/hourly/${year}.parquet`), 'hour')
  state.hourlyYear = year
  renderPanel()
}
function drawHourly(v) {
  const el = document.getElementById('hourly')
  const { t, cols } = state.hourly
  const hv = { ...v, obs: [v.key === 'smoke' ? 'pm25' : v.hourly], prod: [v.hourly] }
  const srcs = sourcesFor(hv, cols)
  if (!srcs.length) { el.innerHTML = `<p class="muted">No hourly series for this variable in ${state.hourlyYear}.</p>`; return }
  el.innerHTML = `<h3>Hourly, ${state.hourlyYear} (UTC, end of hour; CAMS/HAQES 3-hourly)</h3><div class="chart" id="hchart"></div>`
  if (hplot) hplot.destroy()
  hplot = makePlot(el.querySelector('#hchart'), Array.from(t, (h) => h * 3600), srcs.map(({ col }) => cols[col]), srcs, v.units, true, 30)
}

function fmt(x, d = 2) { return x == null || Number.isNaN(x) ? '' : Number(x).toFixed(d) }
function drawMetrics(v) {
  const el = document.getElementById('metrics')
  const want = METRIC_VARS[v.key] || []
  const m = (state.metrics || []).filter((r) => want.includes(r.var) && (r.method === 'bilinear' || r.method === 'point') && r.window === 'full')
  if (!m.length) { el.innerHTML = '<p class="muted">No metrics for this variable here.</p>'; return }
  const scales = ['hourly', 'daily', 'monthly']
  const heads = ['n', 'mean_obs', 'mean_prod', 'bias', 'nmb', 'rmse', 'r', ...(v.key === 'pm25' ? ['csi_35', 'aqi_agree'] : [])]
  const rows = m.sort((a, b) => scales.indexOf(a.scale) - scales.indexOf(b.scale) || PRODUCTS.indexOf(a.product) - PRODUCTS.indexOf(b.product))
  const remote = state.site.tier === 4
  el.innerHTML = `<p class="note">Full overlap period, bilinear. Bias = product − ${remote ? 'median of the other products (no observations here)' : 'observation'};
    NMB = normalized mean bias; CSI at the US 24-h standard (35 µg m⁻³); "sensor_*" rows score the low-cost sensor against its co-located monitor.</p>
    <div style="overflow-x:auto"><table><tr><th>Product</th><th>Var</th><th>Scale</th>${heads.map((h) => `<th>${h}</th>`).join('')}</tr>
    ${rows.map((r) => `<tr><td>${PRODMETA[r.product]?.title || r.product}</td><td>${r.var}</td><td>${r.scale}</td>${heads.map((h) => `<td>${h === 'n' ? r.n : fmt(r[h])}</td>`).join('')}</tr>`).join('')}</table></div>`
}

// ---- summary view -----------------------------------------------------------------------
const sum = { group: 'tier', value: '1', scale: 'daily', window: 'common', method: 'bilinear', metric: 'r' }
function heatColor(val, metric, colMax) {
  if (val == null) return 'transparent'
  const mix = (a, b, t) => `color-mix(in oklab, ${a} ${Math.round((1 - t) * 100)}%, ${b})`
  if (metric === 'bias' || metric === 'nmb') {
    const t = Math.max(-1, Math.min(1, val / (colMax || 1)))
    return t < 0 ? mix(css('--div-mid'), css('--div-neg'), -t) : mix(css('--div-mid'), css('--div-pos'), t)
  }
  if (['r', 'kge', 'csi_35', 'csi_15', 'csi_70', 'aqi_agree'].includes(metric)) {
    const t = Math.max(0, Math.min(1, metric === 'r' ? (val - 0.3) / 0.6 : val))
    return mix(css('--div-mid'), css('--s1'), t)
  }
  const t = Math.max(0, Math.min(1, val / (colMax || 1)))
  return mix(css('--div-mid'), css('--s2'), t)
}
const GROUP_LABEL = { tier: { 1: 'Tier 1: US reference', 2: 'Tier 2: global reference', 3: 'Tier 3: low-cost sensors', 4: 'Tier 4: remote points (vs other products)' } }
function renderSummary() {
  const el = document.getElementById('view-summary')
  const opts = (k, vals, labels = {}) => `<select data-k="${k}">${vals.map((v) => `<option value="${v}" ${String(v) === String(sum[k]) ? 'selected' : ''}>${labels[v] || v}</option>`).join('')}</select>`
  const values = [...new Set(SUMMARY.filter((r) => r.group === sum.group).map((r) => r.group_value))].sort()
  if (!values.includes(String(sum.value))) sum.value = values[0]
  const rows = SUMMARY.filter((r) => r.group === sum.group && r.group_value === String(sum.value) && r.scale === sum.scale
    && r.window === sum.window && r.method === sum.method && r[sum.metric] != null)
  const order = ['pm25', 'pm25_frm', 'pm10', 'o3', 'o3_mda8', 'no2', 'spec_so4', 'spec_no3', 'spec_nh4', 'spec_om', 'spec_bc', 'spec_dust', 'spec_ss']
  const cols = order.filter((c) => rows.some((r) => r.var === c))
  const prods = PRODUCTS.filter((p) => rows.some((r) => r.product === p))
  const cell = Object.fromEntries(rows.map((r) => [`${r.product}|${r.var}`, r]))
  const colMax = Object.fromEntries(cols.map((c) => [c, Math.max(...rows.filter((r) => r.var === c).map((r) => Math.abs(r[sum.metric])))]))
  el.innerHTML = `<h2>Median skill across sites</h2>
    <div class="row">${opts('group', ['tier', 'network', 'region'])} ${opts('value', values, GROUP_LABEL[sum.group] || {})}
      ${opts('scale', ['hourly', 'daily', 'monthly'])} ${opts('window', ['full', 'common', 'recent', 'v1v2'])}
      ${opts('method', ['bilinear', 'nearest'])} ${opts('metric', ['r', 'bias', 'nmb', 'rmse', 'kge', 'csi_35', 'csi_15', 'csi_70', 'aqi_agree', 'mean_obs', 'mean_prod'])}</div>
    <p class="note">Each cell: median over sites of the per-site ${sum.metric} for that product and variable (number of sites in the tooltip).
      Windows: full = each product's whole overlap; common = 2018-01..2023-12; recent = 2025-08..2026-10; v1v2 = 2025-08-04..2026-01-02 (GEOS-CF v1 and v2 both available).
      Daily filter comparisons (pm25_frm, species) are 24-h samples on their sampling days. Bias = product − observation.
      Products trained on or corrected with monitors (see About) are not independent of these observations.</p>
    <div style="overflow-x:auto"><table class="heat"><tr><th>Product</th>${cols.map((c) => `<th>${c}</th>`).join('')}</tr>
    ${prods.map((p) => `<tr><td>${PRODMETA[p]?.title || p}</td>${cols.map((c) => {
      const r = cell[`${p}|${c}`]
      const val = r ? r[sum.metric] : null
      return `<td class="cell" style="background:${heatColor(val, sum.metric, colMax[c])}" title="${r ? r.n_sites + ' sites' : ''}">${fmt(val)}</td>`
    }).join('')}</tr>`).join('')}</table></div>`
  el.querySelectorAll('select').forEach((s) => (s.onchange = (e) => { sum[e.target.dataset.k] = e.target.value; renderSummary() }))
}

function renderAbout() {
  const el = document.getElementById('view-about')
  el.innerHTML = `<div class="about"><h2>Products and access paths</h2>
    <table><tr><th>Product</th><th>Step</th><th>Source</th><th>Surface observations used</th></tr>
    ${PRODUCTS.filter((p) => PRODMETA[p]).map((p) => `<tr><td>${PRODMETA[p].title}</td><td>${PRODMETA[p].freq}</td><td style="text-align:left;white-space:normal">${PRODMETA[p].source}<br><span class="muted">${PRODMETA[p].notes}</span></td><td style="text-align:left;white-space:normal">${PRODMETA[p].dependence}</td></tr>`).join('')}
    </table>
    <h2>Sites</h2><ul class="note">
      <li><b>Tier 1</b>: US EPA AQS continuous monitors (PM2.5, PM10, O3, NO2; ≥ 75 % complete in ≥ 4 of 2018–2023; one per 0.25° cell), 24-h FRM PM2.5 filters, and IMPROVE/CSN speciation filters.</li>
      <li><b>Tier 2</b>: US State Department embassy/consulate PM2.5 monitors (AirNow) and SPARTAN (nephelometer-based hourly PM2.5).</li>
      <li><b>Tier 3</b>: Sensor.Community low-cost optical sensors, 2023–2024, hours with RH > 75 % dropped, κ-Köhler humidity correction (κ = 0.4).</li>
      <li><b>Tier 4</b>: ~90 land points far from known monitors, stratified by region × ACAG PM2.5 class; products vs the median of the others.</li>
    </ul><p class="note">See the experiment README for methods, caveats and how to reproduce.</p></div>`
}

// ---- boot -------------------------------------------------------------------------------
document.querySelectorAll('nav button').forEach((b) => (b.onclick = () => {
  document.querySelectorAll('nav button').forEach((x) => x.classList.toggle('active', x === b))
  document.querySelectorAll('.view').forEach((x) => x.classList.toggle('active', x.id === `view-${b.dataset.view}`))
  if (b.dataset.view === 'map') map.invalidateSize()
}))
Promise.all([
  fetch(`${DATA}/sites.json`).then((r) => r.json()),
  fetch(`${DATA}/products.json`).then((r) => r.json()),
  fetch(`${DATA}/summary.json`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
  fetch(`${DATA}/scales.json`).then((r) => r.json()),
]).then(([s, p, m, sc]) => {
  SITES = s; PRODMETA = p; SUMMARY = m; SCALES = sc
  initMap(); renderSummary(); renderAbout()
  window.__aqc = { selectSite, SITES }  // used by the headless smoke test
})

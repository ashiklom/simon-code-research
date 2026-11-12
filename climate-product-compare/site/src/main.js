import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { asyncBufferFromUrl, parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'

const DATA = './data'

// ---- fixed product styling (color follows the product, never its rank) -------------------
// 8 validated categorical slots; products 9-16 reuse the hues with a dashed line.
const PRODUCTS = [
  'era5', 'era5land', 'merra2', 'nldas2_forcing', 'hrrr', 'prism', 'gridmet', 'daymet',
  'chelsa', 'chirps3', 'imerg_final_daily', 'imerg_late', 'geosfp', 'nldas2_noah', 'nldas2_vic', 'nldas2_mosaic',
  'imerg_final_hh',
]
const css = (v) => getComputedStyle(document.querySelector('.viz-root')).getPropertyValue(v).trim()
function productStyle(p) {
  let i = PRODUCTS.indexOf(p)
  if (p === 'imerg_final_hh') i = PRODUCTS.indexOf('imerg_final_daily')
  if (i < 0) i = 15
  return { color: css(`--s${(i % 8) + 1}`), dash: i >= 8 ? [6, 4] : null }
}
const TIERS = { 1: ['USCRN', '--s1'], 2: ['Other high-quality stations', '--s2'], 3: ['Station-remote points', '--s3'] }

// ---- variables offered in the panel: obs columns + product columns plotted together ------
const VARS = [
  { key: 'tair', label: 'Air temperature (mean)', units: '°C', obs: ['tair'], prod: ['tair'] },
  { key: 'tmax', label: 'Daily max temperature', units: '°C', obs: ['tmax'], prod: ['tmax'] },
  { key: 'tmin', label: 'Daily min temperature', units: '°C', obs: ['tmin'], prod: ['tmin'] },
  { key: 'pr', label: 'Precipitation', units: 'mm', obs: ['pr'], prod: ['pr'], sum: true },
  { key: 'sw', label: 'Downward shortwave', units: 'W m⁻²', obs: ['sw'], prod: ['sw'] },
  { key: 'rh', label: 'Relative humidity', units: '%', obs: ['rh'], prod: ['rh'] },
  { key: 'tdew', label: 'Dewpoint', units: '°C', obs: ['tdew'], prod: ['tdew'] },
  { key: 'vpd', label: 'Vapour pressure deficit', units: 'kPa', obs: ['vpd'], prod: ['vpd'] },
  { key: 'tsurf', label: 'Surface (skin / IR) temperature', units: '°C', obs: ['tsurf'], prod: ['tsurf'] },
  { key: 'wind', label: 'Wind speed (obs 1.5–10 m; products 10 m)', units: 'm s⁻¹', obs: ['wind'], prod: ['wind'] },
  { key: 'sm', label: 'Soil moisture, top layer', units: 'm³ m⁻³', obs: ['sm05', 'sm10'], prod: ['soilm1', 'soilm_top'] },
  { key: 'ts', label: 'Soil temperature, top layer', units: '°C', obs: ['ts05', 'ts10'], prod: ['tsoil1'] },
  { key: 'swe', label: 'Snow water equivalent', units: 'mm', obs: ['swe'], prod: ['swe'] },
  { key: 'snowd', label: 'Snow depth', units: 'm', obs: ['snowd'], prod: ['snowd'] },
  { key: 'ps', label: 'Surface pressure', units: 'Pa', obs: ['ps'], prod: ['ps'] },
]
const OBS_NETWORKS = ['USCRN', 'SURFRAD', 'NEON', 'AMERIFLUX', 'SCAN', 'SNOTEL', 'ISUSM']

let SITES = [], PRODMETA = {}, SUMMARY = [], SCALES = {}
const state = { site: null, daily: null, varKey: 'tair', agg: 'daily', hidden: new Set(), hourly: null, hourlyYear: null }

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
const tierOn = new Set([1, 2, 3])
function initMap() {
  map = L.map('map', { preferCanvas: true }).setView([39, -98], 4)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 12, attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map)
  const f = document.getElementById('tier-filters')
  for (const [k, [label, v]] of Object.entries(TIERS)) {
    const b = document.createElement('button')
    b.className = 'chip on'
    b.innerHTML = `<span class="dot" style="background:${css(v)}"></span>${label}`
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
      radius: s.tier === 1 ? 6 : 5, color: css('--surface-1'), weight: 2, fillColor: css(TIERS[s.tier][1]), fillOpacity: 1,
    }).addTo(map)
    m.bindTooltip(`<b>${s.name}</b><br>${s.network}${s.state ? ' · ' + s.state : ''}`)
    m.on('click', () => selectSite(s))
    markers.push(m)
  }
}

// ---- site panel -------------------------------------------------------------------------
async function selectSite(s) {
  state.site = s
  state.hourly = null
  state.hourlyYear = null
  const panel = document.getElementById('panel')
  panel.innerHTML = `<h2>${s.name}</h2><p class="secondary">${s.site_id} · ${s.network}${s.state ? ' · ' + s.state : ''} ·
    ${s.lat.toFixed(3)}, ${s.lon.toFixed(3)}${s.elev_m != null ? ' · ' + Math.round(s.elev_m) + ' m' : ''}</p>
    ${s.independence ? `<p class="note">${s.independence}</p>` : ''}
    ${s.d_station_km != null ? `<p class="note">Station-remote point (${s.stratum}); nearest station ${s.d_station_km} km. No observations: products are compared with each other.</p>` : ''}
    <p class="muted">Loading…</p>`
  const rows = await readParquet(`${DATA}/site/${s.id}/daily.parquet`)
  state.daily = toColumns(rows, 'day')
  state.metrics = await (await fetch(`${DATA}/site/${s.id}/metrics.json`)).json().catch(() => [])
  renderPanel()
}

function sourcesFor(v, cols) {
  // returns [{src, col, isObs}] for the variable group, first matching column per source
  const out = []
  const bySrc = {}
  for (const c of Object.keys(cols)) { const [src, name] = c.split('|'); (bySrc[src] ||= []).push(name) }
  for (const [src, names] of Object.entries(bySrc)) {
    const isObs = OBS_NETWORKS.includes(src)
    const want = isObs ? v.obs : v.prod
    const hit = want.find((w) => names.includes(w))
    if (hit) out.push({ src, col: `${src}|${hit}`, isObs })
  }
  out.sort((a, b) => (b.isObs - a.isObs) || PRODUCTS.indexOf(a.src) - PRODUCTS.indexOf(b.src))
  return out
}

function aggregate(t, series, how, sum) {
  if (how === 'daily') return { t: Array.from(t, (d) => d * 86400), series }
  // monthly mean (or sum for precip), requiring >= 90 % of days
  const key = (d) => { const dt = new Date(d * 86400e3); return dt.getUTCFullYear() * 12 + dt.getUTCMonth() }
  const keys = []; const idx = new Map()
  for (let i = 0; i < t.length; i++) { const k = key(t[i]); if (!idx.has(k)) { idx.set(k, keys.length); keys.push(k) } }
  const days = keys.map((k) => new Date(Date.UTC(Math.floor(k / 12), (k % 12) + 1, 0)).getUTCDate())
  const out = series.map((s) => {
    const acc = new Float64Array(keys.length), n = new Int32Array(keys.length)
    for (let i = 0; i < t.length; i++) { const v = s[i]; if (v != null) { const j = idx.get(key(t[i])); acc[j] += v; n[j]++ } }
    return keys.map((_, j) => (n[j] >= 0.9 * days[j] ? (sum ? acc[j] : acc[j] / n[j]) : null))
  })
  return { t: keys.map((k) => Date.UTC(Math.floor(k / 12), k % 12, 15) / 1000), series: out }
}

let plot = null
function renderPanel() {
  const s = state.site, panel = document.getElementById('panel')
  const cols = state.daily.cols
  const avail = VARS.filter((v) => sourcesFor(v, cols).length)
  if (!avail.find((v) => v.key === state.varKey)) state.varKey = avail[0]?.key
  const v = VARS.find((x) => x.key === state.varKey)
  const srcs = sourcesFor(v, cols)
  panel.innerHTML = `<h2>${s.name}</h2><p class="secondary">${s.site_id} · ${s.network}${s.state ? ' · ' + s.state : ''} ·
      ${s.lat.toFixed(3)}, ${s.lon.toFixed(3)}${s.elev_m != null ? ' · ' + Math.round(s.elev_m) + ' m' : ''}</p>
    ${s.independence ? `<p class="note">${s.independence}</p>` : ''}
    ${s.d_station_km != null ? `<p class="note">Station-remote point (${s.stratum}); nearest station ${s.d_station_km} km. No observations here, so products are compared with each other.</p>` : ''}
    <div class="row">
      <select id="var">${avail.map((x) => `<option value="${x.key}" ${x.key === v.key ? 'selected' : ''}>${x.label}</option>`).join('')}</select>
      <select id="agg">${['daily', 'monthly'].map((a) => `<option ${a === state.agg ? 'selected' : ''}>${a}</option>`).join('')}</select>
      ${s.hourly_years?.length ? `<span class="secondary">Hourly:</span>${s.hourly_years.map((y) => `<button class="btn" data-year="${y}">${y}</button>`).join('')}` : ''}
    </div>
    <div class="legend" id="legend"></div>
    <div class="chart" id="chart"></div>
    <p class="note">Daily values: observations and hourly products are aggregated to UTC days; daily products keep their own day
      definitions (PRISM ends 12 UTC, gridMET 07 UTC, Daymet local midnight), which the metrics below account for. Spatial values are
      bilinear from the 4 surrounding pixels. The daily chart opens on the last three years: drag to zoom, double-click for the full record.</p>
    <div id="hourly"></div>
    <h3>Skill for this variable</h3>
    <div id="metrics"></div>`
  panel.querySelector('#var').onchange = (e) => { state.varKey = e.target.value; renderPanel() }
  panel.querySelector('#agg').onchange = (e) => { state.agg = e.target.value; renderPanel() }
  panel.querySelectorAll('[data-year]').forEach((b) => (b.onclick = () => loadHourly(+b.dataset.year)))
  drawLegend(srcs)
  drawDaily(v, srcs)
  drawMetrics(v, srcs)
  if (state.hourly) drawHourly(v)
}

function drawLegend(srcs) {
  const el = document.getElementById('legend')
  el.innerHTML = ''
  for (const { src, isObs } of srcs) {
    const st = isObs ? { color: css('--obs'), dash: null } : productStyle(src)
    const b = document.createElement('button')
    b.className = 'chip' + (state.hidden.has(src) ? ' off' : '')
    b.innerHTML = `<span class="swatch ${st.dash ? 'dashed' : ''}" style="border-color:${st.color}"></span>${isObs ? src + ' (obs)' : (PRODMETA[src]?.title || src)}`
    b.title = isObs ? 'Station observations' : (PRODMETA[src]?.source || '')
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
          return s.show && val != null ? `<div><span class="swatch" style="border-color:${s._color}"></span>${s.label}: <span class="v">${val.toFixed(2)} ${units}</span></div>` : ''
        }).join('')
        tt.innerHTML = `<div class="secondary">${d.toISOString().slice(0, u._hourly ? 16 : 10).replace('T', ' ')} UTC</div>${rows}`
        tt.style.display = rows ? 'block' : 'none'
        const left = Math.min(u.cursor.left + 12, u.over.clientWidth - tt.offsetWidth - 4)
        tt.style.left = left + 'px'; tt.style.top = Math.max(0, u.cursor.top - tt.offsetHeight - 8) + 'px'
      },
    },
  }
}

function makePlot(el, t, series, srcs, units, hourly, initialDays = null) {
  // draw observations last so they sit on top of the product lines
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
    series: [{}, ...srcs.map(({ src, isObs }) => {
      const st = isObs ? { color: css('--obs'), dash: null } : productStyle(src)
      return { label: isObs ? `${src} (obs)` : (PRODMETA[src]?.title || src), stroke: st.color, dash: st.dash || undefined,
        width: isObs ? 2 : 1.5, show: !state.hidden.has(src), spanGaps: false, _color: st.color, points: { show: false } }
    })],
    plugins: [tooltipPlugin(units)],
  }
  const tt = Array.from(t)
  const u = new uPlot(opts, [tt, ...series], el)
  u._hourly = hourly
  if (initialDays && tt.length) u.setScale('x', { min: tt[tt.length - 1] - initialDays * 86400, max: tt[tt.length - 1] })
  return u
}

function drawDaily(v, srcs) {
  const el = document.getElementById('chart')
  const { t, cols } = state.daily
  const a = aggregate(t, srcs.map(({ col }) => cols[col]), state.agg, v.sum)
  if (plot) plot.destroy()
  plot = makePlot(el, a.t, a.series, srcs, v.units + (v.sum ? (state.agg === 'daily' ? ' / day' : ' / month') : ''), false,
    state.agg === 'daily' ? 3 * 365 : null)
}

async function loadHourly(year) {
  const s = state.site
  const rows = await readParquet(`${DATA}/site/${s.id}/hourly/${year}.parquet`)
  state.hourly = toColumns(rows, 'hour')
  state.hourlyYear = year
  renderPanel()
}

let hplot = null
function drawHourly(v) {
  const el = document.getElementById('hourly')
  const { t, cols } = state.hourly
  const srcs = sourcesFor(v, cols)
  if (!srcs.length) { el.innerHTML = `<p class="muted">No hourly series for this variable in ${state.hourlyYear}.</p>`; return }
  el.innerHTML = `<h3>Hourly, ${state.hourlyYear} (UTC, end of hour)</h3><div class="chart" id="hchart"></div>`
  if (hplot) hplot.destroy()
  hplot = makePlot(el.querySelector('#hchart'), Array.from(t, (h) => h * 3600), srcs.map(({ col }) => cols[col]), srcs,
    v.units + (v.sum ? ' / h' : ''), true)
}

function fmt(x, d = 2) { return x == null || Number.isNaN(x) ? '' : Number(x).toFixed(d) }
function drawMetrics(v, srcs) {
  const el = document.getElementById('metrics')
  const m = (state.metrics || []).filter((r) => v.obs.includes(r.obs_var) && r.method === 'bilinear' && r.window === 'full'
    && !String(r.var).endsWith('_adj'))
  if (!m.length) {
    // station-remote point (or no matching obs): spread among products over the shared days
    const { cols } = state.daily
    const prods = srcs.filter((x) => !x.isObs)
    const n = state.daily.t.length
    const common = []
    for (let i = 0; i < n; i++) if (prods.every(({ col }) => cols[col][i] != null)) common.push(i)
    if (!prods.length || common.length < 30) { el.innerHTML = '<p class="muted">No station metrics for this variable here.</p>'; return }
    const means = prods.map(({ col }) => common.reduce((a, i) => a + cols[col][i], 0) / common.length)
    const sorted = [...means].sort((a, b) => a - b)
    const med = sorted[Math.floor(sorted.length / 2)]
    el.innerHTML = `<p class="note">No observations: mean over the ${common.length} days all ${prods.length} products share, and difference from their median.</p>
      <table><tr><th>Product</th><th>Mean (${v.units})</th><th>− median</th></tr>
      ${prods.map((p, k) => `<tr><td>${PRODMETA[p.src]?.title || p.src}</td><td>${fmt(means[k])}</td><td>${fmt(means[k] - med)}</td></tr>`).join('')}</table>`
    return
  }
  const scales = ['hourly', 'daily', 'monthly']
  const kind = m[0].kind
  const heads = kind === 'precip' ? ['n', 'bias', 'rmse', 'r', 'ratio', 'csi_1.0'] : (kind === 'anom' ? ['n', 'r', 'anom_r'] : ['n', 'bias', 'rmse', 'r', 'kge', ...(kind === 'sm' ? ['anom_r'] : [])])
  const rows = m.sort((a, b) => scales.indexOf(a.scale) - scales.indexOf(b.scale) || PRODUCTS.indexOf(a.product) - PRODUCTS.indexOf(b.product))
  el.innerHTML = `<p class="note">Full overlap period, bilinear. Bias = product − station. ${kind === 'precip' ? 'ratio = product total / station total; CSI at 1 mm/day.' : ''}</p>
    <table><tr><th>Product</th><th>Product var</th><th>Station var</th><th>Scale</th>${heads.map((h) => `<th>${h}</th>`).join('')}</tr>
    ${rows.map((r) => `<tr><td>${PRODMETA[r.product]?.title || r.product}</td><td>${r.var}</td><td>${r.obs_var}</td><td>${r.scale}</td>${heads.map((h) => `<td>${h === 'n' ? r.n : fmt(r[h])}</td>`).join('')}</tr>`).join('')}</table>`
}

// ---- summary view -----------------------------------------------------------------------
const sum = { network: 'USCRN', scale: 'daily', window: 'common', method: 'bilinear', metric: 'r' }
function heatColor(val, metric, colMax) {
  if (val == null) return 'transparent'
  const mix = (a, b, t) => `color-mix(in oklab, ${a} ${Math.round((1 - t) * 100)}%, ${b})`
  if (metric === 'bias') {
    const t = Math.max(-1, Math.min(1, val / (colMax || 1)))
    return t < 0 ? mix(css('--div-mid'), css('--div-neg'), -t) : mix(css('--div-mid'), css('--div-pos'), t)
  }
  if (metric === 'r' || metric === 'kge' || metric === 'anom_r') {
    const t = Math.max(0, Math.min(1, (val - 0.5) / 0.5))
    return mix(css('--div-mid'), css('--s1'), t)
  }
  const t = Math.max(0, Math.min(1, val / (colMax || 1)))
  return mix(css('--div-mid'), css('--s2'), t)
}
function renderSummary() {
  const el = document.getElementById('view-summary')
  const opts = (k, vals) => `<select data-k="${k}">${vals.map((v) => `<option ${v === sum[k] ? 'selected' : ''}>${v}</option>`).join('')}</select>`
  const nets = [...new Set(SUMMARY.map((r) => r.network))]
  const rows = SUMMARY.filter((r) => r.network === sum.network && r.scale === sum.scale && r.window === sum.window && r.method === sum.method
    && !String(r.var).endsWith('_adj') && r[sum.metric] != null)
  const cols = [...new Set(rows.map((r) => r.obs_var))]
  const prods = PRODUCTS.filter((p) => rows.some((r) => r.product === p))
  const cell = {}
  for (const r of rows) { const k = `${r.product}|${r.obs_var}`; if (!cell[k] || r.n_sites > cell[k].n_sites) cell[k] = r }
  const colMax = Object.fromEntries(cols.map((c) => [c, Math.max(...rows.filter((r) => r.obs_var === c).map((r) => Math.abs(r[sum.metric])))]))
  el.innerHTML = `<h2>Median skill across sites</h2>
    <div class="row">${opts('network', nets)} ${opts('scale', ['hourly', 'daily', 'monthly'])} ${opts('window', ['full', 'common', 'recent'])}
      ${opts('method', ['bilinear', 'nearest'])} ${opts('metric', ['r', 'bias', 'rmse', 'kge', 'anom_r', 'ratio'])}</div>
    <p class="note">Each cell: median over sites of the per-site ${sum.metric} for that product and station variable (n sites in the tooltip).
      Windows: full = each product's whole overlap; common = 2018-09-01..2025-08-31 (all products except GEOS-FP, IMERG Late, half-hourly IMERG Final);
      recent = 2025-11..2026-10 (includes GEOS-FP). Bias = product − station. Color is a reading aid; values are printed.</p>
    <table class="heat"><tr><th>Product</th>${cols.map((c) => `<th>${c}</th>`).join('')}</tr>
    ${prods.map((p) => `<tr><td>${PRODMETA[p]?.title || p}</td>${cols.map((c) => {
      const r = cell[`${p}|${c}`]
      const val = r ? r[sum.metric] : null
      return `<td class="cell" style="background:${heatColor(val, sum.metric, colMax[c])}" title="${r ? r.n_sites + ' sites; product var ' + r.var : ''}">${fmt(val)}</td>`
    }).join('')}</tr>`).join('')}</table>`
  el.querySelectorAll('select').forEach((s) => (s.onchange = (e) => { sum[e.target.dataset.k] = e.target.value; renderSummary() }))
}

function renderAbout() {
  const el = document.getElementById('view-about')
  el.innerHTML = `<div class="about"><h2>Products and access paths</h2>
    <table><tr><th>Product</th><th>Step</th><th>Source</th></tr>
    ${PRODUCTS.filter((p) => PRODMETA[p]).map((p) => `<tr><td>${PRODMETA[p].title}</td><td>${PRODMETA[p].freq}</td><td style="text-align:left;white-space:normal">${PRODMETA[p].source}<br><span class="muted">${PRODMETA[p].notes}</span></td></tr>`).join('')}
    </table><p class="note">See the experiment README for methods, caveats and how to reproduce.</p></div>`
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
  window.__cpc = { selectSite, SITES }  // used by the headless smoke test
})

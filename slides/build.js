// Builds the results deck from the CSVs in <project>/results.
// Usage: node build.js <project dir> <skill dir>
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const PROJECT = process.argv[2];
const SKILL = process.argv[3];
const { applyTheme } = require(path.join(SKILL, "scripts/apply_theme.js"));
const RES = path.join(PROJECT, "results");
const OUT = path.join(PROJECT, "ERA5_Alps_results.pptx");

function csv(name) {
  const [head, ...rows] = fs.readFileSync(path.join(RES, name), "utf8").trim().split("\n");
  const cols = head.split(",");
  return rows.map((r) => {
    const cells = r.match(/("([^"]|"")*"|[^,]*)(,|$)/g).map((c) => c.replace(/,$/, "").replace(/^"|"$/g, ""));
    return Object.fromEntries(cols.map((c, i) => [c, cells[i]]));
  });
}
const num = (v, d = 2) => Number(v).toFixed(d);
const era5 = (rows) => rows.filter((r) => r.product === "ERA5");

const overall = era5(csv("metrics_overall.csv"));
const byRegimeAll = csv("metrics_by_regime.csv");
const byRegime = era5(byRegimeAll);
const land = byRegimeAll.filter((r) => r.product === "ERA5-Land" && r.version === "corrected");
const bySeason = era5(csv("metrics_by_regime_season.csv"));
const lapse = era5(csv("empirical_lapse_rates.csv"));
const stations = era5(csv("metrics_per_station.csv")).filter((r) => r.version === "raw");

const pick = (rows, where) => rows.find((r) => Object.entries(where).every(([k, v]) => r[k] === v));
const coastalN = stations.filter((r) => r.regime === "Coastal").length;
const REGIMES = ["Lowland", "Coastal", "Valley / foothill", "Mountain"];
const SEASONS = ["DJF", "MAM", "JJA", "SON"];
const oRaw = pick(overall, { version: "raw" });
const oCor = pick(overall, { version: "corrected" });
const mRaw = pick(byRegime, { regime: "Mountain", version: "raw" });
const mCor = pick(byRegime, { regime: "Mountain", version: "corrected" });
const lapseAll = pick(lapse, { season: "All year" });
const nStations = stations.length;
const nCells = new Set(stations.map((s) => s.cell)).size;
const nDays = Number(oRaw.n).toLocaleString("en-US");
const FUNNEL = { withData: 699, synop: 322, nearExchanged: 381, independent: 301 }; // printed by run.py

const THEME = {
  name: "Alpine Reanalysis",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14263A", lt1: "FFFFFF", dk2: "4A5B6C", lt2: "EEF2F6",
    accent1: "2A78D6", accent2: "EB6834", accent3: "1BAF7A", accent4: "9EC5F4",
    accent5: "F6B99F", accent6: "7A8794", hlink: "2A78D6", folHlink: "6250D6",
  },
};
const T = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "How accurate are ERA5 temperatures in the Alps?";
const C = pres.SchemeColor;
const FOOT = "ERA5 vs. ECA&D stations in the Alps, 2005–2024";

pres.defineSlideMaster({
  title: "Dark title",
  background: { color: T.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.5, w: 8.8, h: 1.6, fontSize: 38, bold: true, color: C.background1, valign: "top", margin: 0 }, text: "Title" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.3, w: 8.8, h: 1.9, fontSize: 16, color: C.accent4, valign: "top", margin: 0 }, text: "Subtitle" } },
  ],
});
pres.defineSlideMaster({
  title: "Content",
  background: { color: T.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9.0, h: 0.95, fontSize: 26, bold: true, color: C.text1, valign: "top", margin: 0 }, text: "Title" } },
    { text: { text: FOOT.replace("&", "&amp;"), options: { x: 0.5, y: 5.2, w: 7, h: 0.25, fontSize: 10, color: C.accent6, margin: 0 } } },
  ],
  slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontSize: 10, color: T.accent6, align: "right" },
});

let section = "";
const startSection = (title) => { section = title; pres.addSection({ title }); };
const content = (title, notes) => {
  const s = pres.addSlide({ masterName: "Content", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  return s;
};
const text = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, valign: "top", fontSize: 14, color: C.text1, ...o });
const card = (s, x, y, w, h, name, fill = C.background2) =>
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, objectName: name });
const stat = (s, x, y, w, value, label, color = C.accent1) => {
  card(s, x, y, w, 1.75, `Stat card ${label}`);
  text(s, value, { x: x + 0.2, y: y + 0.18, w: w - 0.4, h: 0.75, fontSize: 24, bold: true, color, fontFace: THEME.headFontFace, objectName: `Stat ${label}` });
  text(s, label, { x: x + 0.2, y: y + 0.98, w: w - 0.4, h: 0.65, fontSize: 13, color: C.text2 });
};
const bullets = (s, items, o) =>
  text(s, items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 8 } })), o);
const chartStyle = (title) => ({
  showTitle: true, title, titleFontSize: 12, titleColor: T.dk2, titleFontFace: "+mn-lt",
  catAxisLabelColor: T.dk2, valAxisLabelColor: T.dk2, catAxisLabelFontSize: 11, valAxisLabelFontSize: 11,
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  valGridLine: { color: "DDE3E9", size: 0.75 }, catGridLine: { style: "none" },
  dataLabelColor: T.dk1, dataLabelFontSize: 10, dataLabelFontFace: "+mn-lt",
  legendFontSize: 11, legendColor: T.dk2, legendFontFace: "+mn-lt",
});

// ---------------------------------------------------------------- Summary
startSection("Summary");
{
  const s = pres.addSlide({ masterName: "Dark title", sectionTitle: section });
  s.addText("How accurate are ERA5 temperatures in the Alps?", { placeholder: "title" });
  s.addText(`ERA5 reanalysis against ${nStations} ECA&D ground stations, daily mean 2 m temperature, 2005–2024`, { placeholder: "body" });
}
{
  const s = content("ERA5 is accurate once elevation is accounted for",
    "Headline numbers pooled over all station-days. Raw = the grid-cell value as delivered. Corrected = shifted to the station height with a fixed -6.5 degC per km lapse rate.");
  stat(s, 0.5, 1.45, 2.85, `${num(oRaw.RMSE, 1)} → ${num(oCor.RMSE, 1)} °C`, "RMSE over all stations, raw then elevation-corrected");
  stat(s, 3.575, 1.45, 2.85, `${num(mRaw.RMSE, 1)} → ${num(mCor.RMSE, 1)} °C`, "RMSE at mountain stations (800 m and above)", C.accent2);
  stat(s, 6.65, 1.45, 2.85, `r = ${num(oCor.r)}`, "Correlation with station daily means after correction", C.accent3);
  bullets(s, [
    "Most of the raw error is a height mismatch between the smoothed model terrain and the real station, not a weather error.",
    "What remains is concentrated in winter at mountain stations, where a fixed lapse rate fails.",
    "Every station used is one whose data ERA5 cannot have assimilated.",
  ], { x: 0.5, y: 3.45, w: 9.0, h: 1.6 });
}

// ---------------------------------------------------------------- Method
startSection("Method");
{
  const s = content("One grid cell is not one valley",
    "ERA5 has about 31 km grid spacing. In the Alps a single cell contains peaks and valley floors, so the model surface height can differ from a station by more than a kilometre.");
  const maxDz = stations.reduce((a, b) => (Math.abs(b.dz_m) > Math.abs(a.dz_m) ? b : a));
  stat(s, 0.5, 1.45, 2.85, "~31 km", "ERA5 grid spacing; one cell holds both peaks and valleys");
  stat(s, 0.5, 3.3, 2.85, `${Math.abs(Math.round(maxDz.dz_m)).toLocaleString("en-US")} m`, "Largest model-to-station height gap in the sample", C.accent2);
  text(s, "The question", { x: 3.75, y: 1.45, w: 5.75, h: 0.35, fontSize: 16, bold: true });
  text(s, "How close is ERA5 daily mean 2 m temperature to what stations measure in complex terrain, and how much of the gap does a simple elevation correction close?",
    { x: 3.75, y: 1.85, w: 5.75, h: 1.0, color: C.text2 });
  text(s, "What is compared", { x: 3.75, y: 3.0, w: 5.75, h: 0.35, fontSize: 16, bold: true });
  bullets(s, [
    "ERA5: hourly model product, averaged to daily means (00–24 UTC)",
    "ECA&D: daily mean temperature measured at one point",
    "Domain: 43.5–48.5°N, 5–16.5°E, including forelands and coasts",
  ], { x: 3.75, y: 3.4, w: 5.75, h: 1.6, fontSize: 13, color: C.text2 });
}
{
  const s = content("Four steps from raw data to error metrics",
    "Same four steps as the project plan. Regimes: lowland below 300 m inland, coastal below 300 m within 25 km of the sea, valley or foothill 300 to 800 m, mountain 800 m and above.");
  const steps = [
    ["1", "Get stations", "ECA&D daily mean temperature and true altitude. Independent stations only, up to 20 per regime."],
    ["2", "Get ERA5", "2 m temperature and model surface height for the grid cell containing each station."],
    ["3", "Match", "Same grid cell, same calendar day. One value per station-day."],
    ["4", "Correct and check", "Shift ERA5 to station height at −6.5 °C/km, then compute MBE, RMSE and Pearson r."],
  ];
  steps.forEach(([n, head, body], i) => {
    const x = 0.5 + i * 2.3;
    card(s, x, 1.45, 2.1, 2.8, `Step ${n} card`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: 1.65, w: 0.5, h: 0.5, fill: { color: C.accent1 }, line: { type: "none" }, objectName: `Step ${n} badge` });
    text(s, n, { x: x + 0.2, y: 1.65, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, head, { x: x + 0.2, y: 2.3, w: 1.7, h: 0.35, fontSize: 15, bold: true });
    text(s, body, { x: x + 0.2, y: 2.7, w: 1.7, h: 1.45, fontSize: 12, color: C.text2 });
  });
  text(s, `Result: ${nStations} stations, ${nDays} matched station-days, ${nCells} ERA5 grid cells.`,
    { x: 0.5, y: 4.5, w: 9.0, h: 0.4, fontSize: 15, bold: true });
}
{
  const s = content("How the pipeline works",
    "Run with: python run.py. Everything downloaded is cached in data/, so a second run downloads nothing and takes seconds.");
  const rows = [
    ["Stations read remotely", "The ECA&D archive is one 0.9 GB zip. The code reads its index over HTTP range requests and pulls only the station files it needs, about 12 MB."],
    ["ERA5 by grid cell", `Requests are made per unique grid cell, not per station: ${nStations} stations need ${nCells} cells. Raw cell values and model height, no third-party downscaling.`],
    ["Cache and resume", "Every file and cell is cached. A rerun downloads nothing, and a run stopped by an API limit continues where it left off."],
    ["One command", "python run.py writes the metric tables (CSV) and figures to results/. Domain, period, sample size and lapse rate sit in one config file."],
  ];
  rows.forEach(([head, body], i) => {
    const x = 0.5 + (i % 2) * 4.6, y = 1.45 + Math.floor(i / 2) * 1.8;
    card(s, x, y, 4.4, 1.6, `Pipeline card ${i + 1}`);
    text(s, head, { x: x + 0.25, y: y + 0.18, w: 3.9, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
    text(s, body, { x: x + 0.25, y: y + 0.58, w: 3.9, h: 0.95, fontSize: 12, color: C.text2 });
  });
}
{
  const s = content("No measurement is counted twice",
    "ECA&D blended files fill gaps with data from neighbouring stations, so the same measurements can sit under several station IDs. The selection removes those before any statistics are computed.");
  const rows = [
    ["Own-site data only", "ECA&D fills gaps with neighbours' data. Only values measured within 2 km and 50 m height of the station are kept."],
    ["One source, one station", "A source series may feed a single station. Co-located stations are skipped."],
    ["One value per station-day", "Checked after matching. Duplicate dates in a station file are dropped."],
    ["Each ERA5 cell fetched once", "Stations in the same cell share one download and one cached series."],
  ];
  rows.forEach(([head, body], i) => {
    const y = 1.45 + i * 0.9;
    s.addShape(pres.shapes.OVAL, { x: 0.5, y: y + 0.05, w: 0.45, h: 0.45, fill: { color: C.accent3 }, line: { type: "none" }, objectName: `Check badge ${i + 1}` });
    text(s, "✓", { x: 0.5, y: y + 0.05, w: 0.45, h: 0.45, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, head, { x: 1.15, y, w: 2.9, h: 0.6, fontSize: 15, bold: true, valign: "middle" });
    text(s, body, { x: 4.1, y, w: 5.4, h: 0.6, fontSize: 13, color: C.text2, valign: "middle" });
  });
}

{
  const s = content("Every station is one ERA5 never saw",
    "ERA5's 4D-Var does not assimilate 2 m temperature, but its surface analysis uses 2 m temperature from stations exchanged on the WMO network. Stations are excluded if ECA&D lists a SYNOP-derived series for them or if a NOAA ISD station active in the period lies within 5 km. In an earlier mixed sample, exchanged and independent stations scored alike: 1.74 vs 1.72 degC corrected RMSE.");
  stat(s, 0.5, 1.45, 2.85, String(FUNNEL.withData), "Stations in the domain with data reaching both ends of the period", C.accent6);
  stat(s, 3.575, 1.45, 2.85, String(FUNNEL.independent), "Left after removing every station exchanged on the weather network", C.accent1);
  stat(s, 6.65, 1.45, 2.85, String(nStations), "Used: complete records, no duplicates, up to 20 per regime", C.accent3);
  text(s, "The risk", { x: 0.5, y: 3.45, w: 4.3, h: 0.35, fontSize: 15, bold: true });
  text(s, "ERA5's surface analysis ingests 2 m temperature from stations exchanged internationally. Scoring ERA5 against those would be partly circular.",
    { x: 0.5, y: 3.85, w: 4.3, h: 1.2, fontSize: 13, color: C.text2 });
  text(s, "The rule", { x: 5.2, y: 3.45, w: 4.3, h: 0.35, fontSize: 15, bold: true });
  bullets(s, [
    "No SYNOP-derived series for the station in ECA&D",
    "No NOAA ISD station (exchanged SYNOP and airport reports) within 5 km",
  ], { x: 5.2, y: 3.85, w: 4.3, h: 1.2, fontSize: 13, color: C.text2 });
}

// ---------------------------------------------------------------- Results
startSection("Results");
{
  const s = content("Error grows with terrain, and correction removes most of it",
    "RMSE of daily mean temperature by regime. The plan expected about 1.2 degC in lowlands, 1.8 at coasts and 3.5 or more in mountains for raw ERA5.");
  const val = (v) => REGIMES.map((r) => Number(num(pick(byRegime, { regime: r, version: v }).RMSE)));
  s.addChart(pres.charts.BAR, [
    { name: "Raw ERA5", labels: REGIMES, values: val("raw") },
    { name: "Elevation-corrected", labels: REGIMES, values: val("corrected") },
  ], {
    x: 0.5, y: 1.35, w: 5.9, h: 3.7, barDir: "col", barGapWidthPct: 60, chartColors: [T.accent4, T.accent1],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", showLegend: true, legendPos: "b",
    valAxisMinVal: 0, valAxisLabelFormatCode: "0", ...chartStyle("RMSE of daily mean temperature (°C)"), objectName: "RMSE by regime chart",
  });
  text(s, "Against the plan's expectations", { x: 6.7, y: 1.45, w: 2.8, h: 0.35, fontSize: 15, bold: true });
  const exp = { Lowland: "≤ 1.2", Coastal: "~ 1.8", Mountain: "≥ 3.5" };
  bullets(s, Object.entries(exp).map(([r, e]) => `${r}: expected ${e} °C, found ${num(pick(byRegime, { regime: r, version: "raw" }).RMSE, 1)} °C raw`),
    { x: 6.7, y: 1.9, w: 2.8, h: 1.5, fontSize: 13, color: C.text2 });
  text(s, `Valleys and mountains gain the most. Lowlands barely change, and at the ${coastalN} coastal stations the correction does not help.`,
    { x: 6.7, y: 3.55, w: 2.8, h: 1.4, fontSize: 13, color: C.text2 });
}
{
  const s = content("The cold bias along the Alpine arc disappears",
    "Each dot is a station. Blue means ERA5 is colder than the station, red warmer. Left panel raw, right panel after the elevation correction.");
  s.addImage({ path: path.join(RES, "fig1_bias_map.png"), x: 0.5, y: 1.3, w: 9.0, h: 3.16, altText: "Maps of ERA5 mean bias at each station before and after elevation correction" });
  text(s, "Raw ERA5 is too cold at valley stations because the model surface sits above them. After correction the remaining bias is small and has no clear spatial pattern.",
    { x: 0.5, y: 4.55, w: 9.0, h: 0.55, fontSize: 13, color: C.text2 });
}
{
  const s = content("Raw bias is an elevation mismatch",
    "Each point is one station: its mean raw bias against the difference between model height and station height. A straight line through these points is an empirical lapse rate.");
  const pts = stations.map((r) => [Number(r.dz_m), Number(r.MBE)]).sort((a, b) => a[0] - b[0]);
  s.addChart(pres.charts.SCATTER, [
    { name: "Height difference (m)", values: pts.map((p) => p[0]) },
    { name: "Station", values: pts.map((p) => p[1]) },
  ], {
    x: 0.5, y: 1.35, w: 5.9, h: 3.7, lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 7, chartColors: [T.accent1],
    showLegend: false, showCatAxisTitle: true, catAxisTitle: "Model height − station height (m)", catAxisTitleColor: T.dk2, catAxisTitleFontSize: 11,
    showValAxisTitle: true, valAxisTitle: "Raw bias (°C)", valAxisTitleColor: T.dk2, valAxisTitleFontSize: 11,
    ...chartStyle("Mean raw bias per station, ERA5 − station"), objectName: "Bias vs height difference chart",
  });
  stat(s, 6.7, 1.45, 2.8, `${num(lapseAll.lapse_rate_C_per_km, 1).replace("-", "−")} °C/km`, "Fitted to the stations; the standard value is −6.5 °C/km");
  text(s, `Height difference alone explains ${Math.round(100 * lapseAll.r ** 2)}% of the variance in station bias (r = ${num(lapseAll.r).replace("-", "−")}).`,
    { x: 6.7, y: 3.4, w: 2.8, h: 1.5, fontSize: 13, color: C.text2 });
}
{
  const s = content("Winter in the mountains is the hardest case",
    "Left: lapse rate implied by the stations in each season. Right: remaining RMSE at mountain stations after the standard correction. Winter inversions decouple cold valley air from the free atmosphere.");
  const ls = SEASONS.map((x) => Number(num(pick(lapse, { season: x }).lapse_rate_C_per_km, 1)));
  s.addChart(pres.charts.BAR, [{ name: "Fitted lapse rate", labels: SEASONS, values: ls }], {
    x: 0.5, y: 1.35, w: 4.4, h: 2.75, barDir: "col", barGapWidthPct: 70, chartColors: [T.accent1], showLegend: false,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", valAxisMaxVal: 0, valAxisMinVal: -8,
    catAxisLabelPos: "high", ...chartStyle("Fitted lapse rate by season (°C/km)"), objectName: "Lapse rate by season chart",
  });
  const ms = SEASONS.map((x) => Number(num(pick(bySeason, { regime: "Mountain", season: x, version: "corrected" }).RMSE)));
  s.addChart(pres.charts.BAR, [{ name: "Mountain RMSE", labels: SEASONS, values: ms }], {
    x: 5.1, y: 1.35, w: 4.4, h: 2.75, barDir: "col", barGapWidthPct: 70, chartColors: [T.accent2], showLegend: false,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", valAxisMinVal: 0,
    ...chartStyle("Mountain RMSE after correction (°C)"), objectName: "Mountain RMSE by season chart",
  });
  const djf = pick(bySeason, { regime: "Mountain", season: "DJF", version: "corrected" });
  text(s, `The fitted lapse rate is shallower than the assumed −6.5 °C/km in every season. Mountain error after correction peaks in winter, when corrected ERA5 is still ${num(Math.abs(djf.MBE), 1)} °C too cold in December–February.`,
    { x: 0.5, y: 4.25, w: 9.0, h: 0.8, fontSize: 13, color: C.text2 });
}
{
  const s = content("A finer grid did not mean lower error",
    "ERA5-Land has about 9 km grid spacing and is a land-surface rerun driven by ERA5. Both products are scored after the same elevation correction.");
  const have = land.length === REGIMES.length;
  const cor = (rows, r) => Number(num(pick(rows, { regime: r, version: "corrected" }).RMSE));
  const e5 = have ? REGIMES.map((r) => cor(byRegime, r)) : [1.17, 1.66, 1.54, 2.04];
  const el = have ? REGIMES.map((r) => cor(land, r)) : [1.23, 1.30, 1.68, 2.26];
  const label = have ? "2005–2024" : "2018–2020 pilot";
  s.addChart(pres.charts.BAR, [
    { name: "ERA5 (~31 km)", labels: REGIMES, values: e5 },
    { name: "ERA5-Land (~9 km)", labels: REGIMES, values: el },
  ], {
    x: 0.5, y: 1.35, w: 5.9, h: 3.7, barDir: "col", barGapWidthPct: 60, chartColors: [T.accent1, T.accent2],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", showLegend: true, legendPos: "b", valAxisMinVal: 0,
    ...chartStyle(`Elevation-corrected RMSE (°C), ${label}`), objectName: "ERA5 vs ERA5-Land chart",
  });
  text(s, "By regime", { x: 6.7, y: 1.45, w: 2.8, h: 0.35, fontSize: 15, bold: true });
  bullets(s, REGIMES.map((r, k) => `${r}: ${el[k] < e5[k] - 0.05 ? "ERA5-Land better" : el[k] > e5[k] + 0.05 ? "ERA5 better" : "no difference"}`),
    { x: 6.7, y: 1.9, w: 2.8, h: 2.0, fontSize: 13, color: C.text2 });
  text(s, have ? "Same stations and days for both products. ERA5-Land assimilates no observations itself; it is driven by ERA5."
    : "From an earlier 3-year run on 76 stations not screened for independence. The 20-year comparison is not finished.",
    { x: 6.7, y: 4.0, w: 2.8, h: 0.95, fontSize: 12, italic: true, color: C.text2 });
}

// ---------------------------------------------------------------- Conclusion
startSection("Conclusion");
{
  const s = content("What these numbers do not cover",
    "Limits of the study that should be stated alongside the results.");
  const rows = [
    ["Sample, not census", `${nStations} stations, so the pooled figure is not an area-weighted Alpine mean. France dominates, and only ${coastalN} coastal stations qualify.`],
    ["Daily means only", "Station daily means are defined differently by each national service; ERA5 uses 00–24 UTC. Daily extremes were not tested."],
    ["Data route", "ERA5 came through the Open-Meteo archive, not the Copernicus store. Values are rounded to 0.1 °C."],
    ["Independent, not isolated", "The stations' own data were not exchanged, but ERA5 still draws on exchanged stations nearby. The screen uses public station lists."],
  ];
  rows.forEach(([head, body], i) => {
    const x = 0.5 + (i % 2) * 4.6, y = 1.45 + Math.floor(i / 2) * 1.8;
    card(s, x, y, 4.4, 1.6, `Limit card ${i + 1}`);
    text(s, head, { x: x + 0.25, y: y + 0.18, w: 3.9, h: 0.35, fontSize: 15, bold: true });
    text(s, body, { x: x + 0.25, y: y + 0.58, w: 3.9, h: 0.95, fontSize: 12, color: C.text2 });
  });
}
{
  const s = pres.addSlide({ masterName: "Dark title", sectionTitle: section });
  s.addText("ERA5 is reliable in the Alps if you correct for height", { placeholder: "title" });
  s.addText([
    { text: `Raw ERA5 misses station temperature by ${num(oRaw.RMSE, 1)} °C RMSE; a standard lapse-rate correction brings that to ${num(oCor.RMSE, 1)} °C.`, options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "The remaining error is largest in winter at mountain stations. Every station used is independent of ERA5.", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Next: a seasonal or locally fitted lapse rate, daily extremes, and the 20-year ERA5-Land comparison.", options: { bullet: true } },
  ], { placeholder: "body" });
  s.addNotes("Always apply an elevation correction before using ERA5 at a point in complex terrain. Treat winter values at mountain and valley sites with caution.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();

// Download cards: PNGs drawn client-side on a canvas from data the page already shows (a match before kickoff or at
// full time, a day's calls, the race so far), at 1080×1350 portrait and 1200×675 landscape. Nothing is posted.
import { crestPath, pct, pct1, dec, xgBy } from "./core.js";

const SIZES = { portrait: [1080, 1350], landscape: [1200, 675] };
const SITE = "hediblk.github.io/football-predictions";
const TOKENS = ["bg", "bulb-off", "rule", "rule-2", "ink", "ink-2", "dim", "amber", "amber-t", "red", "green", "green-t", "draw", "sign", "mono"];
const builders = {}; // card kind -> () => card, set by the page that shows its chips

/* "Download card" chips, one per size; `what` names the card for screen readers */
export function cardChips(kind, what) {
  return `<div class="card-dl" role="group" aria-label="Download ${what} card"><span class="card-dl-lbl" aria-hidden="true">Download card</span>${
    Object.entries(SIZES).map(([size, [w, h]]) => `<button type="button" class="chip" data-card="${kind}" data-size="${size}"
      aria-label="Download ${what} card, ${size}, ${w} by ${h} PNG">${size === "portrait" ? "Portrait" : "Landscape"}<span>${w}×${h}</span></button>`).join("")}</div>`;
}
export const offerCard = (kind, build) => { builders[kind] = build; };

document.addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-card]");
  if (!b || !builders[b.dataset.card] || b.getAttribute("aria-busy") === "true") return;
  b.setAttribute("aria-busy", "true");
  try {
    const card = builders[b.dataset.card]();
    save(await draw(card, b.dataset.size), `${card.file}-${b.dataset.size}.png`);
  } catch (err) {
    console.error(`Card not drawn: ${err.message}`);
  } finally {
    b.removeAttribute("aria-busy");
  }
});

function save(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

export const fileName = (...parts) => ["floodlight", ...parts].join("-").toLowerCase().normalize("NFD")
  .replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-");

/* ---------- the cards ---------- */
const OUT = (m) => [`${m.home} win`, "Draw", `${m.away} win`];
const kickoffDay = (iso) => new Date(iso).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const kickoffTime = (iso) => `${new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC`;
const pair = (p, d) => `${dec(p[0], d)}–${dec(p[1], d)}`;

/* home, draw and away chances on the chances alone: two independent Poissons with the observed xG as means */
function onChances([a, b]) {
  const pois = (mean) => { const p = [Math.exp(-mean)]; for (let k = 1; k <= 15; k++) p.push(p[k - 1] * mean / k); return p; };
  const [ph, pa] = [pois(a), pois(b)];
  const r = [0, 0, 0];
  ph.forEach((x, i) => pa.forEach((y, j) => { r[i > j ? 0 : i === j ? 1 : 2] += x * y; }));
  const total = r[0] + r[1] + r[2];
  return r.map((x) => x / total);
}

/* the match page's card: the preview before kickoff, or full time after. `o`: { legend, mode, stake (the Stakes
   tag's line), pending, verdict (the match page's line from the exported `miss`, when there is one) } */
export function matchCard(m, o) {
  const labels = OUT(m);
  const crests = [m.home_id, m.away_id];
  if (o.mode !== "after") {
    const fav = m.p.indexOf(Math.max(...m.p));
    const [h, a, p] = m.top[0];
    const when = `${o.pending ? `${o.pending} · was set for ` : ""}${kickoffDay(m.kickoff)} · ${kickoffTime(m.kickoff)}`;
    return {
      file: fileName(m.home, m.away, m.kickoff.slice(0, 10), "preview"), legend: o.legend, crests,
      hero: [text(when, { center: true, caps: true }), teams(m), numeral(labels[fav], [[Math.round(m.p[fav] * 100)], ["%", 0.3, true]])],
      detail: [heading("The forecast"), bulbs(m.p, labels), rows([["Expected goals", pair(m.exp, 1)], ["Most likely score", `${h}–${a} · ${pct1(p)}`]]),
        o.stake ? tag("Stakes", o.stake) : null,
        note(`Forecast from the model run of ${new Date(m.at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })}, ${kickoffTime(m.at)}.`)],
      sources: "Fixtures: football-data.org · xG: Understat · Forecast: Floodlight model",
    };
  }
  const actual = m.score[0] > m.score[1] ? 0 : m.score[0] === m.score[1] ? 1 : 2;
  const hit = m.p.indexOf(Math.max(...m.p)) === actual;
  const ucl = o.legend.startsWith("Champions League");
  return {
    file: fileName(m.home, m.away, m.kickoff.slice(0, 10), "full-time"), legend: o.legend, crests,
    hero: [text(`Full time · ${kickoffDay(m.kickoff)}`, { center: true, caps: true }), teams(m), numeral("Final score", [[`${m.score[0]}–${m.score[1]}`]])],
    detail: [
      heading(`Our forecast · ${m.published ? "published before kickoff" : "reconstructed"}`),
      bulbs(m.p, labels, actual),
      lamp(hit, hit ? "Called" : "Missed", `${labels[actual]} had ${pct1(m.p[actual])}`),
      o.verdict ? text(o.verdict, { color: "ink" }) : null,
      heading("On chances · from xG, not a forecast"),
      m.xg ? bulbs(m.xg_p || onChances(m.xg), labels, -1, true) : note("No xG for this game, so no on-chances line."),
      rows([["Expected goals before kickoff", pair(m.exp, 1)], ...(m.xg ? [[`Shot xG (${xgBy(m)})`, pair(m.xg, 2)]] : [])]),
      note((m.published ? `Published before kickoff, from the model run of ${new Date(m.at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })}, ${kickoffTime(m.at)}.`
        : "Reconstructed: forecast as of 00:00 UTC on match day, from results before then.") + (m.xg ? " On-chances shares treat each side's xG as the mean of a Poisson." : "")),
    ],
    sources: `Results: football-data.org${m.xg ? ` · xG: ${xgBy(m)}` : ""} · Forecast: Floodlight model`,
  };
}

/* "How we did": a day's finished games with a forecast, in kickoff order; `scope` names the competitions shown */
export function roundCard(games, { day, scope }) {
  const rows_ = games.map((m) => {
    const actual = m.score[0] > m.score[1] ? 0 : m.score[0] === m.score[1] ? 1 : 2;
    const hit = m.p.indexOf(Math.max(...m.p)) === actual;
    // a miss is a draw when the favourite drew and an upset otherwise (the model hasn't called a draw this season)
    return { m, actual, given: m.p[actual], kind: hit ? "called" : actual === 1 ? "draw" : "upset" };
  });
  const n = rows_.length, count = (k) => rows_.filter((r) => r.kind === k).length;
  const rated = rows_.filter((r) => r.m.elo);
  const ll = (list, key) => list.reduce((t, r) => t - Math.log(Math.max(1e-12, r.m[key][r.actual])), 0) / list.length;
  const [model, elo] = rated.length ? [ll(rated, "p"), ll(rated, "elo")] : [ll(rows_, "p"), null];
  const best = rows_.reduce((a, b) => (b.given > a.given ? b : a));
  const upsets = rows_.filter((r) => r.kind === "upset");
  const worst = upsets.length ? upsets.reduce((a, b) => (b.given < a.given ? b : a)) : null;
  const published = rows_.filter((r) => r.m.published).length;
  const said = (r) => `${OUT(r.m)[r.actual]} had ${pct1(r.given)}`;
  return {
    file: fileName(day.key, scope, "round"), legend: `How we did · ${scope}`,
    crests: [best, worst].filter(Boolean).flatMap((r) => [r.m.home_id, r.m.away_id]),
    hero: [text(day.label, { center: true, caps: true }), numeral("Called right", [[count("called")], [`/${n}`, 0.45, false, "ink-2"]]), dots(rows_.map((r) => r.kind))],
    detail: [
      heading("Misses"), rows([["Draws · the favourite drew", String(count("draw"))], ["Upsets · the favourite lost", String(count("upset"))]]),
      heading("Log loss · lower is better"),
      rows([["Floodlight", dec(model, 3), elo != null && model <= elo], ...(elo != null ? [["Elo", dec(elo, 3), elo < model]] : []), ["Uniform guess", "1.099"]]),
      game("Best call", best.m, said(best)),
      worst ? game("Biggest upset", worst.m, said(worst)) : text("No upsets: every miss was a draw.", { size: 24, color: "ink-2" }),
      note(`${published} of ${n} forecast${n === 1 ? "" : "s"} published before kickoff, the rest reconstructed from results before match day.${rated.length < n ? ` Elo compared on ${rated.length} of ${n} games.` : ""}`),
    ],
    sources: "Results: football-data.org · Forecasts: Floodlight model and its Elo ratings",
  };
}

/* "The race so far": up to three races of { label, key, red, place, rows: [{ id, name, now, d }], empty }, with changes
   (whole points) since `since` (the Clubs ranking's baseline Monday), or none without one */
export function raceCard({ name, slug, date, runs, since, races }) {
  const [first] = races;
  const lead = first.rows[0];
  return {
    file: fileName(slug, date, "race"), legend: `${name} · The race`,
    crests: races.flatMap((r) => r.rows.map((x) => x.id)),
    hero: [text(`${date} · ${runs}`, { center: true, caps: true }),
      lead ? numeral(`${lead.name} · ${first.label}`, [[Math.round(lead.now)], ["%", 0.3, true]], first.red ? "red" : "amber") : null,
      heading(first.label), race(first, since)],
    detail: [...races.slice(1).flatMap((r) => [heading(r.label), race(r, since)]),
      note(since ? `Arrows give the change since ${since}; under 3 points shows as –. Green is good news for that club, red bad.` : "No frozen Monday to compare with yet, so no changes are shown.")],
    sources: "Results: football-data.org · xG: Understat · Chances: Floodlight model",
  };
}

/* ---------- drawing ---------- */
let ctx, T, S; // the canvas context, the page's colour and font tokens, crest images by club id

async function draw(card, size) {
  const [W, H] = SIZES[size];
  const css = getComputedStyle(document.documentElement);
  T = Object.fromEntries(TOKENS.map((k) => [k, css.getPropertyValue(`--${k}`).trim()]));
  // Ask for the weights the card uses, then wait for every font; with web fonts blocked the fallbacks draw instead.
  await Promise.all(["800", "900"].map((w) => document.fonts.load(`${w} 40px ${T.sign}`))
    .concat(["400", "700"].map((w) => document.fonts.load(`${w} 20px ${T.mono}`)))).catch(() => {});
  await document.fonts.ready;
  S = new Map(await Promise.all([...new Set(card.crests)].map(async (id) => [id, await image(crestPath(id))])));
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  ctx = canvas.getContext("2d");
  const portrait = H > W, s = portrait ? 1 : 0.6, pad = portrait ? 64 : 40;
  const foot = portrait ? 120 : 80;
  ctx.fillStyle = T.bg;
  ctx.fillRect(0, 0, W, H);
  const box = { x: pad, y: pad, w: W - 2 * pad, h: H - 2 * pad - foot };
  frame(box, card.legend, s);
  const inner = { x: box.x + 44 * s, y: box.y + 52 * s, w: box.w - 88 * s, h: box.h - 92 * s };
  if (portrait) column([...card.hero, ...card.detail], inner, s);
  else {
    const gap = 64, w = (inner.w - gap) / 2;
    column(card.hero, { ...inner, w }, s);
    column(card.detail, { ...inner, x: inner.x + w + gap, w }, s);
    line(inner.x + w + gap / 2, inner.y, inner.x + w + gap / 2, inner.y + inner.h, T["rule-2"]);
  }
  footer(pad, box.y + box.h + 30 * s, box.w, card.sources, s);
  return new Promise((ok, fail) => canvas.toBlob((b) => (b ? ok(b) : fail(new Error("empty canvas"))), "image/png"));
}

const image = (src) => new Promise((ok) => {
  if (!src) return ok(null);
  const img = new Image();
  img.onload = () => ok(img);
  img.onerror = () => ok(null);
  img.src = src;
});

/* blocks stacked down a column, centred, with even gaps; shrunk to fit when they don't */
function column(blocks, { x, y, w, h }, s) {
  blocks = blocks.filter(Boolean);
  const gap = 30, need = (k) => blocks.reduce((t, b) => t + b.h(w, k), 0) + gap * k * (blocks.length - 1);
  for (let i = 0; i < 4 && need(s) > h; i++) s *= (h / need(s)) * 0.99;
  const heights = blocks.map((b) => b.h(w, s)), sum = heights.reduce((a, b) => a + b, 0);
  const spread = blocks.length > 1 ? Math.min(gap * s * 2.2, (h - sum) / (blocks.length - 1)) : 0;
  let at = y + Math.max(0, (h - sum - spread * (blocks.length - 1)) / 2);
  blocks.forEach((b, i) => { b.draw(x, at, w, s); at += heights[i] + spread; });
}

/* set the font for `str`, shrinking to 60% and then truncating so it fits `max`; returns the text and its width */
function fit(str, { size, weight = 400, sign = false, track = 0, max = Infinity }) {
  str = String(str);
  const set = (px) => {
    ctx.font = `${weight} ${px}px ${sign ? T.sign : T.mono}`;
    if ("letterSpacing" in ctx) ctx.letterSpacing = `${track * px}px`;
  };
  let px = size;
  set(px);
  while (ctx.measureText(str).width > max && px > size * 0.6) set(px *= 0.96);
  if (ctx.measureText(str).width > max) {
    while (str.length > 1 && ctx.measureText(`${str}…`).width > max) str = str.slice(0, -1);
    str = `${str.trimEnd()}…`;
  }
  return { str, width: ctx.measureText(str).width };
}
function put(str, x, y, o) {
  const f = fit(o.caps ? String(str).toUpperCase() : str, o);
  ctx.fillStyle = T[o.color || "ink"];
  ctx.textAlign = o.align || "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(f.str, x, y);
  return f.width;
}
function line(x1, y1, x2, y2, color, width = 2) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}
function circle(x, y, r, color, glow = 0) {
  ctx.save();
  if (glow) { ctx.shadowColor = color; ctx.shadowBlur = glow; }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}
function crest(id, x, y, size) {
  const img = S.get(id);
  if (!img) return;
  const [w, h] = img.naturalWidth && img.naturalHeight ? [img.naturalWidth, img.naturalHeight] : [1, 1];
  const k = size / Math.max(w, h);
  ctx.drawImage(img, x + (size - w * k) / 2, y + (size - h * k) / 2, w * k, h * k);
}
/* the site's bulb: near-linear brightness against the brightest chance on show, off below 2% of it */
function bulbColor(p, top) {
  const t = Math.min(1, Math.pow(Math.max(0, p) / top, 0.9));
  if (t < 0.02) return T["bulb-off"];
  const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const [a, b] = [rgb(T.amber), rgb(T["bulb-off"])];
  return `rgb(${a.map((v, i) => Math.round(v * t + b[i] * (1 - t))).join(",")})`;
}
function triangle(x, y, size, up, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(x, up ? y : y - size);
  ctx.lineTo(x + size * 1.15, up ? y : y - size);
  ctx.lineTo(x + size * 0.575, up ? y - size : y);
  ctx.fill();
}

/* the frame with its legend cut into the top border, as on the site */
function frame({ x, y, w, h }, legend, s) {
  ctx.strokeStyle = T.rule;
  ctx.lineWidth = 2;
  ctx.strokeRect(x, y, w, h);
  const o = { size: 28 * s, weight: 800, sign: true, track: 0.2, caps: true, color: "ink-2", max: w - 120 * s };
  const { width } = fit(legend.toUpperCase(), o);
  ctx.fillStyle = T.bg;
  ctx.fillRect(x + 26 * s, y - 20 * s, width + 32 * s, 40 * s);
  put(legend, x + 42 * s, y + 10 * s, o);
}

/* the logo's 3×3 bulb grid (five lit) and wordmark, the address, and the sources */
function footer(x, y, w, sources, s) {
  const m = 44 * s, r = (1.6 / 16) * m;
  [[4, 4], [8, 4], [12, 4], [12, 8], [8, 12]].forEach(([cx, cy]) => circle(x + (cx / 16) * m, y + (cy / 16) * m, r, T.amber));
  [[4, 8], [8, 8], [4, 12], [12, 12]].forEach(([cx, cy]) => circle(x + (cx / 16) * m, y + (cy / 16) * m, r, T.rule));
  const mark = put("Floodlight", x + m + 14 * s, y + m * 0.86, { size: 42 * s, weight: 900, sign: true, track: 0.04, caps: true, max: w * 0.4 });
  put(SITE, x + w, y + m * 0.8, { size: 24 * s, weight: 500, color: "amber-t", align: "right", max: w - m - mark - 60 * s });
  put(sources, x, y + m + 44 * s, { size: 20 * s, color: "dim", max: w });
}

/* ---------- blocks: { h(width, scale), draw(x, y, width, scale) } ---------- */
function text(str, { size = 26, color = "ink-2", center = false, caps = false } = {}) {
  return {
    h: (w, s) => size * s * 1.4,
    draw: (x, y, w, s) => put(str, center ? x + w / 2 : x, y + size * s, { size: size * s, color, caps, align: center ? "center" : "left", max: w, track: caps ? 0.06 : 0 }),
  };
}

function note(str, size = 21) {
  const lines = (w, s) => {
    ctx.font = `400 ${size * s}px ${T.mono}`;
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    return str.split(" ").reduce((out, word) => {
      const last = out[out.length - 1];
      if (last && ctx.measureText(`${last} ${word}`).width <= w) out[out.length - 1] = `${last} ${word}`;
      else out.push(word);
      return out;
    }, []);
  };
  return {
    h: (w, s) => lines(w, s).length * size * s * 1.5,
    draw: (x, y, w, s) => lines(w, s).forEach((l, i) => put(l, x, y + size * s * (1.1 + 1.5 * i), { size: size * s, color: "dim", max: w })),
  };
}

function heading(str) {
  return {
    h: (w, s) => 46 * s,
    draw(x, y, w, s) {
      const width = put(str, x, y + 30 * s, { size: 26 * s, weight: 800, sign: true, track: 0.2, caps: true, color: "ink-2", max: w - 40 * s });
      line(x + width + 14 * s, y + 21 * s, x + w, y + 21 * s, T.rule);
    },
  };
}

function teams(m) {
  const C = 150;
  return {
    h: (w, s) => (C + 76) * s,
    draw(x, y, w, s) {
      const half = (w - 70 * s) / 2;
      [[m.home_id, m.home, x + half / 2], [m.away_id, m.away, x + w - half / 2]].forEach(([id, name, cx]) => {
        crest(id, cx - (C / 2) * s, y, C * s);
        put(name, cx, y + (C + 66) * s, { size: 56 * s, weight: 900, sign: true, caps: true, align: "center", max: half });
      });
      put("v", x + w / 2, y + (C / 2 + 14) * s, { size: 40 * s, weight: 800, sign: true, caps: true, color: "dim", align: "center" });
    },
  };
}

/* the poster numeral: `parts` are [text, scale, raised, colour], centred, under a tracked label */
function numeral(label, parts, color = "amber") {
  const N = 250;
  return {
    h: (w, s) => (60 + N * 0.86) * s,
    draw(x, y, w, s) {
      put(label, x + w / 2, y + 30 * s, { size: 30 * s, weight: 800, sign: true, track: 0.2, caps: true, color: "ink-2", align: "center", max: w });
      const widths = (px) => parts.map(([t, k = 1]) => fit(t, { size: px * k, weight: 900, sign: true }).width);
      let px = N * s;
      const total = widths(px).reduce((a, b) => a + b, 0);
      if (total > w) px *= w / total;
      const ws = widths(px);
      let at = x + (w - ws.reduce((a, b) => a + b, 0)) / 2;
      const base = y + (60 + N * 0.78) * s;
      parts.forEach(([t, k = 1, raised = false, c = color], i) => {
        put(t, at, raised ? base - px * 0.5 : base, { size: px * k, weight: 900, sign: true, color: c });
        at += ws[i];
      });
    },
  };
}

/* three outcome bulbs with their chances; a ruled box marks what happened; `plain` drops the bulbs */
function bulbs(p, labels, actual = -1, plain = false) {
  return {
    h: (w, s) => (plain ? 110 : 150) * s,
    draw(x, y, w, s) {
      const top = Math.max(...p), cw = w / 3;
      p.forEach((v, i) => {
        const cx = x + cw * i + cw / 2;
        if (i === actual) { ctx.strokeStyle = T["ink-2"]; ctx.lineWidth = 2; ctx.strokeRect(x + cw * i + 6 * s, y, cw - 12 * s, 150 * s); }
        if (!plain) circle(cx, y + 38 * s, 22 * s, bulbColor(v, top));
        put(pct1(v), cx, y + (plain ? 56 : 100) * s, { size: 44 * s, weight: 700, color: v === top && !plain ? "ink" : "ink-2", align: "center", max: cw - 20 * s });
        put(labels[i], cx, y + (plain ? 94 : 134) * s, { size: 22 * s, weight: 800, sign: true, track: 0.12, caps: true, color: "dim", align: "center", max: cw - 24 * s });
      });
    },
  };
}

/* a ruled board of [label, value, lit] rows */
function rows(list) {
  return {
    h: (w, s) => list.length * 58 * s,
    draw(x, y, w, s) {
      list.forEach(([label, value, lit], i) => {
        const ry = y + i * 58 * s;
        put(label, x, ry + 38 * s, { size: 24 * s, color: "ink-2", max: w * 0.64 });
        put(value, x + w, ry + 38 * s, { size: 28 * s, weight: 700, color: lit ? "amber" : "ink", align: "right", max: w * 0.34 });
        line(x, ry + 57 * s, x + w, ry + 57 * s, T["rule-2"]);
      });
    },
  };
}

/* the Stakes tag: the ruled word, then the race it swings */
function tag(word, detail) {
  return {
    h: (w, s) => 56 * s,
    draw(x, y, w, s) {
      const o = { size: 24 * s, weight: 800, sign: true, track: 0.14, caps: true, color: "ink-2" };
      const { width } = fit(word.toUpperCase(), o);
      ctx.strokeStyle = T.rule;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y + 6 * s, width + 24 * s, 42 * s);
      put(word, x + 12 * s, y + 36 * s, o);
      put(detail, x + width + 44 * s, y + 36 * s, { size: 24 * s, color: "ink-2", max: w - width - 44 * s });
    },
  };
}

/* a called or missed result: the lamp and its word, never colour alone */
function lamp(hit, word, detail) {
  return {
    h: (w, s) => 54 * s,
    draw(x, y, w, s) {
      circle(x + 10 * s, y + 26 * s, 10 * s, hit ? T.green : T.red, 14 * s);
      const width = put(word, x + 34 * s, y + 38 * s, { size: 34 * s, weight: 800, sign: true, track: 0.14, caps: true, color: hit ? "green-t" : "red" });
      put(detail, x + 34 * s + width + 22 * s, y + 37 * s, { size: 24 * s, color: "ink-2", max: w - width - 60 * s });
    },
  };
}

/* one bulb per game in kickoff order, green for a call, grey for a draw, red for an upset, with a worded key */
const KINDS = [["called", "Called", "green"], ["draw", "Draw", "draw"], ["upset", "Upset", "red"]];
function dots(kinds) {
  const step = 46, per = (w, s) => Math.max(1, Math.floor(w / (step * s)));
  const lines = (w, s) => Math.ceil(kinds.length / per(w, s));
  return {
    h: (w, s) => (lines(w, s) * step + 48) * s,
    draw(x, y, w, s) {
      const n = per(w, s), across = Math.min(n, kinds.length) * step * s;
      kinds.forEach((k, i) => {
        const color = T[KINDS.find(([key]) => key === k)[2]];
        circle(x + (w - across) / 2 + (i % n + 0.5) * step * s, y + (Math.floor(i / n) + 0.5) * step * s, 15 * s, color, 10 * s);
      });
      const key = KINDS.map(([k, word]) => [word, kinds.filter((x) => x === k).length, k]);
      const ky = y + (lines(w, s) * step + 36) * s;
      const o = { size: 22 * s, weight: 800, sign: true, track: 0.14, caps: true, color: "ink-2" };
      const widths = key.map(([word, c]) => fit(`${word} ${c}`.toUpperCase(), o).width + 26 * s);
      let at = x + (w - widths.reduce((a, b) => a + b, 0) - 30 * s * (key.length - 1)) / 2;
      key.forEach(([word, c, k], i) => {
        circle(at + 8 * s, ky - 8 * s, 8 * s, T[KINDS.find(([kk]) => kk === k)[2]]);
        put(`${word} ${c}`, at + 24 * s, ky, o);
        at += widths[i] + 30 * s;
      });
    },
  };
}

/* one game: a small label, crests either side of "Home 3–0 Away", and what the model gave the result */
function game(label, m, detail) {
  return {
    h: (w, s) => 136 * s,
    draw(x, y, w, s) {
      put(label, x, y + 24 * s, { size: 24 * s, weight: 800, sign: true, track: 0.2, caps: true, color: "dim", max: w });
      const c = 40 * s;
      crest(m.home_id, x, y + 38 * s, c);
      const width = put(`${m.home} ${m.score[0]}–${m.score[1]} ${m.away}`, x + c + 14 * s, y + 72 * s, { size: 38 * s, weight: 800, sign: true, caps: true, max: w - 2 * c - 40 * s });
      crest(m.away_id, x + c + 26 * s + width, y + 38 * s, c);
      put(detail, x, y + 118 * s, { size: 24 * s, color: "ink-2", max: w });
    },
  };
}

/* a race's contenders: crest, name, chance (the title or drop favourite lit) and the change since the baseline Monday */
function race(r, since) {
  const H = 56;
  return {
    h: (w, s) => Math.max(1, r.rows.length) * H * s,
    draw(x, y, w, s) {
      if (!r.rows.length) { put(r.empty, x, y + 36 * s, { size: 24 * s, color: "dim", max: w }); return; }
      r.rows.forEach((t, i) => {
        const ry = y + i * H * s;
        crest(t.id, x, ry + 8 * s, 38 * s);
        put(t.name, x + 54 * s, ry + 40 * s, { size: 34 * s, weight: 800, sign: true, caps: true, max: w - 54 * s - 250 * s });
        put(pct(t.now), x + w - 130 * s, ry + 40 * s, { size: 30 * s, weight: 700, align: "right", color: i || r.place ? "ink" : r.red ? "red" : "amber" });
        if (since && t.d != null && Math.abs(t.d) >= 3) {
          const good = (t.d > 0) !== r.red;
          const color = good ? "green-t" : "red";
          triangle(x + w - 108 * s, ry + 36 * s, 16 * s, t.d > 0, T[color]);
          put(`${t.d > 0 ? "+" : "−"}${Math.abs(t.d)}`, x + w, ry + 39 * s, { size: 26 * s, weight: 700, align: "right", color });
        } else if (since) put("–", x + w, ry + 39 * s, { size: 26 * s, align: "right", color: "dim" });
        line(x, ry + (H - 1) * s, x + w, ry + (H - 1) * s, T["rule-2"]);
      });
    },
  };
}

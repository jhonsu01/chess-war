// chess-war viewer: live (?live, polls /live.json) or replay (?m=<id>, reads data/). ?lang=xx picks the language.
"use strict";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const SQ = 64;          // square size in canvas pixels
const FRAME = 32;       // frame around the board
const LIGHT = "#e3c393", LIGHT2 = "#d8b683", DARK = "#a0694b", DARK2 = "#93603f";

const params = new URLSearchParams(location.search);
const LIVE = params.has("live");
const $ = (id) => document.getElementById(id);
const canvas = $("board");
const ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;

let rep = null;      // match record (replay.json or live.json)
let gi = 0;          // visible game
let pi = 0;          // plies shown (0 = initial position)
let playing = false;
let timer = null;
let anim = null;
let liveSig = "";
let idx = null;

// ------------------------------------------------------------------ language
function pickLang() {
  const q = params.get("lang");
  if (q && I18N[q]) return q;
  try {
    const s = localStorage.getItem("chesswar-lang");
    if (s && I18N[s]) return s;
  } catch { /* storage unavailable */ }
  return "en"; // English is always the default
}
let LANG = pickLang();

function T(key, vars) {
  let v = I18N[LANG]?.[key] ?? I18N.en[key] ?? key;
  if (typeof v === "string" && vars) v = v.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
  return v;
}
const opening = (name) => {
  const i = OPENING_KEYS.indexOf(name);
  return i >= 0 ? T("openings")[i] : name;
};
const locale = () => LANG_LOCALE[LANG] || "en";
const reason = (r) => {
  const i = REASON_KEYS.indexOf(r);
  return i >= 0 ? (REASONS[LANG] ?? REASON_KEYS)[i] : r;
};

function applyStatic() {
  document.documentElement.lang = locale();
  document.title = T("title");
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = T(el.dataset.i18n); });
  // data-i18n-html only ever receives strings from our own dictionary (i18n.js)
  document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = T(el.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = T(el.dataset.i18nTitle); });
}

function setLang(code) {
  LANG = code;
  try { localStorage.setItem("chesswar-lang", code); } catch { /* ignore */ }
  const u = new URL(location.href);
  u.searchParams.set("lang", code);
  history.replaceState(null, "", u);
  applyStatic();
  renderMatches();
  if (rep) { applyTitles(); fillGameSelect(); render(false); } else { $("game-head").textContent = LIVE ? T("waiting") : ""; }
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const game = () => rep?.games?.[gi];
const plies = () => game()?.plies ?? [];
const meta = (name) => rep?.players?.[name] ?? { label: (name || "?").toUpperCase(), colour: "#ccc", detail: "" };

// ------------------------------------------------------------------ board
function parseFen(fen) {
  return fen.split(" ")[0].split("/").map((r) => {
    const out = [];
    for (const ch of r) {
      if (/\d/.test(ch)) for (let i = 0; i < +ch; i++) out.push(null);
      else out.push(ch);
    }
    return out;
  });
}

function sqXY(name) {
  return [FRAME + (name.charCodeAt(0) - 97) * SQ, FRAME + (8 - Number(name[1])) * SQ];
}

function drawFrame() {
  ctx.fillStyle = "#2a1a24";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#3d2635";
  ctx.fillRect(8, 8, canvas.width - 16, canvas.height - 16);
  ctx.fillStyle = "#170e15";
  ctx.fillRect(FRAME - 4, FRAME - 4, 8 * SQ + 8, 8 * SQ + 8);
  ctx.fillStyle = "#c9a878";
  ctx.font = "10px 'Press Start 2P', monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let i = 0; i < 8; i++) {
    ctx.fillText("abcdefgh"[i], FRAME + i * SQ + SQ / 2, canvas.height - FRAME / 2 + 1);
    ctx.fillText(String(8 - i), FRAME / 2, FRAME + i * SQ + SQ / 2 + 1);
  }
}

function drawSquares(highlight) {
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const light = (r + f) % 2 === 0;
      const x = FRAME + f * SQ, y = FRAME + r * SQ;
      ctx.fillStyle = light ? LIGHT : DARK;
      ctx.fillRect(x, y, SQ, SQ);
      // pixel texture: a fixed 4 px dot pattern
      ctx.fillStyle = light ? LIGHT2 : DARK2;
      for (let u = 0; u < 16; u++) for (let v = 0; v < 16; v++) {
        if ((u * 5 + v * 3 + r * 7 + f * 11) % 13 === 0) ctx.fillRect(x + u * 4, y + v * 4, 4, 4);
      }
    }
  }
  for (const [name, colour, alpha] of highlight) {
    const [x, y] = sqXY(name);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = colour;
    ctx.fillRect(x, y, SQ, SQ);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 4;
    ctx.strokeRect(x + 2, y + 2, SQ - 4, SQ - 4);
  }
}

const drawPiece = (ch, x, y) => ctx.drawImage(pieceSprite(ch), x, y, SQ, SQ);

function drawPosition(fen, skip) {
  parseFen(fen).forEach((row, r) => row.forEach((ch, f) => {
    if (!ch || "abcdefgh"[f] + (8 - r) === skip) return;
    drawPiece(ch, FRAME + f * SQ, FRAME + r * SQ);
  }));
}

function kingInCheck(fen, san) {
  if (!san || !/[+#]$/.test(san)) return null;
  const king = fen.split(" ")[1] === "w" ? "K" : "k";
  const grid = parseFen(fen);
  for (let r = 0; r < 8; r++) for (let f = 0; f < 8; f++) if (grid[r][f] === king) return "abcdefgh"[f] + (8 - r);
  return null;
}

const fenAt = (i) => (i <= 0 ? START_FEN : plies()[i - 1].fen);

function highlights(i) {
  if (i <= 0) return [];
  const p = plies()[i - 1];
  const colour = p.by === "book" ? "#ffffff" : meta(p.by).colour;
  const out = [[p.uci.slice(0, 2), colour, 0.28], [p.uci.slice(2, 4), colour, 0.42]];
  const chk = kingInCheck(p.fen, p.san);
  if (chk) out.push([chk, "#ff2244", 0.55]);
  return out;
}

function render(animate = false) {
  cancelAnimationFrame(anim);
  const i = pi;
  if (animate && i > 0) {
    const p = plies()[i - 1];
    const from = p.uci.slice(0, 2), to = p.uci.slice(2, 4);
    const before = fenAt(i - 1);
    const [fx, fy] = sqXY(from), [tx, ty] = sqXY(to);
    const ch = parseFen(before)[8 - Number(from[1])][from.charCodeAt(0) - 97];
    const t0 = performance.now(), dur = 170;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur);
      drawFrame();
      drawSquares(highlights(i - 1));
      drawPosition(before, from);
      if (ch) drawPiece(ch, Math.round(fx + (tx - fx) * k), Math.round(fy + (ty - fy) * k));
      if (k < 1) anim = requestAnimationFrame(step);
      else render(false);
    };
    anim = requestAnimationFrame(step);
    updateSide();
    return;
  }
  drawFrame();
  drawSquares(highlights(i));
  drawPosition(fenAt(i));
  updateSide();
}

// ------------------------------------------------------------------ panels
const fmtClock = (ms) => {
  if (ms == null) return "--:--";
  const s = Math.max(0, ms) / 1000;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};
const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
const num = (x, u = "") => (x == null ? "—" : `${Math.round(x).toLocaleString(locale())}${u}`);

function lastBy(name) {
  for (let i = pi - 1; i >= 0; i--) if (plies()[i].by === name) return plies()[i];
  return null;
}

function clocks() {
  for (let i = pi - 1; i >= 0; i--) if (plies()[i].clock) return plies()[i].clock;
  const c = rep?.config?.clock_s;
  return c ? [c * 1000, c * 1000] : null;
}

function panelHTML(name) {
  const m = meta(name), g = game();
  const s = rep.summary?.[name] ?? {};
  const color = g ? (g.white === name ? "w" : "b") : "w";
  const icon = pieceSprite(color === "w" ? "K" : "k").toDataURL();
  const cl = clocks();
  const ms = cl ? cl[color === "w" ? 0 : 1] : null;
  const p = lastBy(name);
  let think = `<p class="muted">${esc(T("waiting_first"))}</p>`;
  if (p) {
    const top = (p.top || []).map(([san, prob]) =>
      `<div class="kv"><span>${esc(san)}</span><b>${pct(prob)}</b></div><div class="bar"><i style="width:${Math.round(prob * 100)}%"></i></div>`).join("");
    think = `
      <div class="kv"><span>${esc(T("move"))}</span><b>${esc(p.san)}${p.forced ? " " + esc(T("forced")) : ""}</b></div>
      <div class="kv"><span>${esc(T("latency"))}</span><b>${num(p.ms, " ms")}</b></div>
      <div class="kv"><span>${esc(T("plan"))}</span><b>${esc(T("plans")[p.plan] ?? p.plan ?? "—")}</b></div>
      <div class="kv"><span>${esc(T("danger"))}</span><b>${pct(p.danger)}</b></div>
      <div class="bar"><i style="width:${Math.round((p.danger ?? 0) * 100)}%;background:var(--bad)"></i></div>
      ${top ? `<h3>${esc(T("top"))}</h3>${top}` : ""}
      ${p.ovr ? `<div class="shield">${esc(T("shield_box"))}: <s>${esc(p.raw)}</s> → ${esc(p.san)}<br>${esc(reason(p.ovr))}</div>` : ""}
      ${p.fb ? `<div class="shield">${esc(T("fallback"))}</div>` : ""}`;
  }
  return `
    <div class="ph" style="color:${esc(m.colour)}"><img src="${icon}" alt=""><span class="name">${esc(m.label)}</span></div>
    <div class="detail">${esc(m.detail)}</div>
    <div class="clock${ms != null && ms < 20000 ? " low" : ""}">${fmtClock(ms)}</div>
    <div class="think" style="color:${esc(m.colour)}"><h3>${esc(T("thinking"))}</h3><div style="color:var(--ink)">${think}</div></div>
    <div class="stats"><h3>${esc(T("match"))}</h3><div class="grid">
      <div><span>${esc(T("points"))}</span><b>${esc(s.points ?? 0)}</b></div>
      <div><span>${esc(T("p50"))}</span><b>${num(s.latency_ms_p50, " ms")}</b></div>
      <div><span>${esc(T("shield"))}</span><b>${esc(s.overridden_pct ?? 0)}%</b></div>
      <div><span>${esc(T("acpl_raw"))}</span><b>${num(s.acpl_raw)}</b></div>
      <div><span>${esc(T("decisions"))}</span><b>${esc(s.decisions ?? 0)}</b></div>
      <div><span>${esc(T("cost"))}</span><b>$${(s.cost_usd ?? 0).toFixed(4)}</b></div>
    </div></div>`;
}

function updateSide() {
  if (!rep) return;
  const g = game();
  for (const [slot, name] of [["panel-p1", rep.p1], ["panel-p2", rep.p2]]) {
    const el = $(slot);
    el.innerHTML = panelHTML(name);
    const toMove = g ? (fenAt(pi).split(" ")[1] === "w" ? g.white : g.black) : null;
    el.classList.toggle("turn", LIVE && toMove === name && g?.result === "*");
    el.style.color = meta(name).colour;
  }
  if (g) {
    $("game-head").textContent = T("game_head", {
      n: g.n, total: rep.config?.games ?? rep.games.length, opening: opening(g.opening).toUpperCase(),
      white: meta(g.white).label, black: meta(g.black).label,
    });
    const done = g.result && g.result !== "*" && pi === plies().length;
    const banner = $("banner");
    banner.hidden = !done;
    if (done) {
      const winner = g.result === "1-0" ? g.white : g.result === "0-1" ? g.black : null;
      banner.innerHTML = `${esc(g.result)}<br>${esc((T("term")[g.termination] ?? g.termination ?? "").toUpperCase())}<br>` +
        (winner ? `<span style="color:${esc(meta(winner).colour)}">${esc(T("wins", { name: meta(winner).label }))}</span>` : esc(T("draw")));
    }
  }
  renderMoves();
  renderSummary();
  $("b-play").textContent = playing ? "❚❚" : "▶";
}

function renderMoves() {
  const ps = plies();
  let html = "";
  for (let i = 0; i < ps.length; i += 2) {
    const cell = (j) => {
      const p = ps[j];
      if (!p) return "<span></span>";
      const cls = ["m", p.by === "book" ? "book" : "", p.ovr ? "ovr" : "", j === pi - 1 ? "cur" : ""].join(" ");
      return `<span class="${cls}" data-i="${j + 1}" title="${esc(p.by)}">${esc(p.san)}</span>`;
    };
    html += `<li><span class="n">${i / 2 + 1}.</span>${cell(i)}${cell(i + 1)}</li>`;
  }
  const ol = $("moves");
  ol.innerHTML = html;
  // scroll the list only, never the page
  const cur = ol.querySelector(".cur");
  if (cur && (cur.offsetTop < ol.scrollTop || cur.offsetTop > ol.scrollTop + ol.clientHeight - 24)) {
    ol.scrollTop = cur.offsetTop - ol.clientHeight / 2;
  }
}

function renderSummary() {
  const a = rep.p1, b = rep.p2, sa = rep.summary?.[a] ?? {}, sb = rep.summary?.[b] ?? {};
  const L = T("rows");
  const rows = [
    [L[0], "points", (x) => esc(x ?? 0), "max"],
    [L[1], null, null],
    [L[2], "latency_ms_mean", (x) => num(x, " ms"), "min"],
    [L[3], "latency_ms_p95", (x) => num(x, " ms"), "min"],
    [L[4], "overridden_pct", (x) => `${esc(x ?? 0)}%`, "min"],
    [L[5], "acpl_raw", (x) => num(x), "min"],
    [L[6], "acpl", (x) => num(x), "min"],
    [L[7], "blunders_raw", (x) => esc(x ?? "—"), "min"],
    [L[8], "time_used_s", (x) => (x == null ? "—" : `${esc(x)} s`), "min"],
    [L[9], "input_tokens", (x) => (x ?? 0).toLocaleString(locale()), null],
    [L[10], "cost_usd", (x) => `$${(x ?? 0).toFixed(5)}`, "min"],
    [L[11], "served_by", (x) => esc(x || "—"), null],
  ];
  let html = `<tr><th></th><th style="color:${esc(meta(a).colour)}">${esc(meta(a).label)}</th><th style="color:${esc(meta(b).colour)}">${esc(meta(b).label)}</th></tr>`;
  for (const [label, key, fmt, better] of rows) {
    if (!key) {
      html += `<tr><td>${esc(label)}</td><td>${esc(`${sa.wins ?? 0} / ${sa.draws ?? 0} / ${sa.losses ?? 0}`)}</td><td>${esc(`${sb.wins ?? 0} / ${sb.draws ?? 0} / ${sb.losses ?? 0}`)}</td></tr>`;
      continue;
    }
    const va = sa[key], vb = sb[key];
    let wa = "", wb = "";
    if (better && typeof va === "number" && typeof vb === "number" && va !== vb) {
      const aWins = better === "max" ? va > vb : va < vb;
      wa = aWins ? "win" : "";
      wb = aWins ? "" : "win";
    }
    html += `<tr><td>${esc(label)}</td><td class="${wa}">${fmt(va)}</td><td class="${wb}">${fmt(vb)}</td></tr>`;
  }
  $("summary").innerHTML = html;
  $("games").innerHTML = (rep.games || []).map((g, k) =>
    `<span class="chip${k === gi ? " cur" : ""}" data-g="${k}">${esc(g.n)} · ${esc(opening(g.opening))} · ${esc(meta(g.white).label)}–${esc(meta(g.black).label)} ${esc(g.result)}</span>`).join("");
}

// ------------------------------------------------------------------ controls
function setPly(i, animate = false) {
  const prev = pi;
  pi = Math.max(0, Math.min(plies().length, i));
  render(animate && pi === prev + 1);
}

function setGame(k) {
  if (!rep || k < 0 || k >= rep.games.length) return;
  gi = k;
  $("s-game").value = String(k);
  setPly(0);
}

function tick() {
  if (!playing) return;
  if (pi < plies().length) {
    setPly(pi + 1, true);
    timer = setTimeout(tick, Number($("s-speed").value));
  } else if (gi < rep.games.length - 1) {
    timer = setTimeout(() => { setGame(gi + 1); timer = setTimeout(tick, 900); }, 2600);
  } else {
    playing = false;
    updateSide();
  }
}

function play(on = !playing) {
  playing = on;
  clearTimeout(timer);
  if (playing) tick();
  updateSide();
}

function fillGameSelect() {
  $("s-game").innerHTML = (rep.games || []).map((g, k) =>
    `<option value="${k}">${esc(T("game_opt", { n: g.n, opening: opening(g.opening) }))}</option>`).join("");
  $("s-game").value = String(gi);
}

function applyTitles() {
  for (const [id, name] of [["t-p1", rep.p1], ["t-p2", rep.p2]]) {
    $(id).textContent = meta(name).label;
    $(id).style.color = meta(name).colour;
  }
  const d = rep.date ? new Date(rep.date).toLocaleString(locale()) : "";
  $("subtitle").textContent = `${T(LIVE ? "sub_live" : "sub_replay")} · ${d} · ${rep.engine ? T("engine", { engine: rep.engine }) : T("no_engine")}`;
}

// ------------------------------------------------------------------ data
async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

async function pollLive() {
  try {
    const data = await getJSON("live.json");
    if (data.status === "waiting") return;
    const g = data.games?.[data.games.length - 1];
    const sig = `${data.status}|${data.games?.length}|${g?.plies?.length}|${g?.result}`;
    if (sig === liveSig) return;
    const follow = !rep || (gi === rep.games.length - 1 && pi === plies().length);
    const firstLoad = !rep;
    liveSig = sig;
    rep = data;
    if (firstLoad) applyTitles();
    fillGameSelect();
    $("live-badge").hidden = data.status !== "playing";
    if (follow) {
      gi = rep.games.length - 1;
      $("s-game").value = String(gi);
      setPly(plies().length, true);
    } else {
      updateSide();
    }
  } catch {
    $("game-head").textContent = T("offline");
  }
}

function renderMatches() {
  const box = $("matches");
  const list = idx?.matches ?? [];
  if (!list.length) {
    box.innerHTML = `<p class="muted">${T("no_matches")}</p>`;
    return;
  }
  box.innerHTML = list.map((m) => {
    const a = m.players[m.p1], b = m.players[m.p2];
    const sa = m.summary[m.p1], sb = m.summary[m.p2];
    return `<a class="match" href="?m=${encodeURIComponent(m.id)}&lang=${LANG}">
      <div class="muted">${esc(new Date(m.date).toLocaleString(locale()))} · ${esc(T("n_games", { n: m.games }))}${m.status !== "finished" ? " · " + esc(m.status) : ""}</div>
      <div class="sc"><span style="color:${esc(a.colour)}">${esc(a.label)} ${esc(sa.points)}</span> – <span style="color:${esc(b.colour)}">${esc(sb.points)} ${esc(b.label)}</span></div>
      <div class="muted">p50 ${num(sa.latency_ms_p50, " ms")} / ${num(sb.latency_ms_p50, " ms")} · ${esc(T("shield"))} ${esc(sa.overridden_pct)}% / ${esc(sb.overridden_pct)}%</div>
    </a>`;
  }).join("");
}

function empty(msg) {
  drawFrame();
  drawSquares([]);
  drawPosition(START_FEN);
  $("game-head").textContent = msg;
}

async function init() {
  const sel = $("s-lang");
  sel.innerHTML = Object.entries(LANG_NAMES).map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join("");
  sel.value = LANG;
  sel.onchange = (e) => setLang(e.target.value);
  applyStatic();

  document.addEventListener("click", (e) => {
    const m = e.target.closest("[data-i]");
    if (m) { play(false); setPly(Number(m.dataset.i)); }
    const c = e.target.closest("[data-g]");
    if (c) { play(false); setGame(Number(c.dataset.g)); }
  });
  $("b-first").onclick = () => { play(false); setPly(0); };
  $("b-prev").onclick = () => { play(false); setPly(pi - 1); };
  $("b-next").onclick = () => { play(false); setPly(pi + 1, true); };
  $("b-last").onclick = () => { play(false); setPly(plies().length); };
  $("b-play").onclick = () => play();
  $("s-game").onchange = (e) => { play(false); setGame(Number(e.target.value)); };
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT") return;
    if (e.key === "ArrowRight") { play(false); setPly(pi + 1, true); }
    else if (e.key === "ArrowLeft") { play(false); setPly(pi - 1); }
    else if (e.key === " ") { e.preventDefault(); play(); }
    else if (e.key === "Home") { play(false); setPly(0); }
    else if (e.key === "End") { play(false); setPly(plies().length); }
  });

  // pixel favicon: the white knight
  const link = document.createElement("link");
  link.rel = "icon";
  link.href = pieceSprite("N").toDataURL();
  document.head.appendChild(link);

  if (document.fonts) await document.fonts.ready.catch(() => {});
  empty(LIVE ? T("waiting") : T("loading"));

  try { idx = await getJSON("data/index.json"); } catch { /* nothing published yet */ }
  renderMatches();

  if (LIVE) {
    $("s-speed").hidden = true;
    pollLive();
    setInterval(pollLive, 350);
    return;
  }
  const id = params.get("m") || idx?.matches?.[0]?.id;
  if (!id) { empty(T("no_games")); return; }
  try {
    rep = await getJSON(`data/${encodeURIComponent(id)}.json`);
  } catch {
    empty(T("not_found"));
    return;
  }
  applyTitles();
  fillGameSelect();
  setGame(0);
  play(true);
}

init();

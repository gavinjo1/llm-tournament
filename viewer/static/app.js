"use strict";

// ------------------------------------------------------------------ helpers

const $ = (id) => document.getElementById(id);
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
// Everything an LLM wrote goes through esc(): messages are untrusted text.
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
const SVG_NS = "http://www.w3.org/2000/svg";

const playerSlot = (p) => p.charCodeAt(p.length - 1) - 64; // "Player C" -> 3
// 8 validated hues; players beyond the 8th share a neutral grey and are told
// apart by their letter labels (never a generated 9th hue)
const color = (p) => (playerSlot(p) <= 8 ? `var(--p${playerSlot(p)})` : "var(--text-muted)");
const short = (p) => p.replace("Player ", "");
const dot = (p) => `<span class="dot" style="background:${color(p)}"></span>`;
const who = (p) => `<span class="who">${dot(p)}${esc(p)}</span>`;
const pieces = (n) => `${n} Piece${n === 1 ? "" : "s"}`;
const byPlayer = (map, fmt = (v) => esc(v)) =>
  Object.entries(map || {}).map(([p, v]) => `${dot(p)}${esc(short(p))} ${fmt(v)}`).join(" &nbsp; ");

// Events that are noise unless "System events" is on.
const SYSTEM = new Set([
  "tournament_start", "seating", "tournament_end", "game_start",
  "conversation_start", "conversation_end", "ante",
]);

// ------------------------------------------------------------------ state

const state = {
  runs: [],
  run: null,
  events: [],
  cursor: 0,        // number of events shown
  view: "god",      // "god" or a player name
  showHidden: true,
  showSystem: false,
  follow: true,
  playing: false,
  source: null,
  timer: null,
  pending: [],
  flushQueued: false,
  openThreads: new Set(),
};

// ------------------------------------------------------------------ loading

async function loadRuns() {
  await refreshRunList();
  const fromHash = new URLSearchParams(location.hash.slice(1)).get("run");
  const pick = state.runs.find((r) => r.name === fromHash) || state.runs[0];
  if (pick) {
    $("run-select").value = pick.name;
    openRun(pick.name);
  }
}

/** Reload the run list (e.g. after a live run ends) without changing the selection. */
async function refreshRunList() {
  state.runs = await fetch("api/runs").then((r) => r.json());
  const select = $("run-select");
  const selected = select.value;
  select.innerHTML = state.runs.length
    ? state.runs.map((r) => {
        const status = r.aborted ? "ABORTED" : r.finished ? `champion ${short(r.winner || "?")}` : "in progress";
        return `<option value="${esc(r.name)}">${esc(r.name)} — ${status}</option>`;
      }).join("")
    : `<option value="">No runs in the runs folder</option>`;
  if (selected) select.value = selected;
}

function openRun(name) {
  if (state.source) state.source.close();
  stopPlaying();
  Object.assign(state, { run: name, events: [], cursor: 0, pending: [], openThreads: new Set() });
  history.replaceState(null, "", `#run=${encodeURIComponent(name)}`);
  const info = state.runs.find((r) => r.name === name);
  setLive(!(info && info.finished));

  const source = new EventSource(`api/runs/${encodeURIComponent(name)}/stream`);
  state.source = source;
  source.onmessage = (msg) => {
    state.pending.push(JSON.parse(msg.data));
    if (!state.flushQueued) {
      state.flushQueued = true;
      requestAnimationFrame(flush);
    }
  };
  source.addEventListener("end", () => {
    source.close();
    setLive(false);
    refreshRunList();
  });
  render();
}

function setLive(live) {
  $("live-badge").hidden = !live;
  const stop = $("btn-stop");
  stop.hidden = !live;
  stop.disabled = false;
  stop.textContent = "■ Stop run";
}

async function stopRun() {
  if (!state.run) return;
  if (!confirm("Stop this run? It will be marked ABORTED and should not be used as data.")) return;
  const button = $("btn-stop");
  button.disabled = true;
  button.textContent = "Stopping…";
  const response = await fetch(`api/runs/${encodeURIComponent(state.run)}/stop`, {
    method: "POST",
    headers: { "X-Viewer": "1" },
  });
  if (!response.ok) {
    button.disabled = false;
    button.textContent = "■ Stop run";
    alert(`Could not stop the run: ${response.status}`);
  }
  // the run ends on its own within one agent reply; the stream then sends "end"
}

function flush() {
  state.flushQueued = false;
  if (!state.pending.length) return;
  const wasAtEnd = state.cursor === state.events.length;
  state.events.push(...state.pending);
  state.pending = [];
  if (state.follow && (wasAtEnd || !state.playing)) state.cursor = state.events.length;
  render();
}

// ------------------------------------------------------------------ derive

/** Fold events [0, n) into the tournament state at that moment. */
function derive(n) {
  const s = {
    players: [], labels: {}, pieces: {}, lives: {}, out: {}, outSeq: {}, champion: null,
    day: null, game: null, subgame: null, round: null, exchange: null,
    history: [], days: [],
  };
  const snapshot = (seq) => s.history.push({ seq, pieces: { ...s.pieces } });
  for (let i = 0; i < n; i++) {
    const e = state.events[i];
    const d = e.data;
    switch (e.type) {
      case "tournament_start":
        s.players = [...d.players];
        Object.assign(s.pieces, d.pieces);
        snapshot(e.seq);
        break;
      case "seating": Object.assign(s.labels, d.agents); break;
      case "day_start":
        Object.assign(s, { day: e.day, game: d.game, subgame: null });
        s.days.push({ seq: e.seq, day: e.day, game: d.game });
        Object.assign(s.pieces, d.pieces);
        break;
      case "game_start": if (d.game !== s.game) s.subgame = d.game; break;
      case "prison_start": s.subgame = `Prison: ${d.game}`; break;
      case "transfer":
        s.pieces[e.actor] -= d.pieces;
        s.pieces[d.to] += d.pieces;
        snapshot(e.seq);
        break;
      case "pieces_change": s.pieces[e.actor] = d.pieces; snapshot(e.seq); break;
      case "placement": Object.assign(s.pieces, d.pieces); snapshot(e.seq); break;
      case "elimination": s.out[d.player] = e.day; s.outSeq[d.player] = e.seq; break;
      case "life_bought":
        s.lives[e.actor] = 1;
        s.pieces[e.actor] = d.pieces;
        snapshot(e.seq);
        break;
      case "life_used": s.lives[d.player] = 0; break;
      case "champion": s.champion = d.player; break;
    }
    s.round = e.round;
    s.exchange = e.exchange;
  }
  return s;
}

function visible(e) {
  if (SYSTEM.has(e.type) && !state.showSystem) return false;
  if (state.view === "god") return e.visible_to !== "god" || state.showHidden;
  return e.visible_to === "all" || (Array.isArray(e.visible_to) && e.visible_to.includes(state.view));
}

// ------------------------------------------------------------------ render

function render() {
  const s = derive(state.cursor);
  renderControls(s);
  renderViewSelect(s);
  renderPlayers(s);
  renderTimeline(s);
  renderThreads();
  renderGraph(s);
  renderChart(s);
}

function renderControls(s) {
  const slider = $("slider");
  slider.max = state.events.length;
  slider.value = state.cursor;
  $("position").textContent = `${state.cursor} / ${state.events.length}`;
  $("btn-play").textContent = state.playing ? "❚❚" : "▶";
  $("btn-play").setAttribute("aria-label", state.playing ? "Pause" : "Play");
  const parts = [];
  if (s.champion) parts.push(`Champion: ${s.champion}`);
  else if (s.day) {
    parts.push(`Day ${s.day} · ${s.game}`);
    if (s.subgame) parts.push(s.subgame);
    if (s.round != null) parts.push(`Round ${s.round}`);
    if (s.exchange != null) parts.push(`Conversation, exchange ${s.exchange}`);
  } else parts.push(state.run ? "Waiting for events…" : "No run loaded");
  $("status").textContent = parts.join(" · ");
}

function renderViewSelect(s) {
  const select = $("view-select");
  const wanted = ["god", ...s.players].join("|");
  if (select.dataset.options !== wanted) {
    select.dataset.options = wanted;
    select.innerHTML = `<option value="god">Researcher (everything)</option>` +
      s.players.map((p) => `<option value="${esc(p)}">${esc(p)}'s view</option>`).join("");
    if (state.view !== "god" && !s.players.includes(state.view)) state.view = "god";
  }
  select.value = state.view;
  $("show-hidden").disabled = state.view !== "god";
}

function renderPlayers(s) {
  $("players").innerHTML = s.players.map((p) => {
    const out = p in s.out;
    const status = s.champion === p ? "🏆 Champion"
      : out ? `Eliminated on day ${s.out[p]}` : "In the game";
    const cls = ["player", out ? "out" : "", s.champion === p ? "champion" : ""].join(" ");
    return `<div class="${cls}">
      ${dot(p)}<span class="name">${esc(p)}${s.lives[p] && !out ? ' <span title="Holds a life">❤</span>' : ""}${state.view === p ? " (viewing)" : ""}</span>
      <span class="pieces" title="Pieces">${out ? "–" : esc(s.pieces[p])}</span>
      <span class="label">${esc(s.labels[p] || "")}</span>
      <span class="state">${status}</span>
    </div>`;
  }).join("") || `<p class="empty">No players yet.</p>`;
}

function renderTimeline() {
  const parts = [];
  let lastShown = null;
  let game = null;      // current game, or the final's current sub-game
  let section = null;   // "game|round" of the last round header
  for (let i = 0; i < state.cursor; i++) {
    const e = state.events[i];
    if (e.type === "day_start") {
      parts.push(`<div class="day-header">Day ${e.day} — ${esc(e.data.game)}</div>`);
      game = e.data.game;
      section = null;
    } else if (e.type === "game_start") {
      game = e.data.game;
    } else if (e.type === "prison_start") {
      parts.push(`<div class="day-header prison-header">🔒 Prison match — ${esc(e.data.game)}: ${esc(e.data.players.join(", "))}</div>`);
      game = e.data.game;
      section = null;
    }
    if (!visible(e)) continue;
    if (e.round != null && `${game}|${e.round}` !== section) {
      section = `${game}|${e.round}`;
      parts.push(`<div class="round-header">${esc(game)} · Round ${e.round}</div>`);
    } else if (e.round == null) {
      section = null;
    }
    let html;
    try {
      html = renderEvent(e);
    } catch (err) {
      html = ev("warn", `could not display ${esc(e.type)}: ${esc(err.message)}`);
    }
    if (html) {
      parts.push(html.replace("<div class=\"ev", `<div data-seq="${e.seq}" class="ev`));
      lastShown = e.seq;
    }
  }
  const timeline = $("timeline");
  timeline.innerHTML = parts.join("") || `<p class="empty">Nothing yet. Press play or move the slider.</p>`;
  const current = timeline.querySelector(`[data-seq="${lastShown}"]`);
  if (current) {
    current.classList.add("current");
    // scroll only the timeline box, never the page
    const top = current.offsetTop - timeline.offsetTop;
    if (top < timeline.scrollTop || top + current.offsetHeight > timeline.scrollTop + timeline.clientHeight) {
      timeline.scrollTop = top - timeline.clientHeight + current.offsetHeight + 8;
    }
  }
}

function ev(cls, body) {
  return `<div class="ev ${cls}">${body}</div>`;
}
const hiddenEv = (label, body) => ev("hidden", `<span class="kind">${esc(label)}</span> ${body}`);
const exTag = (e) => (e.exchange ? `<span class="tag">exchange ${e.exchange}</span>` : "");

function renderEvent(e) {
  const d = e.data;
  const a = e.actor;
  switch (e.type) {
    // conversation
    case "public_message":
      return ev("msg", `${who(a)}<span class="tag">to everyone</span>${exTag(e)}<div>${esc(d.text)}</div>`);
    case "private_message":
      return ev("private", `🔒 ${who(a)} → ${who(d.to)}${exTag(e)}<div>${esc(d.text)}</div>`);
    case "transfer":
      return ev("game", `💰 ${who(a)} gave ${who(d.to)} <b>${pieces(d.pieces)}</b>` +
        (d.last_will ? `<span class="tag">Last Will</span>` : exTag(e)));
    case "reasoning":
      return hiddenEv("thinks", `${who(a)} <span class="reasoning">${esc(d.text)}</span>`);
    case "diary": {
      const notes = Object.entries(d.players || {}).map(([p, note]) => `<div>${who(p)}: ${esc(note)}</div>`).join("");
      if (!d.summary && !notes) return null;
      return ev("private", `🔒 📓 ${who(a)}'s diary<div>${esc(d.summary || "")}</div>${notes}`);
    }
    case "action": {
      // drop unset optional fields, e.g. {"quantity": null, "doubt": false}
      const move = Object.fromEntries(Object.entries(d.action).filter(([, v]) => v !== null && v !== false));
      return hiddenEv("sealed move", `${who(a)} <span class="mono">${esc(JSON.stringify(move))}</span>`);
    }
    case "invalid_output":
      return ev("warn", `⚠ ${who(a)} invalid ${esc(d.kind)} reply (attempt ${d.attempt}): ${esc(d.error)}` +
        `<div class="mono">${esc(typeof d.raw === "string" ? d.raw : JSON.stringify(d.raw))}</div>`);
    case "default_action":
      return ev("warn", `⚠ ${who(a)} kept failing — a random legal ${esc(d.kind)} was used`);

    // structure
    case "day_start": return null; // shown as the day header
    case "tournament_start": return ev("system", `Tournament starts: ${esc(d.players.join(", "))}`);
    case "seating": return ev("system", `Seats: ${byPlayer(d.agents)}`);
    case "game_start": return ev("system", `${esc(d.game)} starts`);
    case "conversation_start": return ev("system", `Conversation opens (up to ${d.max_exchanges} exchanges)`);
    case "conversation_end": return ev("system", `Conversation closed after ${d.exchanges} exchange(s)`);
    case "tournament_end": return ev("system", `Tournament over`);
    case "run_aborted":
      return ev("warn big", `⛔ <b>Run stopped — do not use as data.</b><div class="mono">${esc(d.reason)}</div>`);
    case "pieces_change":
      return ev("game", `${who(a)} ${d.delta > 0 ? "+" : ""}${d.delta} (${esc(d.reason)}) → ${pieces(d.pieces)}`);
    case "placement": {
      const rows = d.ranking.map((group, i) => group.map((p) =>
        `<tr><td>${i + 1}</td><td>${who(p)}</td><td>${d.rewards[p] > 0 ? "+" : ""}${d.rewards[p]}</td><td>${d.pieces[p]}</td></tr>`
      ).join("")).join("");
      return ev("game", `<b>Placement</b><table><tr><th>#</th><th>Player</th><th>Reward</th><th>Pieces</th></tr>${rows}</table>`);
    }
    case "elimination":
      return ev("elim", `❌ <b>${esc(d.player)} is eliminated</b>${d.reason ? ` — ${esc(d.reason)}` : ""}`);
    case "prison": {
      const auto = (d.automatic || []).length ? `<div>Fewest Pieces: ${d.automatic.map(who).join(" ")}</div>` : "";
      const how = (d.deciders || []).length
        ? `chosen by ${d.deciders.map(who).join(" ")} (most Pieces)` + auto +
          `<div>Votes: ${byPlayer(d.votes, (v) => esc(v.map(short).join(", ")))}</div>`
        : "fewest Pieces";
      return ev("game", `🔒 To prison: ${d.prisoners.map(who).join(" ")} — ${how}` +
        ((d.zero_pieces || []).length ? `<div>At 0 Pieces: ${esc(d.zero_pieces.join(", "))}</div>` : "") +
        `<div>Pieces: ${byPlayer(d.pieces)}</div>`);
    }
    case "prison_choice_start":
      return ev("game", `⚖ ${d.deciders.map(who).join(" ")} decide who goes to prison: ${d.seats} from ${esc(d.candidates.join(", "))}`);
    case "prison_start": return null; // shown as a header
    case "prison_result":
      return ev("game", `Prison result: ${d.ranking.map((g) => g.map((p) => esc(short(p))).join("=")).join(" › ")}` +
        (d.winner ? ` — ${who(d.winner)} wins +1 Piece` : ""));

    // Virus Game
    case "roles": return hiddenEv("roles", byPlayer(d.roles));
    case "role_info": return ev("private", `🔒 ${who(a)} ${esc(d.text)}`);
    case "infection": return hiddenEv("infection", `night ${d.night}: ${who(d.player)} infected`);
    case "infected_notice": return ev("private", `🔒 ${who(a)} was told they are INFECTED (now on the terrorists' side)`);
    case "cure": return hiddenEv("cure", `${who(a)} cured ${who(d.player)} — ${d.worked ? "worked" : "wasted"}`);
    case "investigation": return ev("private", `🔒 ${who(a)} learned: ${esc(d.text)}`);
    case "night_result":
      return ev("game", `Night ${d.night}: ` + (d.shot.length ? `🔫 ${d.shot.map(who).join(" ")} shot by the Officer` : "no shots"));
    case "virus_result":
      return ev("big", `Virus Game: <b>${esc(d.winner)}</b> win — infected: ${esc(d.infected.join(", ") || "none")}` +
        `<div>Roles: ${byPlayer(d.roles)}</div>`);

    // Halloween Monster
    case "monster": return ev("game", `👻 Monster ${d.round}: strength <b>${d.strength}</b>, worth ${d.points} points`);
    case "monster_result": {
      const parties = Object.entries(d.parties).map(([leader, x]) =>
        `${esc(short(leader))}'s party (${x.members.map((m) => esc(short(m))).join(", ")}) power ${x.power}`).join("; ");
      const loot = d.winner_party
        ? `${who(d.winner_party)}'s party wins — split: ${byPlayer(d.allocation)}`
        : "nobody defeats it";
      return ev("game", `${loot}<div class="mono">${parties}</div><div>Points: ${byPlayer(d.points)}</div>`);
    }

    // Balance Mancala
    case "pots": return ev("game", `Pots: ${Object.entries(d.pots).map(([pot, n]) => `${esc(pot)} ${n}`).join(" · ")}`);
    case "mancala_result":
      return ev("game", `Picks: ${byPlayer(d.picks)}<div>Lowest colour: ${byPlayer(Object.fromEntries(
        Object.entries(d.totals).map(([p, t]) => [p, Math.min(t.red, t.blue, t.green)])))}</div>`);

    // Equation High-Low (group)
    case "group_hand_result":
      return ev("game", `<b>Hand ${d.hand}</b> (pot ${d.pot}) — won: ${byPlayer(d.won)}` +
        `<table><tr><th>Player</th><th>Target</th><th>Expression</th><th>Value</th></tr>` +
        Object.entries(d.showdown).map(([p, x]) =>
          `<tr><td>${who(p)}</td><td>${esc(x.target)}</td><td class="mono">${esc(x.expression)}</td><td>${esc(x.value)}</td></tr>`).join("") +
        `</table><div>Chips: ${byPlayer(d.chips)}</div>`);

    // Sniper Hold'em
    case "board": return ev("game", `Shared cards: <span class="mono">${esc(d.shown.join(" "))}</span>` +
      (d.folded && d.folded.length ? ` — folded: ${esc(d.folded.join(", "))}` : ""));
    case "holdem_result":
      return ev("game", `<b>Hand ${d.hand}</b> (pot ${d.pot}) — ` +
        (d.winners.length ? `won by ${d.winners.map(who).join(" ")}` : "no winner, pot carries over") +
        `<div>Hands: ${byPlayer(Object.fromEntries(Object.entries(d.showdown).map(([p, x]) => [p, `${x.cards.join(" ")} (${x.best})`])))}</div>` +
        `<div>Snipes: ${byPlayer(Object.fromEntries(Object.entries(d.snipes).map(([p, x]) => [p, x || "—"])))}` +
        (d.disqualified.length ? ` · disqualified: ${esc(d.disqualified.join(", "))}` : "") + `</div>` +
        `<div>Chips: ${byPlayer(d.chips)}</div>`);

    // Triple Dice
    case "shown_dice": return ev("game", `Shown dice: ${byPlayer(d.shown, (x) => esc(x.join(" ")))}`);
    case "dice_result":
      return ev("game", `Dice: ${byPlayer(d.dice, (x) => esc(x.join(" ")))}<div>Ranks: ${byPlayer(d.ranks)} · predicted: ${byPlayer(d.predictions)}</div>` +
        `<div>Points: ${byPlayer(d.points)}</div>`);

    // Suit Survival
    case "suits": return hiddenEv("suits dealt", byPlayer(d.suits));
    case "suit_result":
      return ev(d.everyone_out ? "big" : "game", `<b>Round ${d.round}</b>: ` +
        (d.wrong.length ? `out: ${d.wrong.map(who).join(" ")}${d.everyone_out ? " — everyone" : ""}` : "everyone guessed right") +
        `<div>Suits: ${byPlayer(d.suits)}</div><div>Guesses: ${byPlayer(d.guesses)}</div>`);
    case "no_winner": return ev("big", `No winner — ${esc(d.reason)}`);
    case "hidden_player": return hiddenEv("hidden player", who(d.player));
    case "guesses": return hiddenEv("guesses", `${byPlayer(d.guesses)}<div>Suits: ${byPlayer(d.suits)}</div>`);
    case "hidden_round":
      return ev("game", `<b>Round ${d.round}</b>: ` + (d.eliminated.length ? `out: ${d.eliminated.map(who).join(" ")}` : "nobody out"));
    case "game_clear":
      return ev("big", `✅ GAME CLEAR — the Hidden Player ${who(d.hidden_player)} is out; winners: ${d.winners.map(who).join(" ")}`);
    case "hidden_player_wins": return ev("big", `🃏 The Hidden Player ${who(d.hidden_player)} wins`);

    // Equation Pyramid
    case "pyramid_target": return ev("game", `🎯 Target: <b>${d.target}</b>`);
    case "pyramid_result":
      return ev("game", `Answers: ${byPlayer(Object.fromEntries(Object.entries(d.answers).map(([p, x]) =>
        [p, x ? `${x.tiles.join("")}=${x.value}` : "skip"])))}<div>Points: ${byPlayer(d.points)}</div>`);
    case "day_end": return ev("system", `Day over — nobody is eliminated today`);
    case "life_bought": return ev("game", `❤ ${who(a)} bought a life for ${pieces(d.price)} → ${pieces(d.pieces)} left${exTag(e)}`);
    case "life_used": return ev("elim", `❤ ${who(d.player)} would have been eliminated — their life is used instead`);

    // Team Treasury
    case "contributions":
      return ev("game", `Treasury: ${byPlayer(d.contributions)} → total <b>${d.total} / ${d.goal}</b>`);
    case "team_result":
      return ev(d.success ? "big" : "elim", d.success
        ? `✅ Team goal reached (${d.total}/${d.goal}) — everyone gets +${d.bonus}`
        : `✖ Team goal missed (${d.total}/${d.goal}) — contributions are lost`);
    case "tie_break_draw": return ev("game", `🎲 Tie between ${esc(d.between.join(", "))} — draw picks ${who(d.chosen)}`);
    case "champion": return ev("big", `🏆 ${who(d.player)} is the champion`);
    case "agent_usage": {
      const rows = Object.entries(d).map(([p, u]) =>
        `<tr><td>${who(p)}</td><td>${u.calls}</td><td>${u.errors}</td><td>${u.prompt_tokens}/${u.completion_tokens}</td><td>$${u.cost.toFixed(4)}</td></tr>`
      ).join("");
      return hiddenEv("usage", `<table><tr><th>Player</th><th>Calls</th><th>Errors</th><th>Tokens in/out</th><th>Cost</th></tr>${rows}</table>`);
    }

    // Remove One
    case "round_result":
      return ev("game", `Cards: ${byPlayer(d.plays)} → ` +
        (d.winner ? `${who(d.winner)} wins the round` : "no unique card, nobody scores"));

    // Secret Number
    case "deal":
      if (d.numbers) return hiddenEv("secret numbers", byPlayer(d.numbers));
      if (d.hole) return hiddenEv("cards dealt", byPlayer(d.hole, (c) => esc(c.join(" "))) +
        `<div>Shared: <span class="mono">${esc(d.board.join(" "))}</span></div>`);
      return hiddenEv("cards dealt", byPlayer(d.cards || d.hands, (c) => esc(c.join(" "))));
    case "clue_result":
      return ev("private", `🔒 ${who(a)} bought a clue: higher than ${d.higher_than}? <b>${d.answer ? "YES" : "NO"}</b>`);
    case "reveal": {
      const rows = Object.keys(d.numbers).map((p) =>
        `<tr><td>${who(p)}</td><td>${d.numbers[p]}</td><td>${d.guesses[p]}</td><td>${d.errors[p]}</td></tr>`).join("");
      return ev("game", `<b>Reveal</b><table><tr><th>Player</th><th>Number</th><th>Guess</th><th>Off by</th></tr>${rows}</table>`);
    }

    // Doubt & Bet
    case "roll": return hiddenEv("dice", byPlayer(d.dice, (dice) => esc(dice.join(" "))));
    case "bid": return ev("game", `${who(a)} bids <b>${d.quantity} × ${d.face}s</b>`);
    case "doubt":
      return ev("game", `${who(d.doubter)} doubts ${esc(short(d.bid.player))}'s ${d.bid.quantity} × ${d.bid.face}s — ` +
        `there are <b>${d.count}</b>, so the bid was ${d.bid_was_true ? "true" : "false"}. ${who(d.loser)} loses a die.` +
        `<div>Dice: ${byPlayer(d.dice, (dice) => esc(dice.join(" ")))}</div>`);
    case "out_of_dice": return ev("game", `${who(d.player)} is out of dice`);

    // Time Auction
    case "bids": return hiddenEv("bids", byPlayer(d.bids) + `<div>Banks left: ${byPlayer(d.bank)}</div>`);
    case "auction_result":
      return ev("game", (d.winner ? `${who(d.winner)} wins the token` : "Highest bid tied — no token") +
        `<div>Tokens: ${byPlayer(d.tokens)}</div>`);

    // Equation High-Low
    case "ante": return ev("system", `Ante paid, pot ${d.pot}`);
    case "bet_move": {
      const verb = { check: "checks", bet: `bets ${d.amount}`, call: "calls", fold: "folds" }[d.move];
      return ev("game", `${who(a)} ${esc(verb)}`);
    }
    case "hand_result": {
      let body = `<b>Hand ${d.hand}</b>: `;
      if (d.folded) body += `${esc(short(d.folded))} folded — ${who(d.winner)} takes the pot of ${d.pot}`;
      else {
        body += d.winner ? `${who(d.winner)} wins the pot of ${d.pot}` : `split pot of ${d.pot}`;
        body += `<table><tr><th>Player</th><th>Cards</th><th>Target</th><th>Expression</th><th>Value</th><th>Off by</th></tr>` +
          Object.entries(d.showdown).map(([p, x]) =>
            `<tr><td>${who(p)}</td><td>${esc(x.cards.join(" "))}</td><td>${esc(x.target)}</td>` +
            `<td class="mono">${esc(x.expression)}</td><td>${esc(x.value)}</td><td>${x.distance}</td></tr>`).join("") +
          `</table>`;
      }
      return ev("game", body + `<div>Chips: ${byPlayer(d.chips)}</div>`);
    }

    // Final
    case "first_player": return ev("game", `${who(a)} chose ${who(d.first)} to move first in ${esc(d.game)}`);
    case "final_game_result":
      return ev("game", `<b>${esc(d.game)}</b> won by ${who(d.winner)} — series ${byPlayer(d.wins)}`);

    default:
      return ev(e.visible_to === "god" ? "hidden" : "game",
        `<span class="mono">${esc(e.type)} ${a ? esc(a) : ""} ${esc(JSON.stringify(d))}</span>`);
  }
}

function renderThreads() {
  const threads = new Map();
  for (let i = 0; i < state.cursor; i++) {
    const e = state.events[i];
    if (e.type !== "private_message" || !visible(e)) continue;
    const key = [e.actor, e.data.to].sort().join("|");
    if (!threads.has(key)) threads.set(key, []);
    threads.get(key).push(e);
  }
  const sorted = [...threads.entries()].sort((x, y) => y[1].at(-1).seq - x[1].at(-1).seq);
  $("threads").innerHTML = sorted.map(([key, msgs], i) => {
    const [p, q] = key.split("|");
    const open = state.openThreads.has(key) || (i === 0 && !state.openThreads.has("!" + key));
    return `<details class="thread" data-key="${esc(key)}" ${open ? "open" : ""}>
      <summary>${dot(p)}${esc(short(p))} ↔ ${dot(q)}${esc(short(q))}<span class="count">${msgs.length}</span></summary>
      <div class="msgs">${msgs.map((m) => `<div class="m">${who(m.actor)}
        <span class="meta">day ${m.day}${m.round != null ? `, round ${m.round}` : ""}${m.exchange ? `, exchange ${m.exchange}` : ""}</span>
        <div>${esc(m.data.text)}</div></div>`).join("")}</div>
    </details>`;
  }).join("") || `<p class="empty">No private messages${state.view === "god" ? "" : " for this player"} yet.</p>`;
}

// Remember which threads the user opened or closed across re-renders.
document.addEventListener("toggle", (event) => {
  const el = event.target;
  if (!(el instanceof HTMLDetailsElement) || !el.dataset.key) return;
  const key = el.dataset.key;
  if (el.open) { state.openThreads.add(key); state.openThreads.delete("!" + key); }
  else { state.openThreads.delete(key); state.openThreads.add("!" + key); }
}, true);

// ------------------------------------------------------------------ graph

function renderGraph(s) {
  const W = 240, H = 220, cx = 120, cy = 108, R = 78;
  const n = s.players.length;
  if (!n) { $("graph").innerHTML = ""; return; }
  const pos = {};
  s.players.forEach((p, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
    pos[p] = [cx + R * Math.cos(angle), cy + R * Math.sin(angle)];
  });
  const dms = new Map();
  const gifts = new Map();
  for (let i = 0; i < state.cursor; i++) {
    const e = state.events[i];
    if (!visible(e) && e.type !== "transfer") continue;
    if (e.type === "private_message") {
      const key = [e.actor, e.data.to].sort().join("|");
      dms.set(key, (dms.get(key) || 0) + 1);
    } else if (e.type === "transfer") {
      const key = `${e.actor}|${e.data.to}`;
      gifts.set(key, (gifts.get(key) || 0) + e.data.pieces);
    }
  }
  let svg = "";
  for (const [key, count] of dms) {
    const [p, q] = key.split("|");
    const [x1, y1] = pos[p], [x2, y2] = pos[q];
    svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--text-muted)" stroke-opacity=".55"
      stroke-width="${1 + Math.min(count, 14) * 0.6}" stroke-linecap="round"><title>${esc(key.replace("|", " ↔ "))}: ${count} private message(s)</title></line>`;
  }
  for (const [key, total] of gifts) {
    const [p, q] = key.split("|");
    const [x1, y1] = pos[p], [x2, y2] = pos[q];
    // curve to one side so A→B and B→A do not overlap
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
    const qx = mx - (dy / len) * 22, qy = my + (dx / len) * 22;
    // stop short of the target node, then draw the arrowhead
    const t = 1 - 14 / len;
    const ex = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * qx + t * t * x2;
    const ey = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * qy + t * t * y2;
    const ang = Math.atan2(ey - qy, ex - qx);
    const head = [[ex, ey], [ex - 7 * Math.cos(ang - 0.45), ey - 7 * Math.sin(ang - 0.45)],
      [ex - 7 * Math.cos(ang + 0.45), ey - 7 * Math.sin(ang + 0.45)]].map((pt) => pt.join(",")).join(" ");
    svg += `<g><title>${esc(p)} gave ${esc(q)} ${pieces(total)} in total</title>
      <path d="M${x1},${y1} Q${qx},${qy} ${ex},${ey}" fill="none" stroke="${color(p)}" stroke-width="2"/>
      <polygon points="${head}" fill="${color(p)}"/>
      <text x="${qx}" y="${qy}" font-size="11" text-anchor="middle" dominant-baseline="middle"
        fill="var(--text-primary)" stroke="var(--surface-1)" stroke-width="3" paint-order="stroke">${total}</text></g>`;
  }
  for (const p of s.players) {
    const [x, y] = pos[p];
    const out = p in s.out;
    svg += `<g opacity="${out ? 0.4 : 1}"><circle cx="${x}" cy="${y}" r="13" fill="${color(p)}"
      stroke="var(--surface-1)" stroke-width="2"/>
      <text x="${x}" y="${y}" font-size="12" font-weight="700" text-anchor="middle" dominant-baseline="central"
        fill="#fff">${esc(short(p))}</text><title>${esc(p)}${out ? " (eliminated)" : ""}</title></g>`;
  }
  $("graph").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Private messages and Piece transfers between players">${svg}</svg>`;
}

// ------------------------------------------------------------------ chart

function renderChart(s) {
  const box = $("chart");
  if (!s.players.length || !s.history.length) { box.innerHTML = `<p class="empty">No data yet.</p>`; return; }
  const W = 320, H = 190, L = 26, Rm = 22, T = 14, B = 22;
  const lastSeq = state.cursor ? state.events[state.cursor - 1].seq : 0;
  const maxSeq = Math.max(lastSeq, 1);
  const maxY = Math.max(5, ...s.history.flatMap((h) => Object.values(h.pieces)));
  const x = (seq) => L + (seq / maxSeq) * (W - L - Rm);
  const y = (v) => T + (1 - v / maxY) * (H - T - B);

  let svg = "";
  const step = maxY > 10 ? Math.ceil(maxY / 5) : maxY > 6 ? 2 : 1;
  for (let v = 0; v <= maxY; v += step) {
    svg += `<line x1="${L}" x2="${W - Rm}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/>
      <text x="${L - 6}" y="${y(v)}" font-size="10" text-anchor="end" dominant-baseline="middle" fill="var(--text-muted)">${v}</text>`;
  }
  for (const d of s.days) {
    svg += `<line x1="${x(d.seq)}" x2="${x(d.seq)}" y1="${T}" y2="${H - B}" stroke="var(--border)" stroke-dasharray="3 3"/>
      <text x="${x(d.seq) + 3}" y="${H - B + 13}" font-size="10" fill="var(--text-muted)">D${d.day}</text>`;
  }

  const ends = [];
  for (const p of s.players) {
    const stop = s.outSeq[p] ?? lastSeq;
    const pts = s.history.filter((h) => p in h.pieces && h.seq <= stop);
    if (!pts.length) continue;
    let d = `M${x(pts[0].seq)},${y(pts[0].pieces[p])}`;
    for (const h of pts.slice(1)) d += ` H${x(h.seq)} V${y(h.pieces[p])}`;
    const endValue = pts.at(-1).pieces[p];
    d += ` H${x(stop)}`;
    svg += `<path d="${d}" fill="none" stroke="${color(p)}" stroke-width="2" stroke-linejoin="round"
      opacity="${p in s.out ? 0.45 : 1}"/>`;
    ends.push({ p, x: x(stop), y: y(endValue) });
  }
  // direct labels at line ends; nudge apart when they collide
  ends.sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) {
    if (Math.abs(ends[i].x - ends[i - 1].x) < 14 && ends[i].y - ends[i - 1].y < 10) ends[i].y = ends[i - 1].y + 10;
  }
  for (const e of ends) {
    svg += `<text x="${e.x + 4}" y="${e.y}" font-size="10" font-weight="700" dominant-baseline="middle"
      fill="var(--text-primary)">${esc(short(e.p))}</text>`;
  }
  svg += `<line id="crosshair" y1="${T}" y2="${H - B}" stroke="var(--text-secondary)" visibility="hidden"/>
    <rect id="hover" x="${L}" y="${T}" width="${W - L - Rm}" height="${H - T - B}" fill="transparent"/>`;

  const legend = s.players.map((p) => `<span>${dot(p)}${esc(short(p))}</span>`).join("");
  box.innerHTML = `<div class="legend">${legend}</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Pieces per player over the tournament">${svg}</svg>
    <div class="tooltip" hidden></div>`;

  const svgEl = box.querySelector("svg");
  const tip = box.querySelector(".tooltip");
  const cross = svgEl.querySelector("#crosshair");
  svgEl.querySelector("#hover").addEventListener("mousemove", (ev) => {
    const rect = svgEl.getBoundingClientRect();
    const sx = ((ev.clientX - rect.left) / rect.width) * W;
    const seq = Math.max(0, Math.min(maxSeq, ((sx - L) / (W - L - Rm)) * maxSeq));
    const at = [...s.history].reverse().find((h) => h.seq <= seq) || s.history[0];
    const rows = s.players
      .filter((p) => p in at.pieces && !(s.outSeq[p] < seq))
      .sort((a, b) => at.pieces[b] - at.pieces[a])
      .map((p) => `<div class="row">${dot(p)}${esc(p)}<span class="val">${at.pieces[p]}</span></div>`).join("");
    const day = [...s.days].reverse().find((d) => d.seq <= seq);
    tip.innerHTML = `<div><b>${day ? `Day ${day.day}` : "Start"}</b></div>${rows}`;
    tip.hidden = false;
    cross.setAttribute("x1", sx); cross.setAttribute("x2", sx); cross.setAttribute("visibility", "visible");
    const px = (sx / W) * rect.width;
    tip.style.left = `${Math.min(px + 12, rect.width - tip.offsetWidth)}px`;
    tip.style.top = `30px`;
  });
  svgEl.querySelector("#hover").addEventListener("mouseleave", () => {
    tip.hidden = true;
    cross.setAttribute("visibility", "hidden");
  });
}

// ------------------------------------------------------------------ playback

function setCursor(n, { user = false } = {}) {
  state.cursor = Math.max(0, Math.min(state.events.length, n));
  if (user) {
    state.follow = state.cursor === state.events.length;
    $("follow").checked = state.follow;
  }
  render();
}

function startPlaying() {
  if (state.cursor >= state.events.length) state.cursor = 0;
  state.playing = true;
  const interval = 1000 / Number($("speed").value);
  state.timer = setInterval(() => {
    if (state.cursor < state.events.length) setCursor(state.cursor + 1);
    else if ($("live-badge").hidden) stopPlaying();
  }, interval);
  render();
}

function stopPlaying() {
  state.playing = false;
  clearInterval(state.timer);
  state.timer = null;
  render();
}

// ------------------------------------------------------------------ wiring

$("btn-stop").addEventListener("click", stopRun);
$("run-select").addEventListener("change", (e) => e.target.value && openRun(e.target.value));
$("view-select").addEventListener("change", (e) => { state.view = e.target.value; render(); });
$("show-hidden").addEventListener("change", (e) => { state.showHidden = e.target.checked; render(); });
$("show-system").addEventListener("change", (e) => { state.showSystem = e.target.checked; render(); });
$("follow").addEventListener("change", (e) => {
  state.follow = e.target.checked;
  if (state.follow) setCursor(state.events.length);
});
$("slider").addEventListener("input", (e) => setCursor(Number(e.target.value), { user: true }));
$("btn-start").addEventListener("click", () => setCursor(0, { user: true }));
$("btn-end").addEventListener("click", () => setCursor(state.events.length, { user: true }));
$("btn-back").addEventListener("click", () => setCursor(state.cursor - 1, { user: true }));
$("btn-fwd").addEventListener("click", () => setCursor(state.cursor + 1, { user: true }));
$("btn-play").addEventListener("click", () => (state.playing ? stopPlaying() : startPlaying()));
$("speed").addEventListener("change", () => { if (state.playing) { stopPlaying(); startPlaying(); } });
$("theme-toggle").addEventListener("click", () => {
  const light = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "light"
    : matchMedia("(prefers-color-scheme: light)").matches;
  document.documentElement.dataset.theme = light ? "dark" : "light";
});
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if (e.key === "ArrowRight") setCursor(state.cursor + 1, { user: true });
  else if (e.key === "ArrowLeft") setCursor(state.cursor - 1, { user: true });
  else if (e.key === " ") { e.preventDefault(); state.playing ? stopPlaying() : startPlaying(); }
});

loadRuns();

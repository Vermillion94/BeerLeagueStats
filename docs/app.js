/* Beer League Stats — static front end.
   Everything on screen comes from the precomputed JSON in ./data (built by
   build_site.py). No server calls beyond fetching those files. */
(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct = (v, d = 0) => v == null ? '–' : (v * 100).toFixed(d) + '%';
const num = (v, d = 0) => v == null ? '–' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const sign = (v, d = 0) => v == null ? '–' : (v > 0 ? '+' : '') + num(v, d);
const clock = s => s == null ? '–' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const ROLE = { TOP: 'TOP', JUNGLE: 'JGL', MIDDLE: 'MID', BOTTOM: 'ADC', SUPPORT: 'SUP' };
const ROLE_COLOR = { TOP: '#e5484d', JUNGLE: '#2fbf8f', MIDDLE: '#4f8ff7', BOTTOM: '#f59e0b', SUPPORT: '#a78bfa' };
const PAGES = [['overview', 'Overview'], ['standings', 'Standings'], ['playoffs', 'Playoffs'], ['recap', 'Recap'],
  ['players', 'Players'], ['teams', 'Teams'], ['wins', 'How Games Are Won'], ['champions', 'Champions'],
  ['draft', 'Draft & Items'], ['records', 'Record Book'], ['forecasts', 'Forecasts']];
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

const state = { index: null, cache: {}, D: null, band: null, sid: null, page: 'overview', week: null, timer: null, ddv: null };
const T = id => state.D.teams[id] || { name: '?', color: '#64748b' };
const dot = id => `<span class="dot" style="background:${T(id).color}"></span>`;
const liveTeams = () => Object.keys(state.D.teams).filter(t => !state.D.teams[t].dropped);

/* ── tooltip ── */
const tipEl = $('#tip');
const tip = {
  show(html, ev) { tipEl.innerHTML = html; tipEl.style.opacity = 1; tip.move(ev); },
  move(ev) { const w = tipEl.offsetWidth, x = Math.min(ev.clientX + 14, innerWidth - w - 8); tipEl.style.left = x + 'px'; tipEl.style.top = (ev.clientY + 16) + 'px'; },
  hide() { tipEl.style.opacity = 0; },
};
const withTip = (sel, html) => sel.on('mouseenter', (ev, d) => tip.show(html(d), ev)).on('mousemove', ev => tip.move(ev)).on('mouseleave', tip.hide);

/* ── small animation helpers ── */
function countUp(el) {
  const target = parseFloat(el.dataset.to), dec = +(el.dataset.dec || 0), suf = el.dataset.suf || '';
  if (REDUCED || isNaN(target)) { el.textContent = isNaN(target) ? el.dataset.raw : target.toFixed(dec) + suf; return; }
  const t0 = performance.now(), dur = 900;
  const step = t => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); el.textContent = (target * e).toFixed(dec) + suf; if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
let io;
function observe(root) {
  io?.disconnect();
  io = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add('in');
    e.target.querySelectorAll('[data-to]').forEach(countUp);
    e.target.querySelectorAll('[data-w]').forEach(b => { b.style.width = b.dataset.w; });
    e.target.dispatchEvent(new CustomEvent('reveal'));
    io.unobserve(e.target);
  }), { threshold: 0.12 });
  root.querySelectorAll('.rv').forEach(n => io.observe(n));
}

/* ── building blocks ── */
const chyron = (label, value, sub = '', o = {}) => {
  const anim = o.to != null ? ` data-to="${o.to}" data-dec="${o.dec || 0}" data-suf="${o.suf || ''}"` : '';
  return `<div class="chyron"><div class="l">${esc(label)}</div><div class="v ${o.cls || ''}"${anim}>${o.to != null ? '0' : value}</div><div class="s">${sub}</div></div>`;
};
function bug(s) {
  const w1 = s.s1 > s.s2, w2 = s.s2 > s.s1, sub = [];
  let flag = '';
  if (s.wpm != null) { if (s.wpm < 0.4) flag = '<span class="flag">UPSET</span>'; sub.push(`Model gave the winner <b>${pct(s.wpm)}</b>`); }
  if (s.wpc != null && s.n >= 5) sub.push(`crowd <b>${pct(s.wpc)}</b> (${s.n} picks)`);
  if (s.oog) sub.push('exhibition');
  if (s.label) sub.push(esc(s.label));
  return `<div class="bug ${w1 ? 'lw' : w2 ? 'rw' : ''}">${flag}<div class="bug-row">
    <div class="bug-team ${w1 ? 'w' : ''}">${dot(s.t1)}<span class="n">${esc(T(s.t1).name)}</span></div>
    <div class="bug-score"><span class="${w1 ? 'w' : ''}">${s.s1}</span><span class="${w2 ? 'w' : ''}">${s.s2}</span></div>
    <div class="bug-team r ${w2 ? 'w' : ''}"><span class="n">${esc(T(s.t2).name)}</span>${dot(s.t2)}</div></div>
    ${sub.length ? `<div class="bug-sub">${sub.join(' · ')}</div>` : ''}</div>`;
}
const duel = (label, p, n) => p == null
  ? `<div class="duel"><div class="dl">${label}</div><div class="dn" style="grid-column:2/span 2">${n}</div></div>`
  : `<div class="duel"><div class="dl">${label}</div><div class="dt"><div class="da" data-w="${Math.max(8, Math.round(p * 100))}%">${Math.round(p * 100)}%</div><div class="db">${100 - Math.round(p * 100)}%</div></div><div class="dn">${n}</div></div>`;
function forecastCard(s) {
  const close = s.pm >= 0.42 && s.pm <= 0.58;
  return `<div class="bug">${close ? '<span class="flag">TOSS-UP</span>' : s.oog ? '<span class="flag" style="background:#334155">EXHIBITION</span>' : ''}
    <div class="bug-row"><div class="bug-team w">${dot(s.t1)}<span class="n">${esc(T(s.t1).name)}</span></div>
    <div class="bug-team r w"><span class="n">${esc(T(s.t2).name)}</span>${dot(s.t2)}</div></div>
    ${duel('Model', s.pm, 'likely ' + s.likely)}${duel('Crowd', s.n >= 3 ? s.pc : null, s.n >= 3 ? s.n + ' picks' : 'not enough picks yet')}</div>`;
}
const stories = (list, n = 6) => list.length
  ? list.slice(0, n).map(s => `<div class="story"><div class="t">${esc(s.tag)}</div><div class="x">${s.html}</div></div>`).join('')
  : '<p class="note">Nothing unusual to report — a chalk week.</p>';
function hbars(items, o = {}) {
  const max = Math.max(...items.map(i => Math.abs(i.value)), 1e-9);
  return `<div class="panel rv">${o.title ? `<h3>${esc(o.title)}</h3>` : ''}${o.sub ? `<p class="note" style="margin-top:-4px">${o.sub}</p>` : ''}` +
    items.map(i => { const w = (Math.abs(i.value) / max * 72).toFixed(1); return `<div class="hb" title="${esc(i.title || '')}"><div class="nm">${esc(i.label)}</div><div class="tr"><i data-w="${w}%" style="background:${i.color || o.color || 'var(--gold)'}"></i><span style="left:${w}%">${i.text}</span></div></div>`; }).join('') + '</div>';
}
function bracketHtml() {
  const b = state.D.bracket || [];
  const line = x => `<div class="t"><s>${esc(x.label)}</s>${dot(x.team)}${esc(T(x.team).name)}</div>`;
  return `<div class="bk">${b.map(m => `<div><div class="h">${m.kind === 'match' ? 'Round 1 · ' : ''}${esc(m.title)}</div>${line(m.a)}${m.b ? line(m.b) : '<div class="t bye">awaits a round-1 winner</div>'}</div>`).join('')}</div>`;
}

/* sortable table: cols = [{k, label, f, num, cls, html}] */
function sortable(host, cols, rows, o = {}) {
  let key = o.key, asc = !!o.asc, limit = o.limit || rows.length;
  const draw = () => {
    const sorted = [...rows].sort((a, b) => { const x = a[key], y = b[key]; if (x == null) return 1; if (y == null) return -1; return (typeof x === 'string' ? x.localeCompare(y) : x - y) * (asc ? 1 : -1); });
    host.innerHTML = `<div class="tw"><table><thead><tr>${o.rank ? '<th class="num">#</th>' : ''}${cols.map(c => `<th class="sort ${c.num ? 'num' : ''} ${c.k === key ? 'on' + (asc ? ' asc' : '') : ''}" data-k="${c.k}" title="${esc(c.tip || '')}">${c.label}</th>`).join('')}</tr></thead><tbody>` +
      sorted.slice(0, limit).map((r, i) => `<tr class="${o.onRow ? 'click' : ''}" data-i="${i}">${o.rank ? `<td class="num rk">${i + 1}</td>` : ''}${cols.map(c => `<td class="${c.num ? 'num' : ''} ${c.cls || ''}">${c.html ? c.html(r) : c.f ? c.f(r[c.k], r) : esc(r[c.k] ?? '–')}</td>`).join('')}</tr>`).join('') +
      `</tbody></table></div>${sorted.length > limit ? `<p class="note">Showing ${limit} of ${sorted.length}. <a href="#" data-more>Show all</a></p>` : ''}`;
    host.querySelectorAll('th.sort').forEach(th => th.onclick = () => { const k = th.dataset.k; if (k === key) asc = !asc; else { key = k; asc = typeof rows[0]?.[k] === 'string'; } draw(); });
    if (o.onRow) host.querySelectorAll('tbody tr').forEach(tr => tr.onclick = () => o.onRow(sorted[+tr.dataset.i]));
    const more = host.querySelector('[data-more]'); if (more) more.onclick = e => { e.preventDefault(); limit = rows.length; draw(); };
    host.querySelectorAll('[data-w]').forEach(b => requestAnimationFrame(() => { b.style.width = b.dataset.w; }));
  };
  draw();
}
const cellBar = (v, max, txt) => `<div class="cellbar"><i data-w="${Math.max(2, v / max * 70).toFixed(0)}px" style="width:0"></i><span>${txt}</span></div>`;

/* ── profile drawer ── */
function drawer(html) {
  document.querySelector('.scrim')?.remove();
  const s = document.createElement('div'); s.className = 'scrim';
  s.innerHTML = `<div class="drawer"><button class="x">CLOSE ✕</button>${html}</div>`;
  const close = () => { s.classList.remove('in'); setTimeout(() => s.remove(), 250); removeEventListener('keydown', esc_); };
  const esc_ = e => { if (e.key === 'Escape') close(); };
  s.onclick = e => { if (e.target === s || e.target.classList.contains('x')) close(); };
  addEventListener('keydown', esc_); document.body.appendChild(s);
  requestAnimationFrame(() => { s.classList.add('in'); s.querySelectorAll('[data-w]').forEach(b => b.style.width = b.dataset.w); s.querySelectorAll('[data-to]').forEach(countUp); });
  champIcons();
}
const pctile = (pool, k, v, inv) => { const xs = pool.map(p => p[k]).filter(x => x != null); if (v == null || xs.length < 3) return null; const p = (xs.filter(x => x < v).length + .5 * xs.filter(x => x === v).length) / xs.length; return inv ? 1 - p : p; };
const pbars = rows => rows.filter(r => r[2] != null).map(([l, v, p]) => `<div class="pb"><div class="l">${l}</div><div class="t"><i class="${p >= .75 ? 'hi' : p <= .25 ? 'lo' : ''}" data-w="${Math.max(3, Math.round(p * 100))}%"></i></div><div class="v">${v}</div><div class="p">${Math.round(p * 100)}</div></div>`).join('');
function playerProfile(p) {
  const peers = state.D.players.filter(x => x.role === p.role && x.games >= Math.min(3, p.games)), q = (k, inv) => pctile(peers, k, p[k], inv);
  drawer(`<div class="hero" style="margin-top:34px"><div class="k">${ROLE[p.role] || 'Player'} · ${esc(p.team)}</div><div class="n">${esc(p.player)}</div>
    <div class="m">${dot(p.team_id)}Main: ${esc(p.main)} · ${p.champs} champions played</div>
    <div class="stats"><div>${p.wins}–${p.games - p.wins}<small>Record</small></div><div>${num(p.kda, 2)}<small>KDA</small></div><div data-to="${p.impact ?? 0}">0<small>Impact</small></div><div>${p.salary ?? '–'}<small>Salary</small></div></div></div>
    <p class="note">Percentile among ${peers.length} ${ROLE[p.role] || ''} players — blue is top quarter, red is bottom quarter.</p>
    <div class="panel">${pbars([['Impact', num(p.impact), q('impact')], ['KDA', num(p.kda, 2), q('kda')], ['Kill participation', pct(p.kp), q('kp')], ['Damage / min', num(p.dmg_min), q('dmg_min')], ['Gold / min', num(p.gold_min), q('gold_min')],
      ['CS / min', num(p.cs_min, 1), q('cs_min')], ['Vision / min', num(p.vis_min, 2), q('vis_min')], ['Gold diff @15', p.gd15 == null ? '–' : sign(p.gd15), q('gd15')], ['Deaths / game', num(p.d_g, 1), q('d_g', true)]])}</div>
    <h3 style="margin-top:20px">Champion pool</h3><div class="tw"><table><thead><tr><th>Champion</th><th class="num">Games</th><th class="num">Record</th><th class="num">Win%</th></tr></thead><tbody>
    ${(p.pool || []).map(c => `<tr><td class="team">${esc(c.c)}</td><td class="num">${c.g}</td><td class="num">${c.w}–${c.g - c.w}</td><td class="num">${pct(c.w / c.g)}</td></tr>`).join('')}</tbody></table></div>`);
  document.querySelectorAll('.drawer [data-to] small').length; // count-up replaces text; restore label
  const im = document.querySelector('.drawer [data-to]'); if (im) { const v = document.createElement('span'); v.dataset.to = im.dataset.to; im.removeAttribute('data-to'); im.innerHTML = ''; im.append(v); im.insertAdjacentHTML('beforeend', '<small>Impact</small>'); countUp(v); }
}
function teamProfile(tid) {
  const D = state.D, ts = D.team_stats || [], me = ts.find(t => t.team_id === tid), w = D.weeks.at(-1), q = (k, inv) => pctile(ts, k, me?.[k], inv);
  let row, place, grp = '';
  for (const [g, rows] of Object.entries(D.standings[w])) { const live = rows.filter(r => !r.dropped), i = live.findIndex(r => r.t === tid); if (i >= 0) { row = live[i]; place = i + 1; grp = g === 'all' ? '' : ' in Group ' + g; } }
  const ord = n => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');
  const make = D.playoff?.teams.find(t => t.t === tid)?.make, R = D.ratings.by_team[tid];
  const roster = (D.players || []).filter(p => p.team_id === tid).sort((a, b) => b.games - a.games);
  const res = D.series.filter(s => s.status === 'COMPLETED' && (s.t1 === tid || s.t2 === tid)).sort((a, b) => a.week - b.week);
  drawer(`<div class="hero" style="margin-top:34px;border-top-color:${T(tid).color}"><div class="k">${row ? ord(place) + grp : ''}</div><div class="n">${esc(T(tid).name)}</div>
    <div class="m">Roster salary ${T(tid).salary ?? '–'}${D.cap ? ' of ' + D.cap + ' cap' : ''}${row ? ' · ' + [...row.form].map(c => `<span class="pill ${c}">${c}</span>`).join('') : ''}</div>
    <div class="stats">${row ? `<div>${row.sw}–${row.sl}<small>Series</small></div><div>${row.gw}–${row.gl}<small>Games</small></div>` : ''}${R ? `<div>${num(R.at(-1))}<small>Rating</small></div>` : ''}${make != null ? `<div>${make >= .9995 ? 'IN' : make <= .0005 ? 'OUT' : pct(make)}<small>Playoffs</small></div>` : ''}</div></div>
    ${me ? `<p class="note">Percentile among ${ts.length} teams — blue is top quarter, red is bottom quarter.</p><div class="panel">${pbars([['Kills / game', num(me.kills, 1), q('kills')], ['Deaths / game', num(me.deaths, 1), q('deaths', true)], ['Gold diff @15', me.gd15 == null ? '–' : sign(me.gd15), q('gd15')],
      ['First blood', pct(me.fb), q('fb')], ['First tower', pct(me.ft), q('ft')], ['Dragons / game', num(me.dragons, 1), q('dragons')], ['Barons / game', num(me.barons, 1), q('barons')], ['Vision / min', num(me.vis_min, 1), q('vis_min')], ['Champion pool', me.champ_pool, q('champ_pool')]])}</div>` : ''}
    <h3 style="margin-top:20px">Who played</h3><div class="tw"><table><thead><tr><th>Player</th><th>Role</th><th class="num">GP</th><th class="num">KDA</th><th class="num">Impact</th><th>Main</th></tr></thead><tbody>
    ${roster.map(p => `<tr><td class="team">${esc(p.player)}</td><td>${ROLE[p.role] || '–'}</td><td class="num">${p.games}</td><td class="num">${num(p.kda, 2)}</td><td class="num">${num(p.impact)}</td><td>${esc(p.main)}</td></tr>`).join('')}</tbody></table></div>
    <h3 style="margin-top:20px">Results</h3>${res.map(s => bug({ ...s, wpm: null, wpc: null, label: 'Week ' + s.week })).join('<div style="height:6px"></div>')}`);
}

/* ── standings table (animated between weeks with FLIP) ── */
function standingsHtml(rows, cut, o = {}) {
  const make = o.make;
  const head = `<th class="num">#</th><th>Team</th><th class="num">Series</th>${o.compact ? '' : '<th class="num">Games</th><th>Last 5</th>'}${make ? '<th class="num">Playoffs</th>' : ''}`;
  let rank = 0;
  const body = rows.map(r => {
    if (r.dropped) return `<tr class="dropped" data-t="${r.t}"><td class="num">–</td><td>${dot(r.t)}${esc(T(r.t).name)}</td><td colspan="9">Dropped</td></tr>`;
    rank++;
    let pc = '';
    if (make) { const p = make[r.t]; pc = `<td class="num">${p == null ? '–' : p >= 0.9995 ? '<span class="tag in">IN</span>' : p <= 0.0005 ? '<span class="tag out">OUT</span>' : `<span class="mini"><i data-w="${Math.max(4, p * 100).toFixed(0)}%" style="width:0"></i><span>${p < 0.01 ? '&lt;1' : Math.round(p * 100)}%</span></span>`}</td>`; }
    return `<tr data-t="${r.t}" class="${rank === cut ? 'cut' : ''} ${rank > cut ? 'below' : ''}"><td class="num rk">${rank}</td><td class="team">${dot(r.t)}${esc(T(r.t).name)}${r.tied && rank <= cut + 1 ? ' <span style="color:var(--stout)" title="Still tied after series wins, game wins and head-to-head">=</span>' : ''}</td>
      <td class="num strong">${r.sw}–${r.sl}</td>${o.compact ? '' : `<td class="num">${r.gw}–${r.gl}</td><td>${[...r.form].map(c => `<span class="pill ${c}">${c}</span>`).join('')}</td>`}${pc}</tr>`;
  }).join('');
  return `<div class="tw"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function flip(host, html) {
  const before = new Map([...host.querySelectorAll('tr[data-t]')].map(tr => [tr.dataset.t, tr.getBoundingClientRect().top]));
  host.innerHTML = html;
  host.querySelectorAll('[data-w]').forEach(b => requestAnimationFrame(() => { b.style.width = b.dataset.w; }));
  if (REDUCED || !before.size) return;
  host.querySelectorAll('tr[data-t]').forEach(tr => {
    const old = before.get(tr.dataset.t); if (old == null) return;
    const dy = old - tr.getBoundingClientRect().top; if (!dy) return;
    tr.animate([{ transform: `translateY(${dy}px)`, background: 'rgba(255,215,0,.10)' }, { transform: 'none', background: 'transparent' }], { duration: 700, easing: 'cubic-bezier(.22,.8,.24,1)' });
  });
}
function standingsBlock(host, week, o = {}) {
  const D = state.D, st = D.standings[week] || {}, latest = String(week) === String(D.weeks.at(-1));
  const make = latest && D.playoff ? Object.fromEntries(D.playoff.teams.map(t => [t.t, t.make])) : null;
  const groups = Object.keys(st);
  if (!host.dataset.built) { host.innerHTML = `<div class="cols">${groups.map(g => `<div>${groups.length > 1 ? `<h3>Group ${esc(g)}</h3>` : ''}<div data-g="${g}"></div></div>`).join('')}</div>`; if (groups.length === 1) host.firstChild.style.gridTemplateColumns = '1fr'; host.dataset.built = 1; }
  groups.forEach(g => flip(host.querySelector(`[data-g="${g}"]`), standingsHtml(st[g], groups.length > 1 ? D.spots / 2 : D.spots, { make, compact: o.compact })));
  host.querySelectorAll('tr[data-t]').forEach(tr => { tr.classList.add('click'); tr.onclick = () => teamProfile(tr.dataset.t); });
}

/* ── the season replay: rating race + traced lines, one shared scrubber ── */
function replay(host) {
  const D = state.D, R = D.ratings, ids = liveTeams().filter(t => R.by_team[t]);
  const weeks = R.weeks, last = weeks.length - 1;
  const label = i => weeks[i] === 0 ? 'PRESEASON' : weeks[i] > D.max_week ? 'PLAYOFFS' : 'WEEK ' + weeks[i];
  host.innerHTML = `<div class="player"><button class="play" aria-label="Play">▶</button><div class="wk"></div><input type="range" min="0" max="${last}" step="1" value="${last}"></div>
    <div class="caption"></div><div class="cols w23"><div class="race" style="height:${ids.length * 28}px"></div><div class="lines"></div></div>`;
  const race = $('.race', host), slider = $('input', host), wk = $('.wk', host), cap = $('.caption', host), btn = $('.play', host);
  const all = ids.flatMap(t => R.by_team[t]), lo = Math.min(...all), hi = Math.max(...all), floor = lo - (hi - lo) * 0.12;
  ids.forEach(t => race.insertAdjacentHTML('beforeend', `<div class="race-row" data-t="${t}"><div class="nm">${esc(T(t).name)}</div><div><div class="bar" style="background:${T(t).color};width:0"><span class="val"></span></div></div></div>`));

  // line chart
  const W = 640, H = Math.max(300, ids.length * 28), m = { t: 12, r: 150, b: 26, l: 40 };
  const svg = d3.select($('.lines', host)).append('svg').attr('viewBox', `0 0 ${W} ${H}`);
  const x = d3.scaleLinear([0, last], [m.l, W - m.r]), y = d3.scaleLinear([lo - 20, hi + 20], [H - m.b, m.t]);
  svg.append('g').attr('class', 'grid').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(6).tickSize(-(W - m.l - m.r)).tickFormat(''));
  svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l - 4},0)`).call(d3.axisLeft(y).ticks(6).tickSize(0));
  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b + 6})`).call(d3.axisBottom(x).ticks(last).tickSize(0).tickFormat(i => weeks[i] === 0 ? 'Pre' : weeks[i] > D.max_week ? 'PO' : 'W' + weeks[i]));
  const clip = svg.append('clipPath').attr('id', 'rclip').append('rect').attr('x', 0).attr('y', 0).attr('height', H).attr('width', x(last) + 4);
  const line = d3.line().x((d, i) => x(i)).y(d => y(d)).curve(d3.curveMonotoneX);
  const gl = svg.append('g').attr('clip-path', 'url(#rclip)');
  const paths = gl.selectAll('path').data(ids).join('path').attr('d', t => line(R.by_team[t])).attr('fill', 'none')
    .attr('stroke', t => T(t).color).attr('stroke-width', 1.6).attr('opacity', .28).attr('stroke-linecap', 'round');
  const cursor = svg.append('line').attr('y1', m.t).attr('y2', H - m.b).attr('stroke', 'var(--gold)').attr('stroke-dasharray', '3 4').attr('opacity', .5);
  const dots = svg.selectAll('circle').data(ids).join('circle').attr('r', 4).attr('fill', t => T(t).color).attr('stroke', '#080b12').attr('stroke-width', 1.5);
  const labs = svg.selectAll('text.lab').data(ids).join('text').attr('class', 'lab').text(t => T(t).name);
  const focus = t => { paths.attr('opacity', p => t ? (p === t ? 1 : .08) : .28).attr('stroke-width', p => p === t ? 3 : 1.6); labs.attr('opacity', p => !t || p === t ? 1 : .15); race.querySelectorAll('.race-row').forEach(r => r.style.opacity = !t || r.dataset.t === t ? 1 : .3); };
  paths.on('mouseenter', (e, t) => focus(t)).on('mouseleave', () => focus(null));
  race.querySelectorAll('.race-row').forEach(r => { r.onmouseenter = () => focus(r.dataset.t); r.onmouseleave = () => focus(null); });

  function set(i, animate = true) {
    i = +i; slider.value = i; wk.textContent = label(i);
    const order = [...ids].sort((a, b) => R.by_team[b][i] - R.by_team[a][i]);
    const rank = Object.fromEntries(order.map((t, k) => [t, k]));
    let best = null, worst = null;
    race.querySelectorAll('.race-row').forEach(r => {
      const t = r.dataset.t, v = R.by_team[t][i], d = i ? v - R.by_team[t][i - 1] : 0;
      r.style.transform = `translateY(${rank[t] * 28}px)`;
      $('.bar', r).style.width = ((v - floor) / (hi - floor) * 82).toFixed(1) + '%';
      $('.val', r).innerHTML = `${Math.round(v)}${d ? `<small class="${d > 0 ? 'up' : 'down'}">${d > 0 ? '▲' : '▼'}${Math.abs(Math.round(d))}</small>` : ''}`;
      if (i && (!best || d > best.d)) best = { t, d }; if (i && (!worst || d < worst.d)) worst = { t, d };
    });
    cap.innerHTML = i === 0 ? 'Every team starts on a rating set by its roster salary. Press play to watch the season move it.'
      : `<b>${esc(T(order[0]).name)}</b> lead the ladder. Biggest climb: <b>${esc(T(best.t).name)}</b> (${sign(best.d)}). Biggest fall: <b>${esc(T(worst.t).name)}</b> (${sign(worst.d)}).`;
    const tr = sel => animate && !REDUCED ? sel.transition().duration(800).ease(d3.easeCubicOut) : sel;
    tr(clip).attr('width', x(i) + 4);
    tr(cursor).attr('x1', x(i)).attr('x2', x(i));
    tr(dots).attr('cx', x(i)).attr('cy', t => y(R.by_team[t][i]));
    // right-edge labels: top 4 and bottom 1, de-collided
    const show = new Set([...order.slice(0, 4), order.at(-1)]); let prev = -1e9;
    const pos = {}; order.forEach(t => { if (!show.has(t)) return; const yy = Math.max(y(R.by_team[t][i]), prev + 14); pos[t] = yy; prev = yy; });
    labs.classed('hi', t => t === order[0]).style('display', t => show.has(t) ? null : 'none');
    tr(labs.filter(t => show.has(t))).attr('x', x(i) + 10).attr('y', t => pos[t] + 4);
  }
  slider.oninput = () => { stop(); set(slider.value); };
  const stop = () => { clearInterval(state.timer); state.timer = null; btn.textContent = '▶'; };
  btn.onclick = () => {
    if (state.timer) return stop();
    if (+slider.value >= last) set(0);
    btn.textContent = '❚❚';
    state.timer = setInterval(() => { const n = +slider.value + 1; if (n > last) return stop(); set(n); }, 1150);
  };
  set(last, false);
  return { play: () => btn.click() };
}

/* ── generic scatter ── */
function scatter(host, pts, o) {
  const W = o.w || 640, H = o.h || 400, m = { t: 14, r: 20, b: 40, l: 46 };
  const svg = d3.select(host).append('svg').attr('viewBox', `0 0 ${W} ${H}`);
  const x = d3.scaleLinear(d3.extent(pts, d => d.x), [m.l, W - m.r]).nice(), y = d3.scaleLinear(o.yDomain || d3.extent(pts, d => d.y), [H - m.b, m.t]).nice();
  svg.append('g').attr('class', 'grid').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat(''));
  svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l - 4},0)`).call(d3.axisLeft(y).ticks(5).tickSize(0).tickFormat(o.yf || (d => d)));
  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b + 6})`).call(d3.axisBottom(x).ticks(6).tickSize(0).tickFormat(o.xf || (d => d)));
  svg.append('text').attr('x', (m.l + W - m.r) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text(o.xl || '');
  svg.append('text').attr('transform', `translate(12,${(m.t + H - m.b) / 2}) rotate(-90)`).attr('text-anchor', 'middle').text(o.yl || '');
  if (o.hline != null) svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(o.hline)).attr('y2', y(o.hline)).attr('stroke', '#475569').attr('stroke-dasharray', '3 4');
  if (o.vline != null) svg.append('line').attr('y1', m.t).attr('y2', H - m.b).attr('x1', x(o.vline)).attr('x2', x(o.vline)).attr('stroke', '#475569').attr('stroke-dasharray', '3 4');
  let trend;
  if (o.trend) { const n = pts.length, sx = d3.sum(pts, d => d.x), sy = d3.sum(pts, d => d.y), sxy = d3.sum(pts, d => d.x * d.y), sxx = d3.sum(pts, d => d.x * d.x);
    const b = (n * sxy - sx * sy) / (n * sxx - sx * sx), a = (sy - b * sx) / n, [x0, x1] = x.domain();
    trend = svg.append('line').attr('x1', x(x0)).attr('x2', x(x0)).attr('y1', y(a + b * x0)).attr('y2', y(a + b * x0)).attr('stroke', '#94a3b8').attr('stroke-dasharray', '5 5').attr('stroke-width', 1.5);
    trend.t = () => trend.transition().delay(700).duration(900).attr('x2', x(x1)).attr('y2', y(a + b * x1)); o.onTrend?.(a, b); }
  const c = svg.selectAll('circle.p').data(pts).join('circle').attr('class', 'p').attr('cx', d => x(d.x)).attr('cy', y(o.from ?? y.domain()[0])).attr('r', 0)
    .attr('fill', d => d.color).attr('stroke', '#080b12').attr('stroke-width', 1.5).attr('opacity', .88).style('cursor', 'default');
  withTip(c, d => d.tip);
  const lab = svg.selectAll('text.lab').data(pts.filter(d => d.label)).join('text').attr('class', 'lab').attr('text-anchor', 'middle').attr('x', d => x(d.x)).attr('y', d => y(d.y) - (d.r || 6) - 5).attr('opacity', 0).text(d => d.label);
  const go = () => { c.transition().duration(REDUCED ? 0 : 900).delay((d, i) => REDUCED ? 0 : i * 6).ease(d3.easeCubicOut).attr('cy', d => y(d.y)).attr('r', d => d.r || 6); lab.transition().delay(REDUCED ? 0 : 900).duration(400).attr('opacity', 1); trend?.t(); };
  host.closest('.rv') ? host.closest('.rv').addEventListener('reveal', go, { once: true }) : go();
}

/* ════════════ pages ════════════ */
const pages = {};

pages.overview = el => {
  const D = state.D, k = D.kpi, w = D.weeks.at(-1), wk = D.weekly[w];
  const up = D.series.filter(s => s.status === 'SCHEDULED');
  const future = up.filter(s => s.week > w), nextWk = future.length ? Math.min(...future.map(s => s.week)) : null;
  const next = nextWk ? up.filter(s => s.week === nextWk) : up;
  el.innerHTML = `
    <div class="banner"><div><h1>${esc(D.name)}</h1><p>${D.active ? `Week ${w} in the books` : 'Final'} · ${liveTeams().length} teams · ${D.spots} playoff spots${D.fearless ? ' · fearless draft' : ''}</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <div class="chyrons rv">
      ${chyron('Games played', k.games, `${k.series} series`, { to: k.games })}
      ${chyron('Avg game time', clock(k.avg_time), `longest ${clock(k.max_time)}`, { cls: 'white' })}
      ${chyron('Blue side wins', pct(k.blue), `${k.side_games} games`, { to: k.blue * 100, suf: '%', cls: 'white' })}
      ${chyron('Champions played', k.champs, `most picked: ${esc(k.top_champ)} (${k.top_champ_n})`, { to: k.champs, cls: 'white' })}
      ${chyron('Pentakills', k.pentas, `${k.quadras} quadras`, { to: k.pentas })}
    </div>
    <h2>The season, replayed <small>power ratings week by week — press play</small></h2>
    <div id="replay"></div>
    <div class="cols w32 rv">
      <div><h2>Standings <small>dashed line = playoff cut</small></h2><div id="st"></div></div>
      <div><h2>Week ${w} storylines</h2>${stories(wk.stories, 5)}</div>
    </div>
    ${D.active && next.length ? `<h2>${nextWk ? 'Up next — week ' + nextWk : 'Still to play'} <small>model = Glicko-2 series odds · crowd = Crystal Ball picks</small></h2><div class="grid rv">${next.map(forecastCard).join('')}</div>` : ''}
    ${D.title ? `<h2>Title odds <small>${D.bracket_real ? 'the real bracket' : 'projected bracket'}, simulated · <a href="#/${state.band.toLowerCase()}/${state.sid}/playoffs" style="color:var(--gold)">full bracket →</a></small></h2><div id="tmini"></div>` : ''}
    ${!D.active && D.champion ? `<h2>Champion</h2><div class="hero rv"><div class="k">${esc(D.name)}</div><div class="n">🏆 ${esc(T(D.champion).name)}</div></div>` : ''}
    <h2>Week ${w} results</h2><div class="grid rv">${D.series.filter(s => s.week === w && s.status === 'COMPLETED').map(bug).join('')}</div>`;
  if (D.ratings.weeks.length > 1) replay($('#replay', el)); else $('#replay', el).innerHTML = '<p class="note">Ratings appear after week 1.</p>';
  standingsBlock($('#st', el), w, { compact: true });
  if (D.title) $('#tmini', el).innerHTML = hbars(D.title.odds.filter(o => o.win > 0).slice(0, 8).map(o => ({ label: T(o.t).name, value: o.win, text: pct(o.win, 1), color: T(o.t).color })));
};

pages.standings = el => {
  const D = state.D;
  const drops = Object.values(D.teams).filter(t => t.dropped).map(t => `${esc(t.name)} (${t.drop_mode})`);
  el.innerHTML = `
    <div class="banner"><div><h1>Standings</h1><p>Ranked exactly the way the league site ranks them</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <h2>Standings <small>drag the week to rewind the table · click a team for its profile</small></h2>
    <div class="player"><div class="wk" id="swk"></div><input type="range" id="sw" min="0" max="${D.weeks.length - 1}" value="${D.weeks.length - 1}"></div>
    <div id="st"></div>
    <p class="note"><b>Tiebreakers:</b> ${D.tiebreakers.map(esc).join(' → ')}.${D.cross_group ? `<br><b>Seeding:</b> each group sends its top ${D.spots / 2}, ranked on in-group series only; seeds alternate between groups so round one is always cross-group. Out-of-group weeks are exhibitions.` : ''}
    ${drops.length ? `<br><b>Dropped:</b> ${drops.join(', ')}. A void drop removes every series against that team; a forfeit drop credits each opponent a series win with no games.` : ''}
    <br><b>=</b> marks teams still level after every tiebreaker this page can compute.</p>
    <p class="note"><a href="#/${state.band.toLowerCase()}/${state.sid}/playoffs" style="color:var(--gold)">Playoff odds and the bracket →</a></p>`;
  const sw = $('#sw', el), host = $('#st', el);
  const set = () => { const w = D.weeks[+sw.value]; $('#swk', el).textContent = 'WEEK ' + w; standingsBlock(host, w); };
  sw.oninput = set; set();
};

pages.recap = el => {
  const D = state.D; if (state.week == null || !D.weekly[state.week]) state.week = D.weeks.at(-1);
  const w = state.week, wk = D.weekly[w], top = wk.potw[0];
  const ser = D.series.filter(s => s.week === w && s.status === 'COMPLETED');
  el.innerHTML = `
    <div class="banner"><div><h1>Weekly Recap</h1><p>${esc(D.name)}</p></div><div class="badge">WEEK ${w}</div></div>
    <div class="pills" id="wks">${D.weeks.map(x => `<button class="${x === w ? 'on' : ''}" data-w="${x}">W${x}</button>`).join('')}</div>
    <div class="chyrons rv">${chyron('Games', wk.games, `${ser.length} series`, { to: wk.games })}${chyron('Avg game time', clock(wk.avg_time), '', { cls: 'white' })}
      ${chyron('Kills per game', num(wk.kills, 1), 'both teams', { to: wk.kills, dec: 1, cls: 'white' })}${chyron('Blue side wins', pct(wk.blue), '', { to: (wk.blue || 0) * 100, suf: '%', cls: 'white' })}
      ${chyron('Sweeps', ser.filter(s => !s.s1 || !s.s2).length, 'of ' + ser.length + ' series', { to: ser.filter(s => !s.s1 || !s.s2).length, cls: 'white' })}</div>
    <h2>Results</h2><div class="grid rv">${ser.map(bug).join('') || '<p class="note">No completed series.</p>'}</div>
    <div class="cols rv"><div><h2>Storylines</h2>${stories(wk.stories, 8)}</div>
    <div><h2>Player of the week <small>Impact Factor, ranked within role</small></h2>
      ${top ? `<div class="hero"><div class="k">Player of the week</div><div class="n">${esc(top.player)}</div><div class="m"><img alt="" data-champ="${esc(top.champ_key)}">${dot(top.team_id)}${esc(top.team)} · ${ROLE[top.role] || ''} · ${esc(top.champs)}</div>
        <div class="big" data-to="${top.impact}">0</div><div class="k">Impact factor</div>
        <div class="stats"><div>${top.k}/${top.d}/${top.a}<small>K / D / A</small></div><div>${num(top.kda, 1)}<small>KDA</small></div><div>${pct(top.kp)}<small>Kill part.</small></div><div>${top.wins}–${top.games - top.wins}<small>Games</small></div></div></div>
        <div style="margin-top:10px">${hbars(wk.potw.slice(1, 8).map(p => ({ label: `${p.player} · ${ROLE[p.role] || ''}`, value: p.impact, text: `${num(p.impact)}  ·  ${p.k}/${p.d}/${p.a}`, title: `${p.team} — ${p.champs}` })), { title: 'The chasing pack' })}</div>` : '<p class="note">No player stats this week.</p>'}</div></div>
    <h2>Game lengths <small>every game of the week, coloured by winner</small></h2><div class="panel rv" id="dur"></div>
    ${wk.multikills.length ? `<h2>Multi-kills</h2><div class="grid rv">${wk.multikills.map(m => `<div class="story"><div class="t">${m.kind.toUpperCase()} KILL</div><div class="x"><b>${esc(m.player)}</b> (${esc(m.champ)}, ${esc(T(m.team).name)}) vs ${esc(T(m.opp).name)}</div></div>`).join('')}</div>` : ''}`;
  el.querySelectorAll('#wks button').forEach(b => b.onclick = () => { state.week = +b.dataset.w; render(); });
  const dur = wk.durations; if (dur.length) {
    const W = 1100, H = 110, x = d3.scaleLinear([d3.min(dur, d => d.s) / 60 - 1, d3.max(dur, d => d.s) / 60 + 1], [30, W - 30]);
    const svg = d3.select('#dur').append('svg').attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - 22})`).call(d3.axisBottom(x).ticks(8).tickSize(0).tickFormat(d => d + ' min'));
    svg.append('line').attr('x1', 30).attr('x2', W - 30).attr('y1', 50).attr('y2', 50).attr('stroke', '#1e293b');
    const c = svg.selectAll('circle').data(dur).join('circle').attr('cx', 30).attr('cy', (d, i) => 50 + ((i * 37) % 30) - 15).attr('r', 8).attr('fill', d => T(d.w).color).attr('stroke', '#080b12').attr('stroke-width', 2);
    c.transition().duration(REDUCED ? 0 : 1100).delay((d, i) => REDUCED ? 0 : i * 40).ease(d3.easeCubicOut).attr('cx', d => x(d.s / 60));
    withTip(c, d => `<b>${esc(T(d.w).name)}</b> beat ${esc(T(d.l).name)}<br>${clock(d.s)}`);
  } else $('#dur').innerHTML = '<p class="note">No game lengths recorded.</p>';
};

pages.players = el => {
  const D = state.D, all = D.players || [], maxG = Math.max(...all.map(p => p.games), 1);
  const f = { role: 'ALL', min: Math.min(Math.max(3, Math.floor(maxG / 4)), maxG), q: '' };
  el.innerHTML = `
    <div class="banner"><div><h1>Players</h1><p>${all.length} players · KDA on season totals, like the league site</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <div class="pills" id="pf">${['ALL', ...Object.keys(ROLE)].map(r => `<button data-r="${r}" class="${r === 'ALL' ? 'on' : ''}">${ROLE[r] || 'All'}</button>`).join('')}
      <label>Min games <b id="mg">${f.min}</b></label><input type="range" id="min" min="1" max="${maxG}" value="${f.min}" style="width:150px">
      <input type="search" id="q" placeholder="Find a player or team…" style="margin-left:auto"></div>
    <div id="tbl"></div><p class="note">Click a player for their profile.</p>
    <div class="cols rv"><div><h2>Lane bullies <small>avg gold lead on the lane opponent at 15:00</small></h2><div id="lane"></div></div>
    <div><h2>Price vs. production <small>above the line = bargain</small></h2><div class="panel"><div id="val"></div><p class="note" id="valnote"></p></div></div></div>`;
  const cols = [
    { k: 'player', label: 'Player', cls: 'team', html: r => `${dot(r.team_id)}${esc(r.player)}` }, { k: 'team', label: 'Team' }, { k: 'role', label: 'Role', f: v => ROLE[v] || '–' },
    { k: 'games', label: 'GP', num: 1 }, { k: 'wins', label: 'W', num: 1 },
    { k: 'impact', label: 'Impact', num: 1, tip: 'Season Impact Factor (within-role percentile mix)', html: r => cellBar(r.impact || 0, 100, num(r.impact)) },
    { k: 'kda', label: 'KDA', num: 1, f: v => num(v, 2) }, { k: 'k_g', label: 'K', num: 1, f: v => num(v, 1) }, { k: 'd_g', label: 'D', num: 1, f: v => num(v, 1) }, { k: 'a_g', label: 'A', num: 1, f: v => num(v, 1) },
    { k: 'kp', label: 'KP%', num: 1, f: v => pct(v) }, { k: 'dmg_min', label: 'DPM', num: 1, f: v => num(v) }, { k: 'gold_min', label: 'GPM', num: 1, f: v => num(v) }, { k: 'cs_min', label: 'CS/m', num: 1, f: v => num(v, 1) },
    { k: 'vis_min', label: 'Vis/m', num: 1, f: v => num(v, 2) }, { k: 'gd15', label: 'GD@15', num: 1, tip: 'Gold difference vs. the lane opponent at 15:00', f: v => v == null ? '–' : sign(v) },
    { k: 'salary', label: 'Salary', num: 1, f: v => v ?? '–' }, { k: 'main', label: 'Main' }];
  const draw = () => {
    const rows = all.filter(p => p.games >= f.min && (f.role === 'ALL' || p.role === f.role) && (!f.q || (p.player + ' ' + p.team).toLowerCase().includes(f.q)));
    sortable($('#tbl', el), cols, rows, { key: 'impact', rank: true, limit: 25, onRow: playerProfile });
    const lane = rows.filter(p => p.gd15 != null && p.lane_games >= 3).sort((a, b) => b.gd15 - a.gd15).slice(0, 10);
    $('#lane', el).innerHTML = lane.length ? hbars(lane.map(p => ({ label: `${p.player} · ${ROLE[p.role] || ''}`, value: p.gd15, text: sign(p.gd15), color: 'var(--blue)', title: `${p.team}: ${sign(p.csd15, 1)} CS over ${p.lane_games} games` }))) : '<p class="note">No 15-minute data for this selection.</p>';
    $('#lane .rv', el)?.classList.add('in'); $('#lane', el).querySelectorAll('[data-w]').forEach(b => requestAnimationFrame(() => b.style.width = b.dataset.w));
  };
  el.querySelectorAll('#pf button').forEach(b => b.onclick = () => { f.role = b.dataset.r; el.querySelectorAll('#pf button').forEach(x => x.classList.toggle('on', x === b)); draw(); });
  $('#min', el).oninput = e => { f.min = +e.target.value; $('#mg', el).textContent = f.min; draw(); };
  $('#q', el).oninput = e => { f.q = e.target.value.trim().toLowerCase(); draw(); };
  draw();
  const v = all.filter(p => p.salary > 0 && p.impact != null && p.games >= f.min);
  if (v.length > 5) {
    let A = 0, B = 0;
    const tmp = { onTrend: (a, b) => { A = a; B = b; } };
    // label the biggest over- and under-performers vs. the trend
    const n = v.length, sx = d3.sum(v, d => d.salary), sy = d3.sum(v, d => d.impact), sxy = d3.sum(v, d => d.salary * d.impact), sxx = d3.sum(v, d => d.salary ** 2);
    B = (n * sxy - sx * sy) / (n * sxx - sx * sx); A = (sy - B * sx) / n;
    const res = v.map(p => ({ p, r: p.impact - (A + B * p.salary) })).sort((a, b) => b.r - a.r);
    const tag = new Set([...res.slice(0, 4), ...res.slice(-2)].map(x => x.p.player));
    scatter($('#val', el), v.map(p => ({ x: p.salary, y: p.impact, color: ROLE_COLOR[p.role] || '#64748b', label: tag.has(p.player) ? p.player : '', tip: `<b>${esc(p.player)}</b> · ${ROLE[p.role] || ''} · ${esc(p.team)}<br>Salary ${p.salary} · Impact ${num(p.impact)} · ${p.games} games` })),
      { xl: 'Salary', yl: 'Season Impact', trend: true, h: 380, ...tmp });
    $('#valnote', el).innerHTML = `Each extra salary point buys about <b>${sign(B, 1)}</b> Impact across the league. Best value: ${res.slice(0, 3).map(x => `<b>${esc(x.p.player)}</b> (${sign(x.r)})`).join(', ')}. ` + Object.entries(ROLE).map(([k, s]) => `<span style="color:${ROLE_COLOR[k]}">●</span> ${s}`).join(' ');
  } else $('#val', el).innerHTML = '<p class="note">Not enough players with a salary on file.</p>';
};

pages.teams = el => {
  const D = state.D, ts = (D.team_stats || []).map(t => ({ ...t, team: T(t.team_id).name }));
  el.innerHTML = `
    <div class="banner"><div><h1>Teams</h1><p>How each team actually plays</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <div class="cols w32 rv"><div><h2>Early game vs. results <small>who closes, who throws</small></h2><div class="panel"><div id="quad"></div></div></div>
    <div><h2>Is a lead at 15:00 safe?</h2><div id="lead"></div><p class="note">Win rate of the team ahead on gold at 15 minutes, by the size of the lead.</p></div></div>
    <h2>Every team <small>per-game averages · click a row for the team profile</small></h2><div id="tbl"></div>`;
  const q = ts.filter(t => t.gd15 != null);
  if (q.length) scatter($('#quad', el), q.map(t => ({ x: t.gd15, y: t.win_pct * 100, r: 8, color: T(t.team_id).color, label: T(t.team_id).name, tip: `<b>${esc(t.team)}</b><br>${sign(t.gd15)} gold at 15 · ${pct(t.win_pct)} wins (${t.games} games)` })),
    { xl: 'Team gold difference at 15:00', yl: 'Game win rate', yf: d => d + '%', xf: d => sign(d), hline: 50, vline: 0, h: 420, from: 50 });
  else $('#quad', el).innerHTML = '<p class="note">No 15-minute data for this season.</p>';
  $('#lead', el).innerHTML = (D.lead || []).length ? hbars(D.lead.map(l => ({ label: l.bucket + ' gold', value: l.wr, text: `${pct(l.wr)}  ·  ${l.games} games` }))) : '<p class="note">No 15-minute data for this season.</p>';
  sortable($('#tbl', el), [
    { k: 'team', label: 'Team', cls: 'team', html: r => `${dot(r.team_id)}${esc(r.team)}` }, { k: 'games', label: 'GP', num: 1 }, { k: 'win_pct', label: 'Win%', num: 1, f: v => pct(v) },
    { k: 'kills', label: 'Kills', num: 1, f: v => num(v, 1) }, { k: 'deaths', label: 'Deaths', num: 1, f: v => num(v, 1) }, { k: 'gd15', label: 'GD@15', num: 1, f: v => v == null ? '–' : sign(v) },
    { k: 'fb', label: 'FB%', num: 1, tip: 'First blood rate', f: v => pct(v) }, { k: 'ft', label: 'FT%', num: 1, tip: 'First tower rate', f: v => pct(v) },
    { k: 'dragons', label: 'Drakes', num: 1, f: v => num(v, 1) }, { k: 'barons', label: 'Barons', num: 1, f: v => num(v, 1) }, { k: 'turrets', label: 'Turrets', num: 1, f: v => num(v, 1) },
    { k: 'vis_min', label: 'Vis/m', num: 1, f: v => num(v, 1) }, { k: 'blue_wr', label: 'Blue W%', num: 1, f: v => pct(v) }, { k: 'red_wr', label: 'Red W%', num: 1, f: v => pct(v) },
    { k: 'champ_pool', label: 'Champs', num: 1 }, { k: 'mins', label: 'Avg time', num: 1, f: v => clock(v * 60) }], ts, { key: 'win_pct', onRow: r => teamProfile(r.team_id) });
};

pages.playoffs = el => {
  const D = state.D, P = D.playoff, TT = D.title;
  const fav = TT?.odds[0], alive = TT ? TT.odds.filter(o => o.win > 0).length : 0;
  const fmtName = f => ({ BEST_OF_1: 'Bo1', BEST_OF_3: 'Bo3', BEST_OF_5: 'Bo5' }[f] || f);
  el.innerHTML = `
    <div class="banner"><div><h1>Playoffs</h1><p>${TT ? (D.bracket_real ? 'The real bracket, simulated ' + num(TT.n_sims) + ' times' : 'Projected bracket from today\'s standings') : D.active ? 'Race for the bracket' : 'How it finished'}</p></div><div class="badge ${D.band}">${D.band}</div></div>
    ${TT ? `<div class="chyrons rv">${chyron('Title favourite', esc(T(fav.t).name), pct(fav.win, 1) + ' to win it all', { cls: 'sm' })}
      ${chyron('Favourite\'s odds', pct(fav.win), 'nobody is a lock', { to: fav.win * 100, suf: '%', cls: 'white' })}
      ${chyron('Teams with a path', alive, `of ${TT.odds.length} in the field`, { to: alive, cls: 'white' })}
      ${chyron('Rounds', TT.n_rounds, TT.rounds.map(r => fmtName(r.matches[0]?.fmt)).join(' · '), { cls: 'white' })}</div>
    <h2>Title odds <small>chance to reach each round · click a column to sort</small></h2><div id="odds"></div>
    <h2>The bracket <small>bars = model's chance to win the series</small></h2><div class="brk rv" id="brk"></div>
    <p class="note">Each series is rolled from the calibrated Glicko-2 per-game odds at the series' real format. Completed series keep their actual result. Where a slot is still open, the three most likely teams to fill it are listed.</p>` : ''}
    ${P ? `<h2>Race for the playoffs <small>${P.remaining.length ? P.remaining.length + ' counting series left' : 'regular season complete — field is set'}</small></h2>
      <div class="cols w23"><div><h3>Make the playoffs</h3><div id="mk"></div></div><div><h3>Where each team finishes — % of simulations by seed</h3><div id="heat"></div></div></div>
      ${P.pins ? `<h2>What if? <small>pin results and watch the odds move</small></h2><div class="panel" id="pins"></div><p class="note" id="pinnote"></p>` : ''}
      ${P.leverage.length ? '<h2>Games that matter most</h2><div class="grid">' + P.leverage.map(l => `<div class="story"><div class="t">WEEK ${l.week}</div><div class="x"><b>${esc(l.t1)} vs ${esc(l.t2)}</b> — ${esc(T(l.team_id).name)} make the playoffs in <b>${pct(l.if_t1)}</b> of sims if ${esc(l.t1)} win, <b>${pct(l.if_t2)}</b> if ${esc(l.t2)} win.</div></div>`).join('') + '</div>' : ''}
      <p class="note">${P.remaining.length ? `${num(P.n_sims)} simulations of the remaining regular season, each series rolled to an exact score because game wins are the first tiebreaker. IN / OUT means every simulation agreed — not a mathematical clinch.` : 'The regular season is over, so these are final: seeds follow the site\'s tiebreakers.'}</p>` : ''}
    ${D.playoff_results.length ? `<h2>Playoff results</h2><div class="grid rv">${D.playoff_results.map(bug).join('')}</div>` : ''}
    ${!TT && !P && !D.playoff_results.length ? '<p class="note">No playoff data for this season.</p>' : ''}`;
  if (TT) {
    const rs = d3.range(2, TT.n_rounds + 1), rows = TT.odds.map(o => ({ t: o.t, team: T(o.t).name, rating: o.rating, win: o.win, ...Object.fromEntries(rs.map(r => ['r' + r, o.reach[r] ?? 0])) }));
    sortable($('#odds', el), [{ k: 'team', label: 'Team', cls: 'team', html: r => `${dot(r.t)}${esc(r.team)}` }, { k: 'rating', label: 'Rating', num: 1, f: v => num(v) },
      ...rs.map(r => ({ k: 'r' + r, label: TT.names[r], num: 1, f: v => v >= .9995 ? '✓' : v <= 0 ? '–' : pct(v) })),
      { k: 'win', label: 'Win title', num: 1, html: r => cellBar(r.win, Math.max(...rows.map(x => x.win)), pct(r.win, 1)) }], rows, { key: 'win', rank: true, onRow: r => teamProfile(r.t) });
    const line = (t, p, s, won, done) => t ? `<div class="bl ${won ? 'w' : done ? 'l' : ''}">${dot(t)}<span class="n">${esc(T(t).name)}</span>${done ? `<b>${s}</b>` : p != null ? `<span class="bp"><i data-w="${Math.round(p * 100)}%"></i><em>${Math.round(p * 100)}%</em></span>` : ''}</div>` : '';
    $('#brk', el).style.gridTemplateColumns = `repeat(${TT.n_rounds}, minmax(200px, 1fr))`;
    $('#brk', el).innerHTML = TT.rounds.map(r => `<div class="bcol"><h3>${esc(r.name)} · ${fmtName(r.matches[0]?.fmt)}</h3>${r.matches.map(m => { const done = m.status === 'COMPLETED';
      return `<div class="bm">${line(m.t1, m.p1, m.s1, m.winner === m.t1, done)}${line(m.t2, m.p1 == null ? null : 1 - m.p1, m.s2, m.winner === m.t2, done)}
        ${m.likely.length ? `<div class="bl tbd">${m.t1 || m.t2 ? 'vs' : 'likely'} ${m.likely.map(x => `${esc(T(x.t).name)} <em>${Math.round(x.p * 100)}%</em>`).join(' · ')}</div>` : ''}</div>`; }).join('')}</div>`).join('');
  }
  if (P) {
    const cols = P.spots + 1, heat = $('#heat', el), mk = $('#mk', el);
    const drawMake = probs => { mk.innerHTML = hbars(probs.map(t => ({ label: T(t.t).name, value: Math.max(t.make, .004), text: t.make >= .9995 ? 'IN' : t.make <= .0005 ? 'OUT' : pct(t.make), color: T(t.t).color }))); mk.querySelector('.rv').classList.add('in'); mk.querySelectorAll('[data-w]').forEach(b => requestAnimationFrame(() => b.style.width = b.dataset.w)); };
    const drawHeat = (probs, anim) => { const rows = probs.filter((t, i) => t.make > 0 || i < P.spots + 3);
      heat.className = 'heat'; heat.style.gridTemplateColumns = `minmax(100px,160px) repeat(${cols}, 1fr)`;
      heat.innerHTML = '<div></div>' + d3.range(1, cols).map(i => `<div class="hh">${i}</div>`).join('') + '<div class="hh">MISS</div>' +
        rows.map((t, ri) => `<div class="hn">${esc(T(t.t).name)}</div>` + [...t.seeds, t.miss].map((p, ci) => { const a = Math.pow(p, .6); return `<div class="c" title="${esc(T(t.t).name)} · ${ci < cols - 1 ? 'seed ' + (ci + 1) : 'miss'}: ${(p * 100).toFixed(1)}%" style="${anim ? `animation-delay:${ri * 30 + ci * 18}ms` : 'animation:none;opacity:1'};background:${p > .004 ? `rgba(255,215,0,${(0.1 + a * 0.9).toFixed(2)})` : '#141b2b'};color:${a > .55 ? '#080b12' : '#f1f5f9'}">${p >= .005 ? Math.round(p * 100) : ''}</div>`; }).join('')).join(''); };
    drawMake(P.teams); drawHeat(P.teams, true);
    if (P.pins) {
      const X = P.pins, pin = {};
      $('#pins', el).innerHTML = P.remaining.map((r, i) => `<div class="pinrow" data-i="${i}"><span class="pw">W${r.week}</span><button data-v="1">${esc(T(r.t1Id).name)} <em>${Math.round(r.p_t1 * 100)}%</em></button><button data-v="" class="on">no pin</button><button data-v="0">${esc(T(r.t2Id).name)} <em>${Math.round((1 - r.p_t1) * 100)}%</em></button></div>`).join('');
      const recompute = () => {
        const keep = []; for (let k = 0; k < X.n; k++) { let ok = true; for (const i in pin) if (X.outcomes[i][k] !== pin[i]) { ok = false; break; } if (ok) keep.push(k); }
        const n = keep.length, pinned = Object.keys(pin).length;
        $('#pinnote', el).innerHTML = pinned ? `<b>${pinned} pinned</b> — ${num(n)} of ${num(X.n)} simulations match.${n < 60 ? ' Too few to trust; unpin something.' : ''}` : 'Nothing pinned. Click a team to lock in that result.';
        if (!n) return;
        const probs = X.teams.map((t, ti) => { const seeds = new Array(P.spots).fill(0); let miss = 0, sum = 0; for (const k of keep) { const s = X.seeds[ti].charCodeAt(k) - 48; sum += s; if (s > P.spots) miss++; else seeds[s - 1]++; } return { t, make: 1 - miss / n, miss: miss / n, avg_seed: sum / n, seeds: seeds.map(v => v / n) }; }).sort((a, b) => a.avg_seed - b.avg_seed);
        drawMake(probs); drawHeat(probs, false);
      };
      $('#pins', el).querySelectorAll('.pinrow').forEach(row => row.querySelectorAll('button').forEach(b => b.onclick = () => { row.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); if (b.dataset.v === '') delete pin[row.dataset.i]; else pin[row.dataset.i] = b.dataset.v; recompute(); }));
      recompute();
    }
  }
};

pages.champions = el => {
  const D = state.D, ch = D.champions || [], X = D.champ_x || {}, dr = D.draft || {}, played = ch.filter(c => c.picks > 0);
  const banned = [...ch].sort((a, b) => b.bans - a.bans), names = Object.keys(X.explore || {}).sort();
  const rec = (g, w) => `${w}–${g - w}`;
  el.innerHTML = `
    <div class="banner"><div><h1>Champions</h1><p>Presence = picked or banned</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <div class="chyrons rv">${chyron('Champions played', played.length, X.pool_size ? `of ${X.pool_size} in the game` : `${ch.length} picked or banned`, { to: played.length })}
      ${chyron('Most contested', esc(ch[0]?.name), pct(ch[0]?.presence) + ' presence', { cls: 'white sm' })}
      ${chyron('Most banned', banned[0]?.bans ? esc(banned[0].name) : '–', banned[0]?.bans ? banned[0].bans + ' bans' : 'no ban data', { cls: 'white sm' })}
      ${chyron('Never touched', X.pool_size ? X.never.length : '–', 'not picked, not banned', { to: X.pool_size ? X.never.length : null, cls: 'white' })}
      ${chyron('Blue side wins', pct(dr.blue), `${dr.games} games`, { to: (dr.blue || 0) * 100, suf: '%', cls: 'white' })}</div>
    <h2>What happens when a team picks… <small>choose a champion</small></h2>
    <div class="pills"><select id="cx">${names.map(n => `<option>${esc(n)}</option>`).join('')}</select><span class="note" style="margin:0 0 0 8px">Champions with 3+ games.</span></div><div id="cxcard"></div>
    <div class="cols w32 rv"><div><h2>Contested vs. winning <small>bubble = games played</small></h2><div class="panel"><div id="sc"></div></div></div>
    <div><h2>Most reliable winners</h2><div id="rel"></div><p class="note">Ranked by the low end of a 95% interval, so a 2–0 fluke can't top the list.</p></div></div>
    <h2>Every champion <small>click a column to sort</small></h2><div id="tbl"></div>
    <div class="cols rv"><div><h2>Best duos <small>same team, 4+ games together</small></h2><div id="duo"></div></div>
    <div><h2>Lopsided lanes <small>same role, 3+ meetings</small></h2><div id="mu"></div></div></div>
    <div class="cols rv"><div><h2>Signature picks <small>most games by one player on one champion</small></h2><div id="sig"></div></div>
    <div><h2>Left on the bench</h2>${X.pool_size ? `<h3>Never picked or banned (${X.never.length})</h3><div class="chips">${X.never.map(n => `<span>${esc(n)}</span>`).join('') || '<span>none — everything saw play</span>'}</div>
      <h3 style="margin-top:14px">Banned but never played (${(X.never_picked_only || []).length})</h3><div class="chips">${(X.never_picked_only || []).map(n => `<span class="b">${esc(n)}</span>`).join('') || '<span>none</span>'}</div>` : '<p class="note">Champion list unavailable for this build.</p>'}</div></div>`;
  const card = n => { const c = X.explore[n]; if (!c) { $('#cxcard', el).innerHTML = ''; return; }
    const li = (xs, f) => xs.length ? xs.map(f).join('') : '<div class="kv"><span>not enough games</span></div>';
    $('#cxcard', el).innerHTML = `<div class="cx"><div class="hero"><div class="k">${ROLE[c.role] || ''} · picked ${c.g} times${c.bans ? ' · banned ' + c.bans : ''}</div><div class="n">${esc(n)}</div>
        <div class="m"><img alt="" data-champ="${esc(c.key)}">Teams that pick it win</div><div class="big" data-to="${(c.w / c.g * 100).toFixed(0)}" data-suf="%">0</div>
        <div class="stats"><div>${rec(c.g, c.w)}<small>Record</small></div><div>${c.blue[1] ? pct(c.blue[0] / c.blue[1]) : '–'}<small>Blue side (${c.blue[1]})</small></div><div>${c.red[1] ? pct(c.red[0] / c.red[1]) : '–'}<small>Red side (${c.red[1]})</small></div>
        <div>${c.mins ? num(c.mins, 1) + 'm' : '–'}<small>Avg game</small></div><div>${c.slot ? num(c.slot, 1) : '–'}<small>Avg pick slot</small></div></div></div>
      <div class="panel"><h3>Who plays it</h3>${li(c.players, p => `<div class="kv"><span>${esc(p.p)}</span><b>${rec(p.g, p.w)}</b></div>`)}
        <h3 style="margin-top:12px">Wins most alongside</h3>${li(c.with, p => `<div class="kv"><span>${esc(p.c)}</span><b>${rec(p.g, p.w)}</b></div>`)}</div>
      <div class="panel"><h3>Lane matchups it wins</h3>${li(c.beats.filter(p => p.w / p.g > .5), p => `<div class="kv"><span>vs ${esc(p.c)}</span><b class="up">${rec(p.g, p.w)}</b></div>`)}
        <h3 style="margin-top:12px">Lane matchups it loses</h3>${li(c.loses.filter(p => p.w / p.g < .5), p => `<div class="kv"><span>vs ${esc(p.c)}</span><b class="down">${rec(p.g, p.w)}</b></div>`)}</div></div>`;
    $('#cxcard', el).querySelectorAll('[data-to]').forEach(countUp); champIcons(); };
  if (names.length) { const first = ch.find(c => X.explore[c.name])?.name || names[0]; $('#cx', el).value = first; $('#cx', el).onchange = e => card(e.target.value); card(first); }
  const min = Math.min(5, Math.max(...played.map(c => c.picks), 1)), sc = played.filter(c => c.picks >= min);
  const lab = new Set([...[...sc].sort((a, b) => b.presence - a.presence).slice(0, 7), ...[...sc].sort((a, b) => Math.abs(b.wr - .5) * Math.sqrt(b.picks) - Math.abs(a.wr - .5) * Math.sqrt(a.picks)).slice(0, 5)].map(c => c.name));
  scatter($('#sc', el), sc.map(c => ({ x: c.presence * 100, y: c.wr * 100, r: Math.max(4, Math.sqrt(c.picks) * 2.4), color: c.wr >= .5 ? '#4f8ff7' : '#e5484d', label: lab.has(c.name) ? c.name : '', tip: `<b>${esc(c.name)}</b><br>${c.wins}W in ${c.picks} games (${pct(c.wr)})<br>${c.bans} bans · ${pct(c.presence)} presence` })),
    { xl: 'Presence (pick + ban)', yl: 'Win rate', xf: d => d + '%', yf: d => d + '%', hline: 50, yDomain: [0, 100], h: 400, from: 50 });
  $('#rel', el).innerHTML = hbars([...sc].sort((a, b) => b.wlo - a.wlo).slice(0, 10).map(c => ({ label: c.name, value: c.wr, text: `${pct(c.wr)}  ·  ${c.wins}–${c.picks - c.wins}` })));
  sortable($('#tbl', el), [{ k: 'name', label: 'Champion', cls: 'team' }, { k: 'role', label: 'Role', f: v => ROLE[v] || '–' },
    { k: 'presence', label: 'Presence', num: 1, html: r => cellBar(r.presence, ch[0]?.presence || 1, pct(r.presence)) }, { k: 'picks', label: 'Picks', num: 1 }, { k: 'bans', label: 'Bans', num: 1 }, { k: 'wins', label: 'Wins', num: 1 },
    { k: 'wr', label: 'Win%', num: 1, f: (v, r) => r.picks ? pct(v) : '–' }, { k: 'kda', label: 'KDA', num: 1, f: (v, r) => r.picks ? num(v, 2) : '–' }, { k: 'players', label: 'Players', num: 1 }, { k: 'gd15', label: 'GD@15', num: 1, f: v => v == null ? '–' : sign(v) }], ch,
    { key: 'presence', limit: 15, onRow: r => { if (X.explore[r.name]) { $('#cx', el).value = r.name; card(r.name); $('#cx', el).scrollIntoView({ behavior: 'smooth', block: 'center' }); } } });
  $('#duo', el).innerHTML = (X.duos || []).length ? hbars(X.duos.map(d => ({ label: `${d.a} + ${d.b}`, value: d.w / d.g, text: `${rec(d.g, d.w)}` })), { color: 'var(--blue)' }) : '<p class="note">No pair has 4 games together yet.</p>';
  $('#mu', el).innerHTML = (X.matchups || []).length ? hbars(X.matchups.map(d => ({ label: `${d.a} over ${d.b}`, value: d.w / d.g, text: `${rec(d.g, d.w)}` }))) : '<p class="note">No matchup has 3 meetings yet.</p>';
  $('#sig', el).innerHTML = (X.signature || []).length ? hbars(X.signature.map(s => ({ label: `${s.p} · ${s.c}`, value: s.g, text: `${s.g} games  ·  ${rec(s.g, s.w)}`, color: T(s.t).color }))) : '';
};

pages.draft = el => {
  const D = state.D, ch = D.champions || [], dr = D.draft || {}, I = D.items || {}, banned = [...ch].sort((a, b) => b.bans - a.bans), sf = I.sunfire;
  el.innerHTML = `
    <div class="banner"><div><h1>Draft & Items</h1><p>${dr.drafts ? dr.drafts + ' drafts from the league site\'s draft tool' : 'Bans and builds'}</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <div class="cols rv"><div id="bans"></div><div id="prio"></div></div>
    <div class="cols rv" style="margin-top:22px"><div class="panel"><h3>Which roles get locked first</h3><p class="note" style="margin-top:-4px">Share of each role's picks by draft slot · blue numbers are blue side's picks</p><div id="slot"></div></div>
    <div class="panel"><h3>Blue side win rate by week</h3><p class="note" style="margin-top:-4px">Blue side has first pick</p><div id="side"></div></div></div>
    <h2>Items <small>completed items in the final build · click a column to sort</small></h2>
    <div class="cols w32 rv"><div id="items"></div><div><div id="iwin"></div><p class="note">Items in a final build are a result as much as a cause — winning teams get to finish expensive items, losing teams end on defensive ones.</p>
      ${sf ? `<div class="sunfire"><div class="k">Slamurai's Sunfire Counter</div><div class="q">"This item is grief" — Slamurai, probably</div><div class="row"><div class="big" data-to="${sf.total}">0</div><div><b>${pct(sf.wr)}</b><small>win rate</small></div><div><b class="up">${sf.wins}</b><small>wins</small></div><div><b class="down">${sf.losses}</b><small>losses</small></div></div><div class="q" style="margin-top:8px">Repeat offenders: ${sf.top.map(p => `${esc(p.p)} ×${p.n}`).join(' · ')}</div></div>` : ''}</div></div>`;
  $('#bans', el).innerHTML = banned[0]?.bans ? hbars(banned.slice(0, 10).map(c => ({ label: c.name, value: c.bans, text: `${c.bans}`, color: 'var(--red)' })), { title: 'Most banned' }) : '<p class="note">No ban data recorded for this season.</p>';
  $('#prio', el).innerHTML = dr.priority?.length ? hbars(dr.priority.slice(0, 10).map(c => ({ label: c.name, value: c.r1, text: `${c.r1}${c.wr != null ? '  ·  ' + pct(c.wr) + ' wins' : ''}` })), { title: 'First-rotation picks', sub: 'Taken with one of the first three picks of a draft' }) : '';
  if (dr.role_slot?.length) {
    const roles = Object.keys(ROLE), tot = Object.fromEntries(roles.map(r => [r, d3.sum(dr.role_slot.filter(x => x.role === r), x => x.n)]));
    const get = (r, s) => (dr.role_slot.find(x => x.role === r && x.pick_no === s)?.n || 0) / (tot[r] || 1), side = 'BRRBBRRBBR';
    const h = $('#slot', el); h.className = 'heat'; h.style.gridTemplateColumns = '46px repeat(10,1fr)';
    h.innerHTML = '<div></div>' + d3.range(1, 11).map(s => `<div class="hh" style="color:${side[s - 1] === 'B' ? 'var(--blue)' : 'var(--red)'}">${s}</div>`).join('') +
      roles.map((r, ri) => `<div class="hn">${ROLE[r]}</div>` + d3.range(1, 11).map(s => { const p = get(r, s), a = Math.min(1, p / .3); return `<div class="c" title="${ROLE[r]} · pick ${s}: ${pct(p)} of that role's picks" style="animation-delay:${ri * 50 + s * 25}ms;background:rgba(255,215,0,${(0.06 + a * .94).toFixed(2)});color:${a > .55 ? '#080b12' : '#f1f5f9'}">${Math.round(p * 100)}</div>`; }).join('')).join('');
  } else $('#slot', el).innerHTML = '<p class="note">No draft-tool data for this season.</p>';
  const sw = dr.side_weeks || []; if (sw.length > 1) {
    const W = 560, H = 210, m = { t: 10, r: 14, b: 26, l: 40 }, x = d3.scaleLinear(d3.extent(sw, d => d.week), [m.l, W - m.r]), y = d3.scaleLinear([0, 100], [H - m.b, m.t]);
    const svg = d3.select('#side').append('svg').attr('viewBox', `0 0 ${W} ${H}`);
    svg.append('g').attr('class', 'grid').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)).tickFormat(''));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l - 4},0)`).call(d3.axisLeft(y).ticks(4).tickSize(0).tickFormat(d => d + '%'));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b + 6})`).call(d3.axisBottom(x).ticks(sw.length).tickSize(0).tickFormat(d => 'W' + d));
    svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(50)).attr('y2', y(50)).attr('stroke', '#475569').attr('stroke-dasharray', '3 4');
    const p = svg.append('path').attr('fill', 'none').attr('stroke', 'var(--blue)').attr('stroke-width', 2.5).attr('d', d3.line().x(d => x(d.week)).y(d => y(d.blue * 100)).curve(d3.curveMonotoneX)(sw));
    const len = p.node().getTotalLength(); p.attr('stroke-dasharray', len).attr('stroke-dashoffset', len).transition().duration(REDUCED ? 0 : 1600).ease(d3.easeCubicInOut).attr('stroke-dashoffset', 0);
    withTip(svg.selectAll('circle').data(sw).join('circle').attr('cx', d => x(d.week)).attr('cy', d => y(d.blue * 100)).attr('r', 5).attr('fill', 'var(--blue)').attr('stroke', '#080b12').attr('stroke-width', 2), d => `Week ${d.week}: blue won <b>${pct(d.blue)}</b> of ${d.games} games`);
  }
  const items = I.items || [];
  if (items.length) {
    sortable($('#items', el), [{ k: 'name', label: 'Item', cls: 'team' }, { k: 'builds', label: 'Builds', num: 1 }, { k: 'rate', label: 'Pick rate', num: 1, tip: 'Share of all player-games that finished with this item', html: r => cellBar(r.rate, Math.max(...items.map(i => i.rate)), pct(r.rate, 1)) },
      { k: 'wr', label: 'Win rate', num: 1, html: r => `<span class="${r.wr >= .55 ? 'up' : r.wr <= .45 ? 'down' : ''}">${pct(r.wr)}</span>` }], items, { key: 'builds', limit: 15 });
    const q = items.filter(i => i.builds >= Math.max(10, items[0].builds / 12)), ext = [...[...q].sort((a, b) => b.wr - a.wr).slice(0, 5), ...[...q].sort((a, b) => a.wr - b.wr).slice(0, 5).reverse()];
    $('#iwin', el).innerHTML = hbars(ext.map(i => ({ label: i.name, value: i.wr, text: `${pct(i.wr)}  ·  ${i.builds} builds`, color: i.wr >= .5 ? 'var(--blue)' : 'var(--red)' })), { title: 'Winning and losing builds', sub: 'Best and worst win rates among commonly built items' });
  } else $('#items', el).innerHTML = '<p class="note">No item data for this season.</p>';
};

pages.wins = el => {
  const D = state.D, W = D.wins || { edges: [] }, cards = D.styles || [];
  const ladder = (rows, lab) => rows.length ? hbars(rows.map(r => ({ label: lab(r.n), value: Math.max(r.wr, .004), text: `${pct(r.wr)}  ·  ${r.games} games`, color: r.wr >= .5 ? 'var(--gold)' : '#7a6410' }))) : '<p class="note">Objective counts aren\'t recorded for this season.</p>';
  const h1 = W.herald?.find(h => h.n === 1), b0 = W.barons?.find(b => b.n === 0), b1 = W.barons?.find(b => b.n === 1), fb = W.edges.find(e => e.label === 'First blood');
  el.innerHTML = `
    <div class="banner"><div><h1>How Games Are Won</h1><p>Objectives, leads and what each team leans on</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <div class="chyrons rv">${W.soul ? chyron('Four dragons', pct(W.soul.wr), `win rate · ${W.soul.games} games`, { to: W.soul.wr * 100, suf: '%' }) : ''}
      ${b1 ? chyron('Take a Baron', pct(b1.wr), `vs ${pct(b0?.wr)} with none`, { to: b1.wr * 100, suf: '%', cls: 'white' }) : ''}
      ${h1 ? chyron('Take the Herald', pct(h1.wr), `${h1.games} games`, { to: h1.wr * 100, suf: '%', cls: 'white' }) : ''}
      ${W.lead_hold != null ? chyron('Lead at 15 holds', pct(W.lead_hold), 'any gold lead', { to: W.lead_hold * 100, suf: '%', cls: 'white' }) : ''}
      ${fb ? chyron('First blood', pct(fb.wr), fb.wr < .6 ? 'barely better than a coin flip' : 'win rate', { to: fb.wr * 100, suf: '%', cls: 'white' }) : ''}</div>
    <div class="cols rv"><div><h2>What the winner had <small>win rate of the team that got each edge</small></h2><div id="edges"></div></div>
    <div><h2>Dragons <small>win rate by drakes taken</small></h2>${ladder(W.dragons || [], n => n >= 4 ? '4+ (soul)' : n + (n === 1 ? ' dragon' : ' dragons'))}
      <h2>Barons</h2>${ladder(W.barons || [], n => n >= 2 ? '2+ barons' : n + (n === 1 ? ' baron' : ' barons'))}</div></div>
    ${W.comebacks?.length ? `<h2>Biggest comebacks <small>largest gold deficit at 15:00 that still ended in a win</small></h2><div class="grid rv">${W.comebacks.map(c => `<div class="story"><div class="t">WEEK ${c.week} · ${num(c.mins)} MIN</div><div class="x"><b>${esc(T(c.team).name)}</b> were <b class="down">${num(c.deficit)}</b> gold down to ${esc(T(c.opp).name)} at 15:00 — and won.</div></div>`).join('')}</div>` : ''}
    <h2>How each team wins <small>tags are earned from the numbers · click a card for the full profile</small></h2>
    <div class="styles rv">${cards.map(c => { const r = ([w, g]) => g ? `${w}–${g - w}` : '–', roles = Object.entries(c.dmg);
      return `<div class="sty" data-t="${c.t}" style="border-top-color:${T(c.t).color}"><div class="sn">${dot(c.t)}${esc(T(c.t).name)}<em>${pct(c.win_pct)}</em></div>
        <div class="tags">${c.tags.map(t => `<span title="${esc(t.why)}">${esc(t.tag)}</span>`).join('')}</div><div class="why">${c.tags.map(t => esc(t.why)).join(' · ')}</div>
        <div class="q4"><div><b>${r(c.ahead)}</b><small>ahead at 15</small></div><div><b>${r(c.behind)}</b><small>behind at 15</small></div><div><b>${r(c.short)}</b><small>under 28 min</small></div><div><b>${r(c.long)}</b><small>over 36 min</small></div></div>
        ${roles.length ? `<div class="dmg" title="Share of team damage by role">${roles.map(([k, v]) => `<i data-w="${(v * 100).toFixed(1)}%" style="background:${ROLE_COLOR[Object.keys(ROLE).find(x => ROLE[x] === k)]}" title="${k}: ${pct(v)} of team damage"><span>${v >= .14 ? k : ''}</span></i>`).join('')}</div>` : ''}</div>`; }).join('')}</div>
    <p class="note">Records are games. The coloured bar is each role's share of the team's damage to champions.</p>`;
  $('#edges', el).innerHTML = W.edges.length ? hbars(W.edges.map(e => ({ label: e.label, value: e.wr, text: `${pct(e.wr)}  ·  ${e.n} games` }))) : '<p class="note">Not enough data.</p>';
  el.querySelectorAll('.sty').forEach(c => c.onclick = () => teamProfile(c.dataset.t));
};

pages.records = el => {
  const D = state.D, F = D.fun || { awards: [], records: [] };
  el.innerHTML = `
    <div class="banner"><div><h1>Record Book</h1><p>Season awards nobody asked for</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <h2>Season awards <small>players with ${F.min_games || 3}+ games</small></h2>
    <div class="awards rv">${F.awards.map((a, i) => `<div class="aw" style="animation-delay:${i * 40}ms"><div class="at">${esc(a.title)}</div><div class="ab">${esc(a.blurb)}</div>
      <div class="ap">${dot(a.team)}${esc(a.player)}</div><div class="av">${a.value} <small>${esc(a.unit)}</small></div>
      <div class="an">${a.next.map((n, k) => `${k + 2}. ${esc(n.player)} ${n.value}`).join(' · ')}</div></div>`).join('')}</div>
    <h2>Single-game records</h2>
    <div class="grid rv">${F.records.map(r => `<div class="story"><div class="t">${esc(r.title.toUpperCase())}</div><div class="x"><b style="color:var(--gold);font-family:var(--head);font-size:21px">${esc(r.value)}</b><br>${r.player ? `<b>${esc(r.player)}</b> (${esc(r.champ)}, ${esc(T(r.team).name)}) vs ${esc(T(r.opp).name)}` : `<b>${esc(T(r.team).name)}</b> beat ${esc(T(r.opp).name)}`} · ${r.playoff ? 'playoffs' : 'week ' + r.week}</div></div>`).join('')}</div>`;
};

pages.forecasts = el => {
  const D = state.D, F = D.forecast, s = F.score, R = D.ratings, ids = liveTeams().filter(t => R.by_team[t]);
  const li = R.weeks.length - 1, rows = ids.map(t => { const a = R.by_team[t]; return { t, team: T(t).name, rating: a[li], wk: li ? a[li] - a[li - 1] : 0, seed: a[li] - a[0], rd: (R.rd[t] || 0) * 2 }; });
  const ups = D.series.filter(x => x.wpm != null).sort((a, b) => a.wpm - b.wpm).slice(0, 6);
  el.innerHTML = `
    <div class="banner"><div><h1>Forecasts</h1><p>The model, the crowd, and who was right</p></div><div class="badge ${D.band}">${D.band}</div></div>
    <h2>Model vs. the crowd <small>pre-series picks, graded on results</small></h2>
    ${s.n ? `<div class="chyrons rv">${chyron('Model picks', pct(s.model_acc), `${s.n} series both called`, { to: s.model_acc * 100, suf: '%', cls: s.model_acc >= s.crowd_acc ? '' : 'white' })}
      ${chyron('Crowd picks', pct(s.crowd_acc), 'majority of Crystal Ball picks', { to: s.crowd_acc * 100, suf: '%', cls: s.crowd_acc > s.model_acc ? '' : 'white' })}
      ${chyron('Model Brier', num(s.model_brier, 3), '0.25 = coin flip · lower is better', { to: s.model_brier, dec: 3, cls: s.model_brier < s.crowd_brier ? '' : 'white' })}
      ${chyron('Crowd Brier', num(s.crowd_brier, 3), 'pick share as a probability', { to: s.crowd_brier, dec: 3, cls: s.crowd_brier < s.model_brier ? '' : 'white' })}
      ${chyron('When they disagreed', `${s.model_wins_disagree}–${s.disagree - s.model_wins_disagree}`, 'model right – crowd right', { cls: 'white' })}</div>`
      : s.n_model ? `<div class="chyrons rv">${chyron('Model picks', pct(s.model_acc_all), `${s.n_model} series`, { to: s.model_acc_all * 100, suf: '%' })}${chyron('Model Brier', num(s.model_brier_all, 3), '0.25 = coin flip', { cls: 'white' })}</div><p class="note">No Crystal Ball picks exist for this season, so there is no crowd to compare against.</p>` : '<p class="note">No completed series to grade yet.</p>'}
    <div class="cols w32 rv"><div class="panel"><h3>Did the favourites deliver?</h3><div class="caption" id="calcap"></div><div id="cal"></div></div>
    <div><h3>Biggest upsets</h3>${ups.map(u => { const w = u.t1won ? u.t1 : u.t2, l = u.t1won ? u.t2 : u.t1; return `<div class="story"><div class="t">WEEK ${u.week}</div><div class="x"><b>${esc(T(w).name)}</b> over ${esc(T(l).name)} — model ${pct(u.wpm)}${u.wpc != null && u.n >= 5 ? ` · crowd ${pct(u.wpc)}` : ''}</div></div>`; }).join('')}</div></div>
    <p class="note">The model's number is the Glicko-2 series probability from ratings <b>before</b> that week, shrunk toward 50% to stay calibrated. The crowd's number is the share of Crystal Ball picks on each side. Series involving dropped teams are excluded, as on the site.</p>
    <h2>Power rankings <small>Glicko-2 · seeded by roster salary, then every game moves it</small></h2><div id="pr"></div>
    ${D.pickem.length ? '<h2>Crystal Ball leaderboard <small>exact score = 3 points · right winner = 1</small></h2><div id="lb"></div>' : ''}`;
  sortable($('#pr', el), [{ k: 'team', label: 'Team', cls: 'team', html: r => `${dot(r.t)}${esc(r.team)}` }, { k: 'rating', label: 'Rating', num: 1, html: r => cellBar(r.rating - 800, 800, num(r.rating)) },
    { k: 'wk', label: 'Last week', num: 1, html: r => `<span class="${r.wk > 0 ? 'up' : r.wk < 0 ? 'down' : ''}">${sign(r.wk)}</span>` }, { k: 'seed', label: 'vs. salary seed', num: 1, tip: 'Rating now minus the preseason salary seed', html: r => `<span class="${r.seed > 0 ? 'up' : 'down'}">${sign(r.seed)}</span>` },
    { k: 'rd', label: '± 95%', num: 1, f: v => num(v) }], rows, { key: 'rating', rank: true });
  if (D.pickem.length) sortable($('#lb', el), [{ k: 'username', label: 'Predictor', cls: 'team' }, { k: 'points', label: 'Points', num: 1 }, { k: 'exact', label: 'Exact scores', num: 1 }, { k: 'correct', label: 'Right winner', num: 1 }, { k: 'picks', label: 'Graded', num: 1 },
    { k: 'accuracy', label: 'Winner accuracy', num: 1, html: r => cellBar(r.accuracy, 1, pct(r.accuracy)) }], D.pickem, { key: 'points', rank: true });

  // calibration: dots start ON the "perfect" diagonal, then slide to what really happened
  const sets = [['Model', F.cal_model, '#4f8ff7'], ['Crowd', F.cal_crowd, '#FFD700']].filter(x => x[1].length);
  if (!sets.length) { $('#cal', el).innerHTML = '<p class="note">Not enough graded series yet.</p>'; return; }
  const W = 640, H = 330, m = { t: 14, r: 70, b: 40, l: 46 }, x = d3.scaleLinear([48, 100], [m.l, W - m.r]), y = d3.scaleLinear([30, 102], [H - m.b, m.t]);
  const svg = d3.select('#cal').append('svg').attr('viewBox', `0 0 ${W} ${H}`);
  svg.append('g').attr('class', 'grid').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat(''));
  svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l - 4},0)`).call(d3.axisLeft(y).ticks(5).tickSize(0).tickFormat(d => d + '%'));
  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b + 6})`).call(d3.axisBottom(x).ticks(6).tickSize(0).tickFormat(d => d + '%'));
  svg.append('text').attr('x', (m.l + W - m.r) / 2).attr('y', H - 4).attr('text-anchor', 'middle').text("Favourite's stated chance");
  svg.append('text').attr('transform', `translate(12,${(m.t + H - m.b) / 2}) rotate(-90)`).attr('text-anchor', 'middle').text('Actually won');
  svg.append('line').attr('x1', x(50)).attr('y1', y(50)).attr('x2', x(100)).attr('y2', y(100)).attr('stroke', '#475569').attr('stroke-dasharray', '4 5');
  svg.append('text').attr('x', x(100) - 4).attr('y', y(100) + 16).attr('text-anchor', 'end').text('perfect calibration');
  const ln = d3.line().x(d => x(d.said * 100)).y(d => y(d.actual * 100)), flat = d3.line().x(d => x(d.said * 100)).y(d => y(d.said * 100));
  const cap = $('#calcap', el);
  cap.innerHTML = 'If a forecaster says 70%, the favourite should win about 70% of the time — the dotted line.';
  const run = () => sets.forEach(([name, data, color], si) => {
    const p = svg.append('path').attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2.5).attr('d', flat(data)).attr('opacity', .9);
    const c = svg.selectAll('circle.' + name).data(data).join('circle').attr('class', name).attr('cx', d => x(d.said * 100)).attr('cy', d => y(d.said * 100)).attr('r', 0).attr('fill', color).attr('stroke', '#080b12').attr('stroke-width', 2);
    const t = svg.append('text').attr('class', 'lab hi').attr('x', x(data.at(-1).said * 100) + 12).attr('y', y(data.at(-1).said * 100) + 4).attr('opacity', 0).text(name).style('fill', color);
    const d0 = REDUCED ? 0 : 500 + si * 1500, dur = REDUCED ? 0 : 1300;
    c.transition().delay(d0 - 400).duration(400).attr('r', d => Math.max(5, Math.sqrt(d.n) * 1.9)).transition().duration(dur).ease(d3.easeCubicInOut).attr('cy', d => y(d.actual * 100));
    p.transition().delay(d0).duration(dur).ease(d3.easeCubicInOut).attr('d', ln(data));
    t.transition().delay(d0).duration(dur).ease(d3.easeCubicInOut).attr('y', y(data.at(-1).actual * 100) + 4).attr('opacity', 1);
    withTip(c, d => `<b>${name}</b> said ${pct(d.said)} → won ${pct(d.actual)}<br>${d.n} series`);
    setTimeout(() => {
      const top = data.at(-1), gap = (top.actual - top.said) * 100;
      cap.innerHTML += ` <b>${name}:</b> its most confident picks (${pct(top.said)}) won ${pct(top.actual)} — ${Math.abs(gap) < 6 ? 'about right' : gap < 0 ? 'overconfident' : 'too cautious'}.`;
    }, d0 + dur);
  });
  $('#cal', el).closest('.rv').addEventListener('reveal', run, { once: true });
};

/* ════════════ shell ════════════ */
function ticker() {
  const D = state.D, w = D.weeks.at(-1);
  const items = D.series.filter(s => s.status === 'COMPLETED' && s.week >= w - 1).sort((a, b) => b.week - a.week)
    .map(s => `<span class="ticker-item">W${s.week} · ${s.s1 > s.s2 ? '<b>' : ''}${esc(T(s.t1).name)}${s.s1 > s.s2 ? '</b>' : ''} <i>${s.s1}–${s.s2}</i> ${s.s2 > s.s1 ? '<b>' : ''}${esc(T(s.t2).name)}${s.s2 > s.s1 ? '</b>' : ''}${s.wpm != null && s.wpm < .4 ? ' <i>UPSET</i>' : ''}</span>`).join('');
  $('#ticker').innerHTML = items + items;
}
function champIcons() {
  const imgs = document.querySelectorAll('img[data-champ]'); if (!imgs.length) return;
  const set = v => imgs.forEach(i => { const k = i.dataset.champ === 'FiddleSticks' ? 'Fiddlesticks' : i.dataset.champ; i.onerror = () => i.remove(); i.src = `https://ddragon.leagueoflegends.com/cdn/${v}/img/champion/${k}.png`; });
  if (state.ddv) return set(state.ddv);
  fetch('https://ddragon.leagueoflegends.com/api/versions.json').then(r => r.json()).then(v => { state.ddv = v[0]; set(v[0]); }).catch(() => imgs.forEach(i => i.remove()));
}
function render() {
  clearInterval(state.timer); state.timer = null; tip.hide();
  const D = state.D, el = $('#page');
  $('#nav').innerHTML = PAGES.map(([k, l]) => `<a href="#/${state.band.toLowerCase()}/${state.sid}/${k}" class="${k === state.page ? 'on' : ''}">${l}</a>`).join('');
  $('#sub').textContent = `${D.name} · ${D.active ? 'in progress' : 'final'}`;
  if (!D.weeks || !D.weeks.length) { el.innerHTML = '<p class="note" style="margin-top:30px">No games have been played in this season yet.</p>'; return; }
  (pages[state.page] || pages.overview)(el);
  ticker(); champIcons(); observe(el); scrollTo({ top: 0 });
}
async function route() {
  const [, band, sid, page] = location.hash.split('/');
  const S = state.index.seasons, bands = ['STOUT', 'LITE'].filter(b => S.some(s => s.band === b));
  state.band = bands.includes((band || '').toUpperCase()) ? band.toUpperCase() : bands[0];
  const inBand = S.filter(s => s.band === state.band).sort((a, b) => (b.active - a.active) || (b.id - a.id));
  const newSid = inBand.some(s => s.id === sid) ? sid : inBand[0].id;
  if (newSid !== state.sid) state.week = null;
  state.sid = newSid; state.page = PAGES.some(p => p[0] === page) ? page : 'overview';
  $('#bands').innerHTML = bands.map(b => `<button data-band="${b}" class="${b === state.band ? 'on' : ''}">${b}</button>`).join('');
  $('#bands').querySelectorAll('button').forEach(b => b.onclick = () => { location.hash = `#/${b.dataset.band.toLowerCase()}//${state.page}`; });
  $('#season').innerHTML = inBand.map(s => `<option value="${s.id}" ${s.id === state.sid ? 'selected' : ''}>${esc(s.name)}${s.active ? '' : ' · final'}</option>`).join('');
  $('#season').onchange = e => { location.hash = `#/${state.band.toLowerCase()}/${e.target.value}/${state.page}`; };
  state.cache[state.sid] ??= await fetch(`data/season_${state.sid}.json`).then(r => r.json());
  state.D = state.cache[state.sid];
  render();
}
(async () => {
  try {
    state.index = await fetch('data/index.json').then(r => r.json());
    $('#meta').textContent = 'Data through ' + state.index.data_through;
    $('#foot').innerHTML = `Data through <b>${esc(state.index.data_through)}</b>, rebuilt nightly from the league site. Standings, tiebreakers, dropped teams and playoff seeding follow the site's own rules.`;
    addEventListener('hashchange', route);
    await route();
  } catch (e) { $('#page').innerHTML = `<p class="note" style="margin-top:30px">Could not load the stats data (${esc(e.message)}).</p>`; console.error(e); }
})();
})();

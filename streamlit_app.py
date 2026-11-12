"""
Beer League Stats — Streamlit dashboard (v2)
Run: streamlit run streamlit_app.py

Reads the newest SQLite export of the league website from ./data and mirrors
the website's own rules for standings, tiebreakers, dropped teams, playoff
seeding and stat formulas (see app/league.py).
"""
import numpy as np
import pandas as pd
import streamlit as st

from app import playoff, viz
from app.elo import STARTING_ELO
from app.impact_factor import compute_impact_factors, weight_breakdown
from app.insights import (
    calibration, draft_summary, forecast_scorecard, ladder, lead_conversion,
    series_forecasts, side_by_week, storylines,
)
from app.league import (
    ROLES, ROLE_SHORT, Season, champ_name, champion_table, data_through, kda,
    latest_db, load_seasons, player_table, team_table,
)
from app.styling import champion_icon
from app.theme import apply_theme_v2
from app.viz import esc, fmt_time, h2, kpi, kpi_row, note, pct

st.set_page_config(page_title="Beer League Stats", page_icon="🍺", layout="wide",
                   initial_sidebar_state="expanded")
apply_theme_v2()

PAGES = ["Overview", "Standings & Playoffs", "Weekly Recap", "Players", "Teams",
         "Champions & Draft", "Forecasts"]


def md(html_str: str):
    st.markdown(html_str, unsafe_allow_html=True)


def chart(fig, key=None):
    st.plotly_chart(fig, width="stretch", config=viz.PLOT_CFG, key=key)


# ── Cached data access ───────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_season(db: str, sid: str) -> Season:
    return Season(db, sid)


@st.cache_data(show_spinner=False)
def get_seasons(db: str) -> pd.DataFrame:
    return load_seasons(db)


@st.cache_data(show_spinner=False)
def get_ladder(db: str, sid: str, week: int):
    return ladder(get_season(db, sid), week)


@st.cache_data(show_spinner=False)
def get_forecasts(db: str, sid: str) -> pd.DataFrame:
    return series_forecasts(get_season(db, sid))


@st.cache_data(show_spinner="Simulating the rest of the season…")
def get_sim(db: str, sid: str) -> dict:
    S = get_season(db, sid)
    st_, _ = get_ladder(db, sid, 999)
    return playoff.simulate(S, dict(zip(st_["team_id"], st_["elo"])),
                            dict(zip(st_["team_id"], st_["rd"])))


def impact_table(ps: pd.DataFrame) -> pd.DataFrame:
    """Impact Factor per player over the given games (within-role percentiles)."""
    if ps.empty:
        return pd.DataFrame()
    df = compute_impact_factors(ps.assign(position=ps["role"]))
    g = df.groupby("pid")
    out = g.agg(player=("player", "last"), games=("win", "size"), wins=("win", "sum"),
                avg_if=("impact_factor", "mean"), k=("kills", "sum"), d=("deaths", "sum"),
                a=("assists", "sum"), kp=("killParticipation", "mean"),
                dmg_share=("teamDamagePercentage", "mean")).reset_index()
    out["team"] = g["team"].agg(lambda s: s.mode().iloc[0]).values
    out["role"] = g["role"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None).values
    out["main_key"] = g["championName"].agg(lambda s: s.mode().iloc[0]).values
    out["champs"] = g["champion"].agg(lambda s: ", ".join(list(dict.fromkeys(s))[:3])).values
    out["kda"] = [kda(k, d, a) for k, d, a in zip(out["k"], out["d"], out["a"])]
    return out.sort_values("avg_if", ascending=False).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def get_week_impact(db: str, sid: str, week: int) -> pd.DataFrame:
    ps = get_season(db, sid).ps
    return impact_table(ps[(ps["week"] == week) & ~ps["playoff"]])


@st.cache_data(show_spinner=False)
def get_players(db: str, sid: str) -> pd.DataFrame:
    S = get_season(db, sid)
    pl = player_table(S.ps)
    if pl.empty:
        return pl
    imp = impact_table(S.ps)[["pid", "avg_if"]]
    return pl.merge(imp, on="pid", how="left")


@st.cache_data(show_spinner=False)
def get_teams(db: str, sid: str) -> pd.DataFrame:
    return team_table(get_season(db, sid))


@st.cache_data(show_spinner=False)
def get_team_games(db: str, sid: str) -> pd.DataFrame:
    S = get_season(db, sid)
    team_table(S)
    return S.team_games


@st.cache_data(show_spinner=False)
def get_champs(db: str, sid: str) -> pd.DataFrame:
    S = get_season(db, sid)
    return champion_table(S.ps, S.ban_table(), len(S.games[S.games["has_stats"]]))


@st.cache_data(show_spinner=False)
def get_draft(db: str, sid: str) -> dict:
    return draft_summary(get_season(db, sid))


@st.cache_data(show_spinner=False)
def get_items(db: str, sid: str):
    from app.data_loader import load_item_stats, load_sunfire_stats
    return load_item_stats(db, sid), load_sunfire_stats(db, sid)


# ── Sidebar: league → season → week ──────────────────────────────────────────

db_path = latest_db()
if db_path is None:
    st.error("No database snapshot found in ./data.")
    st.stop()
DB = str(db_path)
seasons = get_seasons(DB)
if seasons.empty:
    st.warning("The snapshot has no seasons with games yet.")
    st.stop()

qp = st.query_params
bands = [b for b in ("STOUT", "LITE") if (seasons["band"] == b).any()]
BAND_LABEL = {"STOUT": "Stout", "LITE": "Lite"}

with st.sidebar:
    md('<div style="font-family:Oswald,sans-serif;font-size:1.25rem;font-weight:700;letter-spacing:2px;'
       'color:#FFD700;margin-bottom:0.6rem">🍺 BEER LEAGUE STATS</div>')
    default_band = qp.get("league", "").upper()
    band = st.radio("League", bands, horizontal=True, format_func=BAND_LABEL.get,
                    index=bands.index(default_band) if default_band in bands else 0)
    band_seasons = seasons[seasons["band"] == band].copy()
    band_seasons["rank"] = (band_seasons["status"] != "ACTIVE").astype(int)
    band_seasons = band_seasons.sort_values(["rank", "id"], ascending=[True, False],
                                            key=lambda s: s if s.name == "rank" else s.astype(int))
    sid_options = band_seasons["id"].tolist()
    labels = {r.id: f"{r.name}{'' if r.status == 'ACTIVE' else '  · final'}"
              for r in band_seasons.itertuples()}
    SID = st.selectbox("Season", sid_options, format_func=labels.get, key=f"season_{band}")
    S = get_season(DB, SID)

    if S.weeks:
        WEEK = st.selectbox("Week", S.weeks, index=len(S.weeks) - 1,
                            format_func=lambda w: f"Week {w}", key=f"week_{SID}",
                            help="Drives the Weekly Recap and the storylines. "
                                 "Standings and playoff odds always use every game played.")
    else:
        WEEK = None
    st.divider()
    md(note(f"Data through <b>{data_through(DB)}</b>. Refreshed nightly from the league site. "
            "Standings, tiebreakers, dropped teams and playoff seeding follow the site's own rules."))

qp["league"] = band.lower()
COLORS = viz.team_colors(S.teams)

# ── Masthead + nav ───────────────────────────────────────────────────────────

n_games = len(S.games)
status = "In progress" if S.active else "Final"
wk_txt = f"Week {max(S.weeks)} played" if S.weeks else "No games yet"
md(f'<div class="mast"><div><div class="mast-title"><b>{esc(S.name)}</b></div>'
   f'<div class="mast-sub">{BAND_LABEL[band]} league · {len(S.live_ids)} teams · '
   f'{S.playoff_spots} playoff spots{" · fearless draft" if S.fearless else ""}</div></div>'
   f'<div class="mast-meta"><b>{status}</b> · {wk_txt} · {n_games} games<br>'
   f'Data through {data_through(DB)}</div></div>')

default_page = next((p for p in PAGES if p.lower().startswith(qp.get("page", "").lower())), PAGES[0]) \
    if qp.get("page") else PAGES[0]
with st.container(key="nav"):
    PAGE = st.radio("Page", PAGES, horizontal=True, label_visibility="collapsed",
                    index=PAGES.index(default_page))
qp["page"] = PAGE.split(" ")[0].lower()

if S.games.empty:
    st.info("No games have been played in this season yet. Check back after week 1.")
    st.stop()

# Shared derived data
LADDER, HISTORY = get_ladder(DB, SID, 999)
RATING = dict(zip(LADDER["team_id"], LADDER["elo"]))
FORE = get_forecasts(DB, SID)
SIM = get_sim(DB, SID) if S.active else None
PROBS = playoff.seed_probabilities(SIM) if SIM else pd.DataFrame()
MAKE = dict(zip(PROBS["team_id"], PROBS["make_playoffs"])) if not PROBS.empty else None
SEEDS = S.seed_order()
SEED_LABEL = {tid: lab for _, tid, lab in SEEDS}


def standings_block(compact=False):
    """Standings exactly as the site ranks them — per group when grouped."""
    sos = None if compact else S.strength_of_schedule()
    if S.cross_group:
        cols = st.columns(len(S.group_labels))
        for col, g in zip(cols, S.group_labels):
            with col:
                md(f'<div class="h2" style="margin-top:0.4rem"><span class="h2-text" '
                   f'style="font-size:0.95rem;color:#94a3b8">Group {esc(g)}</span></div>')
                md(viz.standings_table(S.standings(group=g), COLORS, cut=S.playoff_spots // 2,
                                       ratings=None, probs=MAKE, sos=None, compact=compact,
                                       show_games=not compact, show_streak=False))
    else:
        md(viz.standings_table(S.standings(), COLORS, cut=S.playoff_spots,
                               ratings=None if compact else RATING, probs=MAKE, sos=sos,
                               compact=compact))


def result_cards(week: int) -> str:
    reg = S.regular
    wk = reg[(reg["week"] == week) & (reg["status"] == "COMPLETED") & ~reg["has_dropped"]]
    f = FORE.set_index("seriesId") if not FORE.empty else None
    cards = []
    for r in wk.itertuples():
        badge, sub = "", []
        if f is not None and r.seriesId in f.index:
            fr = f.loc[r.seriesId]
            if pd.notna(fr["winner_p_model"]):
                if fr["winner_p_model"] < 0.40:
                    badge = "UPSET"
                sub.append(f'Model gave the winner <b>{fr["winner_p_model"] * 100:.0f}%</b>')
            if pd.notna(fr["winner_p_crowd"]) and fr["n_picks"] >= 5:
                sub.append(f'crowd <b>{fr["winner_p_crowd"] * 100:.0f}%</b> ({int(fr["n_picks"])} picks)')
        if r.isOog:
            sub.append("out-of-group · doesn't count for standings")
        cards.append(viz.result_card(r.team1Name, r.team2Name, r.t1w, r.t2w,
                                     COLORS.get(r.team1Id, "#64748b"), COLORS.get(r.team2Id, "#64748b"),
                                     badge, " · ".join(sub)))
    if not cards:
        return note("No completed series this week.")
    return f'<div class="card-grid">{"".join(cards)}</div>'


def forecast_cards(df: pd.DataFrame) -> str:
    cards = []
    for r in df.itertuples():
        close = 0.42 <= r.p_model <= 0.58
        foot = f"likely {r.likely}"
        cards.append(viz.forecast_card(
            r.t1Name, r.t2Name, COLORS.get(r.t1, "#64748b"), COLORS.get(r.t2, "#64748b"),
            r.p_model, r.p_crowd, int(r.n_picks),
            tag="TOSS-UP" if close else ("EXHIBITION" if r.isOog else ""), foot=foot))
    return f'<div class="card-grid">{"".join(cards)}</div>'


def bracket_preview() -> str:
    """First-round pairings if the season ended today (standard seeding)."""
    n = len(SEEDS)
    if n < 2:
        return ""
    size = 1 << (n - 1).bit_length()
    byes = size - n
    by_seed = {s: (tid, lab) for s, tid, lab in SEEDS}

    def line(seed):
        tid, lab = by_seed[seed]
        return (f'<div class="bk-t"><span class="s">{esc(lab if S.cross_group else seed)}</span>'
                f'<span class="dot" style="background:{COLORS.get(tid, "#64748b")}"></span>'
                f'{esc(S.names.get(tid, tid))}</div>')

    cells = []
    for hi in range(byes + 1, size // 2 + 1):
        lo = size + 1 - hi
        if lo in by_seed and hi in by_seed:
            cells.append(f'<div class="bk-m"><div class="bk-h">Round 1 · seed {hi} v {lo}</div>'
                         f'{line(hi)}{line(lo)}</div>')
    for s in range(1, byes + 1):
        cells.append(f'<div class="bk-m"><div class="bk-h">Seed {s} · first-round bye</div>{line(s)}'
                     f'<div class="bk-t bye">awaits a round-1 winner</div></div>')
    return f'<div class="bk">{"".join(cells)}</div>'


# ═════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ═════════════════════════════════════════════════════════════════════════════

def page_overview():
    g = S.games[S.games["has_stats"]]
    ps = S.ps
    side = S.games[S.games["blueWon"].notna()]
    blue = side["blueWon"].astype(bool).mean() if len(side) else np.nan
    pentas = int(ps["pentaKills"].sum())
    champs = ps["championName"].nunique()
    top_champ = ps["champion"].value_counts()
    md(kpi_row([
        kpi("Games played", f"{len(S.games)}", f"{S.regular[S.regular['status'] == 'COMPLETED'].shape[0]} series"),
        kpi("Avg game time", fmt_time(g["duration"].mean()),
            f"longest {fmt_time(g['duration'].max())}"),
        kpi("Blue side wins", pct(blue), f"{len(side)} games with side data"),
        kpi("Champions played", f"{champs}", f"most picked: {top_champ.index[0]} ({top_champ.iloc[0]})"),
        kpi("Pentakills", f"{pentas}", f"{int(ps['quadraKills'].sum())} quadras", tone="gold" if pentas else ""),
    ]))

    left, right = st.columns([5, 4], gap="large")
    with left:
        md(h2("Standings", "dashed line = playoff cut" + (" · top %d per group" % (S.playoff_spots // 2) if S.cross_group else "")))
        standings_block(compact=True)
    with right:
        md(h2(f"Week {WEEK} storylines"))
        pw = get_week_impact(DB, SID, WEEK)
        md(viz.story_cards(storylines(S, WEEK, FORE, pw), limit=5))

    up = FORE[FORE["status"] == "SCHEDULED"] if not FORE.empty else pd.DataFrame()
    if S.active and not up.empty:
        future = up[up["week"] > max(S.weeks)]
        nxt = up[up["week"] == future["week"].min()] if not future.empty else up
        title = f"Up next — week {int(nxt['week'].iloc[0])}" if nxt["week"].nunique() == 1 else "Still to play"
        md(h2(title, "model = Glicko-2 series odds · crowd = Crystal Ball picks on the league site"))
        md(forecast_cards(nxt))
        rest = up[~up["seriesId"].isin(nxt["seriesId"])]
        if not rest.empty:
            with st.expander(f"Makeup series still unplayed ({len(rest)})"):
                md(forecast_cards(rest))
    elif S.active:
        md(h2("Playoff field", "regular season complete — first round as seeded today"))
        md(bracket_preview())

    md(h2(f"Week {WEEK} results"))
    md(result_cards(WEEK))

    champ_id = S.meta.get("championTeamId")
    if not S.active and champ_id is not None and not pd.isna(champ_id):
        tid = str(champ_id).replace(".0", "")
        md(h2("Champion"))
        md(f'<div class="hero"><div class="hero-kicker">{esc(S.name)} champions</div>'
           f'<div class="hero-name">🏆 {esc(S.names.get(tid, "Team " + tid))}</div></div>')


# ═════════════════════════════════════════════════════════════════════════════
# STANDINGS & PLAYOFFS
# ═════════════════════════════════════════════════════════════════════════════

def page_standings():
    md(h2("Standings", "regular season"))
    standings_block()
    drops = [f"{S.names[t]} ({'forfeit' if t in S.forfeit else 'void'})" for t in S.dropped]
    bits = ["<b>Tiebreakers:</b> " + " → ".join(esc(x) for x in S.tiebreaker_text) + "."]
    if S.cross_group:
        bits.append(f"<b>Seeding:</b> each group sends its top {S.playoff_spots // 2}, ranked on in-group "
                    "series only; seeds alternate between groups so round one is always cross-group. "
                    "Out-of-group weeks are exhibitions and never count.")
    if drops:
        bits.append("<b>Dropped:</b> " + ", ".join(esc(d) for d in drops) +
                    ". A void drop removes every series against that team; a forfeit drop credits "
                    "every opponent a series win with no games.")
    if not S.cross_group:
        bits.append("<b>SoS</b> = average series win rate of the opponents a team has played.")
    bits.append("<b>=</b> marks teams still level on series wins, game wins and head-to-head — "
                "anything past that is the commissioners' call.")
    md(note("<br>".join(bits)))

    if not S.active:
        if not S.playoffs.empty:
            md(h2("Playoffs"))
            po = S.playoffs[S.playoffs["status"] == "COMPLETED"]
            cards = [viz.result_card(r.team1Name, r.team2Name, r.t1w, r.t2w,
                                     COLORS.get(r.team1Id, "#64748b"), COLORS.get(r.team2Id, "#64748b"),
                                     "", esc(str(r.label or "Playoffs").title()))
                     for r in po.sort_values("seriesId", key=lambda s: s.astype(int)).itertuples()]
            md(f'<div class="card-grid">{"".join(cards)}</div>')
        return

    rem = SIM["remaining"]
    md(h2("Playoff picture", f"{len(rem)} counting series left" if rem else "regular season complete"))
    md(bracket_preview())
    md(note("Bracket as it would be seeded today (standard seeding, top seeds bye when the field "
            "isn't a power of two)."))

    if not rem:
        return

    scenarios, labels = [], []
    with st.expander(f"What if? Pin results for the {len(rem)} remaining series"):
        md(note("Pick winners below. Odds recompute over only the simulations where every pin happened."))
        for idx, r in enumerate(rem):
            choice = st.radio(
                f"W{r['week']} · {r['t1Name']} ({r['p_t1'] * 100:.0f}%) vs {r['t2Name']} ({(1 - r['p_t1']) * 100:.0f}%)",
                ["No pin", r["t1Name"], r["t2Name"]], horizontal=True, key=f"pin_{SID}_{r['seriesId']}")
            if choice != "No pin":
                win_id = r["t1Id"] if choice == r["t1Name"] else r["t2Id"]
                scenarios.append((idx, win_id))
                labels.append(f"{choice} win W{r['week']}")
    probs = PROBS
    if scenarios:
        mask = playoff.apply_scenarios(SIM, scenarios)
        kept = int(mask.sum())
        md(note(f"<b>Pinned:</b> {esc(', '.join(labels))} — {kept:,} of {SIM['n_sims']:,} simulations match."))
        if kept < 100:
            st.warning("Very few simulations match these pins, so the numbers below are noisy.")
        if kept:
            probs = playoff.seed_probabilities(SIM, mask)

    seed_lab = {k: lab for k, _, lab in SEEDS} if S.cross_group else None
    if S.cross_group:
        # label seed columns by slot type (first group's k-th / second group's k-th)
        seed_lab = {k: f"{k}" for k in range(1, S.playoff_spots + 1)}
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        chart(viz.seed_heatmap(probs, S.names, SIM["playoff_spots"], seed_lab), key="seedheat")
    with c2:
        bubble = probs[(probs["make_playoffs"] > 0.001) & (probs["make_playoffs"] < 0.999)]
        if bubble.empty:
            md(h2("On the bubble"))
            md(note("Nobody — every team is either in or out in all simulations."))
        else:
            b = bubble.sort_values("make_playoffs", ascending=False)
            chart(viz.bars([S.names[t] for t in b["team_id"]], b["make_playoffs"] * 100,
                           "On the bubble", "Chance to make the playoffs",
                           text=[f"{v * 100:.0f}%" for v in b["make_playoffs"]],
                           colors=[COLORS.get(t, "#64748b") for t in b["team_id"]]), key="bubble")
        lev = playoff.leverage(SIM)
        if not lev.empty:
            lev["abs"] = lev["swing"].abs()
            top = lev.sort_values("abs", ascending=False).drop_duplicates("seriesId").head(4)
            md(h2("Games that matter most"))
            for r in top.itertuples():
                tm = S.names.get(r.team_id, r.team_id)
                md(f'<div class="story"><div class="story-tag">Week {r.week}</div><div class="story-text">'
                   f'<b>{esc(r.series)}</b> — {esc(tm)} make the playoffs in '
                   f'<b>{r.if_t1 * 100:.0f}%</b> of sims if {esc(r.t1)} win, '
                   f'<b>{r.if_t2 * 100:.0f}%</b> if {esc(r.t2)} win.</div></div>')
    md(note(f"{SIM['n_sims']:,} simulations of the remaining schedule. Each series is rolled to an exact "
            "score from the calibrated Glicko-2 per-game odds, because game wins are the first tiebreaker. "
            "IN / OUT means every simulation agreed — not a mathematical clinch."))


# ═════════════════════════════════════════════════════════════════════════════
# WEEKLY RECAP
# ═════════════════════════════════════════════════════════════════════════════

def page_recap():
    ps = S.ps
    wk = ps[(ps["week"] == WEEK) & ~ps["playoff"]]
    games = S.games[(S.games["week"] == WEEK) & ~S.games["playoff"]]
    if games.empty:
        st.info("No games recorded for this week.")
        return
    kills = wk.groupby("matchId")["kills"].sum()
    side = games[games["blueWon"].notna()]
    gd = games.dropna(subset=["duration"])
    md(kpi_row([
        kpi("Games", f"{len(games)}", f"{games['seriesId'].nunique()} series"),
        kpi("Avg game time", fmt_time(gd["duration"].mean()) if len(gd) else "–"),
        kpi("Kills per game", f"{kills.mean():.1f}" if len(kills) else "–",
            f"bloodiest: {int(kills.max())}" if len(kills) else ""),
        kpi("Blue side wins", pct(side["blueWon"].astype(bool).mean()) if len(side) else "–",
            f"{int(side['blueWon'].astype(bool).sum())} of {len(side)}"),
        kpi("Sweeps", f"{int(((S.regular['week'] == WEEK) & (S.regular['status'] == 'COMPLETED') & ((S.regular['t1w'] == 0) | (S.regular['t2w'] == 0)) & ~S.regular['has_dropped']).sum())}",
            "2–0 series"),
    ]))
    missing = int((~games["has_stats"]).sum())
    md(h2(f"Week {WEEK} results"))
    md(result_cards(WEEK))
    if missing:
        md(note(f"{missing} game{'s' if missing != 1 else ''} this week ha{'ve' if missing != 1 else 's'} a result "
                "but no stat line on the site (played without a tournament code), so player stats exclude "
                f"{'them' if missing != 1 else 'it'}."))

    pw = get_week_impact(DB, SID, WEEK)
    md(h2("Storylines"))
    md(viz.story_cards(storylines(S, WEEK, FORE, pw), limit=8))

    md(h2("Player of the week", "Impact Factor, ranked within role"))
    if pw.empty:
        md(note("No player stats this week."))
    else:
        top = pw.iloc[0]
        c1, c2 = st.columns([2, 3], gap="large")
        with c1:
            icon = champion_icon(top["main_key"], size=40)
            md(f'<div class="hero"><div class="hero-kicker">Player of the week</div>'
               f'<div class="hero-name">{esc(top["player"])}</div>'
               f'<div class="hero-meta">{esc(top["team"])} · {ROLE_SHORT.get(top["role"], "")}</div>'
               f'<div class="hero-meta" style="margin-top:8px">{icon}{esc(top["champs"])}</div>'
               f'<div class="hero-stats">'
               f'<div class="hero-stat"><div class="v" style="color:#FFD700">{top["avg_if"]:.0f}</div><div class="l">Impact</div></div>'
               f'<div class="hero-stat"><div class="v">{top["k"]:.0f}/{top["d"]:.0f}/{top["a"]:.0f}</div><div class="l">K / D / A</div></div>'
               f'<div class="hero-stat"><div class="v">{top["kda"]:.1f}</div><div class="l">KDA</div></div>'
               f'<div class="hero-stat"><div class="v">{top["kp"] * 100:.0f}%</div><div class="l">Kill part.</div></div>'
               f'<div class="hero-stat"><div class="v">{int(top["wins"])}–{int(top["games"] - top["wins"])}</div><div class="l">Games</div></div>'
               f'</div></div>')
        with c2:
            show = pw.head(10).copy()
            show["Role"] = show["role"].map(ROLE_SHORT)
            show["K/D/A"] = [f"{k:.0f}/{d:.0f}/{a:.0f}" for k, d, a in zip(show["k"], show["d"], show["a"])]
            show["Record"] = [f"{int(w)}–{int(g - w)}" for w, g in zip(show["wins"], show["games"])]
            st.dataframe(
                show[["player", "team", "Role", "champs", "Record", "K/D/A", "avg_if"]],
                hide_index=True, width="stretch", height=388,
                column_config={
                    "player": "Player", "team": "Team", "champs": "Champions",
                    "avg_if": st.column_config.ProgressColumn("Impact", min_value=0, max_value=100, format="%.0f"),
                })
        with st.expander("How Impact Factor works"):
            md(note("Every stat is ranked against players in the <b>same role</b> that week, so a support "
                    "is judged against supports. Weighted mix below, ×1.15 for a win, scaled 0–100."))
            st.dataframe(pd.DataFrame(weight_breakdown(), columns=["Metric", "Weight", "Why"]),
                         hide_index=True, width="stretch")

    tg = get_team_games(DB, SID)
    c1, c2 = st.columns(2, gap="large")
    with c1:
        chart(viz.win_conditions(tg, set(games["matchId"])), key="wincond_wk")
        chart(viz.duration_strip(games, COLORS), key="dur_wk")
    with c2:
        mk = wk[(wk["pentaKills"] > 0) | (wk["quadraKills"] > 0) | (wk["tripleKills"] > 0)]
        if not mk.empty:
            rows = []
            for r in mk.itertuples():
                kind = "Penta" if r.pentaKills else "Quadra" if r.quadraKills else "Triple"
                rows.append({"": kind, "Player": r.player, "Champion": r.champion, "Team": r.team, "vs": r.opp,
                             "_o": 0 if r.pentaKills else 1 if r.quadraKills else 2})
            mkdf = pd.DataFrame(rows).sort_values("_o").drop(columns="_o").head(12)
            md('<div class="h2" style="margin-top:0.2rem"><span class="h2-text" style="font-size:0.95rem">Multi-kills</span></div>')
            st.dataframe(mkdf, hide_index=True, width="stretch", height=35 * len(mkdf) + 38)
        else:
            md(note("No triple kills or better this week."))

    md(h2("Superlatives", "best single-game lines of the week"))
    sup = []

    def add(label, col, fmt, per_min=False, df=wk):
        d = df.dropna(subset=[col]) if col in df.columns else pd.DataFrame()
        if d.empty:
            return
        vals = d[col] / d["mins"] if per_min else d[col]
        if vals.max() <= 0:
            return
        r = d.loc[vals.idxmax()]
        sup.append({"Award": label, "Player": r["player"], "Champion": r["champion"],
                    "Team": r["team"], "vs": r["opp"], "Line": fmt.format(vals.max())})
    add("Most damage", "totalDamageDealtToChampions", "{:,.0f} damage")
    add("Damage per minute", "totalDamageDealtToChampions", "{:,.0f} / min", per_min=True)
    add("Most kills", "kills", "{:.0f} kills")
    add("Most assists", "assists", "{:.0f} assists")
    add("Biggest lane lead", "gd15", "{:+,.0f} gold at 15:00")
    add("Farm", "cs", "{:.1f} CS / min", per_min=True)
    add("Vision", "visionScore", "{:.2f} vision / min", per_min=True)
    add("Tank", "damageSelfMitigated", "{:,.0f} mitigated")
    add("Healer", "totalHealsOnTeammates", "{:,.0f} healed on allies")
    add("Crowd control", "cc_s", "{:,.0f}s of CC")
    add("Smite thief", "epicMonsterSteals", "{:.0f} epic steals")
    add("Dodger", "skillshotsDodged", "{:.0f} skillshots dodged")
    add("Ping enthusiast", "totalPings", "{:.0f} pings")
    if sup:
        st.dataframe(pd.DataFrame(sup), hide_index=True, width="stretch", height=35 * len(sup) + 38)


# ═════════════════════════════════════════════════════════════════════════════
# PLAYERS
# ═════════════════════════════════════════════════════════════════════════════

def page_players():
    pl = get_players(DB, SID)
    if pl.empty:
        st.info("No player stats yet.")
        return
    max_g = int(pl["games"].max())
    c1, c2, c3 = st.columns([3, 2, 3])
    with c1:
        role = st.radio("Role", ["All"] + ROLES, horizontal=True,
                        format_func=lambda r: ROLE_SHORT.get(r, "All"), key="pl_role")
    with c2:
        default_min = min(max(3, max_g // 4), max_g)
        min_g = st.slider("Minimum games", 1, max_g, default_min, key=f"pl_min_{SID}")
    with c3:
        search = st.text_input("Find a player or team", placeholder="name…", key="pl_search")
    d = pl[pl["games"] >= min_g]
    if role != "All":
        d = d[d["role"] == role]
    if search.strip():
        s = search.strip().lower()
        d = d[d["player"].str.lower().str.contains(s, regex=False)
              | d["team"].str.lower().str.contains(s, regex=False)]

    md(h2("Leaderboard", f"{len(d)} players · click a column to sort"))
    show = d.sort_values("avg_if", ascending=False).copy()
    show["Role"] = show["role"].map(ROLE_SHORT)
    show["Record"] = [f"{int(w)}–{int(g - w)}" for w, g in zip(show["wins"], show["games"])]
    show["kp"] = show["kp"] * 100
    show["dmg_share"] = show["dmg_share"] * 100
    st.dataframe(
        show[["player", "team", "Role", "games", "Record", "avg_if", "kda", "k_g", "d_g", "a_g",
              "kp", "dmg_share", "dmg_min", "gold_min", "cs_min", "vis_min", "gd15", "salary"]],
        hide_index=True, width="stretch", height=460,
        column_config={
            "player": st.column_config.TextColumn("Player", pinned=True), "team": "Team",
            "games": st.column_config.NumberColumn("GP"),
            "avg_if": st.column_config.ProgressColumn("Impact", min_value=0, max_value=100, format="%.0f",
                                                      help="Season Impact Factor (within-role percentile mix)"),
            "kda": st.column_config.NumberColumn("KDA", format="%.2f", help="(ΣK + ΣA) / ΣD on season totals"),
            "k_g": st.column_config.NumberColumn("K", format="%.1f"),
            "d_g": st.column_config.NumberColumn("D", format="%.1f"),
            "a_g": st.column_config.NumberColumn("A", format="%.1f"),
            "kp": st.column_config.NumberColumn("KP%", format="%.0f"),
            "dmg_share": st.column_config.NumberColumn("Dmg%", format="%.0f"),
            "dmg_min": st.column_config.NumberColumn("DPM", format="%.0f"),
            "gold_min": st.column_config.NumberColumn("GPM", format="%.0f"),
            "cs_min": st.column_config.NumberColumn("CS/m", format="%.1f"),
            "vis_min": st.column_config.NumberColumn("Vis/m", format="%.2f"),
            "gd15": st.column_config.NumberColumn("GD@15", format="%+.0f",
                                                  help="Average gold difference vs. the direct lane opponent at 15:00"),
            "salary": st.column_config.NumberColumn("Salary", format="%g"),
        })

    lane = d[d["lane_games"] >= max(2, min_g // 2)].dropna(subset=["gd15"])
    c1, c2 = st.columns(2, gap="large")
    with c1:
        if lane.empty:
            chart(viz.empty("No 15-minute data for this selection"), key="lane_top")
        else:
            t = lane.nlargest(10, "gd15")
            chart(viz.bars(
                [f"{p} · {ROLE_SHORT.get(r, '')}" for p, r in zip(t["player"], t["role"])], t["gd15"],
                "Lane bullies", "Average gold lead on their lane opponent at 15:00",
                text=[f"{v:+,.0f}" for v in t["gd15"]], color=viz.BLUE,
                hover=[f"{p} ({tm}): {v:+,.0f} gold, {c:+.1f} CS over {int(n)} games"
                       for p, tm, v, c, n in zip(t["player"], t["team"], t["gd15"], t["csd15"], t["lane_games"])]),
                  key="lane_top")
    with c2:
        if lane.empty:
            chart(viz.empty("No 15-minute data for this selection"), key="lane_bot")
        else:
            lane = lane.assign(late=lane["avg_if"])
            t = lane[lane["gd15"] < 0].nlargest(10, "avg_if")
            if t.empty:
                chart(viz.empty("Nobody behind in lane qualifies"), key="lane_bot")
            else:
                chart(viz.bars(
                    [f"{p} · {ROLE_SHORT.get(r, '')}" for p, r in zip(t["player"], t["role"])], t["avg_if"],
                    "Loses lane, wins game", "Highest Impact among players who trail at 15:00",
                    text=[f"{v:.0f}  ({g:+,.0f} @15)" for v, g in zip(t["avg_if"], t["gd15"])],
                    color=viz.BLUE), key="lane_bot")

    md(h2("Value", "what teams get for the salary they spend"))
    val = pl[pl["games"] >= min_g].dropna(subset=["salary", "avg_if"])
    val = val[val["salary"] > 0]
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        chart(viz.value_scatter(val), key="value_sc")
    with c2:
        if len(val) >= 6:
            slope, icpt = np.polyfit(val["salary"], val["avg_if"], 1)
            val = val.assign(over=val["avg_if"] - (slope * val["salary"] + icpt))
            steals = val.nlargest(8, "over")
            show = steals.assign(Role=steals["role"].map(ROLE_SHORT))
            md('<div class="h2" style="margin-top:0"><span class="h2-text" style="font-size:0.95rem">Biggest bargains</span></div>')
            st.dataframe(show[["player", "team", "Role", "salary", "avg_if", "over"]], hide_index=True,
                         width="stretch", height=320,
                         column_config={"player": "Player", "team": "Team",
                                        "salary": st.column_config.NumberColumn("Salary", format="%g"),
                                        "avg_if": st.column_config.NumberColumn("Impact", format="%.0f"),
                                        "over": st.column_config.NumberColumn("vs. price", format="%+.0f",
                                                                              help="Impact above what that salary usually buys")})
            md(note(f"Across the league, each extra salary point buys about <b>{slope:+.1f}</b> Impact. "
                    "Salaries are the ones locked in at team registration."))

    md(h2("Player profile"))
    names = pl.sort_values("games", ascending=False)
    opts = names["pid"].tolist()
    label = {r.pid: f"{r.player} — {r.team}" for r in names.itertuples()}
    pid = st.selectbox("Player", opts, format_func=label.get, key=f"pl_pick_{SID}",
                       label_visibility="collapsed")
    me = pl[pl["pid"] == pid].iloc[0]
    peers = pl[(pl["role"] == me["role"]) & (pl["games"] >= min(3, me["games"]))]

    def pr(col, inverse=False):
        if pd.isna(me[col]) or peers[col].notna().sum() < 3:
            return None
        p = (peers[col] < me[col]).mean() + 0.5 * (peers[col] == me[col]).mean()
        return 1 - p if inverse else p
    sal_txt = "–" if pd.isna(me["salary"]) else format(me["salary"], "g")
    main_icon = champion_icon(S.ps[S.ps["pid"] == pid]["championName"].mode().iloc[0], 28)
    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        md(f'<div class="hero"><div class="hero-kicker">{ROLE_SHORT.get(me["role"], "Player")} · {esc(me["team"])}</div>'
           f'<div class="hero-name">{esc(me["player"])}</div>'
           f'<div class="hero-meta">{main_icon}'
           f'Main: {esc(me["main"])} · {int(me["champs"])} champions played</div>'
           f'<div class="hero-stats">'
           f'<div class="hero-stat"><div class="v">{int(me["wins"])}–{int(me["games"] - me["wins"])}</div><div class="l">Record</div></div>'
           f'<div class="hero-stat"><div class="v">{me["kda"]:.2f}</div><div class="l">KDA</div></div>'
           f'<div class="hero-stat"><div class="v">{me["avg_if"]:.0f}</div><div class="l">Impact</div></div>'
           f'<div class="hero-stat"><div class="v">{sal_txt}</div><div class="l">Salary</div></div>'
           f'</div></div>')
        md(note(f"Bars show percentile among {len(peers)} {ROLE_SHORT.get(me['role'], '')} players "
                "(blue = top quarter, red = bottom quarter)."))
        md(viz.pct_bars([
            ("Impact", f"{me['avg_if']:.0f}", pr("avg_if")),
            ("KDA", f"{me['kda']:.2f}", pr("kda")),
            ("Kill participation", pct(me["kp"]), pr("kp")),
            ("Damage / min", f"{me['dmg_min']:,.0f}", pr("dmg_min")),
            ("Gold / min", f"{me['gold_min']:,.0f}", pr("gold_min")),
            ("CS / min", f"{me['cs_min']:.1f}", pr("cs_min")),
            ("Vision / min", f"{me['vis_min']:.2f}", pr("vis_min")),
            ("Gold diff @15", "–" if pd.isna(me["gd15"]) else f"{me['gd15']:+,.0f}", pr("gd15")),
            ("Deaths / game", f"{me['d_g']:.1f}", pr("d_g", inverse=True)),
        ]))
    with c2:
        mine = S.ps[S.ps["pid"] == pid].sort_values(["week", "seriesId", "gameNumber"], ascending=False)
        pool = mine.groupby("champion").agg(G=("win", "size"), W=("win", "sum"), K=("kills", "sum"),
                                            D=("deaths", "sum"), A=("assists", "sum")).reset_index()
        pool["KDA"] = [kda(k, d_, a) for k, d_, a in zip(pool["K"], pool["D"], pool["A"])]
        pool["Win%"] = pool["W"] / pool["G"] * 100
        pool = pool.sort_values(["G", "W"], ascending=False)
        st.dataframe(pool[["champion", "G", "W", "Win%", "KDA"]], hide_index=True, width="stretch",
                     height=min(38 * len(pool) + 40, 230),
                     column_config={"champion": "Champion",
                                    "Win%": st.column_config.NumberColumn(format="%.0f%%"),
                                    "KDA": st.column_config.NumberColumn(format="%.2f")})
        log = mine.assign(
            Wk=mine["week"].where(~mine["playoff"], other=0).map(lambda w: "PO" if w == 0 else f"W{w}"),
            Result=mine["win"].map({1: "W", 0: "L"}),
            KDA=[f"{k:.0f}/{d_:.0f}/{a:.0f}" for k, d_, a in zip(mine["kills"], mine["deaths"], mine["assists"])],
            CS=mine["cs"], DMG=mine["totalDamageDealtToChampions"], Time=mine["gameDuration"].map(fmt_time))
        log["GD@15"] = ["" if pd.isna(v) else f"{v:+,.0f}" for v in log["gd15"]]
        st.dataframe(log[["Wk", "opp", "champion", "Result", "KDA", "CS", "DMG", "GD@15", "Time"]],
                     hide_index=True, width="stretch", height=318,
                     column_config={"opp": "Opponent", "champion": "Champion",
                                    "DMG": st.column_config.NumberColumn(format="%d")})


# ═════════════════════════════════════════════════════════════════════════════
# TEAMS
# ═════════════════════════════════════════════════════════════════════════════

def page_teams():
    tt = get_teams(DB, SID)
    tt = tt[tt["team_id"].isin(S.live_ids)]
    if tt.empty:
        st.info("No team stats yet.")
        return
    md(h2("League-wide"))
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        chart(viz.team_quadrant(tt, COLORS), key="team_quad")
    with c2:
        chart(viz.lead_chart(lead_conversion(S)), key="lead_conv")
        fb = tt.sort_values("fb", ascending=False).head(6)
        md(note("Most first bloods: " + ", ".join(f"<b>{esc(t)}</b> {v * 100:.0f}%" for t, v in zip(fb["team"], fb["fb"]))))
    show = tt.sort_values("win_pct", ascending=False).copy()
    for c in ("win_pct", "fb", "ft", "blue_wr", "red_wr"):
        show[c] = show[c] * 100
    show["mins"] = show["mins"].map(lambda m: fmt_time(m * 60))
    st.dataframe(
        show[["team", "games", "win_pct", "kills", "deaths", "gd15", "fb", "ft", "dragons", "barons",
              "turrets", "vis_min", "blue_wr", "red_wr", "champ_pool", "mins"]],
        hide_index=True, width="stretch", height=35 * len(show) + 38,
        column_config={
            "team": st.column_config.TextColumn("Team", pinned=True),
            "games": st.column_config.NumberColumn("GP"),
            "win_pct": st.column_config.NumberColumn("Game win%", format="%.0f%%"),
            "kills": st.column_config.NumberColumn("Kills", format="%.1f"),
            "deaths": st.column_config.NumberColumn("Deaths", format="%.1f"),
            "gd15": st.column_config.NumberColumn("GD@15", format="%+.0f", help="Team gold difference at 15:00"),
            "fb": st.column_config.NumberColumn("FB%", format="%.0f%%", help="First blood rate"),
            "ft": st.column_config.NumberColumn("FT%", format="%.0f%%", help="First tower rate"),
            "dragons": st.column_config.NumberColumn("Drakes", format="%.1f"),
            "barons": st.column_config.NumberColumn("Barons", format="%.1f"),
            "turrets": st.column_config.NumberColumn("Turrets", format="%.1f"),
            "vis_min": st.column_config.NumberColumn("Vis/m", format="%.1f"),
            "blue_wr": st.column_config.NumberColumn("Blue W%", format="%.0f%%"),
            "red_wr": st.column_config.NumberColumn("Red W%", format="%.0f%%"),
            "champ_pool": st.column_config.NumberColumn("Champs", help="Unique champions played"),
            "mins": "Avg time",
        })
    md(note("Per-game averages over every game the team actually played (exhibition weeks included). "
            "Objective counts need the site's team stat lines and are blank for seasons without them."))

    md(h2("Team deep dive"))
    st_all = S.standings()
    order = st_all[~st_all["dropped"]]["team_id"].tolist()
    tid = st.selectbox("Team", order, format_func=lambda t: S.names.get(t, t), key=f"team_pick_{SID}",
                       label_visibility="collapsed")
    me = tt[tt["team_id"] == tid]
    if me.empty:
        st.info("This team has no recorded games.")
        return
    me = me.iloc[0]
    row = st_all[st_all["team_id"] == tid].iloc[0]
    grp = S.standings(group=S.groups[tid]) if S.cross_group and tid in S.groups else st_all
    place = int(grp[grp["team_id"] == tid]["rank"].iloc[0])
    place_txt = f"{place}{'st' if place == 1 else 'nd' if place == 2 else 'rd' if place == 3 else 'th'}" + \
                (f" in Group {S.groups[tid]}" if S.cross_group and tid in S.groups else "")

    def pr(col, inverse=False):
        if pd.isna(me[col]) or tt[col].notna().sum() < 3:
            return None
        p = (tt[col] < me[col]).mean() + 0.5 * (tt[col] == me[col]).mean()
        return 1 - p if inverse else p
    cap_txt = "" if not S.cap or pd.isna(S.cap) else " of " + format(S.cap, "g") + " cap"
    form_html = viz._form_pills(row["form"])
    odds = "" if MAKE is None else (
        f'<div class="hero-stat"><div class="v">{pct(MAKE.get(tid))}</div><div class="l">Playoff odds</div></div>')
    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        md(f'<div class="hero" style="border-top-color:{COLORS.get(tid, "#FFD700")}">'
           f'<div class="hero-kicker">{esc(place_txt)}</div><div class="hero-name">{esc(S.names[tid])}</div>'
           f'<div class="hero-meta">Roster salary {S.salary.get(tid, 0):g}{cap_txt} · form {form_html}</div>'
           f'<div class="hero-stats">'
           f'<div class="hero-stat"><div class="v">{row["series_w"]}–{row["series_l"]}</div><div class="l">Series</div></div>'
           f'<div class="hero-stat"><div class="v">{row["game_w"]}–{row["game_l"]}</div><div class="l">Games</div></div>'
           f'<div class="hero-stat"><div class="v">{RATING.get(tid, STARTING_ELO):.0f}</div><div class="l">Rating</div></div>'
           f'{odds}</div></div>')
        md(note(f"Percentile among {len(tt)} teams (blue = top quarter, red = bottom quarter)."))
        md(viz.pct_bars([
            ("Kills / game", f"{me['kills']:.1f}", pr("kills")),
            ("Deaths / game", f"{me['deaths']:.1f}", pr("deaths", inverse=True)),
            ("Gold diff @15", "–" if pd.isna(me["gd15"]) else f"{me['gd15']:+,.0f}", pr("gd15")),
            ("First blood", pct(me["fb"]), pr("fb")),
            ("First tower", pct(me["ft"]), pr("ft")),
            ("Dragons / game", "–" if pd.isna(me["dragons"]) else f"{me['dragons']:.1f}", pr("dragons")),
            ("Barons / game", "–" if pd.isna(me["barons"]) else f"{me['barons']:.1f}", pr("barons")),
            ("Vision / min", f"{me['vis_min']:.1f}", pr("vis_min")),
            ("Champion pool", f"{int(me['champ_pool'])}", pr("champ_pool")),
        ]))
    with c2:
        tps = S.ps[S.ps["leagueTeamId"] == tid]
        ros = player_table(tps)
        imp = get_players(DB, SID)[["pid", "avg_if"]]
        ros = ros.merge(imp, on="pid", how="left").sort_values("games", ascending=False)
        ros["Role"] = ros["role"].map(ROLE_SHORT)
        md('<div class="h2" style="margin-top:0"><span class="h2-text" style="font-size:0.95rem">Who played</span></div>')
        st.dataframe(ros[["player", "Role", "games", "wins", "kda", "avg_if", "gd15", "main", "salary"]],
                     hide_index=True, width="stretch", height=min(38 * len(ros) + 40, 290),
                     column_config={"player": "Player", "games": "GP", "wins": "W", "main": "Most played",
                                    "kda": st.column_config.NumberColumn("KDA", format="%.2f"),
                                    "avg_if": st.column_config.NumberColumn("Impact", format="%.0f"),
                                    "gd15": st.column_config.NumberColumn("GD@15", format="%+.0f"),
                                    "salary": st.column_config.NumberColumn("Salary", format="%g")})
        cc1, cc2 = st.columns(2)
        with cc1:
            pool = tps.groupby("champion").agg(G=("win", "size"), W=("win", "sum")).reset_index()
            pool["Win%"] = pool["W"] / pool["G"] * 100
            pool = pool.sort_values(["G", "W"], ascending=False).head(8)
            md('<div class="h2" style="margin-top:0.6rem"><span class="h2-text" style="font-size:0.95rem">Go-to picks</span></div>')
            st.dataframe(pool, hide_index=True, width="stretch", height=320,
                         column_config={"champion": "Champion",
                                        "Win%": st.column_config.NumberColumn(format="%.0f%%")})
        with cc2:
            dr = get_draft(DB, SID)
            md('<div class="h2" style="margin-top:0.6rem"><span class="h2-text" style="font-size:0.95rem">Banned against them</span></div>')
            if dr.get("drafts"):
                b = dr["bans"]
                b = b[b["target"] == tid]
                n_d = b["sessionId"].nunique()
                ba = b.groupby("champion").size().rename("Bans").reset_index().sort_values("Bans", ascending=False).head(8)
                ba["Rate"] = ba["Bans"] / max(n_d, 1) * 100
                st.dataframe(ba, hide_index=True, width="stretch", height=320,
                             column_config={"champion": "Champion",
                                            "Rate": st.column_config.NumberColumn("of drafts", format="%.0f%%")})
            else:
                md(note("No draft-tool data for this season."))

    md('<div class="h2"><span class="h2-bar"></span><span class="h2-text">Results</span></div>')
    reg = S.regular
    mine = reg[((reg["team1Id"] == tid) | (reg["team2Id"] == tid)) & (reg["status"] == "COMPLETED") & ~reg["has_dropped"]]
    cards = [viz.result_card(r.team1Name, r.team2Name, r.t1w, r.t2w, COLORS.get(r.team1Id, "#64748b"),
                             COLORS.get(r.team2Id, "#64748b"), "",
                             f"Week {r.week}" + (" · exhibition" if r.isOog else ""))
             for r in mine.sort_values("week").itertuples()]
    md(f'<div class="card-grid">{"".join(cards)}</div>' if cards else note("No completed series."))


# ═════════════════════════════════════════════════════════════════════════════
# CHAMPIONS & DRAFT
# ═════════════════════════════════════════════════════════════════════════════

def page_champions():
    ch = get_champs(DB, SID)
    if ch.empty:
        st.info("No champion data yet.")
        return
    dr = get_draft(DB, SID)
    played = ch[ch["picks"] > 0]
    n_stat_games = int(S.games["has_stats"].sum())
    top_pres = ch.iloc[0]
    most_banned = ch.sort_values("bans", ascending=False).iloc[0]
    never = ch[(ch["picks"] == 0) & (ch["bans"] >= 3)].sort_values("bans", ascending=False)
    md(kpi_row([
        kpi("Champions played", f"{len(played)}", f"{len(ch)} picked or banned"),
        kpi("Most contested", esc(top_pres["champion"]), f"{top_pres['presence'] * 100:.0f}% presence"),
        kpi("Most banned", esc(most_banned["champion"]) if most_banned["bans"] else "–",
            f"{int(most_banned['bans'])} bans" if most_banned["bans"] else "no ban data"),
        kpi("Blue side wins", pct(dr.get("blue_wr")), f"{dr.get('games', 0)} games"),
        kpi("Banned, never played", esc(never.iloc[0]["champion"]) if len(never) else "–",
            f"{int(never.iloc[0]['bans'])} bans, 0 picks" if len(never) else ""),
    ]))
    c1, c2 = st.columns([1, 3])
    with c1:
        min_p = st.slider("Minimum games", 1, max(2, int(played["picks"].max())),
                          min(5, int(played["picks"].max())), key=f"ch_min_{SID}")
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        chart(viz.champion_scatter(played, min_p), key="champ_sc")
    with c2:
        q = played[played["picks"] >= min_p].nlargest(10, "wilson_lo")
        chart(viz.bars(q["champion"], q["win_rate"] * 100, "Most reliable winners",
                       "Ranked by the low end of a 95% interval, so 2–0 flukes don't top the list",
                       text=[f"{w * 100:.0f}%  ({int(wi)}–{int(p - wi)})" for w, wi, p in zip(q["win_rate"], q["wins"], q["picks"])],
                       ref=50), key="champ_rel")

    md(h2("Every champion", "click a column to sort"))
    c1, c2 = st.columns([2, 3])
    with c1:
        role = st.radio("Role", ["All"] + ROLES, horizontal=True, format_func=lambda r: ROLE_SHORT.get(r, "All"),
                        key="ch_role")
    t = ch if role == "All" else ch[ch["role"] == role]
    t = t.assign(Role=t["role"].map(ROLE_SHORT), presence=t["presence"] * 100, win_rate=t["win_rate"] * 100,
                 ban_rate=t["ban_rate"] * 100)
    st.dataframe(
        t[["champion", "Role", "presence", "picks", "bans", "wins", "win_rate", "kda", "players", "gd15"]],
        hide_index=True, width="stretch", height=420,
        column_config={
            "champion": st.column_config.TextColumn("Champion", pinned=True),
            "presence": st.column_config.ProgressColumn("Presence", min_value=0, max_value=100, format="%.0f%%",
                                                        help="Share of games in which the champion was picked or banned"),
            "picks": "Picks", "bans": "Bans", "wins": "Wins",
            "win_rate": st.column_config.NumberColumn("Win%", format="%.0f%%"),
            "kda": st.column_config.NumberColumn("KDA", format="%.2f"),
            "players": st.column_config.NumberColumn("Players", help="Different players who picked it"),
            "gd15": st.column_config.NumberColumn("GD@15", format="%+.0f"),
        })

    md(h2("Draft", "from the league site's draft tool" if dr.get("drafts") else ""))
    if dr.get("drafts"):
        prio = dr["priority"].copy()
        prio["champion"] = prio["championKey"].map(champ_name)
        c1, c2 = st.columns(2, gap="large")
        with c1:
            b = ch[ch["bans"] > 0].nlargest(12, "bans")
            chart(viz.bars(b["champion"], b["ban_rate"] * 100, "Most banned",
                           f"Share of {dr['drafts']} drafts",
                           text=[f"{r * 100:.0f}%  ({int(n)})" for r, n in zip(b["ban_rate"], b["bans"])],
                           color=viz.RED), key="bans")
        with c2:
            p = prio[prio["r1"] > 0].nlargest(12, "r1")
            chart(viz.bars(p["champion"], p["r1"], "First-rotation picks",
                           "Times taken with one of the first three picks of a draft",
                           text=[str(int(n)) + ("" if pd.isna(w) else "  ·  %.0f%% wins" % (w * 100))
                                 for n, w in zip(p["r1"], p["wr"])]),
                  key="prio")
        c1, c2 = st.columns(2, gap="large")
        with c1:
            chart(viz.role_slot_heatmap(dr["role_slot"]), key="roleslot")
        with c2:
            chart(viz.side_chart(side_by_week(S), dr["blue_wr"]), key="sidewk")
        if S.fearless:
            picks = dr["picks"]
            ser = S.games.set_index("matchId")["seriesId"]
            per_series = picks.assign(seriesId=picks["matchId"].map(ser)).groupby("seriesId")["championKey"].nunique()
            md(note(f"<b>Fearless draft:</b> a champion can be picked once per series. The average series "
                    f"burned through <b>{per_series.mean():.0f}</b> different champions; the deepest went "
                    f"through <b>{int(per_series.max())}</b>."))
    else:
        b = ch[ch["bans"] > 0].nlargest(12, "bans")
        if b.empty:
            md(note("No ban data was recorded for this season."))
        else:
            chart(viz.bars(b["champion"], b["ban_rate"] * 100, "Most banned", "Share of games with ban data",
                           text=[f"{r * 100:.0f}%  ({int(n)})" for r, n in zip(b["ban_rate"], b["bans"])],
                           color=viz.RED), key="bans")
            chart(viz.side_chart(side_by_week(S), dr["blue_wr"]), key="sidewk")

    items, sf = get_items(DB, SID)
    if not items.empty:
        md(h2("Items", "completed items in the final build"))
        c1, c2 = st.columns(2, gap="large")
        with c1:
            t = items.nlargest(12, "games")
            chart(viz.bars(t["item_name"], t["games"], "Most built", "Final-build appearances",
                           text=[f"{int(g)}  ·  {w * 100:.0f}% wins" for g, w in zip(t["games"], t["win_rate"])]),
                  key="items_built")
        with c2:
            q = items[items["games"] >= max(10, n_stat_games // 12)].copy()
            q["delta"] = (q["win_rate"] - 0.5) * 100
            q = pd.concat([q.nlargest(6, "delta"), q.nsmallest(6, "delta")]).drop_duplicates("item_id")
            q = q.sort_values("delta", ascending=False)
            chart(viz.diverging_bars(q["item_name"], q["delta"], "Winning and losing builds",
                                     "Win rate vs. 50% when the item is in the final build",
                                     fmt="{:+.0f} pts",
                                     hover=[f"{n}: {w * 100:.0f}% over {int(g)} builds" for n, w, g in
                                            zip(q["item_name"], q["win_rate"], q["games"])]), key="items_wr")
        md(note("Items in a final build are a result as much as a cause — winning teams get to finish "
                "expensive items, losing teams end on defensive ones."))
        if sf["total_builds"]:
            from app.styling import sunfire_counter
            top = pd.Series([b["player"] for b in sf["builders"]]).value_counts().head(6)
            md(sunfire_counter(sf["total_builds"], sf["wins"], sf["losses"], sf["win_rate"], None))
            md(note("Repeat offenders: " + ", ".join(f"<b>{esc(p)}</b> ×{n}" for p, n in top.items())))


# ═════════════════════════════════════════════════════════════════════════════
# FORECASTS
# ═════════════════════════════════════════════════════════════════════════════

def page_forecasts():
    live = LADDER[LADDER["team_id"].isin(S.live_ids)].reset_index(drop=True)
    prev_week = max([w for w in S.weeks[:-1]], default=0)
    prev, _ = get_ladder(DB, SID, prev_week)
    prev_map = dict(zip(prev["team_id"], prev["elo"]))
    prev_rank = {t: i + 1 for i, t in enumerate(prev[prev["team_id"].isin(S.live_ids)]["team_id"])}
    seed_map = HISTORY[HISTORY["week"] == 0].set_index("team_id")["elo"].to_dict() if not HISTORY.empty else {}

    md(h2("Power rankings", "Glicko-2 · seeded by roster salary, then every game moves it"))
    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        rows = []
        for i, r in enumerate(live.itertuples(), start=1):
            d_rank = prev_rank.get(r.team_id, i) - i
            rows.append({"#": i, "Team": r.name, "Rating": r.elo,
                         "Move": "▲" + str(d_rank) if d_rank > 0 else ("▼" + str(-d_rank) if d_rank < 0 else "–"),
                         "Wk": r.elo - prev_map.get(r.team_id, r.elo),
                         "vs seed": r.elo - seed_map.get(r.team_id, r.elo),
                         "±": 2 * r.rd})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     height=35 * len(rows) + 38,
                     column_config={
                         "#": st.column_config.NumberColumn(width=40),
                         "Rating": st.column_config.NumberColumn(format="%.0f"),
                         "Move": st.column_config.TextColumn(help="Places gained or lost since last week"),
                         "Wk": st.column_config.NumberColumn("Last wk", format="%+.0f"),
                         "vs seed": st.column_config.NumberColumn(format="%+.0f",
                                                                  help="Rating now minus the preseason salary seed"),
                         "±": st.column_config.NumberColumn(format="%.0f", help="95% uncertainty band"),
                     })
    with c2:
        names = dict(zip(live["team_id"], live["name"]))
        default = live["team_id"].head(4).tolist() + live["team_id"].tail(1).tolist()
        focus = st.multiselect("Highlight teams", live["team_id"].tolist(), default=default,
                               format_func=names.get, key=f"focus_{SID}")
        hist = HISTORY[HISTORY["team_id"].isin(S.live_ids)]
        chart(viz.ladder_history(hist, COLORS, focus, S.max_regular_week, height=470), key="ladder")
    if seed_map:
        delta = live.assign(d=[r.elo - seed_map.get(r.team_id, r.elo) for r in live.itertuples()])
        best, worst = delta.nlargest(1, "d").iloc[0], delta.nsmallest(1, "d").iloc[0]
        md(note(f"Biggest overachiever vs. its salary seed: <b>{esc(best['name'])}</b> ({best['d']:+.0f}). "
                f"Biggest disappointment: <b>{esc(worst['name'])}</b> ({worst['d']:+.0f})."))

    sc = forecast_scorecard(FORE)
    md(h2("Model vs. the crowd", "pre-series picks, graded on results"))
    if not sc.get("n_model"):
        md(note("No completed series to grade yet."))
        return
    if sc.get("n"):
        better = "model" if sc["model_brier"] < sc["crowd_brier"] else "crowd"
        md(kpi_row([
            kpi("Model picks", pct(sc["model_acc"]), f"{sc['n']} series both called"),
            kpi("Crowd picks", pct(sc["crowd_acc"]), "majority of Crystal Ball picks"),
            kpi("Model Brier", f"{sc['model_brier']:.3f}", "0.25 = coin flip · lower is better",
                tone="gold" if better == "model" else ""),
            kpi("Crowd Brier", f"{sc['crowd_brier']:.3f}", "pick share treated as a probability",
                tone="gold" if better == "crowd" else ""),
            kpi("When they disagreed", f"{sc['model_wins_disagree']}–{sc['disagree'] - sc['model_wins_disagree']}",
                "model right – crowd right"),
        ]))
    else:
        md(kpi_row([
            kpi("Model picks", pct(sc["model_acc_all"]), f"{sc['n_model']} series"),
            kpi("Model Brier", f"{sc['model_brier_all']:.3f}", "0.25 = coin flip · lower is better"),
        ]))
        md(note("No Crystal Ball picks exist for this season, so there is no crowd to compare against."))
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        chart(viz.calibration_chart(calibration(FORE, "p_model"), calibration(FORE, "p_crowd")), key="calib")
    with c2:
        ups = FORE[FORE["winner_p_model"].notna()].nsmallest(6, "winner_p_model")
        md('<div class="h2" style="margin-top:0"><span class="h2-text" style="font-size:0.95rem">Biggest upsets</span></div>')
        for r in ups.itertuples():
            w, l = (r.t1Name, r.t2Name) if r.t1_won == 1 else (r.t2Name, r.t1Name)
            crowd = f" · crowd {r.winner_p_crowd * 100:.0f}%" if pd.notna(r.winner_p_crowd) and r.n_picks >= 5 else ""
            md(f'<div class="rc" style="margin-bottom:6px"><div class="rc-sub" style="margin-top:0">'
               f'<b style="color:#f1f5f9">W{r.week} · {esc(w)}</b> over {esc(l)} — model {r.winner_p_model * 100:.0f}%{crowd}</div></div>')
    md(note("The model's number is the Glicko-2 series probability from ratings <b>before</b> that week "
            "(salary seeds before week 1), shrunk toward 50% to stay calibrated. The crowd's number is the "
            "share of Crystal Ball picks on each side. Series involving dropped teams are excluded, as on the site."))

    lb = S.pickem_leaderboard()
    if not lb.empty:
        md(h2("Crystal Ball leaderboard", "exact score = 3 points · right winner = 1"))
        lb = lb[lb["picks"] >= 5].head(15).copy()
        lb.insert(0, "#", range(1, len(lb) + 1))
        lb["accuracy"] = lb["accuracy"] * 100
        st.dataframe(lb[["#", "username", "points", "exact", "correct", "picks", "accuracy"]],
                     hide_index=True, width="stretch", height=35 * len(lb) + 38,
                     column_config={"#": st.column_config.NumberColumn(width=40), "username": "Predictor", "points": "Points", "exact": "Exact scores",
                                    "correct": "Right winner", "picks": "Graded picks",
                                    "accuracy": st.column_config.ProgressColumn("Winner accuracy", min_value=0,
                                                                                max_value=100, format="%.0f%%")})


# ── Router ───────────────────────────────────────────────────────────────────

{
    "Overview": page_overview,
    "Standings & Playoffs": page_standings,
    "Weekly Recap": page_recap,
    "Players": page_players,
    "Teams": page_teams,
    "Champions & Draft": page_champions,
    "Forecasts": page_forecasts,
}[PAGE]()

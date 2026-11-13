"""
Beer League Stats — static site builder.

Runs every analysis ONCE (after the nightly DB sync) and writes plain JSON
into docs/data/. The site in docs/ is then just static files: a hundred
people can browse the deep analytics and the only thing serving them is a
CDN — no Python process, no database, nothing on the league web server.

    python build_site.py            # newest snapshot in ./data  ->  docs/data
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from app import playoff
from app.impact_factor import compute_impact_factors
from app.insights import (
    calibration, draft_summary, forecast_scorecard, ladder, lead_conversion,
    series_forecasts, side_by_week, storylines,
)
from app.league import (
    ROLE_SHORT, Season, champ_name, champion_table, data_through, kda, latest_db,
    load_seasons, player_table, team_table,
)
from app.viz import team_colors
from app.labs import lab
from app.extras import (
    champion_extras, fun_awards, item_table, real_bracket, seeded_bracket, team_styles,
    title_odds, win_conditions,
)

OUT = Path(__file__).resolve().parent / "docs" / "data"


def clean(o):
    """Make anything JSON-safe: NaN/NaT -> null, numpy -> python, round floats."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    if o is None or o is pd.NaT:
        return None
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    try:
        if pd.isna(o):
            return None
    except (TypeError, ValueError):
        pass
    return o


def recs(df: pd.DataFrame, cols: list | dict) -> list:
    """DataFrame -> list of dicts with only the listed (optionally renamed) columns."""
    if df is None or df.empty:
        return []
    if isinstance(cols, dict):
        df = df[list(cols)].rename(columns=cols)
    else:
        df = df[cols]
    return clean(df.to_dict("records"))


def impact_table(ps: pd.DataFrame) -> pd.DataFrame:
    if ps.empty:
        return pd.DataFrame()
    df = compute_impact_factors(ps.assign(position=ps["role"]))
    g = df.groupby("pid")
    out = g.agg(player=("player", "last"), games=("win", "size"), wins=("win", "sum"),
                impact=("impact_factor", "mean"), k=("kills", "sum"), d=("deaths", "sum"),
                a=("assists", "sum"), kp=("killParticipation", "mean")).reset_index()
    out["team"] = g["team"].agg(lambda s: s.mode().iloc[0]).values
    out["team_id"] = g["leagueTeamId"].agg(lambda s: s.mode().iloc[0]).values
    out["role"] = g["role"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None).values
    out["champ_key"] = g["championName"].agg(lambda s: s.mode().iloc[0]).values
    out["champs"] = g["champion"].agg(lambda s: ", ".join(list(dict.fromkeys(s))[:3])).values
    out["kda"] = [kda(k, d, a) for k, d, a in zip(out["k"], out["d"], out["a"])]
    # names used by insights.storylines
    out["avg_if"] = out["impact"]
    return out.sort_values("impact", ascending=False).reset_index(drop=True)


def bracket(seeds: list, cross: bool) -> list:
    n = len(seeds)
    if n < 2:
        return []
    size = 1 << (n - 1).bit_length()
    byes = size - n
    by = {s: (tid, lab) for s, tid, lab in seeds}
    out = []
    for hi in range(byes + 1, size // 2 + 1):
        lo = size + 1 - hi
        if hi in by and lo in by:
            out.append({"kind": "match", "title": f"Seed {hi} v {lo}",
                        "a": {"seed": hi, "team": by[hi][0], "label": by[hi][1] if cross else str(hi)},
                        "b": {"seed": lo, "team": by[lo][0], "label": by[lo][1] if cross else str(lo)}})
    for s in range(1, byes + 1):
        out.append({"kind": "bye", "title": f"Seed {s} · bye",
                    "a": {"seed": s, "team": by[s][0], "label": by[s][1] if cross else str(s)}})
    return out


def _champion_keys() -> set:
    """Every champion in the game (Data Dragon), or empty when offline."""
    try:
        from app.data_loader import _ddragon_data
        return set(_ddragon_data()[2].values())
    except Exception:
        return set()


def _round_formats(db: str, sid: str) -> dict:
    import sqlite3
    try:
        with sqlite3.connect(db) as conn:
            row = conn.execute("SELECT roundFormats FROM playoff_config WHERE seasonId = ?", (sid,)).fetchone()
        return json.loads(row[0]) if row and row[0] else {}
    except Exception:
        return {}


def build_season(db: str, sid: str) -> dict:
    S = Season(db, sid)
    colors = team_colors(S.teams)
    out = {
        "id": S.id, "name": S.name, "band": S.band, "active": S.active,
        "spots": S.playoff_spots, "cross_group": S.cross_group, "groups": S.group_labels,
        "fearless": S.fearless, "weeks": S.weeks, "max_week": S.max_regular_week,
        "tiebreakers": S.tiebreaker_text, "cap": S.cap,
        "champion": None if S.active or pd.isna(S.meta.get("championTeamId"))
        else str(S.meta.get("championTeamId")).replace(".0", ""),
        "teams": {tid: {"name": S.names[tid], "tag": S.tags.get(tid, ""), "color": colors[tid],
                        "group": S.groups.get(tid), "salary": S.salary.get(tid),
                        "dropped": tid in S.dropped,
                        "drop_mode": ("forfeit" if tid in S.forfeit else "void") if tid in S.dropped else None}
                  for tid in S.teams["teamId"]},
    }
    if S.games.empty:
        return clean(out)

    # ── ratings + forecasts ────────────────────────────────────────────
    lad, hist = ladder(S, 999)
    rating = dict(zip(lad["team_id"], lad["elo"]))
    out["ratings"] = {
        "weeks": sorted(hist["week"].unique().tolist()) if not hist.empty else [],
        "by_team": {tid: d.sort_values("week")["elo"].round(0).tolist()
                    for tid, d in hist.groupby("team_id")} if not hist.empty else {},
        "rd": dict(zip(lad["team_id"], lad["rd"])),
    }
    fore = series_forecasts(S)

    # ── standings, week by week (drives the animated table) ───────────
    def table(week, group=None):
        st = S.standings(week, group)
        return [{"t": r.team_id, "sw": r.series_w, "sl": r.series_l, "gw": r.game_w, "gl": r.game_l,
                 "form": r.form, "streak": r.streak, "tied": r.tied, "dropped": r.dropped}
                for r in st.itertuples()]
    weeks = S.weeks
    out["standings"] = {
        str(w): ({g: table(w, g) for g in S.group_labels} if S.cross_group else {"all": table(w)})
        for w in weeks
    }
    out["sos"] = S.strength_of_schedule()

    # ── playoff picture ────────────────────────────────────────────────
    seeds = S.seed_order()
    out["bracket"] = bracket(seeds, S.cross_group)
    if S.active:
        sim = playoff.simulate(S, rating, dict(zip(lad["team_id"], lad["rd"])))
        probs = playoff.seed_probabilities(sim)
        spots = sim["playoff_spots"]
        out["playoff"] = {
            "n_sims": sim["n_sims"], "spots": spots,
            "remaining": [{k: r[k] for k in ("seriesId", "week", "t1Id", "t2Id", "p_t1")}
                          for r in sim["remaining"]],
            "teams": [{"t": r.team_id, "make": r.make_playoffs, "avg_seed": r.avg_seed,
                       "seeds": [getattr(r, f"seed_{k}") for k in range(1, spots + 1)], "miss": r.miss}
                      for r in probs.sort_values("avg_seed").itertuples()],
            "pins": None if not sim["remaining"] else {
                "n": min(sim["n_sims"], 2000), "teams": sim["team_ids"],
                "outcomes": ["".join(map(str, sim["sim_outcomes"][:2000, s]))
                             for s in range(len(sim["remaining"]))],
                "seeds": ["".join(chr(48 + int(v)) for v in sim["sim_seeds"][:2000, i])
                          for i in range(len(sim["team_ids"]))],
            },
            "leverage": recs(playoff.leverage(sim).assign(a=lambda d: d["swing"].abs())
                             .sort_values("a", ascending=False).drop_duplicates("seriesId").head(5),
                             ["week", "team_id", "t1", "t2", "if_t1", "if_t2"]),
        }
    if S.active:
        rdm = dict(zip(lad["team_id"], lad["rd"]))
        br = real_bracket(S)
        out["bracket_real"] = br is not None
        if br is None and len(seeds) >= 2:
            br = seeded_bracket([tid for _, tid, _ in seeds], _round_formats(db, sid))
        if br:
            out["title"] = title_odds(S, rating, rdm, br)
    po = S.playoffs[S.playoffs["status"] == "COMPLETED"]
    out["playoff_results"] = [
        {"label": str(r.label or "Playoffs").title(), "t1": r.team1Id, "t2": r.team2Id,
         "s1": r.t1w, "s2": r.t2w}
        for r in po.sort_values("seriesId", key=lambda s: s.astype(int)).itertuples()]

    # ── series (results + upcoming, with model and crowd numbers) ─────
    if not fore.empty:
        out["series"] = recs(fore, {
            "seriesId": "id", "week": "week", "status": "status", "isOog": "oog", "t1": "t1", "t2": "t2",
            "t1w": "s1", "t2w": "s2", "p_model": "pm", "p_crowd": "pc", "n_picks": "n",
            "likely": "likely", "winner_p_model": "wpm", "winner_p_crowd": "wpc", "t1_won": "t1won"})
    else:
        out["series"] = []
    sc = forecast_scorecard(fore)
    out["forecast"] = {
        "score": sc,
        "cal_model": recs(calibration(fore, "p_model").astype({"bin": str}), ["bin", "n", "said", "actual"])
        if not calibration(fore, "p_model").empty else [],
        "cal_crowd": recs(calibration(fore, "p_crowd").astype({"bin": str}), ["bin", "n", "said", "actual"])
        if not calibration(fore, "p_crowd").empty else [],
    }
    lb = S.pickem_leaderboard()
    out["pickem"] = recs(lb[lb["picks"] >= 5].head(15), ["username", "points", "exact", "correct", "picks", "accuracy"]) \
        if not lb.empty else []

    # ── weekly: storylines, player of the week, facts ─────────────────
    ps = S.ps
    weekly = {}
    for w in weeks:
        wk = ps[(ps["week"] == w) & ~ps["playoff"]]
        g = S.games[(S.games["week"] == w) & ~S.games["playoff"]]
        pw = impact_table(wk)
        side = g[g["blueWon"].notna()]
        kills = wk.groupby("matchId")["kills"].sum()
        mk = wk[(wk["pentaKills"] > 0) | (wk["quadraKills"] > 0)]
        weekly[str(w)] = {
            "stories": [{"tag": t, "html": h} for t, h, _ in storylines(S, w, fore, pw)[:8]],
            "potw": recs(pw.head(10), ["player", "team", "team_id", "role", "champ_key", "champs", "games",
                                       "wins", "impact", "k", "d", "a", "kda", "kp"]),
            "games": len(g), "avg_time": g["duration"].mean(),
            "kills": kills.mean() if len(kills) else None,
            "blue": side["blueWon"].astype(bool).mean() if len(side) else None,
            "durations": [{"s": d, "w": t, "l": l} for d, t, l in
                          zip(g["duration"], g["winnerId"], g["loserId"]) if pd.notna(d)],
            "multikills": [{"kind": "Penta" if r.pentaKills else "Quadra", "player": r.player,
                            "champ": r.champion, "team": r.leagueTeamId, "opp": r.oppTeamId}
                           for r in mk.sort_values("pentaKills", ascending=False).itertuples()],
        }
    out["weekly"] = weekly

    # ── season KPIs ────────────────────────────────────────────────────
    g = S.games
    side = g[g["blueWon"].notna()]
    top_champ = ps["champion"].value_counts()
    out["kpi"] = {
        "games": len(g), "series": int((S.regular["status"] == "COMPLETED").sum()),
        "avg_time": g["duration"].mean(), "max_time": g["duration"].max(),
        "blue": side["blueWon"].astype(bool).mean() if len(side) else None, "side_games": len(side),
        "champs": ps["championName"].nunique(),
        "top_champ": top_champ.index[0] if len(top_champ) else None,
        "top_champ_n": int(top_champ.iloc[0]) if len(top_champ) else 0,
        "pentas": int(ps["pentaKills"].sum()), "quadras": int(ps["quadraKills"].sum()),
    }

    # ── players / teams / champions ───────────────────────────────────
    pl = player_table(ps)
    if not pl.empty:
        pl = pl.merge(impact_table(ps)[["pid", "impact"]], on="pid", how="left")
        pool = (ps.groupby(["pid", "champion"]).agg(g=("win", "size"), w=("win", "sum")).reset_index()
                .sort_values(["g", "w"], ascending=False))
        pools = {pid: [{"c": r.champion, "g": int(r.g), "w": int(r.w)} for r in d.head(6).itertuples()]
                 for pid, d in pool.groupby("pid")}
        pl["pool"] = pl["pid"].map(pools)
        out["players"] = recs(pl, ["pool", "player", "team", "team_id", "role", "games", "wins", "impact", "kda",
                                   "k_g", "d_g", "a_g", "kp", "dmg_share", "dmg_min", "gold_min", "cs_min",
                                   "vis_min", "gd15", "csd15", "lane_games", "salary", "main", "champs"])
    tt = team_table(S)
    if not tt.empty:
        tt = tt[tt["team_id"].isin(S.live_ids)]
        out["team_stats"] = recs(tt, ["team_id", "games", "win_pct", "kills", "deaths", "gd15", "fb", "ft",
                                      "dragons", "barons", "turrets", "vis_min", "blue_wr", "red_wr",
                                      "champ_pool", "mins"])
    out["lead"] = recs(lead_conversion(S).astype({"bucket": str}), ["bucket", "games", "wr"]) \
        if not lead_conversion(S).empty else []
    ch = champion_table(ps, S.ban_table(), int(S.games["has_stats"].sum()))
    out["champions"] = recs(ch, {"champion": "name", "championKey": "key", "role": "role", "picks": "picks",
                                 "bans": "bans", "wins": "wins", "win_rate": "wr", "presence": "presence",
                                 "kda": "kda", "players": "players", "gd15": "gd15", "wilson_lo": "wlo"})
    dr = draft_summary(S)
    draft = {"games": dr["games"], "blue": dr["blue_wr"], "drafts": dr["drafts"],
             "side_weeks": recs(side_by_week(S), ["week", "games", "blue"])}
    if dr["drafts"]:
        pr = dr["priority"].assign(name=dr["priority"]["championKey"].map(champ_name))
        draft["priority"] = recs(pr[pr["r1"] > 0].nlargest(12, "r1"), ["name", "r1", "picks", "wr"])
        draft["role_slot"] = recs(dr["role_slot"], ["role", "pick_no", "n"])
    out["draft"] = draft

    # ── the fun stuff ──────────────────────────────────────────────────
    out["wins"] = win_conditions(S)
    out["styles"] = team_styles(S)
    out["champ_x"] = champion_extras(S, _champion_keys())
    out["fun"] = fun_awards(S)
    out["items"] = item_table(db, S)
    out["lab"] = lab(S)
    return clean(out)


def main():
    db = latest_db()
    if db is None:
        sys.exit("no database snapshot in ./data")
    db = str(db)
    OUT.mkdir(parents=True, exist_ok=True)
    seasons = load_seasons(db)
    index = {"data_through": data_through(db), "roles": ROLE_SHORT, "seasons": []}
    for r in seasons.itertuples():
        data = build_season(db, r.id)
        path = OUT / f"season_{r.id}.json"
        path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        index["seasons"].append({"id": r.id, "name": r.name, "band": r.band,
                                 "active": r.status == "ACTIVE"})
        print(f"  {r.name:<36} {path.stat().st_size / 1024:7.0f} KB")
    (OUT / "index.json").write_text(json.dumps(clean(index), separators=(",", ":"), ensure_ascii=False),
                                    encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()

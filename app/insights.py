"""
Beer League Stats — derived analyses (pure functions, no Streamlit).

  * ladder            : Glicko ladder snapshot through a week
  * series_forecasts  : walk-forward pre-series odds for every series, joined
                        with the Crystal Ball crowd split -> model vs. crowd
  * storylines        : the handful of things worth saying out loud this week
  * draft_summary     : pick-order / side / first-pick numbers from the draft tool
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.elo import compute_elo_through_week, win_probability, STARTING_ELO
from app.league import Season, score_distribution, team_table


def ladder(season: Season, through_week: int):
    """(standings_df, history_df) through the given week (0 = salary seeds)."""
    return compute_elo_through_week(season.rating_games(), through_week,
                                    season.names, season.salary)


def series_forecasts(season: Season) -> pd.DataFrame:
    """One row per regular-season series between two live teams.

    Pre-series model odds use ONLY games from earlier weeks (salary seeds
    before week 1), so nothing here has seen the result it is judged on.
    """
    reg = season.regular
    reg = reg[~reg["has_dropped"]].copy()
    if reg.empty:
        return pd.DataFrame()
    crowd = season.crowd_picks().set_index("seriesId") if not season.predictions.empty else None
    cache, rows = {}, []
    played_weeks = season.weeks
    last = max(played_weeks) if played_weeks else 0
    for r in reg.itertuples(index=False):
        prior = max([w for w in played_weeks if w < r.week], default=0)
        if r.status != "COMPLETED":
            prior = last
        if prior not in cache:
            st, _ = ladder(season, prior)
            cache[prior] = (dict(zip(st["team_id"], st["elo"])), dict(zip(st["team_id"], st["rd"])))
        rm, rd = cache[prior]
        r1, r2 = rm.get(r.team1Id, STARTING_ELO), rm.get(r.team2Id, STARTING_ELO)
        p_game = win_probability(r1, r2, rd.get(r.team1Id, 200.0), rd.get(r.team2Id, 200.0))
        dist = score_distribution(p_game, r.format)
        p_series = sum(p for a, b, p in dist if a > b) + 0.5 * sum(p for a, b, p in dist if a == b)
        best = max(dist, key=lambda d: d[2])
        row = {
            "seriesId": r.seriesId, "week": r.week, "status": r.status, "isOog": r.isOog,
            "format": r.format, "t1": r.team1Id, "t2": r.team2Id,
            "t1Name": r.team1Name, "t2Name": r.team2Name, "t1w": r.t1w, "t2w": r.t2w,
            "winner": r.winnerId, "r1": r1, "r2": r2, "p_game": p_game, "p_model": p_series,
            "likely": f"{best[0]}-{best[1]}", "n_picks": 0, "p_crowd": np.nan,
        }
        if crowd is not None and r.seriesId in crowd.index:
            row["n_picks"] = int(crowd.at[r.seriesId, "n"])
            row["p_crowd"] = float(crowd.at[r.seriesId, "t1_share"])
        rows.append(row)
    f = pd.DataFrame(rows)
    done = (f["status"] == "COMPLETED") & f["winner"].notna()
    f["t1_won"] = np.where(done, (f["winner"] == f["t1"]).astype(float), np.nan)
    f["model_hit"] = np.where(done, ((f["p_model"] >= 0.5) == (f["t1_won"] == 1)).astype(float), np.nan)
    has_crowd = done & f["p_crowd"].notna() & (f["n_picks"] >= 5) & (f["p_crowd"] != 0.5)
    f["crowd_hit"] = np.where(has_crowd, ((f["p_crowd"] > 0.5) == (f["t1_won"] == 1)).astype(float), np.nan)
    f["winner_p_model"] = np.where(f["t1_won"] == 1, f["p_model"], 1 - f["p_model"])
    f["winner_p_crowd"] = np.where(f["t1_won"] == 1, f["p_crowd"], 1 - f["p_crowd"])
    f.loc[~done, ["winner_p_model", "winner_p_crowd"]] = np.nan
    return f


def forecast_scorecard(f: pd.DataFrame) -> dict:
    """Head-to-head record of the model and the crowd on the SAME series."""
    out = {"n": 0, "n_model": 0}
    if f.empty:
        return out
    done = f[f["model_hit"].notna()]
    both = done[done["crowd_hit"].notna()]
    out["n_model"] = len(done)
    if len(done):
        out["model_acc_all"] = float(done["model_hit"].mean())
        out["model_brier_all"] = float(((done["p_model"] - done["t1_won"]) ** 2).mean())
    out["n"] = len(both)
    if len(both):
        out["model_acc"] = float(both["model_hit"].mean())
        out["crowd_acc"] = float(both["crowd_hit"].mean())
        out["model_brier"] = float(((both["p_model"] - both["t1_won"]) ** 2).mean())
        out["crowd_brier"] = float(((both["p_crowd"] - both["t1_won"]) ** 2).mean())
        dis = both[(both["p_model"] >= 0.5) != (both["p_crowd"] > 0.5)]
        out["disagree"] = len(dis)
        out["model_wins_disagree"] = int(dis["model_hit"].sum())
    return out


def calibration(f: pd.DataFrame, col: str) -> pd.DataFrame:
    """When the forecaster made a side an X% favourite, how often did that
    favourite actually win the series?"""
    if f.empty:
        return pd.DataFrame()
    d = f[f["t1_won"].notna() & f[col].notna()].copy()
    if col == "p_crowd":
        d = d[d["n_picks"] >= 5]
    if d.empty:
        return pd.DataFrame()
    d["fav_p"] = np.where(d[col] >= 0.5, d[col], 1 - d[col])
    d["fav_won"] = np.where(d[col] >= 0.5, d["t1_won"], 1 - d["t1_won"])
    d["bin"] = pd.cut(d["fav_p"], bins=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0001], right=False,
                      labels=["50s", "60s", "70s", "80s", "90s+"])
    out = d.groupby("bin", observed=True).agg(n=("fav_won", "size"), said=("fav_p", "mean"),
                                              actual=("fav_won", "mean")).reset_index()
    return out[out["n"] > 0]


# -- Storylines ---------------------------------------------------------------

def storylines(season: Season, week: int, forecasts: pd.DataFrame, potw) -> list:
    """[(tag, html_text, weight)] - most interesting first."""
    out = []
    ps = season.ps
    wk = ps[(ps["week"] == week) & ~ps["playoff"]]

    if forecasts is not None and not forecasts.empty:
        fw = forecasts[(forecasts["week"] == week) & forecasts["winner_p_model"].notna()]
        for r in fw[fw["winner_p_model"] < 0.40].sort_values("winner_p_model").head(2).itertuples():
            w, l = (r.t1Name, r.t2Name) if r.t1_won == 1 else (r.t2Name, r.t1Name)
            ws, ls = (r.t1w, r.t2w) if r.t1_won == 1 else (r.t2w, r.t1w)
            crowd = ""
            if pd.notna(r.winner_p_crowd) and r.n_picks >= 5:
                crowd = (f" Only {r.winner_p_crowd * 100:.0f}% of {r.n_picks} "
                         f"Crystal Ball picks saw it coming.")
            out.append(("UPSET", f"<b>{w}</b> beat <b>{l}</b> {ws}-{ls} as a "
                        f"{r.winner_p_model * 100:.0f}% underdog.{crowd}",
                        90 - r.winner_p_model * 50))

    for r in wk[wk["pentaKills"] > 0].itertuples():
        out.append(("PENTAKILL", f"<b>{r.player}</b> ({r.champion}, {r.team}) picked up a "
                    f"pentakill against {r.opp}.", 95))

    st = season.standings(week)
    st = st[~st["dropped"]]
    for r in st.itertuples():
        if r.streak and int(r.streak[1:]) >= 4:
            won = r.streak[0] == "W"
            unbeaten = " and are still unbeaten" if (r.series_l == 0 and won) else ""
            out.append(("HEATER" if won else "SKID",
                        f"<b>{r.team}</b> have {'won' if won else 'lost'} {r.streak[1:]} straight "
                        f"series{unbeaten} ({r.series_w}-{r.series_l}).",
                        50 + 5 * int(r.streak[1:]) + (0 if won else -8)))

    if potw is not None and len(potw):
        p = potw.iloc[0]
        out.append(("PLAYER OF THE WEEK",
                    f"<b>{p['player']}</b> ({p['team']}) — {p['k']:.0f}/{p['d']:.0f}/{p['a']:.0f} "
                    f"across {int(p['games'])} games on {p['champs']}. Impact {p['avg_if']:.0f}.", 80))

    if not wk.empty:
        top = wk.loc[wk["totalDamageDealtToChampions"].idxmax()]
        out.append(("DAMAGE", f"<b>{top['player']}</b> ({top['champion']}) dealt "
                    f"{top['totalDamageDealtToChampions'] / 1000:.1f}k damage in a "
                    f"{top['mins']:.0f}-minute game vs {top['opp']} — the week's high.", 45))
        g = season.games[(season.games["week"] == week) & season.games["duration"].notna()]
        if len(g) >= 3:
            fast = g.loc[g["duration"].idxmin()]
            out.append(("STOMP", f"<b>{fast['winnerName']}</b> closed out {fast['loserName']} in "
                        f"{int(fast['duration'] // 60)}:{int(fast['duration'] % 60):02d} — "
                        f"the fastest game of the week.", 40))
        lane = wk.dropna(subset=["gd15"])
        if not lane.empty:
            b = lane.loc[lane["gd15"].idxmax()]
            if b["gd15"] >= 2500:
                out.append(("LANE KINGDOM", f"<b>{b['player']}</b> ({b['champion']}) was "
                            f"+{b['gd15']:,.0f} gold up on their lane opponent at 15:00 "
                            f"vs {b['opp']}.", 48))
    return sorted(out, key=lambda x: -x[2])


# -- Draft ---------------------------------------------------------------------

def draft_summary(season: Season) -> dict:
    """Side and pick-order facts. Blue side = first pick in the site's draft."""
    g = season.games
    side = g[g["blueWon"].notna()]
    out = {"games": len(side),
           "blue_wr": float(side["blueWon"].astype(bool).mean()) if len(side) else np.nan,
           "drafts": 0}
    d = season.draft_actions()
    if d.empty:
        return out
    out["drafts"] = int(d["sessionId"].nunique())
    picks = d[d["actionType"] == "PICK"].copy()
    res = season.ps[["matchId", "championName", "win", "role"]].rename(
        columns={"championName": "championKey"})
    picks = picks.merge(res, on=["matchId", "championKey"], how="left")
    out["picks"] = picks
    out["by_slot"] = picks.dropna(subset=["win"]).groupby("pick_no").agg(
        n=("win", "size"), wr=("win", "mean")).reset_index()
    out["role_slot"] = (picks.dropna(subset=["role"]).groupby(["role", "pick_no"]).size()
                        .rename("n").reset_index())
    out["priority"] = picks.groupby("championKey").agg(
        picks=("pick_no", "size"), avg_slot=("pick_no", "mean"),
        r1=("pick_no", lambda s: int((s <= 3).sum())), wr=("win", "mean")).reset_index()
    bans = d[d["actionType"] == "BAN"].copy()
    bans["target"] = np.where(bans["team"] == "blue", bans["redTeamId"], bans["blueTeamId"])
    bans["target"] = bans["target"].astype(str).str.replace(r"\.0$", "", regex=True)
    out["bans"] = bans
    return out


def side_by_week(season: Season) -> pd.DataFrame:
    g = season.games[season.games["blueWon"].notna()]
    if g.empty:
        return pd.DataFrame()
    return g.groupby("week").agg(games=("blueWon", "size"),
                                 blue=("blueWon", lambda s: s.astype(bool).mean())).reset_index()


def lead_conversion(season: Season) -> pd.DataFrame:
    """Win rate by team gold lead at 15:00 - how safe is an early lead here?"""
    if not hasattr(season, "team_games"):
        team_table(season)
    tg = getattr(season, "team_games", None)
    if tg is None or tg.empty or tg["gd15"].notna().sum() == 0:
        return pd.DataFrame()
    d = tg.dropna(subset=["gd15"])
    d = d[d["gd15"] > 0]            # one row per game: the side that was ahead
    d = d.assign(bucket=pd.cut(d["gd15"], bins=[0, 1000, 2500, 5000, 1e9],
                               labels=["under 1k", "1k–2.5k", "2.5k–5k", "5k+"]))
    return d.groupby("bucket", observed=True).agg(games=("win", "size"),
                                                  wr=("win", "mean")).reset_index()

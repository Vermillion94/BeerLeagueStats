"""The stats lab: analyses that try to separate cause from "the team that was
already winning also did this".

  • gold_curve      how much a gold lead at 15:00 is worth (fitted S-curve)
  • even_games      objective win rates, raw vs. only games level at 15:00
  • lane_leads      which lane's lead says most about who wins
  • damage_mix      physical/magic damage split vs. winning
  • counterpicks    does picking after your lane opponent actually help?
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.extras import _team_games
from app.league import ROLES, Season, team_table

EVEN_GOLD = 1500        # "level at 15:00" = within this much team gold


def _sig(z):
    return 1.0 / (1.0 + np.exp(-z))


def _fit_slope(x: np.ndarray, y: np.ndarray) -> float:
    """One-parameter logistic fit P(win) = sigmoid(k·x), no intercept, so an
    even game is a coin flip by construction. Newton's method."""
    k = 0.3
    for _ in range(50):
        p = _sig(k * x)
        grad = float(np.sum((y - p) * x))
        hess = float(np.sum(p * (1 - p) * x * x))
        if hess < 1e-9:
            break
        step = grad / hess
        k += step
        if abs(step) < 1e-7:
            break
    return float(k)


def gold_curve(season: Season) -> dict | None:
    tg = _team_games(season)
    a = tg[tg["gd15"] > 0]                      # the team ahead at 15: one row a game
    if len(a) < 20:
        return None
    x, y = a["gd15"].to_numpy(float) / 1000.0, a["win"].to_numpy(float)
    k = _fit_slope(x, y)
    edges = [0, 0.5, 1, 1.5, 2, 3, 4, 6, 99]
    bins = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (x >= lo) & (x < hi)
        if m.sum() >= 4:
            bins.append({"lo": lo, "hi": hi, "x": float(x[m].mean()), "n": int(m.sum()), "wr": float(y[m].mean())})
    dots = [{"x": float(r.gd15), "w": int(r.win), "t": r.leagueTeamId, "o": r.opp, "wk": int(r.week)}
            for r in a.itertuples()]
    out = {"k": k, "n": len(a), "bins": bins, "dots": dots, "hold": float(y.mean()),
           "p1k": float(_sig(k)), "p3k": float(_sig(3 * k))}
    if k > 0:
        out["need75"] = math.log(3) / k * 1000
        out["need90"] = math.log(9) / k * 1000
    return out


def even_games(season: Season) -> dict | None:
    """Raw objective win rates flatter the objective: the team already ahead
    takes it. Re-ask the question using only games level at 15:00."""
    tg = _team_games(season)
    if tg.empty or not tg["gd15"].notna().any():
        return None
    ev = tg[tg["gd15"].abs() <= EVEN_GOLD]
    rows = []

    def add(label, col_mask):
        r, e = tg[col_mask(tg).fillna(False)], ev[col_mask(ev).fillna(False)]
        if len(r) >= 8 and len(e) >= 8:
            rows.append({"label": label, "raw": float(r["win"].mean()), "n": len(r),
                         "even": float(e["win"].mean()), "n_even": len(e)})
    add("First blood", lambda d: d["fb"] > 0)
    add("First tower", lambda d: d["ft"] > 0)
    if tg["dragons"].notna().any():
        add("Rift Herald", lambda d: d["heralds"] > d["opp_heralds"])
        add("More dragons", lambda d: d["dragons"] > d["opp_dragons"])
        add("More barons", lambda d: d["barons"] > d["opp_barons"])
        add("More kills", lambda d: d["kills"] > d["opp_kills"])
    if not rows:
        return None
    rows.sort(key=lambda r: -r["raw"])
    return {"thr": EVEN_GOLD, "games": int(len(ev) // 2), "of": int(len(tg) // 2), "rows": rows}


def lane_leads(season: Season) -> list:
    ps = season.ps.dropna(subset=["role", "gd15"])
    out = []
    for role in ROLES:
        d = ps[(ps["role"] == role) & (ps["gd15"] > 0)]
        if len(d) < 10:
            continue
        x, y = d["gd15"].to_numpy(float) / 1000.0, d["win"].to_numpy(float)
        out.append({"role": role, "n": len(d), "wr": float(y.mean()), "avg": float(d["gd15"].mean()),
                    "p1k": float(_sig(_fit_slope(x, y)))})
    return out


def damage_mix(season: Season) -> dict | None:
    ps = season.ps
    need = {"physicalDamageDealtToChampions", "magicDamageDealtToChampions"}
    if ps.empty or not need <= set(ps.columns):
        return None
    t = ps.groupby(["matchId", "leagueTeamId"]).agg(p=("physicalDamageDealtToChampions", "sum"),
                                                     m=("magicDamageDealtToChampions", "sum"),
                                                     win=("win", "first")).reset_index()
    t = t[(t["p"] + t["m"]) > 0]
    if len(t) < 20:
        return None
    t["ad"] = t["p"] / (t["p"] + t["m"])
    cuts = [(0, .35, "Under 35% physical"), (.35, .45, "35–45%"), (.45, .55, "45–55% (balanced)"),
            (.55, .65, "55–65%"), (.65, 1.01, "Over 65% physical")]
    bins = []
    for lo, hi, lab in cuts:
        d = t[(t["ad"] >= lo) & (t["ad"] < hi)]
        if len(d):
            bins.append({"label": lab, "n": len(d), "wr": float(d["win"].mean())})
    by = t.groupby("leagueTeamId")["ad"].mean()
    by = by[by.index.isin(season.live_ids)].sort_values()
    return {"bins": bins, "avg": float(t["ad"].mean()),
            "most_ap": {"t": by.index[0], "ad": float(by.iloc[0])} if len(by) else None,
            "most_ad": {"t": by.index[-1], "ad": float(by.iloc[-1])} if len(by) else None}


def counterpicks(season: Season) -> dict | None:
    d = season.draft_actions()
    ps = season.ps
    if d.empty or ps.empty:
        return None
    picks = d[d["actionType"] == "PICK"][["matchId", "championKey", "pick_no"]].copy()
    picks["ck"] = picks["championKey"].astype(str).str.lower()
    base = ps.dropna(subset=["role"])[["matchId", "leagueTeamId", "role", "championName", "champion", "win", "gd15"]].copy()
    base["ck"] = base["championName"].astype(str).str.lower()
    base = base.merge(picks[["matchId", "ck", "pick_no"]].drop_duplicates(["matchId", "ck"]), on=["matchId", "ck"])
    lanes = base.merge(base, on=["matchId", "role"], suffixes=("", "_o"))
    lanes = lanes[lanes["leagueTeamId"] != lanes["leagueTeamId_o"]]
    cp = lanes[lanes["pick_no"] > lanes["pick_no_o"]]        # picked second in the lane
    if len(cp) < 20:
        return None
    out = {"n": len(cp), "wr": float(cp["win"].mean()), "gd15": float(cp["gd15"].mean()),
           "lane_won": float((cp["gd15"] > 0).mean()), "roles": []}
    for role in ROLES:
        r = cp[cp["role"] == role]
        if len(r) >= 10:
            out["roles"].append({"role": role, "n": len(r), "wr": float(r["win"].mean()), "gd15": float(r["gd15"].mean()),
                                 "lane_won": float((r["gd15"] > 0).mean())})
    blind = lanes[lanes["pick_no"] < lanes["pick_no_o"]]
    b = blind.groupby("champion").agg(g=("win", "size"), w=("win", "sum"), gd15=("gd15", "mean")).reset_index()
    c = cp.groupby("champion").agg(g=("win", "size"), w=("win", "sum"), gd15=("gd15", "mean")).reset_index()
    rec = lambda df: [{"c": r.champion, "g": int(r.g), "w": int(r.w), "gd15": float(r.gd15)} for r in df.itertuples()]
    out["blind_most"] = rec(b.sort_values(["g", "w"], ascending=False).head(8))
    out["blind_safe"] = rec(b[b["g"] >= 4].sort_values("gd15", ascending=False).head(6))
    out["blind_risky"] = rec(b[b["g"] >= 4].sort_values("gd15").head(6))
    out["counter_best"] = rec(c[c["g"] >= 3].sort_values("gd15", ascending=False).head(6))
    return out


def lab(season: Season) -> dict:
    out = {}
    if not hasattr(season, "team_games"):
        team_table(season)
    if not hasattr(season, "team_games"):
        return out
    for key, fn in (("gold", gold_curve), ("even", even_games), ("lanes", lane_leads),
                    ("mix", damage_mix), ("counter", counterpicks)):
        v = fn(season)
        if v:
            out[key] = v
    return out

"""
Beer League Stats — Model Report Card

Holds the win-odds model publicly accountable: for every completed game,
what did the ladder say BEFORE the game (ratings through the prior week,
salary seeds before week 1), and what happened? Produces the running
record, Brier score, per-week results, and the season's biggest upsets.

Pure module — no Streamlit. The app caches per (db, season).
"""

import pandas as pd

from app.elo import compute_elo_through_week, win_probability, STARTING_ELO


def build_report_card(matches_df: pd.DataFrame, weeks: list,
                      team_names: dict, team_salaries: dict) -> dict:
    """Walk-forward predictions for every completed game.

    Returns
    -------
    dict with:
      n, hits, acc, brier          : season totals (None-safe when n=0)
      weekly    : list of {week, hits, total}
      upsets    : list of {week, fav_name, dog_name, fav_prob} — games the
                  favorite lost, sorted by how heavy a favorite they were
      preds     : per-game rows (week, favorite, prob, winner, hit)
    """
    out = {"n": 0, "hits": 0, "acc": None, "brier": None,
           "weekly": [], "upsets": [], "preds": []}
    if matches_df is None or matches_df.empty or not weeks:
        return out

    brier_sum = 0.0
    for wk_i, wk in enumerate(weeks):
        prior_week = weeks[wk_i - 1] if wk_i > 0 else 0  # 0 → salary seeds
        standings, _ = compute_elo_through_week(
            matches_df, prior_week, team_names, team_salaries)
        rmap = dict(zip(standings["team_id"].astype(str), standings["elo"]))
        rdmap = dict(zip(standings["team_id"].astype(str), standings["rd"]))

        wk_games = matches_df[matches_df["week"] == wk]
        wk_hits = wk_total = 0
        for _, r in wk_games.iterrows():
            t1, t2 = str(r["team1Id"]), str(r["team2Id"])
            winner = str(r["winnerId"])
            p1 = win_probability(rmap.get(t1, STARTING_ELO), rmap.get(t2, STARTING_ELO),
                                 rdmap.get(t1, 300.0), rdmap.get(t2, 300.0))
            fav, dog = (t1, t2) if p1 >= 0.5 else (t2, t1)
            fav_prob = max(p1, 1.0 - p1)
            hit = (winner == fav)
            y1 = 1.0 if winner == t1 else 0.0
            brier_sum += (p1 - y1) ** 2

            wk_total += 1
            wk_hits += int(hit)
            out["preds"].append({
                "week": int(wk),
                "fav_name": team_names.get(fav, fav),
                "dog_name": team_names.get(dog, dog),
                "fav_prob": fav_prob,
                "winner_name": team_names.get(winner, winner),
                "hit": hit,
            })
            if not hit:
                out["upsets"].append({
                    "week": int(wk),
                    "fav_name": team_names.get(fav, fav),
                    "dog_name": team_names.get(dog, dog),
                    "fav_prob": fav_prob,
                })
        if wk_total:
            out["weekly"].append({"week": int(wk), "hits": wk_hits, "total": wk_total})
        out["n"] += wk_total
        out["hits"] += wk_hits

    if out["n"]:
        out["acc"] = out["hits"] / out["n"]
        out["brier"] = brier_sum / out["n"]
    out["upsets"].sort(key=lambda u: -u["fav_prob"])
    return out

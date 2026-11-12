"""
Beer League Stats — Playoff Outlook Simulator

Monte Carlo over the regular-season series that are still to be played,
seeded with the website's own standings rules (see app/league.py):

  * series wins → game wins → head-to-head inside the tied group → name
  * dropped teams never qualify; void drops erase their series, forfeit
    drops award every opponent a series win; neither is "remaining"
  * out-of-group exhibition series and seed-slot placeholders never count
  * two-group seasons seed cross-group (A1, B1, A2, B2 …), each group
    sending half the field, ranked on in-group series only

Because game wins are the first tiebreaker, every remaining series is rolled
to an exact score (2-0 / 2-1 / …) from the calibrated per-game probability —
not just to a winner.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.elo import win_probability, STARTING_ELO
from app.league import Season, score_distribution

DEFAULT_N_SIMS = 5000


def _order(idx, sw, gw, h2h, name_rank):
    """Order team indices for one sim. sw/gw are 1-D arrays over all teams;
    h2h is an (n, n) array of series wins [winner, loser]."""
    key = sw[idx] * 1000 + gw[idx]
    if len(np.unique(key)) == len(idx):
        return [idx[i] for i in np.argsort(-key, kind="stable")]
    base = sorted(idx, key=lambda t: (-sw[t], -gw[t], name_rank[t]))
    out, i = [], 0
    while i < len(base):
        j = i + 1
        while j < len(base) and sw[base[j]] == sw[base[i]] and gw[base[j]] == gw[base[i]]:
            j += 1
        run = base[i:j]
        if len(run) > 1:
            inner = {t: sum(h2h[t, o] for o in run if o != t) for t in run}
            run = sorted(run, key=lambda t: (-inner[t], name_rank[t]))
        out.extend(run)
        i = j
    return out


def simulate(season: Season, rating_map: dict, rd_map: dict,
             n_sims: int = DEFAULT_N_SIMS, rng_seed: int = 42) -> dict:
    """Simulate the rest of the regular season.

    Returns dict with:
      remaining    : list of {seriesId, week, t1Id, t2Id, t1Name, t2Name, p_t1, p_game}
      team_ids     : live (non-dropped) team ids
      sim_outcomes : int8 (n_sims, n_remaining) — 1 team1 won, 0 team2 won, 2 draw
      sim_wins     : (n_sims, n_teams) final series wins
      sim_seeds    : (n_sims, n_teams) playoff seed; > playoff_spots means missed
      n_sims, playoff_spots
    """
    rng = np.random.default_rng(rng_seed)
    ids = list(season.live_ids)
    n = len(ids)
    ix = {t: i for i, t in enumerate(ids)}
    names_sorted = sorted(ids, key=lambda t: season.names.get(t, "").lower())
    name_rank = np.zeros(n, dtype=int)
    for r, t in enumerate(names_sorted):
        name_rank[ix[t]] = r
    spots = min(season.playoff_spots, n)

    # Scopes: overall table, plus one table per group when seeding is cross-group
    cross = season.cross_group
    scopes = {"__all__": ids}
    if cross:
        for gname in season.group_labels:
            scopes[gname] = [t for t in ids if season.groups.get(t) == gname]

    reg = season.regular
    base = {}
    for name, members in scopes.items():
        mset = set(members)
        sub = reg if name == "__all__" else reg[
            reg["team1Id"].isin(mset | season.dropped) & reg["team2Id"].isin(mset | season.dropped)]
        sw, _sl, gw, _gl, h2h, _ = season._tally(sub, members)
        sw0 = np.zeros(n, dtype=np.int32); gw0 = np.zeros(n, dtype=np.int32)
        h0 = np.zeros((n, n), dtype=np.int16)
        for t in members:
            sw0[ix[t]] = sw[t]; gw0[ix[t]] = gw[t]
        for (w, l), c in h2h.items():
            if w in ix and l in ix:
                h0[ix[w], ix[l]] += c
        base[name] = (sw0, gw0, h0, np.array([ix[t] for t in members]))

    rem_df = season.remaining_series().sort_values(["week", "seriesId"])
    remaining, dists = [], []
    for r in rem_df.itertuples(index=False):
        if r.team1Id not in ix or r.team2Id not in ix:
            continue
        p = win_probability(rating_map.get(r.team1Id, STARTING_ELO),
                            rating_map.get(r.team2Id, STARTING_ELO),
                            rd_map.get(r.team1Id, 200.0), rd_map.get(r.team2Id, 200.0))
        dist = score_distribution(p, r.format)
        dists.append(dist)
        remaining.append({
            "seriesId": r.seriesId, "week": int(r.week), "t1Id": r.team1Id, "t2Id": r.team2Id,
            "t1Name": season.names.get(r.team1Id, r.team1Id),
            "t2Name": season.names.get(r.team2Id, r.team2Id),
            "p_game": p, "format": r.format,
            "p_t1": sum(pr for a, b, pr in dist if a > b) + 0.5 * sum(pr for a, b, pr in dist if a == b),
        })
    m = len(remaining)
    n_eff = n_sims if m else 1

    g1 = np.zeros((n_eff, m), dtype=np.int8)
    g2 = np.zeros((n_eff, m), dtype=np.int8)
    for s, dist in enumerate(dists):
        probs = np.array([d[2] for d in dist]); probs = probs / probs.sum()
        pick = rng.choice(len(dist), size=n_eff, p=probs)
        g1[:, s] = np.array([d[0] for d in dist], dtype=np.int8)[pick]
        g2[:, s] = np.array([d[1] for d in dist], dtype=np.int8)[pick]
    outcomes = np.where(g1 > g2, 1, np.where(g2 > g1, 0, 2)).astype(np.int8)

    t1i = [ix[r["t1Id"]] for r in remaining]
    t2i = [ix[r["t2Id"]] for r in remaining]
    in_scope = {
        name: [(season.groups.get(r["t1Id"]) == name and season.groups.get(r["t2Id"]) == name)
               if name != "__all__" else True for r in remaining]
        for name in scopes
    }

    SW, GW = {}, {}
    for name, (sw0, gw0, _h, _members) in base.items():
        sw = np.tile(sw0, (n_eff, 1)); gw = np.tile(gw0, (n_eff, 1))
        for s in range(m):
            if not in_scope[name][s]:
                continue
            sw[:, t1i[s]] += (outcomes[:, s] == 1); sw[:, t2i[s]] += (outcomes[:, s] == 0)
            gw[:, t1i[s]] += g1[:, s]; gw[:, t2i[s]] += g2[:, s]
        SW[name], GW[name] = sw, gw

    seeds = np.zeros((n_eff, n), dtype=np.int16)
    all_idx = list(range(n))
    per = spots // 2
    glabels = season.group_labels if cross else []
    for k in range(n_eff):
        h = {}
        for name, (_s, _g, h0, _mm) in base.items():
            hk = h0
            if m and (outcomes[k] != 2).any():
                hk = h0.copy()
                for s in range(m):
                    if not in_scope[name][s] or outcomes[k, s] == 2:
                        continue
                    w, l = (t1i[s], t2i[s]) if outcomes[k, s] == 1 else (t2i[s], t1i[s])
                    hk[w, l] += 1
            h[name] = hk
        overall = _order(all_idx, SW["__all__"][k], GW["__all__"][k], h["__all__"], name_rank)
        if cross:
            ranked = {gn: _order(list(base[gn][3]), SW[gn][k], GW[gn][k], h[gn], name_rank)
                      for gn in glabels}
            a, b = glabels
            if overall.index(ranked[b][0]) < overall.index(ranked[a][0]):
                a, b = b, a
            field = []
            for j in range(per):
                if j < len(ranked[a]):
                    field.append(ranked[a][j])
                if j < len(ranked[b]):
                    field.append(ranked[b][j])
            rest = [t for t in overall if t not in set(field)]
            final = field + rest
        else:
            final = overall
        for pos, t in enumerate(final, start=1):
            seeds[k, t] = pos

    return {
        "remaining": remaining, "team_ids": ids, "team_index": ix,
        "sim_outcomes": outcomes, "sim_wins": SW["__all__"], "sim_seeds": seeds,
        "n_sims": n_eff, "playoff_spots": spots,
    }


def seed_probabilities(sim: dict, scenario_mask: np.ndarray | None = None) -> pd.DataFrame:
    """P(seed = k) per team, plus make/miss, average seed and average wins.
    Columns: team_id, seed_1..seed_N, miss, make_playoffs, avg_seed, avg_wins."""
    seeds, wins = sim["sim_seeds"], sim["sim_wins"]
    if scenario_mask is not None:
        seeds, wins = seeds[scenario_mask], wins[scenario_mask]
    if seeds.shape[0] == 0:
        return pd.DataFrame()
    spots = sim["playoff_spots"]
    rows = []
    for tid, i in sim["team_index"].items():
        ts = seeds[:, i]
        row = {"team_id": tid}
        for k in range(1, spots + 1):
            row[f"seed_{k}"] = float((ts == k).mean())
        row["miss"] = float((ts > spots).mean())
        row["make_playoffs"] = 1.0 - row["miss"]
        row["avg_seed"] = float(ts.mean())
        row["avg_wins"] = float(wins[:, i].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def apply_scenarios(sim: dict, scenarios: list) -> np.ndarray:
    """Boolean mask over sims matching every pinned (series_index, winner_id)."""
    mask = np.ones(sim["sim_outcomes"].shape[0], dtype=bool)
    for s_idx, winner_id in scenarios:
        rem = sim["remaining"][s_idx]
        want = 1 if winner_id == rem["t1Id"] else 0
        mask &= sim["sim_outcomes"][:, s_idx] == want
    return mask


def leverage(sim: dict) -> pd.DataFrame:
    """How much each remaining series swings each team's playoff odds:
    P(make | team1 wins) − P(make | team2 wins). The biggest absolute swing
    per series tells you which games actually matter."""
    spots = sim["playoff_spots"]
    made = sim["sim_seeds"] <= spots
    rows = []
    for s, rem in enumerate(sim["remaining"]):
        o = sim["sim_outcomes"][:, s]
        a, b = o == 1, o == 0
        if a.sum() < 30 or b.sum() < 30:
            continue
        diff = made[a].mean(axis=0) - made[b].mean(axis=0)
        for tid, i in sim["team_index"].items():
            if abs(diff[i]) >= 0.02:
                rows.append({"seriesId": rem["seriesId"], "week": rem["week"],
                             "series": f'{rem["t1Name"]} vs {rem["t2Name"]}',
                             "team_id": tid, "swing": float(diff[i]),
                             "if_t1": float(made[a][:, i].mean()),
                             "if_t2": float(made[b][:, i].mean()),
                             "t1": rem["t1Name"], "t2": rem["t2Name"]})
    return pd.DataFrame(rows, columns=["seriesId", "week", "series", "team_id", "swing",
                                       "if_t1", "if_t2", "t1", "t2"])

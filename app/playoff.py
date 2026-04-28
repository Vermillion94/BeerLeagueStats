"""
Beer League Stats — Playoff Outlook Simulator

Monte Carlo simulation of the remainder of the regular season using current
Glicko-2 ratings. Tiebreaker rules (per league commish):
  1. Series record (wins)
  2. For 2-way ties:    head-to-head series record between the two teams
  3. For 3+ way ties:   overall series record within the tying group, then
                        head-to-head for any remaining sub-ties (recursive)
  4. Anything still tied → deterministic fallback by team_id

All series are best-of-3, so per-game Glicko-2 probability is converted to a
series win probability via p^2 * (3 - 2p).
"""

import numpy as np
import pandas as pd

from app.elo import win_probability, STARTING_ELO

PLAYOFF_SPOTS = 8
DEFAULT_N_SIMS = 8000


# ── Tiebreaker primitives ────────────────────────────────────────────────────

def _bo3_prob(p_game: float) -> float:
    """Series win probability for BO3 given per-game probability."""
    return p_game * p_game * (3.0 - 2.0 * p_game)


def _build_h2h_completed(series_df: pd.DataFrame) -> dict:
    """h2h[(a, b)] = number of series team a has won against team b."""
    h2h = {}
    completed = series_df[series_df["status"] == "COMPLETED"]
    for _, r in completed.iterrows():
        winner = str(r.get("winnerId") or "")
        if not winner or winner == "nan" or winner == "None":
            continue
        t1, t2 = str(r["team1Id"]), str(r["team2Id"])
        loser = t2 if winner == t1 else t1
        h2h[(winner, loser)] = h2h.get((winner, loser), 0) + 1
    return h2h


def _current_wins(series_df: pd.DataFrame, team_ids: list) -> dict:
    rec = {tid: 0 for tid in team_ids}
    completed = series_df[series_df["status"] == "COMPLETED"]
    for _, r in completed.iterrows():
        winner = str(r.get("winnerId") or "")
        if winner and winner in rec:
            rec[winner] += 1
    return rec


def _tiebreak(tied: list, h2h: dict) -> list:
    """Recursively order a tied group of team IDs.

    Returns a list of teams in seed order (best first).
    """
    if len(tied) <= 1:
        return list(tied)

    if len(tied) == 2:
        a, b = tied
        ab = h2h.get((a, b), 0)
        ba = h2h.get((b, a), 0)
        if ab > ba:
            return [a, b]
        if ba > ab:
            return [b, a]
        return sorted(tied)

    # 3+ way tie: split by record within the tying group
    internal = {t: sum(h2h.get((t, o), 0) for o in tied if o != t) for t in tied}
    groups: dict = {}
    for t in tied:
        groups.setdefault(internal[t], []).append(t)

    if len(groups) == 1:
        # Internal records all equal → recurse into pairwise h2h pass
        # (does nothing more useful than sorted; deterministic fallback)
        return sorted(tied)

    result = []
    for level in sorted(groups, reverse=True):
        result.extend(_tiebreak(groups[level], h2h))
    return result


def compute_seeds(records: dict, h2h: dict, team_ids: list) -> list:
    """Return team_ids ordered by final seed (best first)."""
    by_wins: dict = {}
    for tid in team_ids:
        by_wins.setdefault(records.get(tid, 0), []).append(tid)

    ordered = []
    for w in sorted(by_wins, reverse=True):
        ordered.extend(_tiebreak(by_wins[w], h2h))
    return ordered


# ── Monte Carlo engine ───────────────────────────────────────────────────────

def simulate(
    series_df: pd.DataFrame,
    rating_map: dict,
    rd_map: dict,
    team_ids: list,
    n_sims: int = DEFAULT_N_SIMS,
    rng_seed: int = 42,
) -> dict:
    """Run a Monte Carlo simulation of the remaining season.

    Returns
    -------
    dict with:
      remaining       : list of {seriesId, week, t1Id, t2Id, t1Name, t2Name, p_t1}
      team_ids        : list of team_ids
      team_index      : dict tid -> column index
      current_wins    : dict tid -> wins so far
      h2h_completed   : dict (a, b) -> series wins of a over b (completed only)
      sim_outcomes    : int8 ndarray (n_sims, n_remaining), 1 = team1 won
      sim_wins        : int16 ndarray (n_sims, n_teams) final series wins
      sim_seeds       : int8 ndarray (n_sims, n_teams) final seed (1 = best)
      n_sims          : effective sim count (may be 1 if season is over)
    """
    rng = np.random.default_rng(rng_seed)
    team_ids = list(team_ids)
    team_idx = {tid: i for i, tid in enumerate(team_ids)}

    scheduled = series_df[series_df["status"] == "SCHEDULED"].copy()
    scheduled = scheduled.sort_values(["week", "seriesId"]).reset_index(drop=True)

    h2h_completed = _build_h2h_completed(series_df)
    cur_wins = _current_wins(series_df, team_ids)

    n_remaining = len(scheduled)
    n_teams = len(team_ids)

    # Remaining-series metadata
    remaining = []
    p_t1_arr = np.zeros(n_remaining)
    t1_idx_arr = np.zeros(n_remaining, dtype=int)
    t2_idx_arr = np.zeros(n_remaining, dtype=int)
    for i, r in scheduled.iterrows():
        t1, t2 = str(r["team1Id"]), str(r["team2Id"])
        r1 = rating_map.get(t1, STARTING_ELO)
        r2 = rating_map.get(t2, STARTING_ELO)
        rd1 = rd_map.get(t1, 60.0)
        rd2 = rd_map.get(t2, 60.0)
        p_game = win_probability(r1, r2, rd1, rd2)
        p_ser = _bo3_prob(p_game)
        p_t1_arr[i] = p_ser
        t1_idx_arr[i] = team_idx.get(t1, -1)
        t2_idx_arr[i] = team_idx.get(t2, -1)
        remaining.append({
            "seriesId": str(r["seriesId"]),
            "week": int(r["week"]),
            "t1Id": t1, "t2Id": t2,
            "t1Name": r.get("team1Name", t1),
            "t2Name": r.get("team2Name", t2),
            "p_t1": p_ser,
        })

    # No remaining series → deterministic outcome
    if n_remaining == 0:
        sim_outcomes = np.zeros((1, 0), dtype=np.int8)
        sim_wins = np.zeros((1, n_teams), dtype=np.int16)
        for tid, w in cur_wins.items():
            sim_wins[0, team_idx[tid]] = w
        seeds = compute_seeds(cur_wins, h2h_completed, team_ids)
        sim_seeds = np.zeros((1, n_teams), dtype=np.int8)
        for rank, tid in enumerate(seeds, start=1):
            sim_seeds[0, team_idx[tid]] = rank
        return {
            "remaining": remaining,
            "team_ids": team_ids,
            "team_index": team_idx,
            "current_wins": cur_wins,
            "h2h_completed": h2h_completed,
            "sim_outcomes": sim_outcomes,
            "sim_wins": sim_wins,
            "sim_seeds": sim_seeds,
            "n_sims": 1,
        }

    # Roll random series outcomes
    randoms = rng.random((n_sims, n_remaining))
    sim_outcomes = (randoms < p_t1_arr[None, :]).astype(np.int8)

    # Wins per team per sim
    sim_wins = np.zeros((n_sims, n_teams), dtype=np.int16)
    for tid, w in cur_wins.items():
        sim_wins[:, team_idx[tid]] = w
    for s in range(n_remaining):
        if t1_idx_arr[s] >= 0:
            sim_wins[:, t1_idx_arr[s]] += sim_outcomes[:, s]
        if t2_idx_arr[s] >= 0:
            sim_wins[:, t2_idx_arr[s]] += (1 - sim_outcomes[:, s])

    # Seeds per sim — apply tiebreakers with per-sim h2h
    sim_seeds = np.zeros((n_sims, n_teams), dtype=np.int8)

    # Pre-extract per-series winner/loser team ids for the per-sim h2h build
    rem_t1 = [r["t1Id"] for r in remaining]
    rem_t2 = [r["t2Id"] for r in remaining]

    for sim in range(n_sims):
        # Per-sim h2h — start from completed and add this sim's results
        h2h = dict(h2h_completed)
        outcomes = sim_outcomes[sim]
        for s in range(n_remaining):
            if outcomes[s] == 1:
                w, l = rem_t1[s], rem_t2[s]
            else:
                w, l = rem_t2[s], rem_t1[s]
            key = (w, l)
            h2h[key] = h2h.get(key, 0) + 1

        records = {tid: int(sim_wins[sim, team_idx[tid]]) for tid in team_ids}
        ordered = compute_seeds(records, h2h, team_ids)
        for rank, tid in enumerate(ordered, start=1):
            sim_seeds[sim, team_idx[tid]] = rank

    return {
        "remaining": remaining,
        "team_ids": team_ids,
        "team_index": team_idx,
        "current_wins": cur_wins,
        "h2h_completed": h2h_completed,
        "sim_outcomes": sim_outcomes,
        "sim_wins": sim_wins,
        "sim_seeds": sim_seeds,
        "n_sims": n_sims,
    }


# ── Probability extraction ───────────────────────────────────────────────────

def seed_probabilities(sim_data: dict, scenario_mask: np.ndarray = None) -> pd.DataFrame:
    """Return P(seed = k) for each team across all seeds, plus P(miss).

    Columns: team_id, seed_1, seed_2, ..., seed_8, miss, make_playoffs,
             avg_seed, avg_wins
    """
    seeds = sim_data["sim_seeds"]
    wins = sim_data["sim_wins"]
    team_ids = sim_data["team_ids"]
    team_idx = sim_data["team_index"]

    if scenario_mask is not None:
        seeds = seeds[scenario_mask]
        wins = wins[scenario_mask]
    n_sims = seeds.shape[0]
    if n_sims == 0:
        return pd.DataFrame()

    rows = []
    for tid in team_ids:
        i = team_idx[tid]
        team_seeds = seeds[:, i]
        row = {"team_id": tid}
        for k in range(1, PLAYOFF_SPOTS + 1):
            row[f"seed_{k}"] = float((team_seeds == k).mean())
        row["miss"] = float((team_seeds > PLAYOFF_SPOTS).mean())
        row["make_playoffs"] = 1.0 - row["miss"]
        row["avg_seed"] = float(team_seeds.mean())
        row["avg_wins"] = float(wins[:, i].mean())
        rows.append(row)

    return pd.DataFrame(rows)


def apply_scenarios(sim_data: dict, scenarios: list) -> np.ndarray:
    """Build a boolean mask over sims that match the pinned scenarios.

    scenarios: list of (series_index_in_remaining, winner_team_id)
    """
    n_sims = sim_data["sim_outcomes"].shape[0]
    mask = np.ones(n_sims, dtype=bool)
    for s_idx, winner_id in scenarios:
        rem = sim_data["remaining"][s_idx]
        if winner_id == rem["t1Id"]:
            mask &= sim_data["sim_outcomes"][:, s_idx] == 1
        elif winner_id == rem["t2Id"]:
            mask &= sim_data["sim_outcomes"][:, s_idx] == 0
    return mask


def standings_table(sim_data: dict, name_map: dict) -> pd.DataFrame:
    """Current standings (no simulation) — useful as a 'now' snapshot.

    Columns: seed, team, wins, losses (from completed series only).
    """
    cur = sim_data["current_wins"]
    team_ids = sim_data["team_ids"]
    h2h = sim_data["h2h_completed"]

    # Losses = total completed series involving team minus wins
    # We need total completed series for each team — derive from h2h sums
    losses = {tid: 0 for tid in team_ids}
    for (w, l), n in h2h.items():
        if l in losses:
            losses[l] += n

    ordered = compute_seeds(cur, h2h, team_ids)

    rows = []
    for seed, tid in enumerate(ordered, start=1):
        rows.append({
            "seed": seed,
            "team_id": tid,
            "team": name_map.get(tid, tid),
            "wins": cur.get(tid, 0),
            "losses": losses.get(tid, 0),
        })
    return pd.DataFrame(rows)

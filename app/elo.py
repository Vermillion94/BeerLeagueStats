"""
Beer League Stats — Bayesian Glicko-2 Rating Engine (with retrodiction)

Full Bayesian approach: Glicko-2 tracks rating, uncertainty (RD), and
volatility per team, then iterative convergence re-simulates the season
multiple times so that early wins against eventually-strong teams are
properly credited retroactively.

Each pass:
  1. Seed teams with the previous pass's final ratings (pass 0 uses salary)
  2. Run all games through Glicko-2 (per-game updates, not per-series)
  3. Record final ratings

Repeat until ratings converge (< 1.0 rating point change across all teams).
Typically converges in 3-5 passes with ~168 games.

Salary prior: teams start at salary-seeded ratings (1100-1300) with moderate
RD. On subsequent passes, they start at converged ratings with fresh RD —
the system naturally discovers true strength regardless of salary.

NULL-week matches are excluded (pre-season series 100-106).
"""

import math
from dataclasses import dataclass, field

import pandas as pd

from app.config import ANCHOR_GAMES, MIN_GAMES_FOR_RETRO

# -- Public constants (backward-compatible names) -----------------------------

STARTING_ELO = 1200.0            # display-scale center
STARTING_RD = 300.0              # high uncertainty for unknown teams
SALARY_INITIAL_RD = 200.0        # lower RD when salary info available
INITIAL_VOLATILITY = 0.06        # Glicko-2 default

# -- Glicko-2 internals ------------------------------------------------------

_TAU = 0.5                       # constrains volatility change rate
_CONV_TOL = 1e-6                 # Illinois algorithm tolerance
_MAX_ITER = 100                  # Illinois algorithm max iterations
_SCALE = 173.7178                # 400 / ln(10), Glicko-2 scaling factor

# -- Retrodiction settings ---------------------------------------------------

RETRO_PASSES = 6                 # max convergence passes
RETRO_THRESHOLD = 10.0           # converged when max delta < this

# -- Salary seeding range ----------------------------------------------------

_SAL_MIN = 1100.0
_SAL_MAX = 1300.0


# ── Glicko-2 math ───────────────────────────────────────────────────────────

def _to_g2(rating, rd):
    return (rating - STARTING_ELO) / _SCALE, rd / _SCALE


def _from_g2(mu, phi):
    return mu * _SCALE + STARTING_ELO, phi * _SCALE


def _g(phi):
    """Reduction factor based on opponent uncertainty."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi ** 2))


def _E(mu, mu_j, phi_j):
    """Expected score given ratings and opponent RD."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _new_volatility(sigma, phi, v, delta):
    """Compute new volatility via Illinois algorithm (Glicko-2 step 5)."""
    a = math.log(sigma * sigma)
    d2 = delta * delta
    p2 = phi * phi

    def f(x):
        ex = math.exp(x)
        num = ex * (d2 - p2 - v - ex)
        den = 2.0 * (p2 + v + ex) ** 2
        return num / den - (x - a) / (_TAU * _TAU)

    A = a
    if d2 > p2 + v:
        B = math.log(d2 - p2 - v)
    else:
        k = 1
        while f(a - k * _TAU) < 0:
            k += 1
            if k > 100:
                break
        B = a - k * _TAU

    fA, fB = f(A), f(B)

    for _ in range(_MAX_ITER):
        if abs(B - A) < _CONV_TOL:
            break
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB <= 0:
            A, fA = B, fB
        else:
            fA /= 2.0
        B, fB = C, fC

    return math.exp(A / 2.0)


# ── Public: win probability ─────────────────────────────────────────────────

def win_probability(rating_a, rating_b, rd_a=None, rd_b=None):
    """
    Win probability for team A (0.0-1.0).

    When RDs are provided, high uncertainty pulls the prediction toward 50-50.
    Backward-compatible: win_probability(elo_a, elo_b) still works.
    """
    if rd_a is None:
        rd_a = 60.0
    if rd_b is None:
        rd_b = 60.0

    mu_a, phi_a = _to_g2(rating_a, rd_a)
    mu_b, phi_b = _to_g2(rating_b, rd_b)

    combined_phi = math.sqrt(phi_a ** 2 + phi_b ** 2)
    return 1.0 / (1.0 + math.exp(-_g(combined_phi) * (mu_a - mu_b)))


# ── Team state ──────────────────────────────────────────────────────────────

@dataclass
class _Team:
    rating: float = STARTING_ELO
    rd: float = STARTING_RD
    volatility: float = INITIAL_VOLATILITY
    games: int = 0


def _update_game(teams, t1_id, t2_id, winner_id):
    """Update two teams' Glicko-2 ratings for one game result."""
    a = teams[t1_id]
    b = teams[t2_id]

    mu_a, phi_a = _to_g2(a.rating, a.rd)
    mu_b, phi_b = _to_g2(b.rating, b.rd)

    a_won = (winner_id == t1_id)
    s_a = 1.0 if a_won else 0.0
    s_b = 1.0 - s_a

    # Update A
    g_b = _g(phi_b)
    E_a = _E(mu_a, mu_b, phi_b)
    v_a = 1.0 / (g_b * g_b * E_a * (1.0 - E_a))
    delta_a = v_a * g_b * (s_a - E_a)

    new_vol_a = _new_volatility(a.volatility, phi_a, v_a, delta_a)
    phi_star_a = math.sqrt(phi_a ** 2 + new_vol_a ** 2)
    new_phi_a = 1.0 / math.sqrt(1.0 / (phi_star_a ** 2) + 1.0 / v_a)
    new_mu_a = mu_a + new_phi_a ** 2 * g_b * (s_a - E_a)

    # Update B
    g_a = _g(phi_a)
    E_b = _E(mu_b, mu_a, phi_a)
    v_b = 1.0 / (g_a * g_a * E_b * (1.0 - E_b))
    delta_b = v_b * g_a * (s_b - E_b)

    new_vol_b = _new_volatility(b.volatility, phi_b, v_b, delta_b)
    phi_star_b = math.sqrt(phi_b ** 2 + new_vol_b ** 2)
    new_phi_b = 1.0 / math.sqrt(1.0 / (phi_star_b ** 2) + 1.0 / v_b)
    new_mu_b = mu_b + new_phi_b ** 2 * g_a * (s_b - E_b)

    # Write back
    a.rating, a.rd = _from_g2(new_mu_a, new_phi_a)
    b.rating, b.rd = _from_g2(new_mu_b, new_phi_b)
    a.volatility = new_vol_a
    b.volatility = new_vol_b
    a.games += 1
    b.games += 1


# ── Single forward pass ────────────────────────────────────────────────────

def _salary_to_rating(salary, min_sal, max_sal):
    if max_sal == min_sal:
        return STARTING_ELO
    return _SAL_MIN + (salary - min_sal) / (max_sal - min_sal) * (_SAL_MAX - _SAL_MIN)


def _run_pass(game_list, team_names, seed_ratings=None, team_salaries=None,
              pass_number=0):
    """
    Run one forward pass of Glicko-2 over all games.

    Parameters
    ----------
    game_list : list of (week, seriesId, gameNumber, team1Id, team2Id, winnerId)
    team_names : dict team_id -> display name
    seed_ratings : dict team_id -> starting rating (from previous pass)
    team_salaries : dict team_id -> salary total (first pass only)
    pass_number : which retrodiction pass (0 = first)

    Returns
    -------
    teams : dict team_id -> _Team (final state)
    history_records : list of dicts for trend chart
    """
    teams = {}

    # Initialize teams
    if seed_ratings:
        # Subsequent pass: start at converged ratings with tighter RD
        # Each pass narrows initial RD — we're more confident in the seed
        retro_rd = max(120.0, SALARY_INITIAL_RD - pass_number * 20.0)
        for tid in team_names:
            r = seed_ratings.get(tid, STARTING_ELO)
            teams[tid] = _Team(rating=r, rd=retro_rd,
                               volatility=INITIAL_VOLATILITY)
    elif team_salaries:
        # First pass with salary data
        sals = list(team_salaries.values())
        min_sal = min(sals) if sals else 0
        max_sal = max(sals) if sals else 0
        for tid in team_names:
            sal = team_salaries.get(tid, 0)
            r = _salary_to_rating(sal, min_sal, max_sal) if sal else STARTING_ELO
            rd = SALARY_INITIAL_RD if sal else STARTING_RD
            teams[tid] = _Team(rating=r, rd=rd)
    else:
        for tid in team_names:
            teams[tid] = _Team()

    # Ensure any team in game_list but not in team_names gets created
    all_game_tids = set()
    for g in game_list:
        all_game_tids.add(g[3])
        all_game_tids.add(g[4])
    for tid in all_game_tids:
        if tid not in teams:
            teams[tid] = _Team()

    # Week 0 snapshot
    history_records = []
    for tid, t in teams.items():
        history_records.append({
            "week": 0, "team_id": tid,
            "name": team_names.get(tid, f"Team {tid}"),
            "elo": round(t.rating, 1), "rd": round(t.rd, 1),
        })

    # Process games in order, snapshot after each week
    current_week = None
    for week, series_id, game_num, t1, t2, winner in game_list:
        _update_game(teams, t1, t2, winner)

        # Snapshot at end of each week
        if current_week is not None and week != current_week:
            for tid, t in teams.items():
                history_records.append({
                    "week": current_week, "team_id": tid,
                    "name": team_names.get(tid, f"Team {tid}"),
                    "elo": round(t.rating, 1), "rd": round(t.rd, 1),
                })
        current_week = week

    # Final week snapshot
    if current_week is not None:
        for tid, t in teams.items():
            history_records.append({
                "week": current_week, "team_id": tid,
                "name": team_names.get(tid, f"Team {tid}"),
                "elo": round(t.rating, 1), "rd": round(t.rd, 1),
            })

    return teams, history_records


# ── Main computation (with retrodiction) ────────────────────────────────────

def compute_elo_through_week(
    matches_df: pd.DataFrame,
    through_week: int,
    team_names: dict,
    team_salaries: dict = None,
) -> tuple:
    """
    Full Bayesian retrodiction: run Glicko-2 forward passes iteratively
    until ratings converge, so early wins against eventually-strong teams
    are properly valued.

    Parameters
    ----------
    matches_df   : from data_loader.load_all_completed_matches(), sorted by
                   (week, seriesId, gameNumber) ascending
    through_week : only process matches with week <= through_week
    team_names   : dict team_id -> display name
    team_salaries : dict team_id -> salary total (optional, seeds first pass)

    Returns
    -------
    standings_df : DataFrame [team_id, name, elo, rd, games_played] sorted desc
    history_df   : DataFrame [week, team_id, name, elo, rd] for trend chart
    """
    # Build sorted game list
    subset = matches_df[
        matches_df["week"].notna() & (matches_df["week"].astype(int) <= through_week)
    ].copy()

    game_list = []
    for _, row in subset.iterrows():
        game_list.append((
            int(row["week"]),
            str(row["seriesId"]),
            int(row["gameNumber"]),
            str(row["team1Id"]),
            str(row["team2Id"]),
            str(row["winnerId"]),
        ))

    if not game_list:
        # No games — return salary-seeded or empty standings
        rows = []
        for tid, name in team_names.items():
            rows.append({
                "team_id": tid, "name": name,
                "elo": STARTING_ELO, "rd": STARTING_RD, "games_played": 0,
            })
        return (
            pd.DataFrame(rows).sort_values("elo", ascending=False).reset_index(drop=True),
            pd.DataFrame(),
        )

    # Pass 0: salary-seeded
    teams, history = _run_pass(game_list, team_names,
                               team_salaries=team_salaries)
    prev_ratings = {tid: t.rating for tid, t in teams.items()}

    # Only run retrodiction when we have enough data for it to be meaningful.
    # With < 30 total games (~2 weeks of Bo3), retrodiction amplifies noise.
    # Scale number of passes by data volume.
    n_games = len(game_list)
    effective_passes = 0 if n_games < MIN_GAMES_FOR_RETRO else min(RETRO_PASSES, 2 + n_games // 40)

    for pass_num in range(1, effective_passes):
        teams, history = _run_pass(game_list, team_names,
                                   seed_ratings=prev_ratings,
                                   pass_number=pass_num)
        new_ratings = {tid: t.rating for tid, t in teams.items()}

        max_delta = max(
            abs(new_ratings.get(tid, STARTING_ELO) - prev_ratings.get(tid, STARTING_ELO))
            for tid in set(prev_ratings) | set(new_ratings)
        )
        prev_ratings = new_ratings

        if max_delta < RETRO_THRESHOLD:
            break

    # Early-season salary anchor: blend match-based rating with salary prior.
    # This prevents wild swings when only a few games have been played.
    # The blend fades linearly: at 0 games = 100% salary, at ANCHOR_GAMES = 0%.
    if team_salaries:
        sals = list(team_salaries.values())
        min_sal = min(sals) if sals else 0
        max_sal = max(sals) if sals else 0
        for tid, t in teams.items():
            sal = team_salaries.get(tid, 0)
            if sal:
                salary_rating = _salary_to_rating(sal, min_sal, max_sal)
                weight = max(0.0, 1.0 - t.games / ANCHOR_GAMES)
                t.rating = weight * salary_rating + (1.0 - weight) * t.rating

        # Apply the same anchor to history so the trend chart matches standings.
        # For each week snapshot, blend based on games played up to that point.
        if history:
            # Count games per team per week from the game list
            games_at_week = {}  # (tid, week) -> cumulative games
            game_counts = {}    # tid -> running count
            current_wk = None
            for week, _, _, t1, t2, _ in game_list:
                if week != current_wk:
                    if current_wk is not None:
                        for tid in game_counts:
                            games_at_week[(tid, current_wk)] = game_counts[tid]
                    current_wk = week
                game_counts[t1] = game_counts.get(t1, 0) + 1
                game_counts[t2] = game_counts.get(t2, 0) + 1
            if current_wk is not None:
                for tid in game_counts:
                    games_at_week[(tid, current_wk)] = game_counts[tid]

            for rec in history:
                tid = rec["team_id"]
                sal = team_salaries.get(tid, 0)
                if sal and rec["week"] > 0:
                    salary_r = _salary_to_rating(sal, min_sal, max_sal)
                    g = games_at_week.get((tid, rec["week"]), 0)
                    w = max(0.0, 1.0 - g / ANCHOR_GAMES)
                    rec["elo"] = round(w * salary_r + (1.0 - w) * rec["elo"], 1)

    # Build standings
    rows = []
    for tid, t in teams.items():
        rows.append({
            "team_id": tid,
            "name": team_names.get(tid, f"Team {tid}"),
            "elo": round(t.rating, 1),
            "rd": round(t.rd, 1),
            "games_played": t.games,
        })
    standings_df = pd.DataFrame(rows).sort_values(
        "elo", ascending=False
    ).reset_index(drop=True)

    history_df = pd.DataFrame(history) if history else pd.DataFrame()

    return standings_df, history_df


# ── Salary-based seeding (active seasons with no games yet) ─────────────────

def salary_seeding(teams_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert salary totals to initial ratings for display.
    Returns DataFrame with: team_id, name, elo, rd, games_played.
    """
    df = teams_df.copy()
    df["team_id"] = df["teamId"].astype(str)

    if df["salaryTotal"].max() == df["salaryTotal"].min():
        df["elo"] = STARTING_ELO
    else:
        lo, hi = df["salaryTotal"].min(), df["salaryTotal"].max()
        df["elo"] = _SAL_MIN + (df["salaryTotal"] - lo) / (hi - lo) * (_SAL_MAX - _SAL_MIN)

    df["elo"] = df["elo"].round(1)
    df["rd"] = SALARY_INITIAL_RD
    df["games_played"] = 0
    return df[["team_id", "name", "elo", "rd", "games_played"]].sort_values(
        "elo", ascending=False
    )

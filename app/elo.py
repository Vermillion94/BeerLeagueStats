"""
Beer League Stats — Glicko-2 Rating Engine (chess-style ladder)

Teams start at salary-seeded ratings (their "preseason ranking", 1100-1300)
and then every game moves the ladder: Glicko-2 per-game updates, where
beating a higher-rated opponent gains more and losing to a lower-rated one
costs more — the fun, chess-like behavior the owner wants (2026-09).

The old retrodiction mode (re-simulating the season to convergence) is
GONE: a 2026-09 walk-forward backtest on seasons 5-6 showed it reprocessed
the same games up to 6x with tightening priors, which spread ratings far
beyond what the data supports — its "80%" predictions hit 64%, and its
Brier score was worse than a coin flip. Single-pass Glicko keeps the
per-game drama without the silent history rewriting.

Probabilities derived from the ladder are SHRUNK toward 50%
(PROB_SHRINK, fit on the same backtest) so matchup odds and playoff sims
say "62%" when they mean 62% — the ladder itself stays untouched.

NULL-week matches are excluded (pre-season series 100-106).
"""

import math
from dataclasses import dataclass, field

import pandas as pd

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

# -- Probability calibration -------------------------------------------------
# Backtest (2026-09, seasons 5-6 walk-forward): raw Glicko log-odds are ~2x
# too extreme at league sample sizes. Displayed/simulated probabilities are
# shrunk toward 50% by this factor; the LADDER ratings are never shrunk.

PROB_SHRINK = 0.5

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

def win_probability(rating_a, rating_b, rd_a=None, rd_b=None, shrink=PROB_SHRINK):
    """
    Win probability for team A (0.0-1.0), calibrated for display.

    When RDs are provided, high uncertainty pulls the prediction toward
    50-50. The result is additionally shrunk toward 50% by `shrink`
    (backtest-fit — see PROB_SHRINK; pass shrink=1.0 for the raw Glicko
    expectation). Backward-compatible: win_probability(elo_a, elo_b) works.
    """
    if rd_a is None:
        rd_a = 60.0
    if rd_b is None:
        rd_b = 60.0

    mu_a, phi_a = _to_g2(rating_a, rd_a)
    mu_b, phi_b = _to_g2(rating_b, rd_b)

    combined_phi = math.sqrt(phi_a ** 2 + phi_b ** 2)
    p = 1.0 / (1.0 + math.exp(-_g(combined_phi) * (mu_a - mu_b)))
    return 0.5 + shrink * (p - 0.5)


def series_win_probability(p_game: float, fmt: str) -> float | None:
    """P(win the series) from per-game probability, by series format.

    BEST_OF_1 → p; BEST_OF_3 → p²(3−2p); BEST_OF_5 → p³(10−15p+6p²).
    BEST_OF_2 returns None — a Bo2 has a DRAW outcome, so a single "series
    win probability" misleads; callers should show the per-game number
    (bo2_outcome_probs gives the full 2-0 / 1-1 / 0-2 split).
    """
    f = (fmt or "").upper()
    if f == "BEST_OF_3":
        return p_game * p_game * (3.0 - 2.0 * p_game)
    if f == "BEST_OF_5":
        p = p_game
        return p ** 3 * (10.0 - 15.0 * p + 6.0 * p * p)
    if f == "BEST_OF_2":
        return None
    return p_game  # BEST_OF_1 / unknown


def bo2_outcome_probs(p_game: float) -> tuple[float, float, float]:
    """(P 2-0, P 1-1 draw, P 0-2) for a Bo2 with independent games."""
    q = 1.0 - p_game
    return p_game * p_game, 2.0 * p_game * q, q * q


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


# ── Main computation ────────────────────────────────────────────────────────

def compute_elo_through_week(
    matches_df: pd.DataFrame,
    through_week: int,
    team_names: dict,
    team_salaries: dict = None,
) -> tuple:
    """
    Salary-seeded single-pass Glicko-2 ladder through the given week.
    Every game moves the ratings; upsets move them more (chess-style).

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
        # No games yet — salary-seeded standings (used to return a flat 1200,
        # which made week-1 upset detection blind)
        sals = list(team_salaries.values()) if team_salaries else []
        min_sal, max_sal = (min(sals), max(sals)) if sals else (0, 0)
        rows = []
        for tid, name in team_names.items():
            sal = (team_salaries or {}).get(tid, 0)
            r = _salary_to_rating(sal, min_sal, max_sal) if sal else STARTING_ELO
            rd = SALARY_INITIAL_RD if sal else STARTING_RD
            rows.append({
                "team_id": tid, "name": name,
                "elo": round(r, 1), "rd": rd, "games_played": 0,
            })
        return (
            pd.DataFrame(rows).sort_values("elo", ascending=False).reset_index(drop=True),
            pd.DataFrame(),
        )

    # One forward pass: salary-seeded start, then honest per-game movement.
    # No retrodiction (double-counted evidence → overconfident, backtested
    # worse than a coin flip) and no anchor-blend (it flattened the trend
    # chart onto the salary line — the ladder should MOVE; owner 2026-09).
    # The salary prior still matters twice: it seeds the starting ratings,
    # and SALARY_INITIAL_RD keeps early swings from being totally unhinged.
    teams, history = _run_pass(game_list, team_names,
                               team_salaries=team_salaries)

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

"""
Beer League Stats — Impact Factor (Player of the Week)

Composite 0-100 score. Each metric is PERCENTILE-normalized WITHIN ROLE
(2026-09 rework): a support's CC/min is compared against other supports,
a mid laner's damage share against other mids. The previous whole-pool
min-max version was measured across seasons 5-6: supports were 19% of the
player pool but 2% of top-5 finishes and won POTW zero times in 19 weeks —
"balanced across roles" was aspiration, not fact. Percentiles also stop a
single outlier game from compressing everyone else's range.

Win bonus applied before final normalization.
"""
import numpy as np
import pandas as pd

# ── Weight configuration ─────────────────────────────────────────────────────
# Tune these without touching the logic below. Must sum to 1.0.

WEIGHTS = {
    "kill_participation": 0.24,   # universal — were you in the fights?
    "kda":                0.16,   # classic metric, capped to limit deathless outliers
    "team_damage_pct":    0.14,   # carry signal (reduced from 25% — was punishing supports)
    "playmaking":         0.12,   # NEW: CC/min + outnumbered kills + epic steals
    "objective_dmg":      0.08,   # NEW: dragon/baron/turret damage per min
    "support_value":      0.08,   # NEW: shields + heals on teammates + saves per min
    "vision_per_min":     0.07,   # map control
    "solo_kills":         0.05,   # mechanical 1v1 dominance
    "cs_per_min":         0.03,   # farm efficiency (low — avoid rewarding AFK farmers)
    "multi_kill_bonus":   0.03,   # triple/quadra/penta bonus
}

WIN_MULTIPLIER = 1.15   # applied after weighted sum if the player's team won
KDA_CAP = 15.0          # cap KDA to reduce deathless-support outliers


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize to [0, 1]. Returns 0.5 for a constant series."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


def _role_percentile(df: pd.DataFrame, series: pd.Series) -> pd.Series:
    """Percentile rank of each value WITHIN its role group (0-1].

    Robust to outliers (rank-based) and role-fair (supports compete with
    supports). Rows without a position fall into their own group.
    """
    if "position" in df.columns:
        roles = df["position"].fillna("UNKNOWN").replace("", "UNKNOWN")
    else:
        roles = pd.Series("UNKNOWN", index=df.index)
    return series.groupby(roles).rank(pct=True)


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    """Get a numeric column, returning zeros if it doesn't exist."""
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)


# ── Core calculation ─────────────────────────────────────────────────────────

def compute_impact_factors(player_stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived stats and impact_factor column to a copy of player_stats_df.

    Expected columns (all from data_loader):
      killParticipation, teamDamagePercentage, kills, deaths, assists,
      visionScore, gameDuration (seconds), soloKills, cs,
      doubleKills, tripleKills, quadraKills, pentaKills, win (0/1),
      totalTimeCCDealt (centiseconds), outnumberedKills, epicMonsterSteals,
      damageDealtToObjectives, totalDamageShieldedOnTeammates,
      totalHealsOnTeammates, saveAllyFromDeath

    Added columns:
      kda, vision_per_min, cs_per_min, multi_kill_bonus,
      playmaking, objective_dmg_per_min, support_value_per_min,
      if_raw, if_adjusted, impact_factor (0-100)
    """
    df = player_stats_df.copy()

    # Guard: ensure numeric types for core columns
    for col in ["kills", "deaths", "assists", "cs", "visionScore",
                "gameDuration", "soloKills", "killParticipation",
                "teamDamagePercentage", "doubleKills", "tripleKills",
                "quadraKills", "pentaKills", "win"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    game_mins = (df["gameDuration"] / 60).clip(lower=1)

    # ── Classic metrics ──
    df["kda"] = (df["kills"] + df["assists"]) / df["deaths"].clip(lower=1)
    df["kda"] = df["kda"].clip(upper=KDA_CAP)
    df["vision_per_min"] = df["visionScore"] / game_mins
    df["cs_per_min"] = df["cs"] / game_mins

    df["multi_kill_bonus"] = (
        _safe_col(df, "tripleKills") * 0.5 +
        _safe_col(df, "quadraKills") * 0.8 +
        _safe_col(df, "pentaKills") * 1.0
    )

    # ── NEW: Playmaking composite ──
    # CC dealt (centiseconds → seconds → per min) + outnumbered kills + epic steals
    cc_per_min = (_safe_col(df, "totalTimeCCDealt") / 100) / game_mins
    outnumbered = _safe_col(df, "outnumberedKills")
    steals = _safe_col(df, "epicMonsterSteals")
    # Combine: CC is the bulk, outnumbered kills add flair, steals are huge
    df["playmaking"] = cc_per_min + outnumbered * 0.3 + steals * 2.0

    # ── NEW: Objective damage per min ──
    df["objective_dmg_per_min"] = _safe_col(df, "damageDealtToObjectives") / game_mins

    # ── NEW: Support value per min ──
    # Shields + heals on teammates + save-ally (clutch peel)
    shields = _safe_col(df, "totalDamageShieldedOnTeammates")
    heals = _safe_col(df, "totalHealsOnTeammates")
    saves = _safe_col(df, "saveAllyFromDeath")
    df["support_value_per_min"] = (shields + heals) / game_mins + saves * 50

    # ── Normalize each metric within ROLE (percentile rank) ──
    df["_n_kp"]      = _role_percentile(df, df["killParticipation"])
    df["_n_dmg"]     = _role_percentile(df, df["teamDamagePercentage"])
    df["_n_kda"]     = _role_percentile(df, df["kda"])
    df["_n_vision"]  = _role_percentile(df, df["vision_per_min"])
    df["_n_solo"]    = _role_percentile(df, df["soloKills"].fillna(0))
    df["_n_cs"]      = _role_percentile(df, df["cs_per_min"])
    df["_n_multi"]   = _role_percentile(df, df["multi_kill_bonus"])
    df["_n_play"]    = _role_percentile(df, df["playmaking"])
    df["_n_obj"]     = _role_percentile(df, df["objective_dmg_per_min"])
    df["_n_support"] = _role_percentile(df, df["support_value_per_min"])

    df["if_raw"] = (
        WEIGHTS["kill_participation"] * df["_n_kp"] +
        WEIGHTS["team_damage_pct"]    * df["_n_dmg"] +
        WEIGHTS["kda"]                * df["_n_kda"] +
        WEIGHTS["playmaking"]         * df["_n_play"] +
        WEIGHTS["objective_dmg"]      * df["_n_obj"] +
        WEIGHTS["support_value"]      * df["_n_support"] +
        WEIGHTS["vision_per_min"]     * df["_n_vision"] +
        WEIGHTS["solo_kills"]         * df["_n_solo"] +
        WEIGHTS["cs_per_min"]         * df["_n_cs"] +
        WEIGHTS["multi_kill_bonus"]   * df["_n_multi"]
    )

    # Win bonus
    df["if_adjusted"] = df["if_raw"] * df["win"].map(
        {1: WIN_MULTIPLIER, 0: 1.0, True: WIN_MULTIPLIER, False: 1.0}
    ).fillna(1.0)

    # Final 0-100 normalization across the pool
    df["impact_factor"] = (_safe_normalize(df["if_adjusted"]) * 100).round(1)

    # Drop temp columns
    df.drop(columns=[c for c in df.columns if c.startswith("_n_")], inplace=True)

    return df


def player_of_the_week(player_stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Impact Factors for all player-game rows, aggregate per player,
    and return the top 5.

    Aggregation uses the MEAN Impact Factor across games (not sum), so a
    player who played 3 games in a Bo3 sweep is fairly compared to one who
    played 2 games in a 2-1 series.

    For players who played multiple champions, the row with the most games
    on one champion is kept (ties broken by higher avg impact factor).

    Returns top-5 DataFrame with columns:
      summonerId, riotId, username, championName,
      games, wins, avg_if, avg_kp, avg_dmg_pct, avg_kda,
      avg_vision_min, avg_solo_kills, avg_cs_per_min
    """
    if player_stats_df.empty:
        return pd.DataFrame()

    df = compute_impact_factors(player_stats_df)

    id_col = "summonerId" if "summonerId" in df.columns else "username"

    # Aggregate per PLAYER across all their games (2026-09: the old
    # per-champion grouping silently discarded a two-champ week's minority
    # games); championName shown is the most-played champion of the week.
    agg = df.groupby([id_col, "riotId", "username"]).agg(
        games=("impact_factor", "count"),
        wins=("win", "sum"),
        avg_if=("impact_factor", "mean"),
        avg_kp=("killParticipation", "mean"),
        avg_dmg_pct=("teamDamagePercentage", "mean"),
        avg_kda=("kda", "mean"),
        avg_vision_min=("vision_per_min", "mean"),
        avg_solo_kills=("soloKills", "mean"),
        avg_cs_per_min=("cs_per_min", "mean"),
    ).reset_index()

    modal_champ = (
        df.groupby(id_col)["championName"]
        .agg(lambda s: s.mode().iloc[0])
        .rename("championName")
    )
    agg = agg.merge(modal_champ, left_on=id_col, right_index=True)

    return agg.sort_values("avg_if", ascending=False).head(5).reset_index(drop=True)


def weight_breakdown() -> list:
    """Return human-readable weight breakdown for the formula expander.

    Note shown to users: every metric is percentile-ranked WITHIN ROLE, so
    a support's playmaking is judged against other supports, not mid laners.
    """
    rows = [
        ("Kill Participation", "24%", "Universal carry signal — were you in every fight?"),
        ("KDA (capped x15)",   "16%", "Classic metric, capped to limit deathless outliers"),
        ("Team Damage %",      "14%", "Raw output share (reduced to not penalize supports)"),
        ("Playmaking",         "12%", "CC/min + outnumbered kills + epic monster steals"),
        ("Objective Damage",    "8%", "Dragon/Baron/turret damage per minute"),
        ("Support Value",       "8%", "Shields + heals on teammates + clutch saves"),
        ("Vision / min",        "7%", "Map control contribution"),
        ("Solo Kills",          "5%", "Mechanical 1v1 dominance"),
        ("CS / min",            "3%", "Farm efficiency (low to avoid rewarding AFK farmers)"),
        ("Multi-kill Bonus",    "3%", "Triple x0.5 / Quadra x0.8 / Penta x1.0"),
    ]
    return rows

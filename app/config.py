"""
Beer League Stats — Tunable Configuration

All behavioral thresholds, display limits, and filter defaults in one place.
Adjust these without touching any other code. Chart sizing and CSS are NOT
included here — only values that affect what data is shown and how it's
interpreted.
"""

# ── Matchup Analysis ──────────────────────────────────────────────────────────

UPSET_THRESHOLD = 0.40
"""A completed series is flagged as an UPSET when the winner's pre-match
win probability was below this value (e.g., 0.40 = won with < 40% odds)."""

CLOSE_MATCHUP_THRESHOLD = 0.40
"""A scheduled series is flagged as a CLOSE MATCHUP when the favored team's
win probability is between this value and 1 - this value (e.g., 0.40-0.60)."""

DEFAULT_RD = 300.0
"""Default rating deviation used when a team has no Glicko-2 history."""

# ── Champion Analytics ────────────────────────────────────────────────────────

CHAMP_MIN_GAMES_DEFAULT = 2
"""Default minimum games for a champion to appear in win rate charts."""

CHAMP_MIN_GAMES_MAX = 10
"""Maximum selectable value for the min-games filter in the sidebar."""

TRENDING_WEEKS_LOOKBACK = 3
"""Number of recent weeks to use for the 'trending champions' comparison."""

MIN_WEEKS_FOR_TRENDING = 4
"""Minimum completed weeks before the trending champions chart is shown."""

TRENDING_CHAMPS_COUNT = 14
"""Number of champions to display in the trending chart (sorted by delta)."""

TOP_CHAMPS_PER_ROLE = 3
"""Number of champions to show per role in the 'Popular by Role' table."""

# ── Player Leaderboards ──────────────────────────────────────────────────────

LEADERBOARD_MIN_GAMES = 2
"""Minimum games for a player to appear on season leaderboards."""

LEADERBOARD_TOP_N = 3
"""Number of players to show per leaderboard category."""

# ── Item Analytics ────────────────────────────────────────────────────────────

ITEM_WINRATE_MIN_BUILDS = 5
"""Minimum number of builds for an item to appear in win rate chart."""

MOST_BUILT_ITEMS_TOP_N = 15
"""Number of items to show in the 'most built' chart."""

ITEM_WINRATE_TOP_N = 20
"""Number of items to show in the 'item win rates' chart."""

# ── Elo / Glicko-2 ───────────────────────────────────────────────────────────

ANCHOR_GAMES = 10
"""Per-team game count at which the salary-prior anchor fades to 0%.
At 0 games = 100% salary rating, at ANCHOR_GAMES = 100% match rating."""

MIN_GAMES_FOR_RETRO = 15
"""Minimum total games before retrodiction passes are enabled.
Below this, noise amplification outweighs the benefit."""

# ── Broadcast Story Weights ─────────────────────────────────────────────────
# Base interest scores (0-100) for each story type detected by stories.py.
# Higher = more likely to be featured in the broadcast.

STORY_WEIGHT_PENTAKILL = 95
STORY_WEIGHT_UPSET = 80
STORY_WEIGHT_RECORD = 75
STORY_WEIGHT_BREAKOUT_PLAYER = 70
STORY_WEIGHT_SALARY_STEAL = 65
STORY_WEIGHT_STANDINGS_SHAKEUP = 65
STORY_WEIGHT_STREAK_BASE = 55
"""Streaks scale: base + 10 per win beyond 2 (3-streak=65, 5-streak=85)."""
STORY_WEIGHT_TEAM_COLLAPSE = 60
STORY_WEIGHT_RIVALRY = 55
STORY_WEIGHT_CLOSE_SERIES = 50
STORY_WEIGHT_FALLBACK = 20
"""Generic 'here are the results' story when nothing interesting happened."""

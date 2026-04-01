"""
Beer League Stats — Data Loader
All SQLite access. Every public function returns a pandas DataFrame or plain Python type.
No business logic lives here — only queries and joins.
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd


# ── Connection helpers ───────────────────────────────────────────────────────

def get_db_paths() -> list:
    """Return all .db files in ./data/, sorted newest-first by filename."""
    data_dir = Path("data")
    return sorted(data_dir.glob("*.db"), reverse=True)


def _conn(db_path: str) -> sqlite3.Connection:
    """Open a read-only connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _df(conn: sqlite3.Connection, sql: str, params=()) -> pd.DataFrame:
    """Execute sql and return a DataFrame. Coerces string IDs."""
    df = pd.read_sql_query(sql, conn, params=params)
    # Coerce common ID columns to str so joins are consistent
    for col in ["seasonId", "teamId", "summonerId", "userId", "seriesId",
                "team1Id", "team2Id", "winnerId", "matchId", "id"]:
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


# ── Season / team meta ───────────────────────────────────────────────────────

def load_seasons(db_path: str) -> pd.DataFrame:
    """All seasons except the test one (id=3). Columns: id, name, status, salaryCap."""
    with _conn(db_path) as conn:
        return _df(conn, """
            SELECT id, name, status, salaryCap, startDate
            FROM season
            WHERE id != 3
            ORDER BY id
        """)


def load_teams_for_season(db_path: str, season_id) -> pd.DataFrame:
    """
    Teams enrolled in a season.
    Columns: teamId, name, tag, color, salaryTotal
    """
    with _conn(db_path) as conn:
        return _df(conn, """
            SELECT st.teamId, t.name, t.tag, t.color, st.salaryTotal
            FROM season_team st
            JOIN team t ON st.teamId = t.id
            WHERE st.seasonId = ?
            ORDER BY t.name
        """, (str(season_id),))


def load_all_teams(db_path: str) -> pd.DataFrame:
    """All teams. Columns: id (as teamId), name, tag, color."""
    with _conn(db_path) as conn:
        df = _df(conn, "SELECT id, name, tag, color FROM team ORDER BY name")
        df.rename(columns={"id": "teamId"}, inplace=True)
        return df


def season_has_data(db_path: str, season_id) -> bool:
    """True if the season has at least one COMPLETED match with a non-NULL week."""
    with _conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM match
            WHERE seasonId = ? AND status = 'COMPLETED' AND week IS NOT NULL
        """, (str(season_id),))
        return cur.fetchone()[0] > 0


def load_completed_weeks(db_path: str, season_id) -> list:
    """Sorted list of week numbers with at least one COMPLETED match."""
    with _conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT week FROM match
            WHERE seasonId = ? AND status = 'COMPLETED' AND week IS NOT NULL
            ORDER BY week
        """, (str(season_id),))
        return [row[0] for row in cur.fetchall()]


# ── Weekly data ──────────────────────────────────────────────────────────────

def load_series_for_week(db_path: str, week: int, season_id) -> pd.DataFrame:
    """
    Series results for a week, including per-game win counts.
    Columns: seriesId, team1Name, team2Name, winnerName, team1Wins, team2Wins, format, status
    """
    with _conn(db_path) as conn:
        series_df = _df(conn, """
            SELECT s.id as seriesId, s.team1Id, s.team2Id, s.winnerId,
                   s.format, s.status,
                   t1.name as team1Name, t2.name as team2Name,
                   tw.name as winnerName
            FROM series s
            JOIN team t1 ON s.team1Id = t1.id
            JOIN team t2 ON s.team2Id = t2.id
            LEFT JOIN team tw ON s.winnerId = tw.id
            WHERE s.week = ? AND s.seasonId = ? AND s.status = 'COMPLETED'
            ORDER BY s.id
        """, (week, str(season_id)))

        if series_df.empty:
            return series_df

        # Count individual game wins per series
        match_df = _df(conn, """
            SELECT seriesId, winnerId, COUNT(*) as cnt
            FROM match
            WHERE week = ? AND seasonId = ? AND status = 'COMPLETED'
              AND winnerId IS NOT NULL
            GROUP BY seriesId, winnerId
        """, (week, str(season_id)))

        win_map = {}
        for _, row in match_df.iterrows():
            win_map[(row["seriesId"], row["winnerId"])] = row["cnt"]

        series_df["team1Wins"] = series_df.apply(
            lambda r: win_map.get((r["seriesId"], r["team1Id"]), 0), axis=1)
        series_df["team2Wins"] = series_df.apply(
            lambda r: win_map.get((r["seriesId"], r["team2Id"]), 0), axis=1)

        return series_df


def load_week_data(db_path: str, week: int, season_id) -> dict:
    """
    Load all data needed for the Weekly Recap tab.
    Returns dict with keys: matches, team_stats, player_stats, series
    All values are DataFrames.
    """
    sid = str(season_id)
    with _conn(db_path) as conn:
        matches = _df(conn, """
            SELECT m.id, m.seasonId, m.seriesId, m.week, m.gameNumber,
                   m.team1Id, m.team2Id, m.winnerId, m.status,
                   t1.name as team1Name, t2.name as team2Name,
                   tw.name as winnerName
            FROM match m
            JOIN team t1 ON m.team1Id = t1.id
            JOIN team t2 ON m.team2Id = t2.id
            LEFT JOIN team tw ON m.winnerId = tw.id
            WHERE m.week = ? AND m.seasonId = ? AND m.status = 'COMPLETED'
            ORDER BY m.seriesId, m.gameNumber
        """, (week, sid))

        if matches.empty:
            return {"matches": matches, "team_stats": pd.DataFrame(),
                    "player_stats": pd.DataFrame(), "series": pd.DataFrame()}

        match_ids = tuple(matches["id"].tolist())
        placeholders = ",".join("?" * len(match_ids))

        team_stats = _df(conn, f"""
            SELECT ts.id, ts.matchId, ts.teamId, t.name as teamName,
                   ts.kills, ts.dragons, ts.barons, ts.heralds,
                   ts.turrets, ts.inhibitors
            FROM team_stats ts
            JOIN team t ON ts.teamId = t.id
            WHERE ts.matchId IN ({placeholders})
        """, match_ids)

        player_stats = _df(conn, f"""
            SELECT ps.*,
                   s.riotIdGameName || '#' || s.riotIdTagline AS riotId,
                   u.username, u.salary
            FROM player_stats ps
            JOIN summoner s ON ps.summonerId = s.id
            JOIN user u ON s.userId = u.id
            WHERE ps.matchId IN ({placeholders})
        """, match_ids)

        # Numeric coercions for player_stats
        for col in ["kills", "deaths", "assists", "cs", "goldEarned",
                    "visionScore", "soloKills", "gameDuration",
                    "killParticipation", "teamDamagePercentage",
                    "doubleKills", "tripleKills", "quadraKills", "pentaKills",
                    "totalDamageDealtToChampions", "damageSelfMitigated",
                    "totalHealsOnTeammates", "wardsPlaced", "totalTimeCCDealt",
                    "skillshotsHit", "skillshotsDodged", "epicMonsterSteals",
                    "survivedSingleDigitHpCount", "fistBumpParticipation",
                    "firstBloodKill", "turretTakedowns"]:
            if col in player_stats.columns:
                player_stats[col] = pd.to_numeric(player_stats[col], errors="coerce").fillna(0)

        player_stats["win"] = player_stats["win"].astype(int)

        series = load_series_for_week(db_path, week, season_id)

    return {
        "matches": matches,
        "team_stats": team_stats,
        "player_stats": player_stats,
        "series": series,
    }


# ── Season-wide data (for Elo + Champion analytics) ──────────────────────────

def load_all_completed_matches(db_path: str, season_id) -> pd.DataFrame:
    """
    All completed matches for a season, ordered for Elo simulation.
    Excludes matches with NULL week (pre-season series 100-106).
    Columns: id, seriesId, week, gameNumber, team1Id, team2Id, winnerId
    """
    with _conn(db_path) as conn:
        return _df(conn, """
            SELECT id, seriesId, week, gameNumber, team1Id, team2Id, winnerId
            FROM match
            WHERE seasonId = ? AND status = 'COMPLETED'
              AND week IS NOT NULL AND winnerId IS NOT NULL
            ORDER BY week ASC, seriesId ASC, gameNumber ASC
        """, (str(season_id),))


def load_all_completed_matches_named(db_path: str, season_id) -> pd.DataFrame:
    """Like load_all_completed_matches but includes team names."""
    with _conn(db_path) as conn:
        return _df(conn, """
            SELECT m.id, m.seriesId, m.week, m.gameNumber,
                   m.team1Id, m.team2Id, m.winnerId,
                   t1.name as team1Name, t2.name as team2Name,
                   tw.name as winnerName
            FROM match m
            JOIN team t1 ON m.team1Id = t1.id
            JOIN team t2 ON m.team2Id = t2.id
            LEFT JOIN team tw ON m.winnerId = tw.id
            WHERE m.seasonId = ? AND m.status = 'COMPLETED'
              AND m.week IS NOT NULL AND m.winnerId IS NOT NULL
            ORDER BY m.week ASC, m.seriesId ASC, m.gameNumber ASC
        """, (str(season_id),))


def load_all_player_stats(db_path: str, season_id) -> pd.DataFrame:
    """
    All player stats for a season's completed matches, with player identity.
    Includes week number joined from match table.
    """
    with _conn(db_path) as conn:
        df = _df(conn, """
            SELECT ps.*,
                   m.week, m.seriesId, m.gameNumber,
                   m.team1Id as matchTeam1Id, m.team2Id as matchTeam2Id,
                   s.riotIdGameName || '#' || s.riotIdTagline AS riotId,
                   u.username, u.salary
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            JOIN summoner s ON ps.summonerId = s.id
            JOIN user u ON s.userId = u.id
            WHERE m.seasonId = ? AND m.status = 'COMPLETED'
              AND m.week IS NOT NULL
        """, (str(season_id),))

        numeric_cols = [
            "kills", "deaths", "assists", "cs", "goldEarned",
            "visionScore", "soloKills", "gameDuration",
            "killParticipation", "teamDamagePercentage",
            "doubleKills", "tripleKills", "quadraKills", "pentaKills",
            "totalDamageDealtToChampions", "damageSelfMitigated",
            "totalHealsOnTeammates", "wardsPlaced", "totalTimeCCDealt",
            "skillshotsHit", "skillshotsDodged", "epicMonsterSteals",
            "survivedSingleDigitHpCount", "fistBumpParticipation",
            "firstBloodKill", "turretTakedowns",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["win"] = df["win"].astype(int)
        return df


def load_champion_stats(db_path: str, season_ids: list) -> pd.DataFrame:
    """
    Aggregated champion stats across given seasons.
    Columns: championName, season_id, season_name, games, wins, losses,
             win_rate, avg_kills, avg_deaths, avg_assists, avg_kda,
             avg_kp, avg_dmg_pct, avg_cs_per_min
    Also includes a 'presence' column: 'Lite', 'Stout', or 'Both'.
    """
    if not season_ids:
        return pd.DataFrame()

    sids = [str(s) for s in season_ids]
    placeholders = ",".join("?" * len(sids))

    with _conn(db_path) as conn:
        # Load season info so we can tag Lite vs Stout
        seasons_df = _df(conn, f"""
            SELECT id, name FROM season WHERE id IN ({placeholders})
        """, tuple(sids))
        season_name_map = {row["id"]: row["name"] for _, row in seasons_df.iterrows()}

        df = _df(conn, f"""
            SELECT ps.championName, m.seasonId,
                   ps.kills, ps.deaths, ps.assists, ps.cs,
                   ps.gameDuration, ps.win,
                   ps.killParticipation, ps.teamDamagePercentage
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            WHERE m.seasonId IN ({placeholders})
              AND m.status = 'COMPLETED'
              AND m.week IS NOT NULL
        """, tuple(sids))

    if df.empty:
        return df

    for col in ["kills", "deaths", "assists", "cs", "gameDuration",
                "killParticipation", "teamDamagePercentage"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["win"] = pd.to_numeric(df["win"], errors="coerce").fillna(0).astype(int)

    df["kda"] = (df["kills"] + df["assists"]) / df["deaths"].clip(lower=1)
    df["cs_per_min"] = df["cs"] / (df["gameDuration"] / 60).clip(lower=1)

    agg = df.groupby(["championName", "seasonId"]).agg(
        games=("win", "count"),
        wins=("win", "sum"),
        avg_kills=("kills", "mean"),
        avg_deaths=("deaths", "mean"),
        avg_assists=("assists", "mean"),
        avg_kda=("kda", "mean"),
        avg_kp=("killParticipation", "mean"),
        avg_dmg_pct=("teamDamagePercentage", "mean"),
        avg_cs_per_min=("cs_per_min", "mean"),
    ).reset_index()

    agg["losses"] = agg["games"] - agg["wins"]
    agg["win_rate"] = agg["wins"] / agg["games"]
    agg["season_name"] = agg["seasonId"].map(season_name_map)

    # Add division label based on season name
    def _division(name):
        if name is None:
            return "Unknown"
        if "lite" in name.lower():
            return "Lite"
        if "stout" in name.lower():
            return "Stout"
        return "Other"

    agg["division"] = agg["season_name"].apply(_division)

    return agg


def load_champion_presence(db_path: str, season_ids: list) -> pd.DataFrame:
    """
    For each champion, which divisions it appears in (Lite, Stout, or Both).
    Returns: championName, division_presence (Lite / Stout / Both)
    """
    champ_df = load_champion_stats(db_path, season_ids)
    if champ_df.empty:
        return pd.DataFrame()

    divisions_per_champ = champ_df.groupby("championName")["division"].apply(set).reset_index()
    divisions_per_champ.columns = ["championName", "divisions"]

    def _presence(divs):
        has_lite = "Lite" in divs
        has_stout = "Stout" in divs
        if has_lite and has_stout:
            return "Both"
        elif has_lite:
            return "Lite Only"
        elif has_stout:
            return "Stout Only"
        return "Other"

    divisions_per_champ["presence"] = divisions_per_champ["divisions"].apply(_presence)
    return divisions_per_champ[["championName", "presence"]]


def _ddragon_data() -> tuple:
    """Fetch champion data from Riot Data Dragon CDN.
    Returns (version, {int_id: display_name}, {display_name: ddragon_id}).
    Cached in-memory after first call."""
    if not hasattr(_ddragon_data, "_cache"):
        import urllib.request
        try:
            versions = json.loads(
                urllib.request.urlopen(
                    "https://ddragon.leagueoflegends.com/api/versions.json",
                    timeout=5,
                ).read()
            )
            ver = versions[0]
            data = json.loads(
                urllib.request.urlopen(
                    f"https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion.json",
                    timeout=5,
                ).read()
            )
            id_map = {int(info["key"]): info["name"] for info in data["data"].values()}
            # Map display name → ddragon ID (URL-safe key) e.g. "Miss Fortune" → "MissFortune"
            name_to_key = {info["name"]: info["id"] for info in data["data"].values()}
            # Also map ddragon ID to itself (DB stores ddragon IDs as championName)
            name_to_key.update({info["id"]: info["id"] for info in data["data"].values()})
            _ddragon_data._cache = (ver, id_map, name_to_key)
        except Exception:
            _ddragon_data._cache = ("", {}, {})
    return _ddragon_data._cache


def _champion_id_map() -> dict:
    """Fetch champion ID → name mapping from Riot Data Dragon CDN.
    Returns dict: {int_id: 'ChampionName'}."""
    _, id_map, _ = _ddragon_data()
    return id_map


def ddragon_version() -> str:
    """Return the current Data Dragon version string."""
    ver, _, _ = _ddragon_data()
    return ver


def champion_icon_url(champion_name: str) -> str:
    """Return the Data Dragon square icon URL for a champion name.
    Falls back to empty string if the champion can't be resolved."""
    ver, _, name_to_key = _ddragon_data()
    if not ver:
        return ""
    key = name_to_key.get(champion_name, champion_name)
    return f"https://ddragon.leagueoflegends.com/cdn/{ver}/img/champion/{key}.png"


def load_ban_stats(db_path: str, season_ids: list) -> pd.DataFrame:
    """
    Load ban data from match table and map champion IDs to names.
    Returns: championName, bans (count), ban_rate (fraction of total games).
    Only includes seasons/matches where bans are recorded (non-NULL).
    """
    placeholders = ",".join("?" * len(season_ids))
    with _conn(db_path) as conn:
        df = _df(conn, f"""
            SELECT m.id, m.seasonId,
                   m.team1Ban1, m.team1Ban2, m.team1Ban3, m.team1Ban4, m.team1Ban5,
                   m.team2Ban1, m.team2Ban2, m.team2Ban3, m.team2Ban4, m.team2Ban5
            FROM match m
            JOIN series s ON m.seriesId = s.id
            WHERE m.seasonId IN ({placeholders})
              AND m.status = 'COMPLETED'
              AND s.week IS NOT NULL
              AND m.team1Ban1 IS NOT NULL
        """, season_ids)

    if df.empty:
        return pd.DataFrame()

    id_map = _champion_id_map()
    if not id_map:
        return pd.DataFrame()

    # Unpivot all ban columns into a single list
    ban_cols = [f"team{t}Ban{b}" for t in [1, 2] for b in range(1, 6)]
    records = []
    for _, row in df.iterrows():
        for col in ban_cols:
            val = row.get(col)
            if val is not None and not pd.isna(val):
                champ_name = id_map.get(int(val))
                if champ_name:
                    records.append({"championName": champ_name})

    if not records:
        return pd.DataFrame()

    bans_df = pd.DataFrame(records)
    total_games = len(df)
    agg = bans_df.groupby("championName").size().reset_index(name="bans")
    agg["ban_rate"] = agg["bans"] / total_games
    agg = agg.sort_values("bans", ascending=False).reset_index(drop=True)
    agg["total_games"] = total_games
    return agg


def load_role_mapping(db_path: str, season_id) -> dict:
    """
    Parse season_team.startingLineup JSON to build a summonerId → role mapping.
    Returns dict: {summonerId_str: role} where role is TOP/JUNGLE/MIDDLE/BOTTOM/SUPPORT.
    Join chain: startingLineup userId → summoner.userId → summoner.id (=summonerId).
    """
    with _conn(db_path) as conn:
        rows = conn.execute("""
            SELECT startingLineup FROM season_team
            WHERE seasonId = ? AND startingLineup IS NOT NULL AND startingLineup != ''
        """, (str(season_id),)).fetchall()

        summoner_rows = conn.execute(
            "SELECT id, userId FROM summoner"
        ).fetchall()

    # userId → list of summonerIds (some users have multiple accounts)
    user_to_summoners = {}
    for sid, uid in summoner_rows:
        user_to_summoners.setdefault(str(uid), []).append(str(sid))

    role_map = {}  # summonerId → role
    for (lineup_json,) in rows:
        try:
            lineup = json.loads(lineup_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for role, user_id in lineup.items():
            for summoner_id in user_to_summoners.get(str(user_id), []):
                role_map[summoner_id] = role

    return role_map


def load_all_series(db_path: str, season_id) -> pd.DataFrame:
    """
    All series (COMPLETED + SCHEDULED) for a season, with team names and
    win counts for completed series.
    Columns: seriesId, week, team1Id, team2Id, team1Name, team2Name,
             winnerId, winnerName, team1Wins, team2Wins, status, format
    """
    sid = str(season_id)
    with _conn(db_path) as conn:
        df = _df(conn, """
            SELECT s.id as seriesId, s.week, s.format, s.status,
                   s.team1Id, s.team2Id, s.winnerId,
                   t1.name as team1Name, t2.name as team2Name,
                   tw.name as winnerName
            FROM series s
            JOIN team t1 ON s.team1Id = t1.id
            JOIN team t2 ON s.team2Id = t2.id
            LEFT JOIN team tw ON s.winnerId = tw.id
            WHERE s.seasonId = ? AND s.week IS NOT NULL
            ORDER BY s.week, s.id
        """, (sid,))

        if df.empty:
            return df

        # Count per-series game wins for completed series
        match_df = _df(conn, """
            SELECT seriesId, winnerId, COUNT(*) as cnt
            FROM match
            WHERE seasonId = ? AND status = 'COMPLETED'
              AND winnerId IS NOT NULL
            GROUP BY seriesId, winnerId
        """, (sid,))

        win_map = {}
        for _, row in match_df.iterrows():
            win_map[(row["seriesId"], row["winnerId"])] = row["cnt"]

        df["team1Wins"] = df.apply(
            lambda r: win_map.get((r["seriesId"], r["team1Id"]), 0), axis=1)
        df["team2Wins"] = df.apply(
            lambda r: win_map.get((r["seriesId"], r["team2Id"]), 0), axis=1)

        return df


def load_upcoming_series(db_path: str, season_id) -> pd.DataFrame:
    """
    All SCHEDULED series for a season, with team names and salary totals.
    Columns: seriesId, week, team1Id, team2Id, team1Name, team2Name,
             team1Salary, team2Salary, format
    """
    with _conn(db_path) as conn:
        df = _df(conn, """
            SELECT s.id as seriesId, s.week, s.format,
                   s.team1Id, s.team2Id,
                   t1.name as team1Name, t2.name as team2Name
            FROM series s
            JOIN team t1 ON s.team1Id = t1.id
            JOIN team t2 ON s.team2Id = t2.id
            WHERE s.seasonId = ? AND s.status = 'SCHEDULED'
              AND s.week IS NOT NULL
            ORDER BY s.week, s.id
        """, (str(season_id),))

        if df.empty:
            return df

        # Join salary from season_team
        salaries = _df(conn, """
            SELECT teamId, salaryTotal FROM season_team WHERE seasonId = ?
        """, (str(season_id),))
        sal_map = dict(zip(salaries["teamId"], salaries["salaryTotal"]))

        df["team1Salary"] = df["team1Id"].map(sal_map).fillna(0)
        df["team2Salary"] = df["team2Id"].map(sal_map).fillna(0)
        return df


# ── Team analytics ───────────────────────────────────────────────────────────

def load_head_to_head(db_path: str, team1_id, team2_id, season_id) -> pd.DataFrame:
    """All completed series between two teams in a season, with results."""
    sid = str(season_id)
    t1, t2 = str(team1_id), str(team2_id)
    with _conn(db_path) as conn:
        return _df(conn, """
            SELECT s.id as seriesId, s.week, s.team1Id, s.team2Id,
                   s.winnerId, s.format, s.status,
                   t1.name as team1Name, t2.name as team2Name,
                   tw.name as winnerName
            FROM series s
            JOIN team t1 ON s.team1Id = t1.id
            JOIN team t2 ON s.team2Id = t2.id
            LEFT JOIN team tw ON s.winnerId = tw.id
            WHERE s.seasonId = ? AND s.week IS NOT NULL
              AND s.status = 'COMPLETED'
              AND ((s.team1Id = ? AND s.team2Id = ?)
                OR (s.team1Id = ? AND s.team2Id = ?))
            ORDER BY s.week
        """, (sid, t1, t2, t2, t1))


def load_team_records(db_path: str, season_id) -> pd.DataFrame:
    """
    Compute per-team records for a season: series W-L, game W-L, and avg stats.
    Returns DataFrame with columns: teamId, name, series_wins, series_losses,
    game_wins, game_losses, win_pct, avg_kills, avg_deaths, avg_dragons,
    avg_barons, avg_turrets, avg_duration_s
    """
    sid = str(season_id)
    with _conn(db_path) as conn:
        # Series records
        series_df = _df(conn, """
            SELECT id, team1Id, team2Id, winnerId
            FROM series
            WHERE seasonId = ? AND status = 'COMPLETED' AND week IS NOT NULL
        """, (sid,))

        # Game records
        matches_df = _df(conn, """
            SELECT m.id, m.team1Id, m.team2Id, m.winnerId
            FROM match m
            WHERE m.seasonId = ? AND m.status = 'COMPLETED' AND m.week IS NOT NULL
        """, (sid,))

        # Team stats per game (for avg objectives)
        team_stats_df = _df(conn, """
            SELECT ts.teamId, ts.matchId, ts.kills, ts.deaths,
                   ts.dragons, ts.barons, ts.turrets
            FROM team_stats ts
            JOIN match m ON ts.matchId = m.id
            WHERE m.seasonId = ? AND m.status = 'COMPLETED' AND m.week IS NOT NULL
        """, (sid,))

        # Game durations from player_stats
        dur_df = _df(conn, """
            SELECT ps.matchId, ps.gameDuration
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            WHERE m.seasonId = ? AND m.status = 'COMPLETED' AND m.week IS NOT NULL
            GROUP BY ps.matchId
        """, (sid,))

        teams_df = _df(conn, """
            SELECT st.teamId, t.name
            FROM season_team st
            JOIN team t ON st.teamId = t.id
            WHERE st.seasonId = ?
        """, (sid,))

    if teams_df.empty:
        return pd.DataFrame()

    records = []
    for _, team in teams_df.iterrows():
        tid = str(team["teamId"])
        name = team["name"]

        # Series W-L
        sw = len(series_df[series_df["winnerId"] == tid]) if not series_df.empty else 0
        sl = len(series_df[
            ((series_df["team1Id"] == tid) | (series_df["team2Id"] == tid)) &
            (series_df["winnerId"] != tid) & (series_df["winnerId"].notna())
        ]) if not series_df.empty else 0

        # Game W-L
        gw = len(matches_df[matches_df["winnerId"] == tid]) if not matches_df.empty else 0
        gl = len(matches_df[
            ((matches_df["team1Id"] == tid) | (matches_df["team2Id"] == tid)) &
            (matches_df["winnerId"] != tid) & (matches_df["winnerId"].notna())
        ]) if not matches_df.empty else 0

        total_games = gw + gl
        win_pct = gw / total_games if total_games > 0 else 0

        # Avg stats from team_stats
        ts_team = team_stats_df[team_stats_df["teamId"] == tid] if not team_stats_df.empty else pd.DataFrame()
        for col in ["kills", "deaths", "dragons", "barons", "turrets"]:
            if col in ts_team.columns:
                ts_team[col] = pd.to_numeric(ts_team[col], errors="coerce").fillna(0)

        avg_kills = ts_team["kills"].mean() if not ts_team.empty else 0
        avg_deaths = ts_team["deaths"].mean() if not ts_team.empty else 0
        avg_dragons = ts_team["dragons"].mean() if not ts_team.empty else 0
        avg_barons = ts_team["barons"].mean() if not ts_team.empty else 0
        avg_turrets = ts_team["turrets"].mean() if not ts_team.empty else 0

        # Avg duration
        if not dur_df.empty:
            team_match_ids = set(matches_df[
                (matches_df["team1Id"] == tid) | (matches_df["team2Id"] == tid)
            ]["id"].tolist()) if not matches_df.empty else set()
            team_durs = dur_df[dur_df["matchId"].isin(team_match_ids)]
            avg_dur = pd.to_numeric(team_durs["gameDuration"], errors="coerce").mean() if not team_durs.empty else 0
        else:
            avg_dur = 0

        records.append({
            "teamId": tid, "name": name,
            "series_wins": sw, "series_losses": sl,
            "game_wins": gw, "game_losses": gl,
            "win_pct": round(win_pct, 3),
            "avg_kills": round(avg_kills, 1),
            "avg_deaths": round(avg_deaths, 1),
            "avg_dragons": round(avg_dragons, 1),
            "avg_barons": round(avg_barons, 1),
            "avg_turrets": round(avg_turrets, 1),
            "avg_duration_s": round(avg_dur, 0),
        })

    return pd.DataFrame(records).sort_values("win_pct", ascending=False).reset_index(drop=True)


def load_draft_diversity(db_path: str, season_id) -> pd.DataFrame:
    """
    Count unique champions played per team for a season.
    Returns DataFrame: teamId, name, unique_champs, total_picks, champ_list
    """
    sid = str(season_id)
    with _conn(db_path) as conn:
        # Need to map player_stats to beer league teams via team_member
        df = _df(conn, """
            SELECT ps.championName, tm.teamId, t.name as teamName
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            JOIN summoner s ON ps.summonerId = s.id
            JOIN team_member tm ON s.userId = tm.userId
            JOIN season_team st ON tm.teamId = st.teamId AND st.seasonId = ?
            JOIN team t ON tm.teamId = t.id
            WHERE m.seasonId = ? AND m.status = 'COMPLETED' AND m.week IS NOT NULL
        """, (sid, sid))

    if df.empty:
        return pd.DataFrame()

    agg = df.groupby(["teamId", "teamName"]).agg(
        unique_champs=("championName", "nunique"),
        total_picks=("championName", "count"),
        champ_list=("championName", lambda x: ", ".join(sorted(x.unique()))),
    ).reset_index()
    agg.rename(columns={"teamName": "name"}, inplace=True)

    return agg.sort_values("unique_champs", ascending=False).reset_index(drop=True)


def load_early_game_stats(db_path: str, season_id) -> pd.DataFrame:
    """
    Early game stats per team: first blood rate, first tower rate, avg plates.
    Returns DataFrame: teamId, name, games, fb_wins, fb_rate, ft_wins, ft_rate, avg_plates
    """
    sid = str(season_id)
    with _conn(db_path) as conn:
        df = _df(conn, """
            SELECT ps.matchId, ps.firstBloodKill, ps.firstTowerKill,
                   ps.turretPlatesTaken, ps.win,
                   tm.teamId, t.name as teamName
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            JOIN summoner s ON ps.summonerId = s.id
            JOIN team_member tm ON s.userId = tm.userId
            JOIN season_team st ON tm.teamId = st.teamId AND st.seasonId = ?
            JOIN team t ON tm.teamId = t.id
            WHERE m.seasonId = ? AND m.status = 'COMPLETED' AND m.week IS NOT NULL
        """, (sid, sid))

    if df.empty:
        return pd.DataFrame()

    for col in ["firstBloodKill", "firstTowerKill", "turretPlatesTaken"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # First blood: any player on team got FB in that game
    fb = df.groupby(["teamId", "teamName", "matchId"]).agg(
        got_fb=("firstBloodKill", "max"),
        got_ft=("firstTowerKill", "max"),
        plates=("turretPlatesTaken", "sum"),
    ).reset_index()

    agg = fb.groupby(["teamId", "teamName"]).agg(
        games=("matchId", "nunique"),
        fb_wins=("got_fb", "sum"),
        ft_wins=("got_ft", "sum"),
        avg_plates=("plates", "mean"),
    ).reset_index()

    agg["fb_rate"] = (agg["fb_wins"] / agg["games"]).round(3)
    agg["ft_rate"] = (agg["ft_wins"] / agg["games"]).round(3)
    agg["avg_plates"] = agg["avg_plates"].round(1)
    agg.rename(columns={"teamName": "name"}, inplace=True)

    return agg.sort_values("fb_rate", ascending=False).reset_index(drop=True)


# ── Item stats ───────────────────────────────────────────────────────────────

# Riot item ID -> display name (from Data Dragon 14.24 + 15.3)
ITEM_NAMES = {
    1001: "Boots", 1004: "Faerie Charm", 1006: "Rejuvenation Bead",
    1011: "Giant's Belt", 1018: "Cloak of Agility", 1026: "Blasting Wand",
    1027: "Sapphire Crystal", 1028: "Ruby Crystal", 1029: "Cloth Armor",
    1031: "Chain Vest", 1033: "Null-Magic Mantle", 1036: "Long Sword",
    1037: "Pickaxe", 1038: "B. F. Sword", 1042: "Dagger",
    1043: "Recurve Bow", 1052: "Amplifying Tome", 1053: "Vampiric Scepter",
    1054: "Doran's Shield", 1055: "Doran's Blade", 1056: "Doran's Ring",
    1057: "Negatron Cloak", 1058: "Needlessly Large Rod", 1082: "Dark Seal",
    1083: "Cull", 1101: "Scorchclaw Pup",
    2003: "Health Potion", 2010: "Biscuit", 2019: "Steel Sigil",
    2021: "Tunneler", 2022: "Glowing Mote", 2031: "Refillable Potion",
    2055: "Control Ward", 2065: "Shurelya's Battlesong",
    2138: "Elixir of Iron", 2139: "Elixir of Sorcery", 2152: "Elixir of Force",
    2420: "Seeker's Armguard", 2421: "Shattered Armguard",
    2422: "Slightly Magical Footwear",
    2501: "Overlord's Bloodmail", 2502: "Unending Despair",
    2503: "Blackfire Torch", 2504: "Kaenic Rookern", 2508: "Fated Ashes",
    3002: "Trailblazer", 3006: "Berserker's Greaves",
    3009: "Boots of Swiftness", 3010: "Symbiotic Soles",
    3013: "Synchronized Souls", 3020: "Sorcerer's Shoes",
    3024: "Glacial Buckler", 3026: "Guardian Angel",
    3031: "Infinity Edge", 3032: "Yun Tal Wildarrows",
    3033: "Mortal Reminder", 3035: "Last Whisper",
    3036: "Lord Dominik's Regards", 3040: "Seraph's Embrace",
    3041: "Mejai's Soulstealer", 3042: "Muramana", 3044: "Phage",
    3046: "Phantom Dancer", 3047: "Plated Steelcaps",
    3050: "Zeke's Convergence", 3051: "Hearthbound Axe",
    3053: "Sterak's Gage", 3057: "Sheen", 3065: "Spirit Visage",
    3066: "Winged Moonplate", 3067: "Kindlegem",
    3068: "Sunfire Aegis", 3070: "Tear of the Goddess",
    3071: "Black Cleaver", 3072: "Bloodthirster",
    3073: "Experimental Hexplate", 3074: "Ravenous Hydra",
    3075: "Thornmail", 3076: "Bramble Vest", 3077: "Tiamat",
    3078: "Trinity Force", 3082: "Warden's Mail",
    3083: "Warmog's Armor", 3084: "Heartsteel",
    3085: "Runaan's Hurricane", 3086: "Zeal", 3087: "Statikk Shiv",
    3089: "Rabadon's Deathcap", 3091: "Wit's End",
    3094: "Rapid Firecannon", 3097: "Support Item",
    3100: "Lich Bane", 3102: "Banshee's Veil",
    3105: "Aegis of the Legion", 3107: "Redemption",
    3108: "Fiendish Codex", 3109: "Knight's Vow",
    3110: "Frozen Heart", 3111: "Mercury's Treads",
    3113: "Aether Wisp", 3114: "Forbidden Idol",
    3115: "Nashor's Tooth", 3116: "Rylai's Crystal Scepter",
    3118: "Malignance", 3121: "Fimbulwinter",
    3123: "Executioner's Calling", 3124: "Guinsoo's Rageblade",
    3133: "Caulfield's Warhammer", 3134: "Serrated Dirk",
    3135: "Void Staff", 3137: "Cryptbloom",
    3139: "Mercurial Scimitar", 3140: "Quicksilver Sash",
    3142: "Youmuu's Ghostblade", 3143: "Randuin's Omen",
    3144: "Scout's Slingshot", 3145: "Hextech Alternator",
    3146: "Hextech Gunblade", 3147: "Haunting Guise",
    3152: "Hextech Rocketbelt", 3153: "Blade of the Ruined King",
    3155: "Hexdrinker", 3156: "Maw of Malmortius",
    3157: "Zhonya's Hourglass", 3158: "Ionian Boots of Lucidity",
    3161: "Spear of Shojin", 3165: "Morellonomicon",
    3170: "Swiftmarch", 3171: "Crimson Lucidity",
    3172: "Zephyr", 3173: "Chainlaced Crushers",
    3174: "Armored Advance", 3175: "Spellslinger's Shoes",
    3176: "Forever Forward",
    3179: "Umbral Glaive", 3181: "Hullbreaker",
    3190: "Locket of the Iron Solari",
    3211: "Spectre's Cowl", 3222: "Mikael's Blessing",
    3302: "Terminus", 3330: "Scarecrow Effigy",
    3340: "Stealth Ward", 3363: "Farsight Alteration",
    3364: "Oracle Lens", 3504: "Ardent Censer",
    3508: "Essence Reaver", 3742: "Dead Man's Plate",
    3748: "Titanic Hydra", 3802: "Lost Chapter",
    3814: "Edge of Night", 3869: "Celestial Opposition",
    3870: "Dream Maker", 3871: "Zaz'Zak's Realmspike",
    3876: "Solstice Sleigh", 3877: "Bloodsong",
    3916: "Oblivion Orb", 4005: "Imperial Mandate",
    4401: "Force of Nature", 4628: "Horizon Focus",
    4629: "Cosmic Drive", 4630: "Blighting Jewel",
    4632: "Verdant Barrier", 4633: "Riftmaker",
    4638: "Watchful Wardstone", 4642: "Bandleglass Mirror",
    4643: "Vigilant Wardstone", 4645: "Shadowflame",
    4646: "Stormsurge", 6333: "Death's Dance",
    6609: "Chempunk Chainsword", 6610: "Sundered Sky",
    6616: "Staff of Flowing Water", 6617: "Moonstone Renewer",
    6620: "Echoes of Helia", 6621: "Dawncore",
    6631: "Stridebreaker", 6653: "Liandry's Torment",
    6655: "Luden's Companion", 6657: "Rod of Ages",
    6660: "Bami's Cinder", 6662: "Iceborn Gauntlet",
    6664: "Hollow Radiance", 6665: "Jak'Sho, The Protean",
    6670: "Noonquiver", 6672: "Kraken Slayer",
    6673: "Immortal Shieldbow", 6675: "Navori Flickerblade",
    6676: "The Collector", 6690: "Rectrix",
    6692: "Eclipse", 6694: "Serylda's Grudge",
    6695: "Serpent's Fang", 6696: "Axiom Arc",
    6697: "Hubris", 6698: "Profane Hydra",
    6699: "Voltaic Cyclosword", 6701: "Opportunity",
    8010: "Bloodletter's Curse", 8020: "Abyssal Mask",
}

# Items to exclude from "completed item" stats (components, consumables, trinkets, boots)
_COMPONENT_IDS = {
    # Components
    1001, 1004, 1006, 1011, 1018, 1026, 1027, 1028, 1029, 1031, 1033,
    1036, 1037, 1038, 1042, 1043, 1052, 1053, 1057, 1058, 1082, 1083,
    1101, 2003, 2010, 2019, 2021, 2022, 2031, 2055, 2138, 2139, 2152,
    2420, 2421, 2422, 2508, 3024, 3035, 3044, 3051, 3057, 3066, 3067,
    3070, 3076, 3077, 3082, 3086, 3097, 3105, 3108, 3113, 3114, 3123,
    3133, 3134, 3140, 3144, 3145, 3147, 3155, 3211, 3330, 3340, 3363,
    3364, 3802, 3916, 4630, 4632, 4638, 4642, 6660, 6670, 6690,
    # Starters (Doran's items, Cull)
    1054, 1055, 1056,
    # Boots (completed)
    3006, 3009, 3010, 3013, 3020, 3047, 3111, 3158,
    3170, 3171, 3173, 3174, 3175, 3176,
}

# Sunfire item IDs (Sunfire Cape / Sunfire Aegis across patches)
SUNFIRE_IDS = {3068}


def _item_name(item_id: int) -> str:
    return ITEM_NAMES.get(item_id, f"Item {item_id}")


def load_item_stats(db_path: str, season_id: str) -> pd.DataFrame:
    """
    Compute per-completed-item win rate across a season.
    Returns DataFrame: item_id, item_name, games, wins, win_rate
    Excludes components, consumables, and trinkets.
    """
    with _conn(db_path) as conn:
        ps = _df(conn, """
            SELECT ps.item0, ps.item1, ps.item2, ps.item3,
                   ps.item4, ps.item5, ps.win
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            JOIN series s ON m.seriesId = s.id
            WHERE s.seasonId = ? AND s.week IS NOT NULL
              AND m.status = 'COMPLETED'
        """, (str(season_id),))

    if ps.empty:
        return pd.DataFrame(columns=["item_id", "item_name", "games", "wins", "win_rate"])

    # Unpivot item columns (exclude item6 = trinket slot)
    rows = []
    for _, r in ps.iterrows():
        win = int(r["win"])
        for slot in range(6):
            iid = int(r[f"item{slot}"] or 0)
            if iid > 0 and iid not in _COMPONENT_IDS:
                rows.append({"item_id": iid, "win": win})

    if not rows:
        return pd.DataFrame(columns=["item_id", "item_name", "games", "wins", "win_rate"])

    df = pd.DataFrame(rows)
    agg = df.groupby("item_id").agg(
        games=("win", "count"),
        wins=("win", "sum"),
    ).reset_index()
    agg["win_rate"] = (agg["wins"] / agg["games"]).round(3)
    agg["item_name"] = agg["item_id"].map(_item_name)
    agg = agg.sort_values("games", ascending=False).reset_index(drop=True)
    return agg


def load_sunfire_stats(db_path: str, season_id: str) -> dict:
    """
    Compute Sunfire Cape/Aegis stats for a season.
    Returns dict: total_builds, wins, losses, win_rate, builders (list of player names + champs)
    """
    sunfire_ids_str = ",".join(str(i) for i in SUNFIRE_IDS)

    with _conn(db_path) as conn:
        ps = _df(conn, f"""
            SELECT ps.item0, ps.item1, ps.item2, ps.item3,
                   ps.item4, ps.item5, ps.win, ps.championName,
                   COALESCE(su.riotIdGameName, u.username, 'Unknown') as playerName
            FROM player_stats ps
            JOIN match m ON ps.matchId = m.id
            JOIN series s ON m.seriesId = s.id
            LEFT JOIN summoner su ON ps.summonerId = su.id
            LEFT JOIN user u ON su.userId = u.id
            WHERE s.seasonId = ? AND s.week IS NOT NULL
              AND m.status = 'COMPLETED'
              AND (ps.item0 IN ({sunfire_ids_str})
                OR ps.item1 IN ({sunfire_ids_str})
                OR ps.item2 IN ({sunfire_ids_str})
                OR ps.item3 IN ({sunfire_ids_str})
                OR ps.item4 IN ({sunfire_ids_str})
                OR ps.item5 IN ({sunfire_ids_str}))
        """, (str(season_id),))

    total = len(ps)
    wins = int(ps["win"].sum()) if total > 0 else 0
    losses = total - wins
    wr = wins / total if total > 0 else 0

    builders = []
    if not ps.empty:
        for _, r in ps.iterrows():
            builders.append({
                "player": r["playerName"],
                "champion": r["championName"],
                "win": bool(r["win"]),
            })

    return {
        "total_builds": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "builders": builders,
    }


# ── Rank data ────────────────────────────────────────────────────────────

# Tier ordering (highest → lowest)
_TIER_ORDER = {
    "CHALLENGER": 0, "GRANDMASTER": 1, "MASTER": 2,
    "DIAMOND": 3, "EMERALD": 4, "PLATINUM": 5,
    "GOLD": 6, "SILVER": 7, "BRONZE": 8, "IRON": 9,
}


def load_peak_ranks(db_path: str) -> dict:
    """
    Load each player's peak solo queue rank from historical_rank.
    Returns dict: {username: {'tier': 'DIAMOND', 'division': '2', 'label': 'Diamond II'}}
    Peak = highest tier, then lowest division number within that tier.
    """
    with _conn(db_path) as conn:
        rows = conn.execute("""
            SELECT u.username, hr.tier, hr.division
            FROM historical_rank hr
            JOIN summoner s ON hr.summonerId = s.id
            JOIN user u ON s.userId = u.id
            WHERE hr.queueType = 'SOLO_DUO' AND hr.tier IS NOT NULL
        """).fetchall()

    if not rows:
        return {}

    # Find peak per player
    best = {}  # username → (tier_order, division, tier_str)
    for username, tier, division in rows:
        order = _TIER_ORDER.get(tier, 99)
        div = int(division) if division else 0
        key = (order, div)  # lower = better
        if username not in best or key < best[username]:
            best[username] = key

    result = {}
    division_roman = {"1": "I", "2": "II", "3": "III", "4": "IV"}
    for username, (order, div) in best.items():
        tier = [t for t, o in _TIER_ORDER.items() if o == order][0]
        tier_display = tier.capitalize()
        div_display = division_roman.get(str(div), "") if div else ""
        label = f"{tier_display} {div_display}".strip()
        result[username] = {"tier": tier, "division": str(div) if div else "", "label": label}

    return result

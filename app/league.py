"""
Beer League Stats — season bundle + website-faithful standings.

One place that loads a season out of the website's SQLite export and derives
everything the dashboard needs, using the SAME rules the league website uses
(BLWebsiteFAST `utils/seasons.py`, `utils/predictions.py`, `utils/stats_math.py`):

  * Standings = regular-season series only. Out-of-group (isOog) exhibition
    series, playoff series and unresolved seed-slot placeholders never count.
  * Dropped teams: "void" drops erase every series against them; "forfeit"
    drops hand every opponent a series win (played or not) with no games.
  * Tiebreakers: series wins → game wins → head-to-head series wins inside
    the tied group → team name (deterministic last resort only).
  * Grouped seasons with two groups seed playoffs cross-group: each group
    sends its top N/2, interleaved (A1, B1, A2, B2 …); the group whose winner
    has the better overall record takes the odd seeds.
  * KDA is always (ΣK + ΣA) / ΣD on totals — never a mean of per-game ratios.
  * A player's league team in a game is derived from the result itself
    (win flag ↔ match.winnerId), not from current team membership, so subs
    and players rostered in both leagues are attributed correctly.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
ROLE_SHORT = {"TOP": "TOP", "JUNGLE": "JGL", "MIDDLE": "MID",
              "BOTTOM": "ADC", "SUPPORT": "SUP"}

# Riot's internal champion keys → the names people actually say.
CHAMP_DISPLAY = {
    "MonkeyKing": "Wukong", "FiddleSticks": "Fiddlesticks", "Fiddlesticks": "Fiddlesticks",
    "AurelionSol": "Aurelion Sol", "JarvanIV": "Jarvan IV", "KSante": "K'Sante",
    "Kaisa": "Kai'Sa", "KhaZix": "Kha'Zix", "Khazix": "Kha'Zix", "KogMaw": "Kog'Maw",
    "LeeSin": "Lee Sin", "MasterYi": "Master Yi", "MissFortune": "Miss Fortune",
    "DrMundo": "Dr. Mundo", "RekSai": "Rek'Sai", "TahmKench": "Tahm Kench",
    "TwistedFate": "Twisted Fate", "XinZhao": "Xin Zhao", "Velkoz": "Vel'Koz",
    "Chogath": "Cho'Gath", "Belveth": "Bel'Veth", "Leblanc": "LeBlanc",
    "Nunu": "Nunu & Willump", "RenataGlasc": "Renata Glasc", "Renata": "Renata Glasc",
}


def champ_name(key) -> str:
    return CHAMP_DISPLAY.get(str(key), str(key))


def champ_key(name) -> str:
    """Normalise the one key that differs between the draft tool and stats."""
    return "FiddleSticks" if str(name) == "Fiddlesticks" else str(name)


# ── DB helpers ───────────────────────────────────────────────────────────────

def latest_db() -> Path | None:
    dbs = sorted(DATA_DIR.glob("*.db"), reverse=True)
    return dbs[0] if dbs else None


def _q(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def _cols(conn, table) -> set:
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}


def _sid(v):
    """IDs are VARCHAR-ish everywhere; normalise to str, keep missing as None."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v)
    return s[:-2] if s.endswith(".0") else s


def band_of(row) -> str:
    b = (row.get("band") or "").upper()
    if b in ("LITE", "STOUT"):
        return b
    return "LITE" if "lite" in str(row.get("name", "")).lower() else "STOUT"


def load_seasons(db: str) -> pd.DataFrame:
    """Seasons that have at least one completed game, newest first."""
    with sqlite3.connect(db) as conn:
        df = _q(conn, """
            SELECT s.*, (SELECT COUNT(*) FROM match m
                         WHERE m.seasonId = s.id AND m.status = 'COMPLETED') AS n_games
            FROM season s WHERE s.id != 3
        """)
    df["id"] = df["id"].map(_sid)
    df["band"] = df.apply(band_of, axis=1)
    df = df[(df["n_games"] > 0) | (df["status"] == "ACTIVE")]
    return df.sort_values("id", key=lambda s: s.astype(int), ascending=False).reset_index(drop=True)


def data_through(db: str) -> str:
    """Timestamp of the newest ingested game — the honest 'data through' date."""
    with sqlite3.connect(db) as conn:
        v = conn.execute("SELECT MAX(createdAt) FROM player_stats").fetchone()[0]
    try:
        return pd.Timestamp(v).strftime("%b %d, %Y").replace(" 0", " ")
    except Exception:
        return "unknown"


# ── Series score maths ───────────────────────────────────────────────────────

def need_wins(fmt: str) -> int:
    return {"BEST_OF_1": 1, "BEST_OF_2": 1, "BEST_OF_3": 2, "BEST_OF_5": 3}.get(
        str(fmt or "").upper(), 2)


def score_distribution(p: float, fmt: str) -> list:
    """[(team1_games, team2_games, probability)] for a series of this format
    given team 1's per-game win probability p (independent games)."""
    f = str(fmt or "").upper()
    q = 1.0 - p
    if f == "BEST_OF_1":
        return [(1, 0, p), (0, 1, q)]
    if f == "BEST_OF_2":
        return [(2, 0, p * p), (1, 1, 2 * p * q), (0, 2, q * q)]
    if f == "BEST_OF_5":
        return [(3, 0, p ** 3), (3, 1, 3 * p ** 3 * q), (3, 2, 6 * p ** 3 * q * q),
                (2, 3, 6 * q ** 3 * p * p), (1, 3, 3 * q ** 3 * p), (0, 3, q ** 3)]
    return [(2, 0, p * p), (2, 1, 2 * p * p * q), (1, 2, 2 * q * q * p), (0, 2, q * q)]


# ── Standings (port of the website's build_standings) ───────────────────────

def order_teams(ids, sw, gw, h2h_pairs, names) -> list:
    """Order team ids by series wins, game wins, then head-to-head series wins
    inside each still-tied run, then name.

    h2h_pairs: dict (winner_id, loser_id) -> series wins.
    Returns [(team_id, h2h_wins_in_tie, tied_flag)].
    """
    base = sorted(ids, key=lambda t: (-sw[t], -gw[t], names.get(t, "").lower()))
    out, i = [], 0
    while i < len(base):
        j = i + 1
        while j < len(base) and sw[base[j]] == sw[base[i]] and gw[base[j]] == gw[base[i]]:
            j += 1
        run = base[i:j]
        if len(run) > 1:
            inner = {t: sum(h2h_pairs.get((t, o), 0) for o in run if o != t) for t in run}
            run = sorted(run, key=lambda t: (-inner[t], names.get(t, "").lower()))
            vals = [inner[t] for t in run]
            for k, t in enumerate(run):
                unbroken = vals.count(vals[k]) > 1
                out.append((t, inner[t], unbroken))
        else:
            out.append((run[0], 0, False))
        i = j
    return out


class Season:
    """Everything about one season, loaded once and cached by the app."""

    def __init__(self, db: str, season_id):
        self.db = str(db)
        self.id = _sid(season_id)
        with sqlite3.connect(self.db) as conn:
            self._load(conn)
        self._derive()

    # ── loading ──────────────────────────────────────────────────────────
    def _load(self, conn):
        sid = self.id
        meta = _q(conn, "SELECT * FROM season WHERE id = ?", (sid,)).iloc[0].to_dict()
        self.meta = meta
        self.name = meta["name"]
        self.band = band_of(meta)
        self.status = meta.get("status")
        self.active = self.status == "ACTIVE"
        self.cap = meta.get("salaryCap")
        self.grouped = bool(meta.get("grouped"))
        try:
            self.playoff_spots = int(meta.get("playoff_teams") or 8)
        except (TypeError, ValueError):
            self.playoff_spots = 8
        self.fearless = (meta.get("draftMode") or "") == "fearless"
        own = [ln.strip() for ln in str(meta.get("tiebreakerRules") or "").replace(",", "\n").splitlines()
               if ln.strip()]
        self.tiebreaker_text = own or ["Series wins", "Game wins",
                                       "Head-to-head (series won between the tied teams)"]

        st_cols = _cols(conn, "season_team")
        extra = "".join(f", st.{c}" for c in ("groupName", "dropped", "dropMode",
                                               "playerSalaries", "startingLineup", "approved")
                        if c in st_cols)
        teams = _q(conn, f"""
            SELECT st.teamId, t.name, t.tag, t.color, st.salaryTotal {extra}
            FROM season_team st JOIN team t ON t.id = st.teamId
            WHERE st.seasonId = ?
        """, (sid,))
        teams["teamId"] = teams["teamId"].map(_sid)
        for c, d in (("groupName", None), ("dropped", 0), ("dropMode", "void"),
                     ("playerSalaries", None), ("startingLineup", None), ("approved", 1)):
            if c not in teams.columns:
                teams[c] = d
        teams["dropped"] = teams["dropped"].fillna(0).astype(int).astype(bool)
        if "approved" in teams.columns:
            teams = teams[teams["approved"].fillna(1).astype(int) == 1]
        teams["salaryTotal"] = pd.to_numeric(teams["salaryTotal"], errors="coerce")
        self.teams = teams.sort_values("name").reset_index(drop=True)

        s_cols = _cols(conn, "series")
        opt = "".join(f", s.{c}" for c in ("isOog", "seriesType", "label", "playoffRound",
                                            "resultReason", "scheduledAt") if c in s_cols)
        series = _q(conn, f"""
            SELECT s.id AS seriesId, s.week, s.status, s.format,
                   s.team1Id, s.team2Id, s.winnerId {opt}
            FROM series s WHERE s.seasonId = ? ORDER BY s.week, s.id
        """, (sid,))
        for c in ("seriesId", "team1Id", "team2Id", "winnerId"):
            series[c] = series[c].map(_sid)
        for c, d in (("isOog", 0), ("seriesType", "REGULAR_SEASON"), ("label", None),
                     ("resultReason", None)):
            if c not in series.columns:
                series[c] = d
        series["isOog"] = series["isOog"].fillna(0).astype(int).astype(bool)
        series["seriesType"] = series["seriesType"].fillna("REGULAR_SEASON")
        self._series_raw = series

        games = _q(conn, """
            SELECT id AS matchId, seriesId, week, gameNumber, team1Id, team2Id, winnerId, createdAt
            FROM match WHERE seasonId = ? AND status = 'COMPLETED' AND winnerId IS NOT NULL
            ORDER BY id
        """, (sid,))
        for c in ("matchId", "seriesId", "team1Id", "team2Id", "winnerId"):
            games[c] = games[c].map(_sid)
        self._games_raw = games

        ps = _q(conn, """
            SELECT ps.*, s.userId, s.riotIdGameName, s.riotIdTagline, u.username, u.salary AS currentSalary
            FROM player_stats ps
            JOIN match m ON m.id = ps.matchId
            LEFT JOIN summoner s ON s.id = ps.summonerId
            LEFT JOIN user u ON u.id = s.userId
            WHERE m.seasonId = ? AND m.status = 'COMPLETED'
        """, (sid,))
        ps["matchId"] = ps["matchId"].map(_sid)
        ps["userId"] = ps["userId"].map(_sid)
        self._ps_raw = ps

        ts = _q(conn, """
            SELECT ts.matchId, ts.teamId, ts.kills, ts.turrets, ts.dragons, ts.barons,
                   ts.heralds, ts.inhibitors
            FROM team_stats ts JOIN match m ON m.id = ts.matchId
            WHERE m.seasonId = ? AND m.status = 'COMPLETED'
        """, (sid,))
        ts["matchId"] = ts["matchId"].map(_sid)
        ts["teamId"] = ts["teamId"].map(_sid)
        self.team_stats = ts

        ban_cols = [f"team{t}Ban{b}" for t in (1, 2) for b in range(1, 6)]
        self._bans_raw = _q(conn, f"""
            SELECT id AS matchId, {", ".join(ban_cols)} FROM match
            WHERE seasonId = ? AND status = 'COMPLETED'
        """, (sid,))

        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {"draft_session", "draft_action"} <= tables:
            ds_cols = _cols(conn, "draft_session")
            void_sql = "AND ds.voidedAt IS NULL" if "voidedAt" in ds_cols else ""
            self._draft_raw = _q(conn, f"""
                SELECT da.sessionId, da.actionIndex, da.actionType, da.team, da.championId,
                       da.championName, ds.matchId, ds.blueTeamId, ds.redTeamId
                FROM draft_action da
                JOIN draft_session ds ON ds.id = da.sessionId
                JOIN match m ON m.id = ds.matchId
                WHERE m.seasonId = ? AND m.status = 'COMPLETED' AND ds.phase = 'COMPLETE' {void_sql}
                ORDER BY da.sessionId, da.actionIndex
            """, (sid,))
            self.champ_ids = dict(conn.execute(
                "SELECT DISTINCT championId, championName FROM draft_action").fetchall())
        else:
            self._draft_raw = pd.DataFrame()
            self.champ_ids = {}

        if "series_prediction" in tables:
            preds = _q(conn, """
                SELECT sp.seriesId, sp.userId, sp.predictedWinnerId, sp.predictedScore, u.username
                FROM series_prediction sp
                JOIN series s ON s.id = sp.seriesId
                LEFT JOIN user u ON u.id = sp.userId
                WHERE s.seasonId = ?
            """, (sid,))
            for c in ("seriesId", "userId", "predictedWinnerId"):
                preds[c] = preds[c].map(_sid)
            self.predictions = preds
        else:
            self.predictions = pd.DataFrame()

    # ── derivation ───────────────────────────────────────────────────────
    def _derive(self):
        t = self.teams
        self.names = dict(zip(t["teamId"], t["name"]))
        self.tags = dict(zip(t["teamId"], t["tag"].fillna("")))
        self.groups = {tid: g for tid, g in zip(t["teamId"], t["groupName"]) if g}
        self.dropped = set(t.loc[t["dropped"], "teamId"])
        self.forfeit = set(t.loc[t["dropped"] & (t["dropMode"] == "forfeit"), "teamId"])
        self.live_ids = [tid for tid in t["teamId"] if tid not in self.dropped]
        self.salary = dict(zip(t["teamId"], t["salaryTotal"].fillna(0)))

        # season-snapshot player salaries (what the cap was actually checked against)
        snap = {}
        for raw in t["playerSalaries"].dropna():
            try:
                snap.update({str(k): float(v) for k, v in json.loads(raw).items()})
            except (ValueError, TypeError):
                continue
        self.player_salary = snap

        # games + per-series game wins
        g = self._games_raw.copy()
        g["loserId"] = np.where(g["winnerId"] == g["team1Id"], g["team2Id"], g["team1Id"])
        wins = g.groupby(["seriesId", "winnerId"]).size().to_dict()

        s = self._series_raw.copy()
        s["t1w"] = [wins.get((sid, t1), 0) for sid, t1 in zip(s["seriesId"], s["team1Id"])]
        s["t2w"] = [wins.get((sid, t2), 0) for sid, t2 in zip(s["seriesId"], s["team2Id"])]
        # one-off forfeit (admin override) reads as the full sweep, as on the site
        ff = (s["resultReason"] == "forfeit") & s["winnerId"].notna()
        for idx in s.index[ff]:
            need = need_wins(s.at[idx, "format"])
            if s.at[idx, "winnerId"] == s.at[idx, "team1Id"]:
                s.at[idx, "t1w"] = max(s.at[idx, "t1w"], need)
            else:
                s.at[idx, "t2w"] = max(s.at[idx, "t2w"], need)
        s["team1Name"] = s["team1Id"].map(self.names)
        s["team2Name"] = s["team2Id"].map(self.names)
        s["winnerName"] = s["winnerId"].map(self.names)
        s["playoff"] = s["seriesType"].astype(str).str.upper().eq("PLAYOFF")
        s["placeholder"] = s["team1Id"].isna() | s["team2Id"].isna()
        s["has_dropped"] = s["team1Id"].isin(self.dropped) | s["team2Id"].isin(self.dropped)
        self.series = s
        reg = s[~s["playoff"] & ~s["placeholder"] & s["week"].notna()].copy()
        reg["week"] = reg["week"].astype(int)
        self.regular = reg
        self.playoffs = s[s["playoff"] & ~s["placeholder"]].copy()

        # weeks: playoff games get a pseudo-week after the regular season so the
        # ladder and trend charts stay chronological
        max_reg = int(reg["week"].max()) if not reg.empty else 0
        s_week = dict(zip(reg["seriesId"], reg["week"]))
        po_ids = set(self.playoffs["seriesId"])
        g["playoff"] = g["seriesId"].isin(po_ids)
        g["week"] = [s_week.get(sid, (max_reg + 1) if sid in po_ids else np.nan)
                     for sid in g["seriesId"]]
        g = g[g["week"].notna()].copy()
        g["week"] = g["week"].astype(int)
        self.max_regular_week = max_reg
        self.weeks = sorted(g.loc[~g["playoff"], "week"].unique().tolist())

        # player rows
        ps = self._ps_raw.copy()
        skip = {"championName", "position", "lanePosition", "createdAt", "updatedAt",
                "riotIdGameName", "riotIdTagline", "username", "matchId", "userId"}
        for c in ps.columns:
            if c not in skip and ps[c].dtype == object:
                ps[c] = pd.to_numeric(ps[c], errors="coerce")
        ps = ps.merge(g[["matchId", "week", "playoff", "seriesId", "gameNumber",
                         "winnerId", "loserId"]], on="matchId", how="inner")
        ps["win"] = ps["win"].fillna(0).astype(int)
        ps["leagueTeamId"] = np.where(ps["win"] == 1, ps["winnerId"], ps["loserId"])
        ps["oppTeamId"] = np.where(ps["win"] == 1, ps["loserId"], ps["winnerId"])
        ps["team"] = ps["leagueTeamId"].map(self.names).fillna("?")
        ps["opp"] = ps["oppTeamId"].map(self.names).fillna("?")
        ps["side"] = ps["teamId"].map({100: "Blue", 200: "Red"})
        role = ps["position"].where(ps["position"].isin(ROLES))
        if "lanePosition" in ps.columns:
            role = role.fillna(ps["lanePosition"].where(ps["lanePosition"].isin(ROLES)))
        ps["role"] = role
        ps["player"] = ps["riotIdGameName"].fillna(ps["username"]).fillna("Unknown")
        ps["pid"] = ps["userId"].fillna(ps["summonerId"].astype(str))
        ps["salary"] = ps["userId"].map(self.player_salary)
        ps["salary"] = ps["salary"].fillna(pd.to_numeric(ps["currentSalary"], errors="coerce"))
        ps["mins"] = (ps["gameDuration"].fillna(0) / 60).clip(lower=1)
        ps["champion"] = ps["championName"].map(champ_name)
        ps["cc_s"] = ps["totalTimeCCDealt"].fillna(0)   # Riot reports seconds here
        # laning diffs vs. the direct lane opponent at 15:00
        if "gold15" in ps.columns:
            lane = ps["lanePosition"] if "lanePosition" in ps.columns else ps["role"]
            ps["_lane"] = lane.where(lane.isin(ROLES)).fillna(ps["role"])
            opp = ps[["matchId", "_lane", "teamId", "gold15", "cs15", "xp15"]].copy()
            opp["teamId"] = opp["teamId"].map({100: 200, 200: 100})
            opp = opp.dropna(subset=["_lane", "gold15"]).drop_duplicates(["matchId", "_lane", "teamId"])
            opp = opp.rename(columns={"gold15": "_og", "cs15": "_oc", "xp15": "_ox"})
            ps = ps.merge(opp, on=["matchId", "_lane", "teamId"], how="left")
            ps["gd15"] = ps["gold15"] - ps["_og"]
            ps["csd15"] = ps["cs15"] - ps["_oc"]
            ps["xpd15"] = ps["xp15"] - ps["_ox"]
            ps = ps.drop(columns=["_og", "_oc", "_ox", "_lane"])
        else:
            ps["gd15"] = ps["csd15"] = ps["xpd15"] = np.nan
        self.ps = ps

        # per-game facts: duration, blue side team, kills
        dur = ps.groupby("matchId")["gameDuration"].max()
        g["duration"] = g["matchId"].map(dur)
        blue_won = ps[ps["win"] == 1].groupby("matchId")["teamId"].first().eq(100)
        g["blueWon"] = g["matchId"].map(blue_won)
        bw = g["blueWon"].map({True: 1.0, False: 0.0})
        g["blueTeamId"] = np.where(bw == 1.0, g["winnerId"], g["loserId"])
        g.loc[bw.isna(), "blueTeamId"] = None
        g["has_stats"] = g["matchId"].isin(set(ps["matchId"]))
        g["team1Name"] = g["team1Id"].map(self.names)
        g["team2Name"] = g["team2Id"].map(self.names)
        g["winnerName"] = g["winnerId"].map(self.names)
        g["loserName"] = g["loserId"].map(self.names)
        self.games = g.sort_values(["week", "seriesId", "gameNumber"]).reset_index(drop=True)

    # ── standings ────────────────────────────────────────────────────────
    def _tally(self, series_df, ids):
        """Series/game W-L + head-to-head pairs over the given regular series."""
        ids = set(ids)
        sw = {t: 0 for t in ids}; sl = dict(sw); gw = dict(sw); gl = dict(sw)
        h2h, results = {}, {t: [] for t in ids}
        for r in series_df.itertuples(index=False):
            if r.isOog or r.playoff or r.placeholder:
                continue
            t1, t2 = r.team1Id, r.team2Id
            d1, d2 = t1 in self.dropped, t2 in self.dropped
            if d1 or d2:
                if d1 and d2:
                    continue
                dead, live = (t1, t2) if d1 else (t2, t1)
                if dead not in self.forfeit:
                    continue                      # void drop: series never happened
                if live in ids:                   # forfeit: series W for the live side, no games
                    sw[live] += 1
                    results[live].append((r.week, "W"))
                if dead in ids:
                    sl[dead] += 1
                h2h[(live, dead)] = h2h.get((live, dead), 0) + 1
                continue
            if t1 not in ids or t2 not in ids:
                continue
            if r.status != "COMPLETED" and not r.winnerId:
                continue
            gw[t1] += r.t1w; gl[t1] += r.t2w
            gw[t2] += r.t2w; gl[t2] += r.t1w
            if r.winnerId in (t1, t2):
                w, l = (t1, t2) if r.winnerId == t1 else (t2, t1)
                sw[w] += 1; sl[l] += 1
                h2h[(w, l)] = h2h.get((w, l), 0) + 1
                results[w].append((r.week, "W")); results[l].append((r.week, "L"))
        return sw, sl, gw, gl, h2h, results

    def standings(self, through_week: int | None = None, group: str | None = None) -> pd.DataFrame:
        """The website's standings table. Dropped teams sort last (zeroed)."""
        reg = self.regular
        if through_week is not None:
            reg = reg[reg["week"] <= through_week]
        ids = [t for t in self.teams["teamId"]
               if group is None or self.groups.get(t) == group]
        if group is not None:
            members = set(ids)
            reg = reg[reg["team1Id"].isin(members) & reg["team2Id"].isin(members)]
        sw, sl, gw, gl, h2h, results = self._tally(reg, ids)
        live = [t for t in ids if t not in self.dropped]
        ordered = order_teams(live, sw, gw, h2h, self.names)
        rows = []
        for rank, (tid, h, tied) in enumerate(ordered, start=1):
            res = [x for _, x in sorted(results[tid], key=lambda z: z[0])]
            streak = ""
            if res:
                n = 1
                while n < len(res) and res[-n - 1] == res[-1]:
                    n += 1
                streak = f"{res[-1]}{n}"
            rows.append({
                "rank": rank, "team_id": tid, "team": self.names.get(tid, tid),
                "group": self.groups.get(tid), "series_w": sw[tid], "series_l": sl[tid],
                "game_w": gw[tid], "game_l": gl[tid], "h2h_w": h, "tied": tied,
                "form": "".join(res[-5:]), "streak": streak, "dropped": False,
            })
        for tid in sorted((t for t in ids if t in self.dropped), key=lambda t: self.names.get(t, "")):
            rows.append({
                "rank": None, "team_id": tid, "team": self.names.get(tid, tid),
                "group": self.groups.get(tid), "series_w": 0, "series_l": 0,
                "game_w": 0, "game_l": 0, "h2h_w": 0, "tied": False,
                "form": "", "streak": "", "dropped": True,
            })
        return pd.DataFrame(rows)

    @property
    def group_labels(self) -> list:
        return sorted(set(self.groups.values()))

    @property
    def cross_group(self) -> bool:
        """True when playoffs are seeded cross-group (two groups, even field)."""
        return self.grouped and len(self.group_labels) == 2 and self.playoff_spots % 2 == 0

    def seed_order(self, through_week: int | None = None):
        """[(seed, team_id, label)] for the playoff field as it stands today."""
        if self.cross_group:
            per = self.playoff_spots // 2
            ga, gb = self.group_labels
            ra = self.standings(through_week, ga); ra = ra[~ra["dropped"]]["team_id"].tolist()
            rb = self.standings(through_week, gb); rb = rb[~rb["dropped"]]["team_id"].tolist()
            overall = self.standings(through_week)["team_id"].tolist()
            first, second, la, lb = ra, rb, ga, gb
            if ra and rb and overall.index(rb[0]) < overall.index(ra[0]):
                first, second, la, lb = rb, ra, gb, ga
            out = []
            for k in range(per):
                if k < len(first):
                    out.append((2 * k + 1, first[k], f"{la}{k + 1}"))
                if k < len(second):
                    out.append((2 * k + 2, second[k], f"{lb}{k + 1}"))
            return out
        st = self.standings(through_week)
        st = st[~st["dropped"]].head(self.playoff_spots)
        return [(i + 1, tid, f"#{i + 1}") for i, tid in enumerate(st["team_id"])]

    def remaining_series(self) -> pd.DataFrame:
        """Regular-season series still to be played that count for standings."""
        r = self.regular
        return r[(r["status"] == "SCHEDULED") & ~r["isOog"] & ~r["has_dropped"]].copy()

    def upcoming_series(self) -> pd.DataFrame:
        """Everything still on the schedule (incl. out-of-group exhibitions)."""
        r = self.regular
        return r[(r["status"] == "SCHEDULED") & ~r["has_dropped"]].copy()

    def strength_of_schedule(self) -> dict:
        """Mean series-win% of opponents faced so far (counted series only)."""
        st = self.standings()
        pct = {r.team_id: (r.series_w / (r.series_w + r.series_l)) if (r.series_w + r.series_l) else 0.5
               for r in st.itertuples()}
        opps = {t: [] for t in self.live_ids}
        reg = self.regular
        done = reg[(reg["status"] == "COMPLETED") & ~reg["isOog"] & ~reg["has_dropped"]]
        for r in done.itertuples(index=False):
            if r.team1Id in opps and r.team2Id in opps:
                opps[r.team1Id].append(pct[r.team2Id]); opps[r.team2Id].append(pct[r.team1Id])
        return {t: (float(np.mean(v)) if v else np.nan) for t, v in opps.items()}

    # ── ratings input ────────────────────────────────────────────────────
    def rating_games(self) -> pd.DataFrame:
        """Every played game in order — the evidence the Glicko ladder uses
        (out-of-group and vs-dropped-team games were still real games)."""
        g = self.games
        return g[["matchId", "seriesId", "week", "gameNumber",
                  "team1Id", "team2Id", "winnerId"]].rename(columns={"matchId": "id"})

    # ── draft ────────────────────────────────────────────────────────────
    def draft_actions(self) -> pd.DataFrame:
        """Pick/ban log from the site's draft tool, one row per action, with
        pick_no (1-10) / ban_no (1-10) and the acting league team."""
        d = self._draft_raw
        if d.empty:
            return d
        d = d.copy()
        d["matchId"] = d["matchId"].map(_sid)
        d = d[d["matchId"].isin(set(self.games["matchId"]))]
        d["championKey"] = d["championName"].map(champ_key)
        d["champion"] = d["championKey"].map(champ_name)
        d["teamId"] = np.where(d["team"] == "blue", d["blueTeamId"], d["redTeamId"])
        d["teamId"] = d["teamId"].map(_sid)
        d = d[d["championKey"].astype(str).str.len().gt(0) & ~d["championKey"].isin(["None", "nan"])]
        d["pick_no"] = d[d["actionType"] == "PICK"].groupby("sessionId").cumcount() + 1
        d["ban_no"] = d[d["actionType"] == "BAN"].groupby("sessionId").cumcount() + 1
        return d

    def ban_table(self) -> pd.DataFrame:
        """Bans per champion. Prefers the draft tool log; falls back to the
        match ban columns (champion ids) for seasons drafted in-client."""
        d = self.draft_actions()
        if not d.empty:
            b = d[(d["actionType"] == "BAN") & d["championKey"].astype(str).str.len().gt(0)
                  & d["championId"].fillna(0).gt(0)]
            n = d["sessionId"].nunique()
            out = b.groupby("championKey").size().rename("bans").reset_index()
            out["drafts"] = n
            return out
        raw = self._bans_raw.dropna(subset=["team1Ban1"])
        if raw.empty or not self.champ_ids:
            return pd.DataFrame(columns=["championKey", "bans", "drafts"])
        vals = raw.drop(columns=["matchId"]).to_numpy().ravel()
        keys = [champ_key(self.champ_ids.get(int(v))) for v in vals
                if pd.notna(v) and int(v) in self.champ_ids]
        out = pd.Series(keys).value_counts().rename_axis("championKey").rename("bans").reset_index()
        out["drafts"] = len(raw)
        return out

    # ── crystal ball ─────────────────────────────────────────────────────
    def crowd_picks(self) -> pd.DataFrame:
        """Community pick split per series (dropped-team series are off the
        board, as on the site). Columns: seriesId, n, t1_share."""
        p = self.predictions
        if p.empty:
            return pd.DataFrame(columns=["seriesId", "n", "t1_share"])
        s = self.series.set_index("seriesId")
        p = p[p["seriesId"].isin(s.index[~s["has_dropped"]])]
        t1 = p["seriesId"].map(s["team1Id"])
        p = p.assign(is_t1=(p["predictedWinnerId"] == t1).astype(int))
        out = p.groupby("seriesId").agg(n=("is_t1", "size"), t1_share=("is_t1", "mean")).reset_index()
        return out

    def pickem_leaderboard(self) -> pd.DataFrame:
        """Crystal Ball table, scored like the site: exact score 3, winner 1."""
        p = self.predictions
        if p.empty:
            return pd.DataFrame()
        s = self.series
        done = s[(s["status"] == "COMPLETED") & ~s["has_dropped"]].set_index("seriesId")
        p = p[p["seriesId"].isin(done.index)].copy()
        if p.empty:
            return pd.DataFrame()
        actual = (done["t1w"].astype(str) + "-" + done["t2w"].astype(str))
        p["exact"] = (p["predictedScore"] == p["seriesId"].map(actual)).astype(int)
        p["right"] = (p["predictedWinnerId"] == p["seriesId"].map(done["winnerId"])).astype(int)
        p["points"] = np.where(p["exact"] == 1, 3, p["right"])
        out = p.groupby(["userId", "username"]).agg(
            points=("points", "sum"), exact=("exact", "sum"),
            correct=("right", "sum"), picks=("points", "size")).reset_index()
        out["accuracy"] = out["correct"] / out["picks"]
        out["username"] = out["username"].fillna("?").str.replace(r"#0$", "", regex=True)
        return out.sort_values(["points", "exact"], ascending=False).reset_index(drop=True)


# ── Aggregations shared by several pages ─────────────────────────────────────

def kda(k, d, a) -> float:
    return (k + a) / d if d > 0 else float(k + a)


def player_table(ps: pd.DataFrame, min_games: int = 1) -> pd.DataFrame:
    """One row per player with website-consistent season stats."""
    if ps.empty:
        return pd.DataFrame()
    g = ps.groupby("pid")
    out = g.agg(
        player=("player", "last"), games=("win", "size"), wins=("win", "sum"),
        kills=("kills", "sum"), deaths=("deaths", "sum"), assists=("assists", "sum"),
        cs=("cs", "sum"), gold=("goldEarned", "sum"),
        dmg=("totalDamageDealtToChampions", "sum"), vision=("visionScore", "sum"),
        mins=("mins", "sum"), kp=("killParticipation", "mean"),
        dmg_share=("teamDamagePercentage", "mean"), solo=("soloKills", "sum"),
        pentas=("pentaKills", "sum"), quadras=("quadraKills", "sum"),
        gd15=("gd15", "mean"), csd15=("csd15", "mean"), xpd15=("xpd15", "mean"),
        lane_games=("gd15", "count"), salary=("salary", "max"),
        champs=("championName", "nunique"),
    )
    out["role"] = g["role"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
    out["team"] = g["team"].agg(lambda s: s.mode().iloc[0])
    out["team_id"] = g["leagueTeamId"].agg(lambda s: s.mode().iloc[0])
    out["main"] = g["champion"].agg(lambda s: s.mode().iloc[0])
    out["kda"] = [kda(k, d, a) for k, d, a in zip(out["kills"], out["deaths"], out["assists"])]
    out["win_pct"] = out["wins"] / out["games"]
    for col, src in (("cs_min", "cs"), ("gold_min", "gold"), ("dmg_min", "dmg"), ("vis_min", "vision")):
        out[col] = out[src] / out["mins"]
    out["k_g"] = out["kills"] / out["games"]
    out["d_g"] = out["deaths"] / out["games"]
    out["a_g"] = out["assists"] / out["games"]
    out = out[out["games"] >= min_games]
    return out.reset_index()


def champion_table(ps: pd.DataFrame, bans: pd.DataFrame, n_games: int) -> pd.DataFrame:
    """Picks, bans, presence and results per champion."""
    if ps.empty:
        return pd.DataFrame()
    g = ps.groupby("championName")
    out = g.agg(picks=("win", "size"), wins=("win", "sum"), kills=("kills", "sum"),
                deaths=("deaths", "sum"), assists=("assists", "sum"),
                players=("pid", "nunique"), gd15=("gd15", "mean")).reset_index()
    out["role"] = g["role"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None).values
    out = out.rename(columns={"championName": "championKey"})
    if bans is not None and not bans.empty:
        out = out.merge(bans[["championKey", "bans"]], on="championKey", how="outer")
        drafts = int(bans["drafts"].iloc[0])
    else:
        out["bans"] = 0
        drafts = 0
    for c in ("picks", "wins", "bans", "kills", "deaths", "assists", "players"):
        out[c] = out[c].fillna(0).astype(int)
    out["champion"] = out["championKey"].map(champ_name)
    out["win_rate"] = np.where(out["picks"] > 0, out["wins"] / out["picks"].clip(lower=1), np.nan)
    out["pick_rate"] = out["picks"] / max(n_games, 1)
    out["ban_rate"] = out["bans"] / drafts if drafts else 0.0
    out["presence"] = (out["pick_rate"] + out["ban_rate"]).clip(upper=1.0)
    out["kda"] = [kda(k, d, a) for k, d, a in zip(out["kills"], out["deaths"], out["assists"])]
    # Wilson lower bound: "how good is it at least?" — keeps 2-0 flukes off the top
    n = out["picks"].clip(lower=1); p = out["win_rate"].fillna(0); z = 1.96
    out["wilson_lo"] = ((p + z * z / (2 * n) - z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)))
                        / (1 + z * z / n)).where(out["picks"] > 0, 0)
    return out.sort_values("presence", ascending=False).reset_index(drop=True)


def team_table(season: Season) -> pd.DataFrame:
    """Per-team style numbers from games actually played (all game types)."""
    ps, g = season.ps, season.games
    if ps.empty:
        return pd.DataFrame()
    per_game = ps.groupby(["leagueTeamId", "matchId"]).agg(
        kills=("kills", "sum"), deaths=("deaths", "sum"), gold=("goldEarned", "sum"),
        dmg=("totalDamageDealtToChampions", "sum"), vision=("visionScore", "sum"),
        fb=("firstBloodKill", "max"), ft=("firstTowerKill", "max"),
        gd15=("gd15", lambda s: s.sum(min_count=5)), win=("win", "max"),
        mins=("mins", "max"), side=("side", "first"),
    ).reset_index()
    ts = season.team_stats
    if not ts.empty:
        per_game = per_game.merge(
            ts.rename(columns={"teamId": "leagueTeamId"})[
                ["leagueTeamId", "matchId", "dragons", "barons", "turrets", "heralds"]],
            on=["leagueTeamId", "matchId"], how="left")
    else:
        for c in ("dragons", "barons", "turrets", "heralds"):
            per_game[c] = np.nan
    per_game["ahead15"] = np.where(per_game["gd15"].notna(), (per_game["gd15"] > 0).astype(float), np.nan)
    season.team_games = per_game
    a = per_game.groupby("leagueTeamId").agg(
        games=("win", "size"), wins=("win", "sum"), kills=("kills", "mean"),
        deaths=("deaths", "mean"), mins=("mins", "mean"), fb=("fb", "mean"), ft=("ft", "mean"),
        gd15=("gd15", "mean"), ahead15=("ahead15", "mean"), dragons=("dragons", "mean"),
        barons=("barons", "mean"), turrets=("turrets", "mean"), vision=("vision", "sum"),
        tmins=("mins", "sum"), dmg=("dmg", "sum"), gold=("gold", "sum"),
    ).reset_index().rename(columns={"leagueTeamId": "team_id"})
    a["win_pct"] = a["wins"] / a["games"]
    a["vis_min"] = a["vision"] / a["tmins"]
    a["dmg_min"] = a["dmg"] / a["tmins"]
    a["gold_min"] = a["gold"] / a["tmins"]
    a["kd"] = a["kills"] / a["deaths"].clip(lower=0.1)
    pool = ps.groupby("leagueTeamId")["championName"].nunique()
    a["champ_pool"] = a["team_id"].map(pool)
    blue = per_game[per_game["side"] == "Blue"].groupby("leagueTeamId")["win"].mean()
    red = per_game[per_game["side"] == "Red"].groupby("leagueTeamId")["win"].mean()
    a["blue_wr"] = a["team_id"].map(blue); a["red_wr"] = a["team_id"].map(red)
    a["team"] = a["team_id"].map(season.names)
    a = a[a["team"].notna()]
    return a

"""
Beer League Stats — the fun stuff (pure functions over a Season).

  * title_odds        : simulate the real playoff bracket (or a seeded one)
  * win_conditions    : dragons / barons / heralds / leads — what wins games here
  * team_styles       : how each team actually wins (tags + supporting numbers)
  * champion_extras   : never-picked list, explorer cards, duos, lane matchups
  * fun_awards        : season superlatives and the single-game record book
  * item_table        : completed-item pick and win rates
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.elo import win_probability, STARTING_ELO
from app.league import ROLES, ROLE_SHORT, Season, champ_name, score_distribution, team_table


# ── Playoff bracket simulation ───────────────────────────────────────────────

def _series_p(p_game: float, fmt: str) -> float:
    return sum(p for a, b, p in score_distribution(p_game, fmt) if a > b)


def _round_names(n_rounds: int) -> dict:
    names = {n_rounds: "Final", n_rounds - 1: "Semifinals", n_rounds - 2: "Quarterfinals"}
    return {r: names.get(r, f"Round {r}") for r in range(1, n_rounds + 1)}


def real_bracket(season: Season):
    """The bracket the site generated, as {(round, match): row dict}, or None.
    Labels look like 'WB-R2-M3'; the winner of round r match m moves to
    round r+1 match ceil(m/2) (slot 1 when m is odd, slot 2 when even)."""
    po = season.series[season.series["playoff"]]
    out = {}
    for r in po.itertuples():
        mt = re.match(r"^WB-R(\d+)-M(\d+)$", str(r.label or ""))
        if not mt:
            return None
        out[(int(mt.group(1)), int(mt.group(2)))] = {
            "t1": r.team1Id, "t2": r.team2Id, "fmt": r.format, "status": r.status,
            "winner": r.winnerId if r.status == "COMPLETED" else None, "s1": r.t1w, "s2": r.t2w}
    return out or None


def seeded_bracket(seed_ids: list, formats: dict | None = None) -> dict:
    """Standard single-elimination bracket for a seed list (best first);
    top seeds get byes when the field isn't a power of two."""
    n = len(seed_ids)
    size = 1 << max(1, (n - 1).bit_length())
    order = [1]
    while len(order) < size:
        m = len(order) * 2 + 1
        order = [x for s in order for x in (s, m - s)]
    n_rounds = size.bit_length() - 1
    fmt = lambda r: (formats or {}).get(str(r), "bo5" if r >= n_rounds - 1 and n_rounds > 1 else "bo3")
    code = {"bo1": "BEST_OF_1", "bo3": "BEST_OF_3", "bo5": "BEST_OF_5"}
    out = {}
    for r in range(1, n_rounds + 1):
        for m in range(1, size // (2 ** r) + 1):
            out[(r, m)] = {"t1": None, "t2": None, "fmt": code.get(fmt(r), "BEST_OF_3"),
                           "status": "SCHEDULED", "winner": None, "s1": 0, "s2": 0}
    for m in range(1, size // 2 + 1):
        a, b = order[2 * m - 2], order[2 * m - 1]
        ta = seed_ids[a - 1] if a <= n else None
        tb = seed_ids[b - 1] if b <= n else None
        if ta and tb:
            out[(1, m)].update(t1=ta, t2=tb)
        else:                              # bye: the present team starts in round 2
            del out[(1, m)]
            if n_rounds >= 2:
                out[(2, (m + 1) // 2)]["t1" if m % 2 else "t2"] = ta or tb
    return out


def title_odds(season: Season, rating: dict, rd: dict, bracket: dict,
               n_sims: int = 5000, seed: int = 7) -> dict:
    """Roll the bracket n_sims times. Completed series keep their real winner.
    Returns {rounds: [...matches with model odds...], odds: [{t, reach{r}, win}]}."""
    rng = np.random.default_rng(seed)
    n_rounds = max(r for r, _ in bracket)
    names = _round_names(n_rounds)
    keys = sorted(bracket)
    teams = {t for k in keys for t in (bracket[k]["t1"], bracket[k]["t2"]) if t}
    reach = {t: {r: 0 for r in range(1, n_rounds + 2)} for t in teams}
    pcache = {}

    def p_win(a, b, fmt):
        k = (a, b, fmt)
        if k not in pcache:
            pg = win_probability(rating.get(a, STARTING_ELO), rating.get(b, STARTING_ELO),
                                 rd.get(a, 200.0), rd.get(b, 200.0))
            pcache[k] = _series_p(pg, fmt)
        return pcache[k]

    meet = {k: {} for k in keys}          # how often each pairing occurs in a slot
    for _ in range(n_sims):
        won = {}
        for (r, m) in keys:
            row = bracket[(r, m)]
            a = row["t1"] or won.get((r - 1, 2 * m - 1))
            b = row["t2"] or won.get((r - 1, 2 * m))
            if a is None or b is None:
                w = a or b
            elif row["winner"] in (a, b):
                w = row["winner"]
            else:
                w = a if rng.random() < p_win(a, b, row["fmt"]) else b
            for t in (a, b):
                if t:
                    reach[t][r] += 1
            won[(r, m)] = w
            if a and b:
                meet[(r, m)][(a, b)] = meet[(r, m)].get((a, b), 0) + 1
        champ = won[(n_rounds, 1)]
        if champ:
            reach[champ][n_rounds + 1] += 1

    rounds = []
    for r in range(1, n_rounds + 1):
        ms = []
        for (rr, m) in keys:
            if rr != r:
                continue
            row = bracket[(rr, m)]
            item = {"m": m, "t1": row["t1"], "t2": row["t2"], "fmt": row["fmt"], "status": row["status"],
                    "s1": row["s1"], "s2": row["s2"], "winner": row["winner"], "p1": None, "likely": []}
            if row["t1"] and row["t2"]:
                item["p1"] = p_win(row["t1"], row["t2"], row["fmt"])
            else:                          # who is most likely to fill the open slot(s)
                cnt = {}
                for (a, b), c in meet[(rr, m)].items():
                    for t, known in ((a, row["t1"]), (b, row["t2"])):
                        if not known:
                            cnt[t] = cnt.get(t, 0) + c
                item["likely"] = [{"t": t, "p": c / n_sims} for t, c in
                                  sorted(cnt.items(), key=lambda x: -x[1])[:3]]
            ms.append(item)
        rounds.append({"r": r, "name": names[r], "matches": ms})
    odds = [{"t": t, "reach": {str(r): v / n_sims for r, v in d.items() if r <= n_rounds},
             "win": d[n_rounds + 1] / n_sims, "rating": rating.get(t)} for t, d in reach.items()]
    odds.sort(key=lambda x: (-x["win"], -x["reach"].get(str(n_rounds), 0)))
    return {"rounds": rounds, "odds": odds, "n_rounds": n_rounds, "names": {str(k): v for k, v in names.items()},
            "n_sims": n_sims}


# ── What wins games ──────────────────────────────────────────────────────────

def _team_games(season: Season) -> pd.DataFrame:
    if not hasattr(season, "team_games"):
        team_table(season)
    tg = season.team_games.copy()
    g = season.games.set_index("matchId")
    tg["week"] = tg["matchId"].map(g["week"])
    tg["opp"] = np.where(tg["matchId"].map(g["winnerId"]) == tg["leagueTeamId"],
                         tg["matchId"].map(g["loserId"]), tg["matchId"].map(g["winnerId"]))
    for c in ("dragons", "barons", "turrets", "heralds", "kills"):
        if c in tg.columns:
            tg["opp_" + c] = tg.groupby("matchId")[c].transform("sum") - tg[c]
    return tg


def win_conditions(season: Season) -> dict:
    tg = _team_games(season)
    out = {"edges": [], "dragons": [], "barons": [], "herald": [], "comebacks": [], "soul": None}
    if tg.empty:
        return out

    def edge(label, mask, blurb=""):
        d = tg[mask.fillna(False)]
        if len(d) >= 8:
            out["edges"].append({"label": label, "wr": d["win"].mean(), "n": len(d), "blurb": blurb})
    edge("First blood", tg["fb"] > 0)
    edge("First tower", tg["ft"] > 0)
    if tg["gd15"].notna().any():
        edge("Gold lead at 15:00", tg["gd15"] > 0)
    has_obj = tg["dragons"].notna().any()
    if has_obj:
        edge("Rift Herald", tg["heralds"] > tg["opp_heralds"])
        edge("More dragons", tg["dragons"] > tg["opp_dragons"])
        edge("More barons", tg["barons"] > tg["opp_barons"])
        edge("More kills", tg["kills"] > tg["opp_kills"])
        d = tg.dropna(subset=["dragons"]).assign(n=lambda x: x["dragons"].clip(upper=4).astype(int))
        out["dragons"] = [{"n": int(n), "games": len(x), "wr": x["win"].mean()} for n, x in d.groupby("n")]
        b = tg.dropna(subset=["barons"]).assign(n=lambda x: x["barons"].clip(upper=2).astype(int))
        out["barons"] = [{"n": int(n), "games": len(x), "wr": x["win"].mean()} for n, x in b.groupby("n")]
        h = tg.dropna(subset=["heralds"])
        out["herald"] = [{"n": int(n), "games": len(x), "wr": x["win"].mean()} for n, x in h.groupby(h["heralds"].clip(upper=1).astype(int))]
        soul = d[d["dragons"] >= 4]
        if len(soul):
            out["soul"] = {"games": len(soul), "wr": soul["win"].mean()}
    out["edges"].sort(key=lambda e: -e["wr"])
    cb = tg[(tg["win"] == 1) & (tg["gd15"] < 0)].nsmallest(6, "gd15")
    out["comebacks"] = [{"team": r.leagueTeamId, "opp": r.opp, "deficit": float(r.gd15), "week": int(r.week),
                         "mins": float(r.mins)} for r in cb.itertuples()]
    lead = tg[tg["gd15"].notna()]
    if len(lead):
        ahead = lead[lead["gd15"] > 0]
        out["lead_hold"] = float(ahead["win"].mean()) if len(ahead) else None
    return out


def team_styles(season: Season) -> list:
    """One card per live team: how they win, in tags and numbers."""
    tt = team_table(season)
    tg = _team_games(season)
    if tt.empty:
        return []
    tt = tt[tt["team_id"].isin(season.live_ids)].copy()
    ps = season.ps
    share = (ps.dropna(subset=["role"]).groupby(["leagueTeamId", "role"])["teamDamagePercentage"].mean()
             .unstack().reindex(columns=ROLES))
    share = share.div(share.sum(axis=1), axis=0)

    def pctl(col, v, inv=False):
        xs = tt[col].dropna()
        if pd.isna(v) or len(xs) < 4:
            return None
        p = ((xs < v).sum() + 0.5 * (xs == v).sum()) / len(xs)
        return 1 - p if inv else p
    tt["pace"] = (tt["kills"] + tt["deaths"]) / tt["mins"]
    cards = []
    for r in tt.itertuples():
        g = tg[tg["leagueTeamId"] == r.team_id]
        ahead, behind = g[g["gd15"] > 0], g[g["gd15"] < 0]
        short, long_ = g[g["mins"] < 28], g[g["mins"] > 36]
        ds = share.loc[r.team_id] if r.team_id in share.index else pd.Series(dtype=float)
        tags = []
        add = lambda t, why: tags.append({"tag": t, "why": why}) if len(tags) < 3 else None
        p = pctl("gd15", r.gd15)
        if p is not None and p >= 0.75:
            add("Lane bullies", f"{r.gd15:+,.0f} gold at 15:00")
        if p is not None and p <= 0.3 and r.win_pct >= 0.5:
            add("Slow starters", f"{r.gd15:+,.0f} at 15 but {r.win_pct * 100:.0f}% wins")
        if len(behind) >= 4 and behind["win"].mean() >= 0.5:
            add("Comeback kings", f"won {int(behind['win'].sum())} of {len(behind)} when behind at 15")
        if len(ahead) >= 4 and ahead["win"].mean() <= 0.6:
            add("Throw risk", f"lost {int(len(ahead) - ahead['win'].sum())} of {len(ahead)} leads")
        if len(ahead) >= 5 and ahead["win"].mean() >= 0.9:
            add("Closers", f"held {int(ahead['win'].sum())} of {len(ahead)} leads")
        if (pctl("pace", r.pace) or 0) >= 0.8:
            add("Bloodbath", f"{r.kills + r.deaths:.0f} kills a game")
        if (pctl("pace", r.pace) or 1) <= 0.2:
            add("Low-kill macro", f"only {r.kills + r.deaths:.0f} kills a game")
        if (pctl("dragons", r.dragons) or 0) >= 0.8:
            add("Dragon hoarders", f"{r.dragons:.1f} drakes a game")
        if (pctl("barons", r.barons) or 0) >= 0.8:
            add("Baron callers", f"{r.barons:.1f} barons a game")
        if (pctl("vis_min", r.vis_min) or 0) >= 0.85:
            add("Vision control", f"{r.vis_min:.1f} vision a minute")
        if len(short) >= 3 and len(long_) >= 3:
            d = long_["win"].mean() - short["win"].mean()
            if d >= 0.25 and long_["win"].mean() >= 0.5:
                add("Late-game team", f"{long_['win'].mean() * 100:.0f}% in 36+ min games")
            elif d <= -0.25 and short["win"].mean() >= 0.5:
                add("Fast finishers", f"{short['win'].mean() * 100:.0f}% in sub-28 min games")
        if len(ds.dropna()):
            top = ds.idxmax()
            if ds[top] >= 0.30:
                add(f"{ROLE_SHORT[top]} carries", f"{ds[top] * 100:.0f}% of team damage")
        if (pctl("champ_pool", r.champ_pool) or 0) >= 0.85:
            add("Deep champion pool", f"{int(r.champ_pool)} champions played")
        if (pctl("fb", r.fb) or 0) >= 0.85:
            add("First-blood hunters", f"first blood in {r.fb * 100:.0f}% of games")
        if not tags:
            add("Balanced", "no single stat stands out")
        cards.append({
            "t": r.team_id, "win_pct": r.win_pct, "games": int(r.games), "tags": tags,
            "ahead": [int(ahead["win"].sum()), len(ahead)], "behind": [int(behind["win"].sum()), len(behind)],
            "short": [int(short["win"].sum()), len(short)], "long": [int(long_["win"].sum()), len(long_)],
            "dmg": {ROLE_SHORT[k]: float(v) for k, v in ds.dropna().items()},
        })
    cards.sort(key=lambda c: -c["win_pct"])
    return cards


# ── Champions ────────────────────────────────────────────────────────────────

def champion_extras(season: Season, all_keys: set | None = None) -> dict:
    ps = season.ps
    out = {"never": [], "explore": {}, "duos": [], "matchups": [], "signature": []}
    if ps.empty:
        return out
    seen = set(ps["championName"])
    d = season.draft_actions()
    banned = set(d.loc[d["actionType"] == "BAN", "championKey"]) if not d.empty else set()
    if all_keys:
        norm = lambda k: "FiddleSticks" if k == "Fiddlesticks" else k
        allk = {norm(k) for k in all_keys}
        out["never"] = sorted(champ_name(k) for k in allk - seen - banned)
        out["never_picked_only"] = sorted(champ_name(k) for k in (allk - seen) & banned)
        out["pool_size"] = len(allk)

    base = ps[["matchId", "leagueTeamId", "championName", "champion", "role", "win", "player", "pid", "side"]]
    mates = base.merge(base, on=["matchId", "leagueTeamId"], suffixes=("", "_o"))
    mates = mates[mates["championName"] != mates["championName_o"]]
    pair = mates.groupby(["championName", "champion_o"]).agg(g=("win", "size"), w=("win", "sum")).reset_index()
    opp = base.dropna(subset=["role"]).merge(base.dropna(subset=["role"]), on=["matchId", "role"], suffixes=("", "_o"))
    opp = opp[opp["leagueTeamId"] != opp["leagueTeamId_o"]]
    vs = opp.groupby(["championName", "champion_o"]).agg(g=("win", "size"), w=("win", "sum")).reset_index()
    dur = season.games.set_index("matchId")["duration"]
    slot = (d[d["actionType"] == "PICK"].groupby("championKey")["pick_no"].mean() if not d.empty else pd.Series(dtype=float))
    bans = (d[d["actionType"] == "BAN"].groupby("championKey").size() if not d.empty else pd.Series(dtype=float))

    for key, g in base.groupby("championName"):
        if len(g) < 3:
            continue
        who = g.groupby("player").agg(g=("win", "size"), w=("win", "sum")).sort_values(["g", "w"], ascending=False).head(3)
        pr = pair[(pair["championName"] == key) & (pair["g"] >= 2)].assign(wr=lambda x: x["w"] / x["g"])
        mu = vs[(vs["championName"] == key) & (vs["g"] >= 2)].assign(wr=lambda x: x["w"] / x["g"])
        side = g.groupby("side")["win"].agg(["size", "sum"])
        out["explore"][champ_name(key)] = {
            "key": key, "g": len(g), "w": int(g["win"].sum()),
            "role": g["role"].mode().iloc[0] if not g["role"].mode().empty else None,
            "blue": [int(side.loc["Blue", "sum"]), int(side.loc["Blue", "size"])] if "Blue" in side.index else [0, 0],
            "red": [int(side.loc["Red", "sum"]), int(side.loc["Red", "size"])] if "Red" in side.index else [0, 0],
            "mins": float(g["matchId"].map(dur).mean() / 60) if g["matchId"].map(dur).notna().any() else None,
            "slot": float(slot.get(key)) if key in slot.index else None,
            "bans": int(bans.get(key, 0)),
            "players": [{"p": p, "g": int(r.g), "w": int(r.w)} for p, r in who.iterrows()],
            "with": [{"c": r.champion_o, "g": int(r.g), "w": int(r.w)} for r in
                     pr.sort_values(["wr", "g"], ascending=False).head(3).itertuples()],
            "beats": [{"c": r.champion_o, "g": int(r.g), "w": int(r.w)} for r in
                      mu.sort_values(["wr", "g"], ascending=False).head(3).itertuples()],
            "loses": [{"c": r.champion_o, "g": int(r.g), "w": int(r.w)} for r in
                      mu.sort_values(["wr", "g"], ascending=[True, False]).head(3).itertuples()],
        }
    # league-wide duos (each pair once) and lopsided lane matchups
    pair["a"] = pair["championName"].map(champ_name)
    duo = pair[pair["a"] < pair["champion_o"]]
    duo = duo[duo["g"] >= 4].assign(wr=lambda x: x["w"] / x["g"]).sort_values(["wr", "g"], ascending=False)
    out["duos"] = [{"a": r.a, "b": r.champion_o, "g": int(r.g), "w": int(r.w)} for r in duo.head(8).itertuples()]
    most = pair[pair["a"] < pair["champion_o"]].sort_values("g", ascending=False).head(6)
    out["duos_most"] = [{"a": r.a, "b": r.champion_o, "g": int(r.g), "w": int(r.w)} for r in most.itertuples()]
    vs["a"] = vs["championName"].map(champ_name)
    lop = vs[(vs["g"] >= 3)].assign(wr=lambda x: x["w"] / x["g"]).sort_values(["wr", "g"], ascending=False)
    out["matchups"] = [{"a": r.a, "b": r.champion_o, "g": int(r.g), "w": int(r.w)} for r in lop.head(8).itertuples()]
    sig = (ps.groupby(["player", "champion", "leagueTeamId"]).agg(g=("win", "size"), w=("win", "sum")).reset_index()
           .sort_values(["g", "w"], ascending=False).head(10))
    out["signature"] = [{"p": r.player, "c": r.champion, "t": r.leagueTeamId, "g": int(r.g), "w": int(r.w)}
                        for r in sig.itertuples()]
    return out


# ── Awards and records ───────────────────────────────────────────────────────

AWARDS = [
    # title, blurb, column, mode, unit
    ("Ping Machine", "Most pings per game", "totalPings", "avg", "pings a game"),
    ("The Question Mark", "Most enemy-missing pings per game", "enemyMissingPings", "avg", "? pings a game"),
    ("Smite Thief", "Epic monsters stolen", "epicMonsterSteals", "sum", "steals"),
    ("Tower Diver", "Kills under the enemy turret", "killsNearEnemyTurret", "sum", "dive kills"),
    ("Outnumbered, Unbothered", "Kills while outnumbered", "outnumberedKills", "sum", "kills"),
    ("Solo Bolo", "Solo kills", "soloKills", "sum", "solo kills"),
    ("Guardian Angel", "Allies saved from death", "saveAllyFromDeath", "sum", "saves"),
    ("Cockroach", "Fights survived on single-digit HP", "survivedSingleDigitHpCount", "sum", "escapes"),
    ("Dodgeball Champ", "Skillshots dodged per game", "skillshotsDodged", "avg", "dodged a game"),
    ("Sharpshooter", "Skillshots landed per game", "skillshotsHit", "avg", "hit a game"),
    ("Ward Bot", "Wards placed per game", "wardsPlaced", "avg", "wards a game"),
    ("Sweeper", "Wards cleared per game", "wardsKilled", "avg", "cleared a game"),
    ("Pink Ward Economy", "Control wards bought per game", "visionWardsBoughtInGame", "avg", "pinks a game"),
    ("Buff Thief", "Enemy buffs stolen", "buffsStolen", "sum", "buffs"),
    ("Plate Collector", "Turret plates per game", "turretPlatesTaken", "avg", "plates a game"),
    ("Fist Bumper", "Fist bumps joined", "fistBumpParticipation", "sum", "fist bumps"),
    ("Damage Sponge", "Damage taken per game", "totalDamageTaken", "avg", "damage taken a game"),
    ("Gray Screen Enjoyer", "Deaths per game", "deaths", "avg", "deaths a game"),
    ("Ult On Cooldown", "Ultimates cast per game", "spell4Casts", "avg", "ults a game"),
    ("Crowd Controller", "Crowd control dealt per game (Riot's CC score)", "cc_s", "avg", "CC score a game"),
    ("Champion Ocean", "Different champions played", "championName", "nunique", "champions"),
]


def fun_awards(season: Season) -> dict:
    ps = season.ps
    out = {"awards": [], "records": []}
    if ps.empty:
        return out
    games = ps.groupby("pid").size()
    min_g = max(3, int(games.max() * 0.3))
    ok = ps[ps["pid"].isin(games.index[games >= min_g])]
    ident = ok.groupby("pid").agg(player=("player", "last"),
                                  team=("leagueTeamId", lambda s: s.mode().iloc[0]))
    for title, blurb, col, mode, unit in AWARDS:
        if col not in ok.columns:
            continue
        s = ok.groupby("pid")[col].agg({"avg": "mean", "sum": "sum", "nunique": "nunique"}[mode]).dropna()
        s = s[s > 0].sort_values(ascending=False)
        if s.empty:
            continue
        top = s.head(3)
        fmt = (lambda v: f"{v:,.1f}") if mode == "avg" and top.iloc[0] < 100 else (lambda v: f"{v:,.0f}")
        out["awards"].append({
            "title": title, "blurb": blurb, "unit": unit,
            "player": ident.at[top.index[0], "player"], "team": ident.at[top.index[0], "team"],
            "value": fmt(top.iloc[0]),
            "next": [{"player": ident.at[i, "player"], "value": fmt(v)} for i, v in top.iloc[1:].items()],
        })
    out["min_games"] = min_g

    def rec(title, col, fmt, per_min=False):
        d = ps.dropna(subset=[col])
        if d.empty:
            return
        vals = d[col] / d["mins"] if per_min else d[col]
        r = d.loc[vals.idxmax()]
        out["records"].append({"title": title, "value": fmt.format(vals.max()), "player": r["player"],
                               "champ": r["champion"], "team": r["leagueTeamId"], "opp": r["oppTeamId"],
                               "week": int(r["week"]), "playoff": bool(r["playoff"])})
    rec("Most kills in a game", "kills", "{:.0f} kills")
    rec("Most deaths in a game", "deaths", "{:.0f} deaths")
    rec("Most assists in a game", "assists", "{:.0f} assists")
    rec("Most damage in a game", "totalDamageDealtToChampions", "{:,.0f} damage")
    rec("Highest damage per minute", "totalDamageDealtToChampions", "{:,.0f} a minute", per_min=True)
    rec("Best farm", "cs", "{:.1f} CS a minute", per_min=True)
    rec("Biggest lane lead", "gd15", "{:+,.0f} gold at 15:00")
    rec("Most vision", "visionScore", "{:.0f} vision score")
    rec("Most pings in a game", "totalPings", "{:.0f} pings")
    rec("Most damage soaked", "totalDamageTaken", "{:,.0f} damage taken")
    rec("Most healing on allies", "totalHealsOnTeammates", "{:,.0f} healed")
    g = season.games.dropna(subset=["duration"])
    if len(g):
        kills = ps.groupby("matchId")["kills"].sum()
        for title, row, val in (
            ("Longest game", g.loc[g["duration"].idxmax()], None),
            ("Fastest win", g.loc[g["duration"].idxmin()], None),
        ):
            out["records"].append({"title": title, "value": f"{int(row['duration'] // 60)}:{int(row['duration'] % 60):02d}",
                                   "player": None, "champ": None, "team": row["winnerId"], "opp": row["loserId"],
                                   "week": int(row["week"]), "playoff": bool(row["playoff"])})
        if len(kills):
            row = season.games.set_index("matchId").loc[kills.idxmax()]
            out["records"].append({"title": "Bloodiest game", "value": f"{int(kills.max())} kills", "player": None,
                                   "champ": None, "team": row["winnerId"], "opp": row["loserId"],
                                   "week": int(row["week"]), "playoff": bool(row["playoff"])})
    return out


# ── Items ────────────────────────────────────────────────────────────────────

def item_table(db: str, season: Season) -> dict:
    from app.data_loader import load_item_stats, load_sunfire_stats
    items = load_item_stats(db, season.id)
    n_rows = max(len(season.ps), 1)
    out = {"items": [], "sunfire": None}
    if not items.empty:
        items = items[items["games"] >= 3]
        out["items"] = [{"name": r.item_name, "builds": int(r.games), "rate": r.games / n_rows,
                         "wr": float(r.win_rate)} for r in items.itertuples()
                        if not str(r.item_name).startswith("Item ")]
    sf = load_sunfire_stats(db, season.id)
    if sf["total_builds"]:
        top = pd.Series([b["player"] for b in sf["builders"]]).value_counts().head(6)
        out["sunfire"] = {"total": sf["total_builds"], "wins": sf["wins"], "losses": sf["losses"],
                          "wr": sf["win_rate"], "top": [{"p": p, "n": int(n)} for p, n in top.items()]}
    return out

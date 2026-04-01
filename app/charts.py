"""
Beer League Stats — Plotly Chart Library (Broadcast Edition)
Every function returns a plotly.graph_objects.Figure.
All charts use the broadcast dark theme defined in styling.py.
Design: ESPN/LCS broadcast overlay aesthetic — no clutter, bold type, embedded labels.
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from app.styling import (
    apply_template, PLOTLY_TEMPLATE,
    ACCENT_GOLD, ACCENT_TEAL, ACCENT_RED, ACCENT_BLUE, ACCENT_CYAN,
    WIN_COLOR, LOSS_COLOR, LITE_COLOR, STOUT_COLOR,
    CARD_BG, CARD_BG_ALT, BORDER_CLR, BORDER_LIGHT,
    SURFACE, DARK_BG,
    TEXT_MAIN, TEXT_SEC, TEXT_MUTED, TEXT_DIM,
    TEAM_PALETTE, team_color,
)


# -- Helpers -------------------------------------------------------------------

def _base(title: str = "", height: int = 380, legend_above: bool = False) -> go.Figure:
    """Create a base figure with broadcast template applied."""
    fig = go.Figure()
    apply_template(fig)
    top_margin = 72 if legend_above else 56
    fig.update_layout(
        title_text=title,
        height=height,
        margin=dict(t=top_margin, l=10, r=40, b=10),
    )
    return fig


def _fmt_time(seconds) -> str:
    try:
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"
    except Exception:
        return "?"


# Broadcast table styling constants
_TBL_HEADER = dict(
    fill_color="#1e293b",
    font=dict(
        color=ACCENT_GOLD, size=12,
        family="Oswald, Barlow Condensed, sans-serif",
    ),
    align="left",
    height=38,
    line_color="#0f172a",
)

_TBL_CELL_BASE = dict(
    font=dict(
        color=TEXT_MAIN, size=13,
        family="Barlow Condensed, sans-serif",
    ),
    align="left",
    height=34,
    line_color="#0f172a",
)


def _alternating_fills(n: int) -> list:
    """Return alternating row fill colors for tables."""
    return [CARD_BG if i % 2 == 0 else CARD_BG_ALT for i in range(n)]


# ════════════════════════════════════════════════════════════════════════════
# WEEKLY RECAP
# ════════════════════════════════════════════════════════════════════════════

def chart_series_results(series_df: pd.DataFrame) -> go.Figure:
    """
    Horizontal grouped bar showing each series score.
    Winner bar = gold, loser bar = muted.
    """
    if series_df.empty:
        return _base("No series data")

    labels, winner_vals, loser_vals, hover = [], [], [], []
    for _, r in series_df.iterrows():
        t1w = r.get("team1Wins", 0)
        t2w = r.get("team2Wins", 0)
        t1 = r["team1Name"]
        t2 = r["team2Name"]
        wn = r.get("winnerName", "")
        if wn == t1:
            labels.append(f"{t1} vs {t2}")
            winner_vals.append(t1w)
            loser_vals.append(t2w)
        else:
            labels.append(f"{t2} vs {t1}")
            winner_vals.append(t2w)
            loser_vals.append(t1w)
        hover.append(f"{t1} {t1w}-{t2w} {t2}")

    fig = _base("Series Results", height=max(260, 65 * len(labels) + 50), legend_above=True)
    fig.add_trace(go.Bar(
        y=labels, x=winner_vals, orientation="h",
        name="Winner", marker_color=ACCENT_GOLD,
        text=winner_vals, textposition="inside",
        textfont=dict(size=16, family="Oswald, sans-serif", color="#080b12"),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover,
        marker_line_width=0,
    ))
    fig.add_trace(go.Bar(
        y=labels, x=loser_vals, orientation="h",
        name="Loser", marker_color="#1e293b",
        text=loser_vals, textposition="inside",
        textfont=dict(size=16, family="Oswald, sans-serif", color=TEXT_MUTED),
        marker_line_width=0,
    ))
    fig.update_layout(
        barmode="stack",
        xaxis=dict(tickvals=[0, 1, 2, 3], showgrid=False, showticklabels=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=14)),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0.5, xanchor="center"),
        showlegend=True,
    )
    return fig


def chart_objectives_winners_vs_losers(
    team_stats_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> go.Figure:
    """
    Horizontal bar showing the winner's EDGE per objective.
    Positive = winners had more on average → "securing this leads to wins."
    Framed as actionable strategic insight.
    """
    if team_stats_df.empty or matches_df.empty:
        return _base("What Wins Games?")

    winner_ids = dict(zip(matches_df["id"].astype(str), matches_df["winnerId"].astype(str)))
    ts = team_stats_df.copy()
    ts["matchId"] = ts["matchId"].astype(str)
    ts["teamId"] = ts["teamId"].astype(str)
    ts["is_winner"] = ts.apply(lambda r: winner_ids.get(r["matchId"]) == r["teamId"], axis=1)

    metrics = ["dragons", "barons", "heralds", "turrets", "kills"]
    metric_labels = ["DRAGONS", "BARONS", "HERALDS", "TURRETS", "KILLS"]

    w_avgs = [ts[ts["is_winner"]][m].mean() for m in metrics]
    l_avgs = [ts[~ts["is_winner"]][m].mean() for m in metrics]
    deltas = [w - l for w, l in zip(w_avgs, l_avgs)]

    # Also compute how often the team with MORE of this objective won
    correlations = []
    for m in metrics:
        by_match = ts.groupby("matchId").apply(
            lambda g: (
                g.loc[g[m].idxmax(), "is_winner"]
                if len(g) == 2 and g[m].iloc[0] != g[m].iloc[1]
                else None
            )
        ).dropna()
        if len(by_match) > 0:
            correlations.append(by_match.mean())
        else:
            correlations.append(0.5)

    colors = [WIN_COLOR if d > 0 else LOSS_COLOR for d in deltas]

    fig = _base("What Wins Games?", height=max(280, 45 * len(metrics) + 70))

    fig.add_trace(go.Bar(
        y=metric_labels, x=deltas, orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.85,
        text=[f"+{d:.1f} avg ({c*100:.0f}% win rate when leading)"
              for d, c in zip(deltas, correlations)],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif", color=TEXT_SEC),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Winner avg: %{customdata[0]:.1f}<br>"
            "Loser avg: %{customdata[1]:.1f}<br>"
            "Edge: %{x:+.1f}<extra></extra>"
        ),
        customdata=list(zip(w_avgs, l_avgs)),
    ))

    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False,
                   title=dict(text="Winner's Edge (avg more than loser)",
                              font=dict(size=10, color=TEXT_MUTED))),
        yaxis=dict(tickfont=dict(size=14, family="Oswald, sans-serif", color=TEXT_SEC)),
        margin=dict(l=10, r=120, t=56, b=30),
    )
    return fig


def chart_game_durations(player_stats_df: pd.DataFrame, matches_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar of game durations, sorted fastest to slowest."""
    if player_stats_df.empty or matches_df.empty:
        return _base("Game Durations")

    dur = (
        player_stats_df.groupby("matchId")["gameDuration"]
        .first().reset_index()
    )
    dur["matchId"] = dur["matchId"].astype(str)
    m_df = matches_df[["id", "team1Name", "team2Name", "winnerName"]].copy()
    m_df["id"] = m_df["id"].astype(str)
    dur = dur.merge(m_df, left_on="matchId", right_on="id", how="left")
    dur = dur.sort_values("gameDuration")

    dur["label"] = dur.apply(
        lambda r: f"{r['team1Name']} vs {r['team2Name']}", axis=1)
    dur["time_str"] = dur["gameDuration"].apply(_fmt_time)

    fig = _base("Game Durations", height=max(240, 50 * len(dur) + 40))
    fig.add_trace(go.Bar(
        y=dur["label"], x=dur["gameDuration"], orientation="h",
        marker_color=ACCENT_TEAL, marker_line_width=0, opacity=0.85,
        text=dur["time_str"], textposition="outside",
        textfont=dict(size=14, family="Oswald, sans-serif", color=ACCENT_TEAL),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Winner: %{customdata[0]}<br>"
            "Duration: %{customdata[1]}<extra></extra>"
        ),
        customdata=list(zip(dur["winnerName"].fillna("?"), dur["time_str"])),
    ))
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(autorange="reversed", tickfont=dict(size=13)),
    )
    return fig


def chart_kill_scatter(team_stats_df: pd.DataFrame, matches_df: pd.DataFrame,
                       player_stats_df: pd.DataFrame) -> go.Figure:
    """Scatter: x=winner kills, y=loser kills. Size=game duration."""
    if team_stats_df.empty or matches_df.empty:
        return _base("Kill Distribution")

    winner_map = dict(zip(matches_df["id"].astype(str), matches_df["winnerId"].astype(str)))
    ts = team_stats_df.copy()
    ts["matchId"] = ts["matchId"].astype(str)
    ts["teamId"] = ts["teamId"].astype(str)

    rows = []
    for mid, group in ts.groupby("matchId"):
        wid = winner_map.get(mid)
        win_row = group[group["teamId"] == wid]
        lose_row = group[group["teamId"] != wid]
        if win_row.empty or lose_row.empty:
            continue
        rows.append({
            "matchId": mid,
            "winner_kills": win_row.iloc[0]["kills"],
            "loser_kills": lose_row.iloc[0]["kills"],
        })

    if not rows:
        return _base("Kill Distribution")

    scatter_df = pd.DataFrame(rows)

    if not player_stats_df.empty:
        dur = player_stats_df.groupby("matchId")["gameDuration"].first().reset_index()
        dur["matchId"] = dur["matchId"].astype(str)
        scatter_df = scatter_df.merge(dur, on="matchId", how="left")
        scatter_df["gameDuration"] = scatter_df["gameDuration"].fillna(1800)
    else:
        scatter_df["gameDuration"] = 1800

    scatter_df = scatter_df.merge(
        matches_df[["id", "team1Name", "team2Name", "winnerName"]].assign(
            id=matches_df["id"].astype(str)),
        left_on="matchId", right_on="id", how="left"
    )

    max_k = max(scatter_df["winner_kills"].max(), scatter_df["loser_kills"].max()) + 3

    fig = _base("Kill Distribution", height=400)
    # Parity line
    fig.add_trace(go.Scatter(
        x=[0, max_k], y=[0, max_k],
        mode="lines",
        line=dict(color="rgba(30,41,59,0.6)", dash="dash", width=1),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=scatter_df["winner_kills"],
        y=scatter_df["loser_kills"],
        mode="markers",
        marker=dict(
            size=(scatter_df["gameDuration"] / 60).clip(15, 45),
            color=ACCENT_GOLD,
            opacity=0.8,
            line=dict(color="rgba(0,0,0,0.3)", width=1),
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b> (W) vs <b>%{customdata[1]}</b><br>"
            "Kills: %{x} - %{y}<br>"
            "Duration: %{customdata[2]}<extra></extra>"
        ),
        customdata=list(zip(
            scatter_df["winnerName"].fillna("?"),
            scatter_df.apply(
                lambda r: r["team1Name"] if r.get("winnerName") == r.get("team2Name")
                else r.get("team2Name", "?"), axis=1
            ),
            scatter_df["gameDuration"].apply(_fmt_time),
        )),
    ))
    fig.update_layout(
        xaxis=dict(title="Winner Kills", range=[0, max_k], showgrid=True,
                    gridcolor="rgba(30,41,59,0.3)"),
        yaxis=dict(title="Loser Kills", range=[0, max_k], showgrid=True,
                    gridcolor="rgba(30,41,59,0.3)"),
    )
    return fig


def chart_multikill_table(player_stats_df: pd.DataFrame) -> go.Figure:
    """Styled table of multi-kill highlights."""
    if player_stats_df.empty:
        return _base("Multi-Kill Highlights")

    rows = []
    tier_order = {"PENTA": 4, "QUADRA": 3}

    for _, p in player_stats_df.iterrows():
        name = p.get("riotId") or p.get("username") or "?"
        champ = p.get("championName", "?")
        for col, label, tier in [
            ("pentaKills",  "PENTA KILL", "PENTA"),
            ("quadraKills", "QUADRA KILL", "QUADRA"),
        ]:
            count = int(p.get(col, 0) or 0)
            if count > 0:
                rows.append({
                    "Type": label,
                    "Player": name,
                    "Champion": champ,
                    "Count": count,
                    "_tier": tier_order[tier],
                })

    if not rows:
        fig = _base("Multi-Kill Highlights", height=180)
        fig.add_annotation(
            text="No multi-kills this week", showarrow=False,
            font=dict(color=TEXT_MUTED, size=14, family="Barlow Condensed, sans-serif"),
            x=0.5, y=0.5, xref="paper", yref="paper",
        )
        return fig

    rows.sort(key=lambda r: (-r["_tier"], r["Player"]))
    for r in rows:
        del r["_tier"]

    df = pd.DataFrame(rows)

    # Row background based on tier
    tier_bg = {
        "PENTA KILL":  "#332800",
        "QUADRA KILL": "#1a1a2e",
    }
    tier_font = {
        "PENTA KILL":  ACCENT_GOLD,
        "QUADRA KILL": "#c0c0c0",
    }
    fills = [tier_bg.get(t, CARD_BG) for t in df["Type"]]
    fonts = [tier_font.get(t, TEXT_SEC) for t in df["Type"]]

    fig = _base("Multi-Kill Highlights", height=max(220, 40 * len(df) + 60))
    fig.add_trace(go.Table(
        header=dict(
            values=["<b>TYPE</b>", "<b>PLAYER</b>", "<b>CHAMPION</b>", "<b>x</b>"],
            **_TBL_HEADER,
        ),
        cells=dict(
            values=[df["Type"], df["Player"], df["Champion"], df["Count"]],
            fill_color=[fills],
            font=dict(color=[fonts], size=13,
                      family="Barlow Condensed, sans-serif"),
            align="left",
            height=34,
            line_color="#0f172a",
        ),
    ))
    return fig


def chart_what_winners_do(
    team_stats_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    player_stats_df: pd.DataFrame,
) -> go.Figure:
    """Horizontal diverging bar: how much MORE winners get vs losers."""
    if team_stats_df.empty or matches_df.empty:
        return _base("What Winners Do Differently")

    winner_ids = dict(zip(matches_df["id"].astype(str), matches_df["winnerId"].astype(str)))
    ts = team_stats_df.copy()
    ts["matchId"] = ts["matchId"].astype(str)
    ts["teamId"] = ts["teamId"].astype(str)
    ts["is_winner"] = ts.apply(lambda r: winner_ids.get(r["matchId"]) == r["teamId"], axis=1)

    team_metrics = {
        "DRAGONS": "dragons", "BARONS": "barons",
        "TURRETS": "turrets", "KILLS": "kills",
    }

    ps = player_stats_df.copy()
    ps["matchId"] = ps["matchId"].astype(str)
    ps_agg = ps.groupby(["matchId", "win"]).agg(
        gold=("goldEarned", "sum"),
        damage=("totalDamageDealtToChampions", "sum"),
    ).reset_index()

    labels, pct_diffs = [], []

    for label, col in team_metrics.items():
        w_avg = ts[ts["is_winner"]][col].mean()
        l_avg = ts[~ts["is_winner"]][col].mean()
        pct = (w_avg - l_avg) / l_avg * 100 if l_avg > 0 else 0
        labels.append(label)
        pct_diffs.append(pct)

    for label, col in [("GOLD", "gold"), ("DAMAGE", "damage")]:
        w_avg = ps_agg[ps_agg["win"] == 1][col].mean() if not ps_agg.empty else 0
        l_avg = ps_agg[ps_agg["win"] == 0][col].mean() if not ps_agg.empty else 0
        pct = (w_avg - l_avg) / l_avg * 100 if l_avg > 0 else 0
        labels.append(label)
        pct_diffs.append(pct)

    colors_list = [WIN_COLOR if v >= 0 else LOSS_COLOR for v in pct_diffs]

    fig = _base("What Winners Do Differently", height=max(280, 45 * len(labels) + 50))
    fig.add_trace(go.Bar(
        y=labels, x=pct_diffs, orientation="h",
        marker_color=colors_list, marker_line_width=0, opacity=0.85,
        text=[f"+{v:.0f}%" if v >= 0 else f"{v:.0f}%" for v in pct_diffs],
        textposition="outside",
        textfont=dict(size=14, family="Oswald, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Winners get %{x:.0f}% more<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False,
                   zeroline=True, zerolinecolor="rgba(100,116,139,0.5)", zerolinewidth=1),
        yaxis=dict(tickfont=dict(size=14, family="Oswald, sans-serif", color=TEXT_SEC)),
    )
    return fig


def chart_role_impact(
    player_stats_df: pd.DataFrame,
    role_map: dict,
) -> go.Figure:
    """Grouped bar: avg damage share and avg KP per role."""
    if player_stats_df.empty or not role_map:
        return _base("Role Impact")

    ps = player_stats_df.copy()
    ps["summonerId"] = ps["summonerId"].astype(str)
    ps["role"] = ps["summonerId"].map(role_map)
    ps = ps.dropna(subset=["role"])

    if ps.empty:
        return _base("Role Impact")

    role_order = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
    role_labels = {"TOP": "TOP", "JUNGLE": "JGL", "MIDDLE": "MID",
                   "BOTTOM": "ADC", "SUPPORT": "SUP"}

    agg = ps.groupby("role").agg(
        avg_dmg_pct=("teamDamagePercentage", "mean"),
        avg_kp=("killParticipation", "mean"),
    ).reindex(role_order).dropna()

    roles = [role_labels.get(r, r) for r in agg.index]

    fig = _base("Role Impact This Week", height=340, legend_above=True)
    fig.add_trace(go.Bar(
        name="Damage %", x=roles, y=(agg["avg_dmg_pct"] * 100).values,
        marker_color=ACCENT_RED, marker_line_width=0, opacity=0.85,
        text=[f"{v:.0f}%" for v in (agg["avg_dmg_pct"] * 100).values],
        textposition="outside",
        textfont=dict(size=13, family="Oswald, sans-serif", color=ACCENT_RED),
    ))
    fig.add_trace(go.Bar(
        name="Kill Part %", x=roles, y=(agg["avg_kp"] * 100).values,
        marker_color=ACCENT_TEAL, marker_line_width=0, opacity=0.85,
        text=[f"{v:.0f}%" for v in (agg["avg_kp"] * 100).values],
        textposition="outside",
        textfont=dict(size=13, family="Oswald, sans-serif", color=ACCENT_TEAL),
    ))
    fig.update_layout(
        barmode="group",
        yaxis=dict(showticklabels=False, showgrid=False, range=[0, 105]),
        xaxis=dict(tickfont=dict(size=14, family="Oswald, sans-serif", color=TEXT_SEC)),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0.5, xanchor="center"),
    )
    return fig


def chart_champions_by_role(
    player_stats_df: pd.DataFrame,
    role_map: dict,
    top_n: int = 3,
) -> go.Figure:
    """Table showing top picked champions per role with win rates."""
    if player_stats_df.empty or not role_map:
        return _base("Popular Champions by Role")

    ps = player_stats_df.copy()
    ps["summonerId"] = ps["summonerId"].astype(str)
    ps["role"] = ps["summonerId"].map(role_map)
    ps = ps.dropna(subset=["role"])

    if ps.empty:
        return _base("Popular Champions by Role")

    role_order = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
    role_labels = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                   "BOTTOM": "ADC", "SUPPORT": "Support"}

    rows = []
    for role in role_order:
        role_df = ps[ps["role"] == role]
        if role_df.empty:
            continue
        champ_agg = role_df.groupby("championName").agg(
            picks=("win", "count"), wins=("win", "sum")
        ).reset_index()
        champ_agg["wr"] = champ_agg["wins"] / champ_agg["picks"]
        champ_agg = champ_agg.sort_values("picks", ascending=False).head(top_n)
        for _, c in champ_agg.iterrows():
            rows.append({
                "Role": role_labels.get(role, role),
                "Champion": c["championName"],
                "Picks": int(c["picks"]),
                "Win Rate": f"{c['wr']*100:.0f}%",
            })

    if not rows:
        return _base("Popular Champions by Role", height=180)

    df = pd.DataFrame(rows)

    fig = _base("Popular Champions by Role", height=max(220, 35 * len(df) + 70))
    fig.add_trace(go.Table(
        header=dict(
            values=["<b>ROLE</b>", "<b>CHAMPION</b>", "<b>PICKS</b>", "<b>WIN RATE</b>"],
            **_TBL_HEADER,
        ),
        cells=dict(
            values=[df["Role"], df["Champion"], df["Picks"], df["Win Rate"]],
            fill_color=[_alternating_fills(len(df))],
            **_TBL_CELL_BASE,
        ),
    ))
    return fig


# ════════════════════════════════════════════════════════════════════════════
# PLAYER OF THE WEEK
# ════════════════════════════════════════════════════════════════════════════

def chart_impact_factor_bar(top5_df: pd.DataFrame, league_name: str = "") -> go.Figure:
    """Horizontal bar of Impact Factor scores. #1 is gold, rest teal."""
    if top5_df.empty:
        return _base(f"Impact Factor - {league_name}")

    names = [r.get("riotId") or r.get("username") or "?" for _, r in top5_df.iterrows()]
    champs = top5_df["championName"].tolist()
    scores = top5_df["avg_if"].tolist()

    labels = [f"{n}  ({c})" for n, c in zip(names, champs)]
    colors = [ACCENT_GOLD if i == 0 else ACCENT_TEAL for i in range(len(labels))]

    fig = _base(f"Impact Factor - {league_name}", height=max(260, 50 * len(labels) + 70))
    fig.add_trace(go.Bar(
        y=labels[::-1], x=scores[::-1], orientation="h",
        marker_color=colors[::-1], marker_line_width=0, opacity=0.9,
        text=[f"{s:.1f}" for s in scores[::-1]],
        textposition="outside",
        textfont=dict(size=16, family="Oswald, sans-serif"),
        hovertemplate="<b>%{y}</b><br>IF: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(range=[0, 115], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=14, family="Barlow Condensed, sans-serif")),
        transition_duration=400,
    )
    return fig


def chart_pow_radar(top5_df: pd.DataFrame, league_name: str = "") -> go.Figure:
    """Radar chart with 5 axes for top-5 performance comparison."""
    if top5_df.empty:
        return _base(f"Performance Radar - {league_name}")

    axes = ["Kill Part%", "Damage %", "KDA", "Vision/min", "Solo Kills"]
    cols = ["avg_kp", "avg_dmg_pct", "avg_kda", "avg_vision_min", "avg_solo_kills"]

    def _norm(vals):
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return [0.5] * len(vals)
        return [(v - mn) / (mx - mn) for v in vals]

    raw = {c: top5_df[c].tolist() if c in top5_df.columns else [0] * len(top5_df) for c in cols}
    normed = {c: _norm(raw[c]) for c in cols}

    colors = [ACCENT_GOLD, ACCENT_TEAL, ACCENT_RED, ACCENT_BLUE, "#a855f7"]

    fig = _base(f"Performance Radar - {league_name}", height=420)
    for i, (_, row) in enumerate(top5_df.iterrows()):
        name = row.get("riotId") or row.get("username") or "?"
        values = [normed[c][i] for c in cols]
        values.append(values[0])
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=axes + [axes[0]],
            name=f"{name} ({row.get('championName', '?')})",
            line=dict(color=colors[i % len(colors)], width=2),
            fill="toself",
            opacity=0.2 + 0.15 * (4 - i),
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=False, range=[0, 1.1])),
        legend=dict(orientation="h", yanchor="top", y=-0.12, x=0.5, xanchor="center",
                    font=dict(size=11)),
        showlegend=True,
        margin=dict(l=50, r=50, t=56, b=100),
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
# CHAMPION ANALYTICS
# ════════════════════════════════════════════════════════════════════════════

def chart_champion_winrates(champion_df: pd.DataFrame, min_games: int = 2,
                             n: int = 20) -> go.Figure:
    """Horizontal bar chart of win rates, red-to-green gradient."""
    if champion_df.empty:
        return _base("Champion Win Rates")

    if "division" in champion_df.columns:
        agg = champion_df.groupby("championName").agg(
            games=("games", "sum"), wins=("wins", "sum")
        ).reset_index()
        agg["win_rate"] = agg["wins"] / agg["games"]
    else:
        agg = champion_df.copy()

    agg = agg[agg["games"] >= min_games].sort_values("win_rate", ascending=True).tail(n)

    def _wr_color(wr: float) -> str:
        if wr <= 0.5:
            t = wr / 0.5
            r = int(239 + (234 - 239) * t)
            g = int(68 + (179 - 68) * t)
            b = int(68 + (8 - 68) * t)
        else:
            t = (wr - 0.5) / 0.5
            r = int(234 + (16 - 234) * t)
            g = int(179 + (185 - 179) * t)
            b = int(8 + (129 - 8) * t)
        return f"rgb({r},{g},{b})"

    colors = [_wr_color(wr) for wr in agg["win_rate"]]

    fig = _base("Champion Win Rates", height=max(300, 28 * len(agg) + 70))
    fig.add_trace(go.Bar(
        y=agg["championName"], x=agg["win_rate"] * 100, orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=[f"{wr*100:.0f}% ({int(w)}-{int(g-w)})"
              for wr, w, g in zip(agg["win_rate"], agg["wins"], agg["games"])],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Win rate: %{x:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(range=[0, 120], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=13)),
        margin=dict(l=10, r=50, t=56, b=10),
    )
    return fig


def chart_champion_confidence_winrates(champion_df: pd.DataFrame,
                                       min_games: int = 3,
                                       n: int = 15) -> go.Figure:
    """Horizontal bar of sample-size-adjusted win rates (Wilson lower bound).

    Ranks champions by the lower bound of a 95% Wilson confidence interval,
    which naturally penalizes small sample sizes. A 90% WR over 10 games
    ranks higher than 100% over 2 games.
    """
    import math

    if champion_df.empty:
        return _base("Confidence-Adjusted Win Rates")

    if "division" in champion_df.columns:
        agg = champion_df.groupby("championName").agg(
            games=("games", "sum"), wins=("wins", "sum")
        ).reset_index()
    else:
        agg = champion_df.copy()

    agg = agg[agg["games"] >= min_games].copy()
    if agg.empty:
        return _base("Confidence-Adjusted Win Rates", height=180)

    agg["win_rate"] = agg["wins"] / agg["games"]

    # Wilson score lower bound (z=1.96 for 95% CI)
    z = 1.96
    def wilson_lower(w, n_games):
        p = w / n_games
        denom = 1 + z * z / n_games
        centre = p + z * z / (2 * n_games)
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n_games)) / n_games)
        return (centre - spread) / denom

    agg["wilson"] = [wilson_lower(w, g) for w, g in zip(agg["wins"], agg["games"])]
    agg = agg.sort_values("wilson", ascending=True).tail(n)

    def _wr_color(wr: float) -> str:
        if wr <= 0.5:
            t = wr / 0.5
            r = int(239 + (234 - 239) * t)
            g = int(68 + (179 - 68) * t)
            b = int(68 + (8 - 68) * t)
        else:
            t = (wr - 0.5) / 0.5
            r = int(234 + (16 - 234) * t)
            g = int(179 + (185 - 179) * t)
            b = int(8 + (129 - 8) * t)
        return f"rgb({r},{g},{b})"

    colors = [_wr_color(w) for w in agg["wilson"]]

    fig = _base("Confidence-Adjusted Win Rates", height=max(300, 28 * len(agg) + 70))
    fig.add_trace(go.Bar(
        y=agg["championName"], x=agg["wilson"] * 100, orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=[f"{wr*100:.0f}% WR ({int(g)} games)"
              for wr, g in zip(agg["win_rate"], agg["games"])],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif"),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Wilson lower: %{x:.1f}%<br>"
            "%{text}<extra></extra>"
        ),
    ))
    fig.update_layout(
        xaxis=dict(range=[0, 120], showticklabels=False, showgrid=False,
                   title=dict(text="Wilson Lower Bound %",
                              font=dict(size=11, color=TEXT_MUTED))),
        yaxis=dict(tickfont=dict(size=13)),
        margin=dict(l=10, r=60, t=56, b=10),
    )
    return fig


def chart_champion_pickrate_scatter(champion_df: pd.DataFrame,
                                     min_games: int = 1) -> go.Figure:
    """Bubble chart: x=pick rate, y=win rate. Size=games played."""
    if champion_df.empty:
        return _base("Champion Pick Rate vs Win Rate")

    if "division" in champion_df.columns:
        agg = champion_df.groupby("championName").agg(
            games=("games", "sum"), wins=("wins", "sum")
        ).reset_index()
        agg["win_rate"] = agg["wins"] / agg["games"]
    else:
        agg = champion_df.copy()

    total_games = agg["games"].sum() / 10
    agg["pick_rate"] = agg["games"] / max(total_games, 1) * 100
    agg = agg[agg["games"] >= min_games]

    fig = _base("Champion Pick Rate vs Win Rate", height=500)

    top_champs = set(agg.nlargest(10, "games")["championName"])
    text_labels = [name if name in top_champs else "" for name in agg["championName"]]

    fig.add_trace(go.Scatter(
        x=agg["pick_rate"], y=agg["win_rate"] * 100,
        mode="markers+text",
        text=text_labels,
        textposition="top center",
        textfont=dict(size=11, color=TEXT_SEC, family="Barlow Condensed, sans-serif"),
        marker=dict(
            size=agg["games"].clip(4, 25) * 2,
            color=agg["win_rate"] * 100,
            colorscale=[[0, LOSS_COLOR], [0.5, ACCENT_GOLD], [1, WIN_COLOR]],
            showscale=True,
            colorbar=dict(title="Win %", ticksuffix="%",
                          bgcolor="rgba(0,0,0,0)", borderwidth=0),
            opacity=0.85,
            line=dict(color="rgba(0,0,0,0.3)", width=1),
        ),
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            "Pick rate: %{x:.1f}%<br>"
            "Win rate: %{y:.1f}%<extra></extra>"
        ),
        customdata=agg["championName"],
    ))
    med_x = agg["pick_rate"].median()
    fig.add_vline(x=med_x, line=dict(color="rgba(30,41,59,0.5)", dash="dot", width=1))
    fig.add_hline(y=50, line=dict(color="rgba(30,41,59,0.5)", dash="dot", width=1))

    for text, x, y in [
        ("HIGH PICK / HIGH WIN", med_x * 1.4, 78),
        ("LOW PICK / HIGH WIN",  med_x * 0.3, 78),
        ("HIGH PICK / LOW WIN",  med_x * 1.4, 22),
        ("LOW PICK / LOW WIN",   med_x * 0.3, 22),
    ]:
        fig.add_annotation(
            x=x, y=y, text=text, showarrow=False,
            font=dict(color=TEXT_DIM, size=10, family="Oswald, sans-serif"),
            align="center",
        )

    fig.update_layout(
        xaxis=dict(title="Pick Rate %", showgrid=True, gridcolor="rgba(30,41,59,0.3)"),
        yaxis=dict(title="Win Rate %", range=[0, 105], showgrid=True,
                   gridcolor="rgba(30,41,59,0.3)"),
    )
    return fig


def chart_trending_champions(all_time_df: pd.DataFrame,
                               recent_df: pd.DataFrame) -> go.Figure:
    """Grouped bar: recent pick rate vs historical."""
    if all_time_df.empty:
        return _base("Trending Champions")

    def _pick_rate(df):
        total = max(df["games"].sum() / 10, 1)
        df = df.groupby("championName")["games"].sum().reset_index()
        df["pick_rate"] = df["games"] / total * 100
        return df.set_index("championName")["pick_rate"]

    hist_pr = _pick_rate(all_time_df)
    rec_pr  = _pick_rate(recent_df) if not recent_df.empty else pd.Series(dtype=float)

    all_champs = sorted(hist_pr.index.union(rec_pr.index))
    diff_abs = [(abs(rec_pr.get(c, 0) - hist_pr.get(c, 0)), c) for c in all_champs]
    diff_abs.sort(reverse=True)
    top_champs = [c for _, c in diff_abs[:14]]

    h_vals = [hist_pr.get(c, 0) for c in top_champs]
    r_vals = [rec_pr.get(c, 0) for c in top_champs]

    fig = _base("Trending Champions (Recent vs Historical)", height=440, legend_above=True)
    fig.add_trace(go.Bar(
        name="Historical", x=top_champs, y=h_vals,
        marker_color=ACCENT_BLUE, marker_line_width=0, opacity=0.5,
    ))
    fig.add_trace(go.Bar(
        name="Recent (3 wks)", x=top_champs, y=r_vals,
        marker_color=ACCENT_GOLD, marker_line_width=0, opacity=0.9,
    ))
    fig.update_layout(
        barmode="group",
        yaxis=dict(showticklabels=False, showgrid=False),
        xaxis=dict(tickangle=-40, tickfont=dict(size=12, family="Barlow Condensed, sans-serif")),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=72, b=80),
    )
    return fig


def chart_ban_rates(ban_df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Horizontal bar chart of most-banned champions with ban rate %."""
    if ban_df.empty:
        return _base("Most Banned Champions")

    df = ban_df.nlargest(top_n, "bans").sort_values("bans", ascending=True)
    total = df["total_games"].iloc[0] if "total_games" in df.columns else 1

    n = len(df)
    fig = _base("Most Banned Champions", height=max(250, 28 * n + 70))

    # Color gradient: more bans = more red
    max_bans = df["bans"].max()
    colors = []
    for b in df["bans"]:
        ratio = b / max_bans if max_bans > 0 else 0
        r = int(100 + 155 * ratio)
        g = int(120 - 80 * ratio)
        b_c = int(120 - 80 * ratio)
        colors.append(f"rgb({r},{g},{b_c})")

    fig.add_trace(go.Bar(
        y=df["championName"], x=df["bans"], orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=[f"{b}  ({b/total*100:.0f}%)" for b in df["bans"]],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Banned %{x} times<extra></extra>",
    ))

    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed, sans-serif", color=TEXT_SEC)),
    )
    return fig


def chart_ban_overlap(ban_df: pd.DataFrame, champ_df: pd.DataFrame,
                       top_n: int = 12) -> go.Figure:
    """Scatter: ban rate vs pick rate for champions that appear in both datasets."""
    if ban_df.empty or champ_df.empty:
        return _base("Ban Rate vs Pick Rate")

    # Merge ban and pick data
    total_ban_games = ban_df["total_games"].iloc[0] if "total_games" in ban_df.columns else 1
    bans = ban_df[["championName", "bans"]].copy()
    bans["ban_rate"] = bans["bans"] / total_ban_games * 100

    picks = champ_df.groupby("championName").agg(
        games=("games", "sum"),
    ).reset_index()
    total_pick_games = picks["games"].sum() / 10  # ~10 players per game
    picks["pick_rate"] = picks["games"] / total_pick_games * 100

    merged = bans.merge(picks, on="championName", how="outer").fillna(0)
    merged = merged[(merged["ban_rate"] > 0) | (merged["pick_rate"] > 5)]

    if merged.empty:
        return _base("Ban Rate vs Pick Rate")

    fig = _base("Ban Rate vs Pick Rate", height=400)
    fig.add_trace(go.Scatter(
        x=merged["pick_rate"], y=merged["ban_rate"],
        mode="markers+text",
        text=merged["championName"],
        textposition="top center",
        textfont=dict(size=10, family="Barlow Condensed, sans-serif", color=TEXT_SEC),
        marker=dict(
            size=merged["games"].clip(4, 20) * 1.5,
            color=ACCENT_RED, opacity=0.7,
            line=dict(color=ACCENT_GOLD, width=1),
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Pick Rate: %{x:.1f}%<br>"
            "Ban Rate: %{y:.1f}%<extra></extra>"
        ),
    ))

    fig.update_layout(
        xaxis=dict(title="Pick Rate %", title_font=dict(size=12, family="Oswald, sans-serif")),
        yaxis=dict(title="Ban Rate %", title_font=dict(size=12, family="Oswald, sans-serif")),
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
# ELO STANDINGS
# ════════════════════════════════════════════════════════════════════════════

def chart_elo_standings(standings_df: pd.DataFrame,
                         team_colors: dict = None) -> go.Figure:
    """Horizontal bar of Elo ratings, sorted highest to lowest."""
    if standings_df.empty:
        return _base("Elo Standings")

    team_colors = team_colors or {}
    df = standings_df.sort_values("elo", ascending=True)

    colors = [team_colors.get(tid, TEAM_PALETTE[i % len(TEAM_PALETTE)])
              for i, tid in enumerate(df["team_id"])]

    fig = _base("Elo Standings", height=max(320, 45 * len(df) + 70))
    fig.add_trace(go.Bar(
        y=df["name"], x=df["elo"], orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=df["elo"].apply(lambda v: f"{v:.0f}"),
        textposition="outside",
        textfont=dict(size=15, family="Oswald, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Elo: %{x:.0f}<extra></extra>",
    ))
    fig.add_vline(
        x=1200, line=dict(color="rgba(100,116,139,0.4)", dash="dot", width=1),
        annotation_text="1200",
        annotation_font=dict(color=TEXT_DIM, size=11, family="Barlow Condensed, sans-serif"),
    )
    elo_min = max(900, df["elo"].min() - 30)
    elo_max = df["elo"].max() + 50
    fig.update_layout(
        xaxis=dict(range=[elo_min, elo_max], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=14, family="Barlow Condensed, sans-serif")),
    )
    return fig


def chart_elo_history(history_df: pd.DataFrame,
                       team_colors: dict = None,
                       visible_teams: list = None,
                       highlight_n: int = 4) -> go.Figure:
    """Line chart of Elo over time. Top teams highlighted, rest faded.
    Direct labels on line endpoints instead of cluttered legend."""
    if history_df.empty:
        return _base("Elo Over Time")

    team_colors = team_colors or {}
    fig = _base("Elo Over Time", height=480)

    teams = history_df["name"].unique()
    if visible_teams:
        teams = [t for t in teams if t in visible_teams]

    # Determine which teams to highlight (top N by final Elo)
    max_week = history_df["week"].max()
    final_elos = (
        history_df[history_df["week"] == max_week]
        .sort_values("elo", ascending=False)
    )
    highlight_names = set(final_elos["name"].head(highlight_n).tolist())
    # Also highlight bottom 1 for contrast
    if len(final_elos) > highlight_n:
        highlight_names.add(final_elos["name"].iloc[-1])

    for i, team_name in enumerate(teams):
        sub = history_df[history_df["name"] == team_name].sort_values("week")
        tid = sub["team_id"].iloc[0] if not sub.empty else ""
        color = team_colors.get(tid, TEAM_PALETTE[i % len(TEAM_PALETTE)])
        is_highlight = team_name in highlight_names

        fig.add_trace(go.Scatter(
            x=sub["week"], y=sub["elo"],
            mode="lines+markers" if is_highlight else "lines",
            name=team_name,
            line=dict(
                color=color, width=3 if is_highlight else 1.5,
            ),
            opacity=1.0 if is_highlight else 0.3,
            marker=dict(size=7, color=color) if is_highlight else dict(size=0),
            showlegend=False,
            hovertemplate=(
                f"<b>{team_name}</b><br>"
                "Week %{x}<br>"
                "Elo: %{y:.0f}<extra></extra>"
            ),
        ))

        # Direct label at end of line for highlighted teams
        if is_highlight and not sub.empty:
            last = sub.iloc[-1]
            fig.add_annotation(
                x=last["week"], y=last["elo"],
                text=f"<b>{team_name}</b> {last['elo']:.0f}",
                font=dict(size=11, color=color, family="Barlow Condensed"),
                showarrow=False, xanchor="left", xshift=8,
            )

    fig.add_hline(y=1200, line=dict(color="rgba(100,116,139,0.3)", dash="dash", width=1))
    weeks = sorted(history_df["week"].unique())
    fig.update_layout(
        xaxis=dict(
            title="",
            tickvals=weeks,
            ticktext=[f"W{int(w)}" if w > 0 else "START" for w in weeks],
            showgrid=True, gridcolor="rgba(30,41,59,0.3)",
            tickfont=dict(size=12, family="Oswald, sans-serif"),
        ),
        yaxis=dict(title="", showgrid=True, gridcolor="rgba(30,41,59,0.3)"),
        margin=dict(l=10, r=120, t=56, b=30),
        transition_duration=400,
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
# SEASON OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

def chart_team_records(records_df: pd.DataFrame, team_colors: dict = None) -> go.Figure:
    """Team standings table."""
    if records_df.empty:
        return _base("Team Standings")

    def _dur(s):
        try:
            m, sec = divmod(int(s), 60)
            return f"{m}:{sec:02d}"
        except:
            return "?"

    df = records_df.copy()
    df["Record"] = df.apply(lambda r: f"{int(r['series_wins'])}-{int(r['series_losses'])}", axis=1)
    df["Game W-L"] = df.apply(lambda r: f"{int(r['game_wins'])}-{int(r['game_losses'])}", axis=1)
    df["Win%"] = (df["win_pct"] * 100).apply(lambda v: f"{v:.0f}%")
    df["Avg Dur"] = df["avg_duration_s"].apply(_dur)

    fig = _base("Team Standings", height=max(280, 40 * len(df) + 70))
    fig.add_trace(go.Table(
        header=dict(
            values=["<b>TEAM</b>", "<b>SERIES</b>", "<b>GAMES</b>", "<b>WIN%</b>",
                    "<b>KILLS</b>", "<b>DEATHS</b>", "<b>DRAGONS</b>",
                    "<b>BARONS</b>", "<b>TURRETS</b>", "<b>AVG DUR</b>"],
            **_TBL_HEADER,
        ),
        cells=dict(
            values=[
                df["name"], df["Record"], df["Game W-L"], df["Win%"],
                df["avg_kills"], df["avg_deaths"], df["avg_dragons"],
                df["avg_barons"], df["avg_turrets"], df["Avg Dur"],
            ],
            fill_color=[_alternating_fills(len(df))],
            **_TBL_CELL_BASE,
        ),
    ))
    return fig


def chart_player_leaderboard(player_stats_df: pd.DataFrame, role_map: dict = None) -> go.Figure:
    """Multi-category leaderboard: top 5 in each stat category."""
    if player_stats_df.empty:
        return _base("Player Leaderboards")

    df = player_stats_df.copy()
    for col in ["kills", "deaths", "assists", "cs", "gameDuration", "visionScore",
                "soloKills", "totalDamageDealtToChampions", "goldEarned"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["kda"] = (df["kills"] + df["assists"]) / df["deaths"].clip(lower=1)
    game_mins = (df["gameDuration"] / 60).clip(lower=1)
    df["cs_per_min"] = df["cs"] / game_mins
    df["vision_per_min"] = df["visionScore"] / game_mins
    df["dmg_per_min"] = df["totalDamageDealtToChampions"] / game_mins
    df["gold_per_min"] = df["goldEarned"] / game_mins

    id_col = "summonerId" if "summonerId" in df.columns else "username"
    df["display_name"] = df.apply(
        lambda r: r.get("riotId") or r.get("username") or "?", axis=1)

    player_agg = df.groupby([id_col, "display_name"]).agg(
        games=("kda", "count"),
        avg_kda=("kda", "mean"),
        avg_cs_min=("cs_per_min", "mean"),
        avg_dmg_min=("dmg_per_min", "mean"),
        avg_vision_min=("vision_per_min", "mean"),
        total_solo_kills=("soloKills", "sum"),
        avg_gold_min=("gold_per_min", "mean"),
    ).reset_index()

    player_agg = player_agg[player_agg["games"] >= 2]

    if player_agg.empty:
        return _base("Player Leaderboards", height=180)

    categories = [
        ("KDA", "avg_kda", "{:.2f}"),
        ("CS/MIN", "avg_cs_min", "{:.1f}"),
        ("DMG/MIN", "avg_dmg_min", "{:.0f}"),
        ("VISION/MIN", "avg_vision_min", "{:.1f}"),
        ("GOLD/MIN", "avg_gold_min", "{:.0f}"),
        ("SOLO KILLS", "total_solo_kills", "{:.0f}"),
    ]

    cat_names, player_names, values = [], [], []
    for cat_label, col, fmt in categories:
        top3 = player_agg.nlargest(3, col)
        for rank, (_, row) in enumerate(top3.iterrows()):
            medal = ["1st", "2nd", "3rd"][rank]
            cat_names.append(cat_label)
            player_names.append(f"{medal}  {row['display_name']}")
            values.append(fmt.format(row[col]))

    result_df = pd.DataFrame({"Category": cat_names, "Player": player_names, "Value": values})

    fig = _base("Player Leaderboards", height=max(300, 30 * len(result_df) + 70))
    fig.add_trace(go.Table(
        header=dict(
            values=["<b>CATEGORY</b>", "<b>PLAYER</b>", "<b>VALUE</b>"],
            **_TBL_HEADER,
        ),
        cells=dict(
            values=[result_df["Category"], result_df["Player"], result_df["Value"]],
            fill_color=[_alternating_fills(len(result_df))],
            **_TBL_CELL_BASE,
        ),
    ))
    return fig


def chart_pow_history(pow_history: list) -> go.Figure:
    """Timeline table showing Player of the Week winners across all weeks.
    pow_history: list of dicts with keys: week, player_name, champion, score
    """
    if not pow_history:
        return _base("Player of the Week History", height=180)

    weeks = [str(int(h["week"])) for h in pow_history]
    players = [h["player_name"] for h in pow_history]
    champs = [h["champion"] for h in pow_history]
    scores = [f"{h['score']:.1f}" for h in pow_history]

    # Count repeat winners
    from collections import Counter
    win_counts = Counter(players)
    badges = []
    for p in players:
        count = win_counts[p]
        badges.append(f"{p} ({count}x)" if count > 1 else p)

    n = len(pow_history)
    fig = _base("Player of the Week History", height=max(200, 38 * n + 60))

    fig.add_trace(go.Table(
        columnwidth=[60, 180, 100, 70],
        header=dict(
            values=["<b>WEEK</b>", "<b>PLAYER</b>", "<b>CHAMPION</b>", "<b>IF</b>"],
            **_TBL_HEADER,
        ),
        cells=dict(
            values=[weeks, badges, champs, scores],
            fill_color=[
                ["rgba(255,215,0,0.15)"] * n,
                _alternating_fills(n),
                _alternating_fills(n),
                _alternating_fills(n),
            ],
            font=dict(color=TEXT_MAIN, size=13, family="Barlow Condensed, sans-serif"),
            align=["center", "left", "left", "center"],
            height=34,
            line_color="#0f172a",
        ),
    ))
    fig.update_layout(margin=dict(l=0, r=0, t=56, b=0))
    return fig


def chart_draft_diversity(diversity_df: pd.DataFrame, team_colors: dict = None) -> go.Figure:
    """Horizontal bar: unique champions per team."""
    if diversity_df.empty:
        return _base("Draft Diversity")

    team_colors = team_colors or {}
    df = diversity_df.sort_values("unique_champs", ascending=True)

    colors = [team_colors.get(tid, TEAM_PALETTE[i % len(TEAM_PALETTE)])
              for i, tid in enumerate(df["teamId"])]

    fig = _base("Draft Diversity", height=max(280, 45 * len(df) + 70))
    fig.add_trace(go.Bar(
        y=df["name"], x=df["unique_champs"], orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=df["unique_champs"].apply(lambda v: f"{int(v)} champs"),
        textposition="outside",
        textfont=dict(size=14, family="Oswald, sans-serif"),
        hovertemplate="<b>%{y}</b><br>%{x} unique champions<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=14, family="Barlow Condensed, sans-serif")),
    )
    return fig


def chart_early_game(early_df: pd.DataFrame, team_colors: dict = None) -> go.Figure:
    """Grouped bar: First Blood rate and First Tower rate per team."""
    if early_df.empty:
        return _base("Early Game")

    team_colors = team_colors or {}
    df = early_df.sort_values("fb_rate", ascending=True)

    fig = _base("Early Game Dominance", height=max(300, 50 * len(df) + 70), legend_above=True)
    fig.add_trace(go.Bar(
        name="First Blood %",
        y=df["name"], x=(df["fb_rate"] * 100), orientation="h",
        marker_color=ACCENT_RED, marker_line_width=0, opacity=0.85,
        text=[f"{v:.0f}%" for v in df["fb_rate"] * 100],
        textposition="outside",
        textfont=dict(size=13, family="Oswald, sans-serif", color=ACCENT_RED),
    ))
    fig.add_trace(go.Bar(
        name="First Tower %",
        y=df["name"], x=(df["ft_rate"] * 100), orientation="h",
        marker_color=ACCENT_TEAL, marker_line_width=0, opacity=0.85,
        text=[f"{v:.0f}%" for v in df["ft_rate"] * 100],
        textposition="outside",
        textfont=dict(size=13, family="Oswald, sans-serif", color=ACCENT_TEAL),
    ))
    fig.update_layout(
        barmode="group",
        xaxis=dict(showticklabels=False, showgrid=False, range=[0, 120]),
        yaxis=dict(tickfont=dict(size=14, family="Barlow Condensed, sans-serif")),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0.5, xanchor="center"),
    )
    return fig


def chart_weekly_superlatives(player_stats_df: pd.DataFrame) -> go.Figure:
    """Broadcast-style table of weekly 'awards' — fun stats superlatives."""
    if player_stats_df.empty:
        return _base("Week Superlatives", height=180)

    ps = player_stats_df.copy()
    for col in ["skillshotsHit", "skillshotsDodged", "wardsPlaced",
                 "damageSelfMitigated", "totalHealsOnTeammates",
                 "epicMonsterSteals", "survivedSingleDigitHpCount", "totalPings"]:
        if col in ps.columns:
            ps[col] = pd.to_numeric(ps[col], errors="coerce").fillna(0)

    def _player_name(row):
        return row.get("riotId") or row.get("username") or "?"

    # Define superlatives: (award_name, column, format_fn, emoji_label)
    superlatives = [
        ("Sharpshooter", "skillshotsHit", lambda v: f"{int(v)} skillshots hit"),
        ("Dodgeball Champ", "skillshotsDodged", lambda v: f"{int(v)} skillshots dodged"),
        ("Meat Shield", "damageSelfMitigated", lambda v: f"{int(v):,} dmg mitigated"),
        ("Ward Master", "wardsPlaced", lambda v: f"{int(v)} wards placed"),
        ("Team Medic", "totalHealsOnTeammates", lambda v: f"{int(v):,} healing"),
        ("Clutch Survivor", "survivedSingleDigitHpCount", lambda v: f"{int(v)} close call(s)"),
        ("Smite Thief", "epicMonsterSteals", lambda v: f"{int(v)} steal(s)"),
    ]

    awards, players, champs, stats = [], [], [], []
    for award_name, col, fmt_fn in superlatives:
        if col not in ps.columns:
            continue
        valid = ps[ps[col] > 0]
        if valid.empty:
            continue
        top = valid.loc[valid[col].idxmax()]
        awards.append(award_name)
        players.append(_player_name(top))
        champs.append(top.get("championName", "?"))
        stats.append(fmt_fn(top[col]))

    if not awards:
        return _base("Week Superlatives", height=180)

    n = len(awards)
    fig = _base("Week Superlatives", height=max(200, 38 * n + 60))

    # Award colors: alternate gold/teal accent
    award_colors = [ACCENT_GOLD if i % 2 == 0 else ACCENT_TEAL for i in range(n)]

    # Wrap award names in bold for emphasis
    styled_awards = [f"<b>{a}</b>" for a in awards]

    fig.add_trace(go.Table(
        columnwidth=[120, 150, 100, 180],
        header=dict(
            values=["<b>AWARD</b>", "<b>PLAYER</b>", "<b>CHAMPION</b>", "<b>STAT</b>"],
            **_TBL_HEADER,
        ),
        cells=dict(
            values=[styled_awards, players, champs, stats],
            fill_color=[
                award_colors,
                [CARD_BG] * n,
                [CARD_BG] * n,
                [CARD_BG] * n,
            ],
            font=dict(
                color=[[("#080b12" if i % 2 == 0 else "#080b12") for i in range(n)],
                       [TEXT_MAIN] * n, [TEXT_SEC] * n, [TEXT_MAIN] * n],
                size=12,
                family="Barlow Condensed, sans-serif",
            ),
            align=["center", "left", "left", "left"],
            height=34,
            line_color="#0f172a",
        ),
    ))

    fig.update_layout(margin=dict(l=0, r=0, t=56, b=0))
    return fig


def chart_gold_economy(player_stats_df: pd.DataFrame, role_map: dict = None) -> go.Figure:
    """Two-panel: Winners vs Losers avg gold, and gold share by role."""
    if player_stats_df.empty:
        return _base("Gold Economy")

    from plotly.subplots import make_subplots

    ps = player_stats_df.copy()
    for col in ["goldEarned", "totalDamageDealtToChampions", "gameDuration"]:
        if col in ps.columns:
            ps[col] = pd.to_numeric(ps[col], errors="coerce").fillna(0)

    game_mins = (ps["gameDuration"] / 60).clip(lower=1)
    ps["gold_per_min"] = ps["goldEarned"] / game_mins

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("GOLD/MIN: WINNERS VS LOSERS", "GOLD SHARE BY ROLE"),
        horizontal_spacing=0.15,
    )
    apply_template(fig)
    fig.update_layout(height=380, margin=dict(t=72))
    fig.update_annotations(font=dict(
        size=13, color=TEXT_SEC, family="Oswald, sans-serif",
    ))

    w_gold = ps[ps["win"] == 1]["gold_per_min"].mean()
    l_gold = ps[ps["win"] == 0]["gold_per_min"].mean()

    fig.add_trace(go.Bar(
        x=["Winners", "Losers"], y=[w_gold, l_gold],
        marker_color=[WIN_COLOR, LOSS_COLOR], marker_line_width=0, opacity=0.9,
        text=[f"{w_gold:.0f}", f"{l_gold:.0f}"],
        textposition="outside",
        textfont=dict(size=16, family="Oswald, sans-serif"),
        showlegend=False,
    ), row=1, col=1)

    if role_map:
        ps["summonerId"] = ps["summonerId"].astype(str)
        ps["role"] = ps["summonerId"].map(role_map)
        role_df = ps.dropna(subset=["role"])

        if not role_df.empty:
            team_gold = role_df.groupby("matchId")["goldEarned"].transform("sum")
            role_df = role_df.copy()
            role_df["gold_share"] = role_df["goldEarned"] / team_gold.clip(lower=1)

            role_order = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
            role_labels = {"TOP": "TOP", "JUNGLE": "JGL", "MIDDLE": "MID",
                           "BOTTOM": "ADC", "SUPPORT": "SUP"}
            role_colors = [ACCENT_RED, "#14b8a6", ACCENT_BLUE, ACCENT_GOLD, "#a855f7"]

            shares = []
            for role in role_order:
                r_df = role_df[role_df["role"] == role]
                shares.append(r_df["gold_share"].mean() * 100 if not r_df.empty else 0)

            fig.add_trace(go.Bar(
                x=[role_labels.get(r, r) for r in role_order],
                y=shares,
                marker_color=role_colors, marker_line_width=0, opacity=0.9,
                text=[f"{v:.0f}%" for v in shares],
                textposition="outside",
                textfont=dict(size=14, family="Oswald, sans-serif"),
                showlegend=False,
            ), row=1, col=2)

    fig.update_xaxes(tickfont=dict(size=13, family="Oswald, sans-serif", color=TEXT_SEC))
    fig.update_yaxes(showticklabels=False, showgrid=False)

    return fig


def chart_damage_composition(
    player_stats_df: pd.DataFrame,
    team_stats_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> go.Figure:
    """Stacked bar showing Physical / Magic / True damage split per team."""
    if player_stats_df.empty or team_stats_df.empty:
        return _base("Damage Composition")

    ps = player_stats_df.copy()
    for col in ["magicDamageDealtToChampions", "physicalDamageDealtToChampions",
                 "trueDamageDealtToChampions"]:
        if col in ps.columns:
            ps[col] = pd.to_numeric(ps[col], errors="coerce").fillna(0)

    # Map in-game teamId (100/200) to beer league team name via team_stats
    ts = team_stats_df.copy()
    ts["matchId"] = ts["matchId"].astype(str)
    ts["teamId"] = ts["teamId"].astype(str)
    ps["matchId"] = ps["matchId"].astype(str)
    ps["teamId"] = ps["teamId"].astype(str)

    # team_stats has beer league teamName; join via matchId
    # For each match, team_stats rows have teamId (beer league) and teamName
    # player_stats teamId is 100/200; we need to figure out which beer team = which side
    # Use kills total to match: sum player kills per side, match to team_stats kills
    side_kills = ps.groupby(["matchId", "teamId"])["kills"].sum().reset_index()
    side_kills.rename(columns={"kills": "side_kills", "teamId": "side"}, inplace=True)

    ts_lookup = ts[["matchId", "teamId", "teamName", "kills"]].copy()
    ts_lookup["kills"] = pd.to_numeric(ts_lookup["kills"], errors="coerce").fillna(0)

    # For each match, find the side (100/200) that matches each beer team's kill count
    side_to_team = {}
    for mid in side_kills["matchId"].unique():
        sk = side_kills[side_kills["matchId"] == mid]
        tl = ts_lookup[ts_lookup["matchId"] == mid]
        for _, sr in sk.iterrows():
            best = None
            best_diff = float("inf")
            for _, tr in tl.iterrows():
                diff = abs(sr["side_kills"] - tr["kills"])
                if diff < best_diff:
                    best_diff = diff
                    best = tr["teamName"]
            if best:
                side_to_team[(mid, sr["side"])] = best

    ps["team_name"] = ps.apply(
        lambda r: side_to_team.get((r["matchId"], r["teamId"]), "Unknown"), axis=1)

    # Aggregate damage by team
    agg = ps.groupby("team_name").agg(
        physical=("physicalDamageDealtToChampions", "sum"),
        magic=("magicDamageDealtToChampions", "sum"),
        true_dmg=("trueDamageDealtToChampions", "sum"),
    ).reset_index()
    agg = agg[agg["team_name"] != "Unknown"]
    if agg.empty:
        return _base("Damage Composition")

    agg["total"] = agg["physical"] + agg["magic"] + agg["true_dmg"]
    agg = agg.sort_values("total", ascending=True)

    # Convert to percentages
    agg["phys_pct"] = (agg["physical"] / agg["total"] * 100).round(1)
    agg["magic_pct"] = (agg["magic"] / agg["total"] * 100).round(1)
    agg["true_pct"] = (agg["true_dmg"] / agg["total"] * 100).round(1)

    n = len(agg)
    fig = _base("Damage Composition", height=max(200, 45 * n + 70))

    fig.add_trace(go.Bar(
        y=agg["team_name"], x=agg["phys_pct"], orientation="h",
        name="Physical", marker_color="#ef4444", marker_line_width=0,
        text=[f"{v:.0f}%" for v in agg["phys_pct"]],
        textposition="inside", textfont=dict(size=11, family="Oswald, sans-serif"),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(
        y=agg["team_name"], x=agg["magic_pct"], orientation="h",
        name="Magic", marker_color="#3b82f6", marker_line_width=0,
        text=[f"{v:.0f}%" for v in agg["magic_pct"]],
        textposition="inside", textfont=dict(size=11, family="Oswald, sans-serif"),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(
        y=agg["team_name"], x=agg["true_pct"], orientation="h",
        name="True", marker_color="#f5f5f5", marker_line_width=0,
        text=[f"{v:.0f}%" if v >= 5 else "" for v in agg["true_pct"]],
        textposition="inside",
        textfont=dict(size=11, family="Oswald, sans-serif", color="#080b12"),
        hoverinfo="skip",
    ))

    fig.update_layout(
        barmode="stack",
        xaxis=dict(range=[0, 100], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed, sans-serif", color=TEXT_SEC)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    return fig


def chart_elo_standings_with_delta(standings_df: pd.DataFrame,
                                     prev_standings_df: pd.DataFrame = None,
                                     team_colors: dict = None) -> go.Figure:
    """Horizontal bar of Elo ratings with delta annotations."""
    if standings_df.empty:
        return _base("Elo Standings")

    team_colors = team_colors or {}
    df = standings_df.sort_values("elo", ascending=True).copy()

    if prev_standings_df is not None and not prev_standings_df.empty:
        prev_map = dict(zip(prev_standings_df["team_id"].astype(str), prev_standings_df["elo"]))
        prev_rank_map = {}
        prev_sorted = prev_standings_df.sort_values("elo", ascending=False).reset_index(drop=True)
        for i, row in prev_sorted.iterrows():
            prev_rank_map[str(row["team_id"])] = i + 1

        df["prev_elo"] = df["team_id"].map(prev_map)
        df["elo_delta"] = df["elo"] - df["prev_elo"].fillna(df["elo"])

        curr_sorted = standings_df.sort_values("elo", ascending=False).reset_index(drop=True)
        curr_rank_map = {}
        for i, row in curr_sorted.iterrows():
            curr_rank_map[str(row["team_id"])] = i + 1
        df["rank_delta"] = df["team_id"].map(
            lambda tid: (prev_rank_map.get(tid, curr_rank_map.get(tid, 0)) -
                        curr_rank_map.get(tid, 0)))
    else:
        df["elo_delta"] = 0
        df["rank_delta"] = 0

    colors = [team_colors.get(tid, TEAM_PALETTE[i % len(TEAM_PALETTE)])
              for i, tid in enumerate(df["team_id"])]

    texts = []
    for _, row in df.iterrows():
        elo_str = f"{row['elo']:.0f}"
        delta = row["elo_delta"]
        if delta != 0:
            arrow = "^" if delta > 0 else "v"
            elo_str += f"  ({arrow}{abs(delta):.0f})"
        texts.append(elo_str)

    fig = _base("Elo Standings", height=max(320, 45 * len(df) + 70))
    fig.add_trace(go.Bar(
        y=df["name"], x=df["elo"], orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=texts,
        textposition="outside",
        textfont=dict(size=15, family="Oswald, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Elo: %{x:.0f}<extra></extra>",
    ))
    fig.add_vline(
        x=1200, line=dict(color="rgba(100,116,139,0.4)", dash="dot", width=1),
        annotation_text="1200",
        annotation_font=dict(color=TEXT_DIM, size=11),
    )
    elo_min = max(900, df["elo"].min() - 30)
    elo_max = df["elo"].max() + 80
    fig.update_layout(
        xaxis=dict(range=[elo_min, elo_max], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=14, family="Barlow Condensed, sans-serif")),
        transition_duration=400,
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
# UPCOMING MATCHUPS
# ════════════════════════════════════════════════════════════════════════════

def chart_win_probability(
    team_a_name: str, team_b_name: str,
    prob_a: float,
    color_a: str = ACCENT_TEAL,
    color_b: str = ACCENT_RED,
) -> go.Figure:
    """Compact stacked horizontal bar showing win probability split."""
    prob_b = 1.0 - prob_a
    pct_a = round(prob_a * 100, 1)
    pct_b = round(prob_b * 100, 1)

    # Use white text with dark outline for readability on any bar color
    _font = dict(color="#fff", size=12, family="Oswald, sans-serif")
    _outline = dict(color="#000", width=1)

    fig = _base("", height=50)
    fig.add_trace(go.Bar(
        y=[""], x=[pct_a], orientation="h",
        name=team_a_name, marker_color=color_a, marker_line_width=0,
        text=[f"{team_a_name}  {pct_a:.0f}%"],
        textposition="inside",
        insidetextanchor="middle",
        textfont=_font,
        outsidetextfont=_font,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(
        y=[""], x=[pct_b], orientation="h",
        name=team_b_name, marker_color=color_b, marker_line_width=0,
        text=[f"{pct_b:.0f}%  {team_b_name}"],
        textposition="inside",
        insidetextanchor="middle",
        textfont=_font,
        outsidetextfont=_font,
        hoverinfo="skip",
    ))
    fig.update_layout(
        barmode="stack",
        xaxis=dict(range=[0, 100], showticklabels=False, showgrid=False),
        yaxis=dict(showticklabels=False),
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        bargap=0,
    )
    return fig


# ════════════════════════════════════════════════════════════════════════════
# ITEM ANALYTICS
# ════════════════════════════════════════════════════════════════════════════

def chart_item_winrates(item_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    """Horizontal bar of item win rates, filtered to completed items with min 5 builds."""
    if item_df.empty:
        return _base("Item Win Rates")

    df = item_df[item_df["games"] >= 5].copy()
    if df.empty:
        return _base("Item Win Rates (min 5 builds)", height=180)

    df = df.sort_values("win_rate", ascending=True).tail(top_n)

    def _wr_color(wr: float) -> str:
        if wr <= 0.5:
            t = wr / 0.5
            r = int(239 + (234 - 239) * t)
            g = int(68 + (179 - 68) * t)
            b = int(68 + (8 - 68) * t)
        else:
            t = (wr - 0.5) / 0.5
            r = int(234 + (16 - 234) * t)
            g = int(179 + (185 - 179) * t)
            b = int(8 + (129 - 8) * t)
        return f"rgb({r},{g},{b})"

    colors = [_wr_color(wr) for wr in df["win_rate"]]

    fig = _base("Item Win Rates", height=max(300, 28 * len(df) + 70))
    fig.add_trace(go.Bar(
        y=df["item_name"], x=df["win_rate"] * 100, orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=[f"{wr*100:.0f}%  ({int(g)} built)"
              for wr, g in zip(df["win_rate"], df["games"])],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Win rate: %{x:.1f}%<br>%{customdata} builds<extra></extra>",
        customdata=df["games"],
    ))
    fig.update_layout(
        xaxis=dict(range=[0, 120], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=13, family="Barlow Condensed, sans-serif")),
        margin=dict(l=10, r=60, t=56, b=10),
    )
    return fig


def chart_ping_stats(player_stats_df: pd.DataFrame) -> go.Figure:
    """Fun 'communication style' chart — who pinged the most and what kind."""
    ps = player_stats_df.copy()
    ping_cols = {
        "totalPings": "Total Pings",
        "enemyMissingPings": "MIA Pings",
        "enemyVisionPings": "Vision Pings",
        "getBackPings": "Get Back Pings",
        "holdPings": "Hold Pings",
    }

    available = [c for c in ping_cols if c in ps.columns]
    if not available:
        return _base("Ping Data Unavailable", height=180)

    for col in available:
        ps[col] = pd.to_numeric(ps[col], errors="coerce").fillna(0)

    ps["player"] = ps.apply(
        lambda r: r.get("riotId") or r.get("username") or "?", axis=1)

    # Aggregate per player
    agg = ps.groupby("player")[available].sum().reset_index()
    agg["totalPings"] = agg[available].sum(axis=1) if "totalPings" not in available else agg["totalPings"]
    agg = agg.sort_values("totalPings", ascending=True).tail(10)

    if agg.empty:
        return _base("Ping Stats", height=180)

    # Stacked bar of ping types (exclude totalPings, use the sub-types)
    sub_cols = [c for c in available if c != "totalPings"]
    colors = {"enemyMissingPings": "#ef4444", "enemyVisionPings": "#3b82f6",
              "getBackPings": "#f59e0b", "holdPings": "#10b981"}

    fig = _base("Comms Check: Ping Leaders", height=max(260, 32 * len(agg) + 70))

    if sub_cols:
        for col in sub_cols:
            fig.add_trace(go.Bar(
                y=agg["player"], x=agg[col], orientation="h",
                name=ping_cols.get(col, col),
                marker_color=colors.get(col, TEXT_MUTED),
                marker_line_width=0,
                hovertemplate=f"<b>%{{y}}</b><br>{ping_cols.get(col, col)}: %{{x}}<extra></extra>",
            ))
        fig.update_layout(barmode="stack")
    else:
        fig.add_trace(go.Bar(
            y=agg["player"], x=agg["totalPings"], orientation="h",
            marker_color=ACCENT_GOLD, marker_line_width=0,
            text=[f"{int(v)}" for v in agg["totalPings"]],
            textposition="outside",
            textfont=dict(size=12, family="Barlow Condensed, sans-serif"),
        ))

    fig.update_layout(
        xaxis=dict(title_text="Pings", showgrid=False),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed, sans-serif")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    return fig


def chart_most_built_items(item_df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Horizontal bar of most frequently built items."""
    if item_df.empty:
        return _base("Most Built Items")

    df = item_df.head(top_n).sort_values("games", ascending=True)

    # Color by win rate
    colors = [WIN_COLOR if wr > 0.5 else LOSS_COLOR if wr < 0.45 else ACCENT_GOLD
              for wr in df["win_rate"]]

    fig = _base("Most Built Items", height=max(300, 28 * len(df) + 70))
    fig.add_trace(go.Bar(
        y=df["item_name"], x=df["games"], orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.9,
        text=[f"{int(g)}  ({wr*100:.0f}% WR)"
              for g, wr in zip(df["games"], df["win_rate"])],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif"),
        hovertemplate="<b>%{y}</b><br>%{x} builds<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=13, family="Barlow Condensed, sans-serif")),
        margin=dict(l=10, r=60, t=56, b=10),
    )
    return fig


# -- Blue / Red Side ---------------------------------------------------------

def chart_side_winrate(player_stats_df: pd.DataFrame) -> go.Figure:
    """Donut chart showing blue (100) vs red (200) side win rates."""
    ps = player_stats_df.copy()
    if ps.empty or "teamId" not in ps.columns:
        return _base("Side Win Rates", height=260)

    # Deduplicate to one row per player per game, then pick one per side per match
    ps["teamId"] = ps["teamId"].astype(str)
    ps["win"] = pd.to_numeric(ps["win"], errors="coerce").fillna(0).astype(int)

    # One row per (matchId, side)
    sides = ps.groupby(["matchId", "teamId"])["win"].first().reset_index()
    blue = sides[sides["teamId"] == "100"]
    red = sides[sides["teamId"] == "200"]

    blue_wins = int(blue["win"].sum())
    blue_total = len(blue)
    red_wins = int(red["win"].sum())
    red_total = len(red)

    if blue_total == 0 and red_total == 0:
        return _base("Side Win Rates", height=260)

    blue_wr = blue_wins / blue_total if blue_total else 0
    red_wr = red_wins / red_total if red_total else 0

    fig = _base("Blue vs Red Side", height=280)
    fig.add_trace(go.Pie(
        labels=["Blue Side", "Red Side"],
        values=[blue_wins, red_wins],
        marker=dict(colors=["#3b82f6", "#ef4444"]),
        hole=0.55,
        textinfo="label+percent",
        textfont=dict(size=14, family="Barlow Condensed, sans-serif"),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "%{value} wins<br>"
            "%{percent}<extra></extra>"
        ),
    ))
    n_games = max(blue_total, red_total)  # one blue + one red per game
    fig.add_annotation(
        text=f"{n_games}<br><span style='font-size:11px;color:{TEXT_MUTED}'>games</span>",
        x=0.5, y=0.5, font=dict(size=20, color=TEXT_MAIN, family="Oswald, sans-serif"),
        showarrow=False,
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=56, b=10),
    )
    return fig


# -- Salary Value (Punching Above Weight) ------------------------------------

def chart_salary_value(player_stats_df: pd.DataFrame,
                       min_games: int = 3) -> go.Figure:
    """Scatter plot of salary (x) vs avg Impact Factor (y).

    Players above the trend line are outperforming their salary;
    players below are underperforming.
    """
    ps = player_stats_df.copy()
    if ps.empty or "salary" not in ps.columns or "impact_factor" not in ps.columns:
        return _base("Salary vs Performance", height=360)

    ps["salary"] = pd.to_numeric(ps["salary"], errors="coerce").fillna(0)
    ps["impact_factor"] = pd.to_numeric(ps["impact_factor"], errors="coerce").fillna(0)

    # Average per player
    name_col = "riotId" if "riotId" in ps.columns else "username"
    agg = ps.groupby(name_col).agg(
        salary=("salary", "first"),
        avg_if=("impact_factor", "mean"),
        games=("impact_factor", "count"),
    ).reset_index()
    agg = agg[agg["games"] >= min_games].copy()

    if agg.empty:
        return _base("Salary vs Performance", height=360)

    # Trend line
    z = np.polyfit(agg["salary"], agg["avg_if"], 1)
    agg["expected_if"] = np.polyval(z, agg["salary"])
    agg["value_delta"] = agg["avg_if"] - agg["expected_if"]

    # Color: green above trend, red below
    colors = [WIN_COLOR if d > 0 else LOSS_COLOR for d in agg["value_delta"]]

    fig = _base("Salary vs Impact Factor", height=400)

    # Trend line
    salary_range = np.linspace(agg["salary"].min(), agg["salary"].max(), 50)
    fig.add_trace(go.Scatter(
        x=salary_range, y=np.polyval(z, salary_range),
        mode="lines", line=dict(color=TEXT_DIM, width=1, dash="dash"),
        name="Expected", showlegend=False,
        hoverinfo="skip",
    ))

    fig.add_trace(go.Scatter(
        x=agg["salary"], y=agg["avg_if"],
        mode="markers",
        marker=dict(size=12, color=colors, line=dict(color=TEXT_DIM, width=0.5)),
        customdata=agg[[name_col, "games", "value_delta"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Salary: %{x}<br>"
            "Avg IF: %{y:.1f}<br>"
            "Games: %{customdata[1]}<br>"
            "vs Expected: %{customdata[2]:+.1f}<extra></extra>"
        ),
    ))

    # Quadrant labels + single biggest outlier per quadrant
    med_sal = agg["salary"].median()
    med_if = agg["avg_if"].median()

    # Quadrant definitions: (filter, label, position, color)
    quadrants = [
        (lambda r: r["salary"] < med_sal and r["avg_if"] > med_if,
         "STEALS", dict(x=agg["salary"].min(), y=agg["avg_if"].max()),
         WIN_COLOR, "value_delta", False),  # biggest positive delta
        (lambda r: r["salary"] >= med_sal and r["avg_if"] > med_if,
         "WORTH IT", dict(x=agg["salary"].max(), y=agg["avg_if"].max()),
         ACCENT_TEAL, "value_delta", False),
        (lambda r: r["salary"] < med_sal and r["avg_if"] <= med_if,
         "DEVELOPING", dict(x=agg["salary"].min(), y=agg["avg_if"].min()),
         TEXT_MUTED, "value_delta", True),  # sort ascending
        (lambda r: r["salary"] >= med_sal and r["avg_if"] <= med_if,
         "OVERPAID", dict(x=agg["salary"].max(), y=agg["avg_if"].min()),
         LOSS_COLOR, "value_delta", True),
    ]

    for filt, label, pos, color, sort_col, ascending in quadrants:
        q_mask = agg.apply(filt, axis=1)
        q_df = agg[q_mask]
        if q_df.empty:
            continue

        # Quadrant label (background)
        xanch = "left" if pos["x"] == agg["salary"].min() else "right"
        yanch = "bottom" if pos["y"] == agg["avg_if"].min() else "top"
        fig.add_annotation(
            x=pos["x"], y=pos["y"],
            text=f"<b>{label}</b>",
            font=dict(size=14, color=color, family="Oswald"),
            opacity=0.25, showarrow=False,
            xanchor=xanch, yanchor=yanch,
            xshift=8 if xanch == "left" else -8,
            yshift=8 if yanch == "bottom" else -8,
        )

        # Label the single biggest outlier in this quadrant
        outlier = q_df.sort_values(sort_col, ascending=ascending).iloc[0]
        fig.add_annotation(
            x=outlier["salary"], y=outlier["avg_if"],
            text=f"<b>{outlier[name_col]}</b>",
            font=dict(size=11, color=color, family="Barlow Condensed"),
            showarrow=True, arrowhead=0, arrowcolor=color, arrowwidth=1,
            ax=0, ay=-22,
        )

    # Median divider lines
    fig.add_hline(y=med_if, line=dict(color="rgba(100,116,139,0.2)", dash="dot", width=1))
    fig.add_vline(x=med_sal, line=dict(color="rgba(100,116,139,0.2)", dash="dot", width=1))

    fig.update_layout(
        xaxis=dict(title=dict(text="Salary", font=dict(size=12, color=TEXT_MUTED)),
                   showgrid=False),
        yaxis=dict(title=dict(text="Avg Impact Factor", font=dict(size=12, color=TEXT_MUTED)),
                   showgrid=False),
        margin=dict(l=50, r=20, t=56, b=40),
        showlegend=False,
    )
    return fig


# -- Team Momentum (Rising / Falling) ----------------------------------------

def chart_team_momentum(all_matches: pd.DataFrame,
                        team_colors: dict,
                        window: int = 3,
                        highlight_n: int = 3) -> go.Figure:
    """Rolling win rate per team. Highlights biggest risers/fallers, fades the rest."""
    if all_matches.empty:
        return _base("Team Momentum", height=360)

    df = all_matches.copy()
    df["week"] = pd.to_numeric(df["week"], errors="coerce")

    # Build per-team per-week win counts
    records = []
    for tid in set(df["team1Id"].tolist() + df["team2Id"].tolist()):
        team_games = df[(df["team1Id"] == tid) | (df["team2Id"] == tid)]
        for wk in sorted(team_games["week"].unique()):
            wk_games = team_games[team_games["week"] == wk]
            wins = int((wk_games["winnerId"] == tid).sum())
            total = len(wk_games)
            records.append({"team_id": tid, "week": wk, "wins": wins, "games": total})

    if not records:
        return _base("Team Momentum", height=360)

    rec_df = pd.DataFrame(records)

    name_map = {}
    for _, row in df.iterrows():
        if "team1Name" in df.columns:
            name_map[row["team1Id"]] = row.get("team1Name", row["team1Id"])
            name_map[row["team2Id"]] = row.get("team2Name", row["team2Id"])

    # Compute final rolling WR per team to determine highlights
    team_final_wr = {}
    team_rolling = {}
    for tid in rec_df["team_id"].unique():
        team_data = rec_df[rec_df["team_id"] == tid].sort_values("week").copy()
        team_data["rolling_wr"] = (
            team_data["wins"].rolling(window, min_periods=1).sum() /
            team_data["games"].rolling(window, min_periods=1).sum()
        )
        team_rolling[tid] = team_data
        team_final_wr[tid] = team_data["rolling_wr"].iloc[-1] if not team_data.empty else 0.5

    # Highlight top N and bottom 1
    sorted_teams = sorted(team_final_wr.items(), key=lambda x: x[1], reverse=True)
    highlight_ids = set(t[0] for t in sorted_teams[:highlight_n])
    if len(sorted_teams) > highlight_n:
        highlight_ids.add(sorted_teams[-1][0])

    fig = _base("Team Momentum", height=400)

    for tid, team_data in team_rolling.items():
        name = name_map.get(tid, tid)
        color = team_colors.get(tid, TEXT_SEC)
        is_hl = tid in highlight_ids

        fig.add_trace(go.Scatter(
            x=team_data["week"], y=team_data["rolling_wr"] * 100,
            mode="lines+markers" if is_hl else "lines",
            name=name,
            line=dict(color=color, width=3 if is_hl else 1.5),
            opacity=1.0 if is_hl else 0.25,
            marker=dict(size=6, color=color) if is_hl else dict(size=0),
            showlegend=False,
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Week %{x}<br>"
                "Win Rate: %{y:.0f}%<extra></extra>"
            ),
        ))

        if is_hl and not team_data.empty:
            last = team_data.iloc[-1]
            fig.add_annotation(
                x=last["week"], y=last["rolling_wr"] * 100,
                text=f"<b>{name}</b>",
                font=dict(size=11, color=color, family="Barlow Condensed"),
                showarrow=False, xanchor="left", xshift=8,
            )

    fig.update_layout(
        xaxis=dict(title=dict(text="Week", font=dict(size=12, color=TEXT_MUTED)),
                   dtick=1, showgrid=False),
        yaxis=dict(title=dict(text=f"{window}-Wk Rolling Win %",
                              font=dict(size=12, color=TEXT_MUTED)),
                   range=[0, 105], showgrid=True, gridcolor=BORDER_LIGHT),
        margin=dict(l=50, r=100, t=56, b=40),
    )
    fig.add_hline(y=50, line_dash="dot", line_color=TEXT_DIM, line_width=1)
    return fig


def chart_hot_cold(all_series: pd.DataFrame,
                   team_colors: dict = None,
                   window: int = 3) -> go.Figure:
    """Simple horizontal bar: each team's record over their last N series.

    Green = winning, red = losing. One bar per team, sorted by recent form.
    Much cleaner than the full rolling-WR spaghetti chart.
    """
    if all_series.empty:
        return _base("Hot & Cold", height=300)

    team_colors = team_colors or {}
    completed = all_series[all_series["status"] == "COMPLETED"].copy()
    completed["week"] = pd.to_numeric(completed["week"], errors="coerce")
    completed = completed.sort_values("week")

    team_ids = set(completed["team1Id"].tolist() + completed["team2Id"].tolist())
    records = []
    for tid in team_ids:
        team_series = completed[
            (completed["team1Id"] == tid) | (completed["team2Id"] == tid)
        ].tail(window)
        if team_series.empty:
            continue
        first = team_series.iloc[0]
        name = first["team1Name"] if str(first["team1Id"]) == str(tid) else first["team2Name"]
        wins = int((team_series["winnerId"].astype(str) == str(tid)).sum())
        losses = len(team_series) - wins
        records.append({
            "team_id": str(tid), "name": name,
            "wins": wins, "losses": losses, "form": wins - losses,
        })

    if not records:
        return _base("Hot & Cold", height=300)

    rec_df = pd.DataFrame(records).sort_values("form", ascending=True)
    n = len(rec_df)
    height = max(280, 34 * n + 60)

    fig = _base(f"Form (Last {window} Series)", height=height)

    colors = []
    for _, row in rec_df.iterrows():
        if row["form"] > 0:
            colors.append(WIN_COLOR)
        elif row["form"] < 0:
            colors.append(LOSS_COLOR)
        else:
            colors.append(TEXT_DIM)

    fig.add_trace(go.Bar(
        y=rec_df["name"],
        x=rec_df["form"],
        orientation="h",
        marker_color=colors,
        marker_line_width=0,
        opacity=0.85,
        text=[f"{row['wins']}-{row['losses']}" for _, row in rec_df.iterrows()],
        textposition="outside",
        textfont=dict(size=13, family="Oswald, sans-serif"),
        hovertemplate="<b>%{y}</b><br>Last 3: %{text}<extra></extra>",
    ))

    fig.update_layout(
        xaxis=dict(range=[-window - 0.5, window + 0.5],
                   showticklabels=False, showgrid=False,
                   zeroline=True, zerolinecolor=TEXT_DIM, zerolinewidth=1),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed")),
        margin=dict(l=10, r=40, t=56, b=20),
    )
    return fig


# -- Game Superlatives --------------------------------------------------------

def chart_game_superlatives(player_stats_df: pd.DataFrame,
                            matches_df: pd.DataFrame,
                            team_stats_df: pd.DataFrame) -> go.Figure:
    """Visual cards showing game-level records: bloodiest, longest, shortest, etc."""
    ps = player_stats_df.copy()
    ms = matches_df.copy() if matches_df is not None else pd.DataFrame()
    ts = team_stats_df.copy() if team_stats_df is not None else pd.DataFrame()

    superlatives = []

    if not ps.empty and "gameDuration" in ps.columns and "matchId" in ps.columns:
        ps["gameDuration"] = pd.to_numeric(ps["gameDuration"], errors="coerce").fillna(0)
        ps["kills"] = pd.to_numeric(ps["kills"], errors="coerce").fillna(0)
        ps["deaths"] = pd.to_numeric(ps["deaths"], errors="coerce").fillna(0)
        ps["goldEarned"] = pd.to_numeric(ps["goldEarned"], errors="coerce").fillna(0)

        dur_per_game = ps.groupby("matchId")["gameDuration"].first()
        kills_per_game = ps.groupby("matchId")["kills"].sum()
        deaths_per_game = ps.groupby("matchId")["deaths"].sum()

        if not dur_per_game.empty:
            longest_id = dur_per_game.idxmax()
            shortest_id = dur_per_game.idxmin()
            superlatives.append(("Longest Game", _fmt_time(dur_per_game.max()), _game_label(longest_id, ms)))
            if len(dur_per_game) > 1:
                superlatives.append(("Shortest Game", _fmt_time(dur_per_game.min()), _game_label(shortest_id, ms)))

        if not kills_per_game.empty:
            bloodiest_id = kills_per_game.idxmax()
            superlatives.append(("Bloodiest Game", f"{int(kills_per_game.max())} kills", _game_label(bloodiest_id, ms)))

        # Closest gold difference at end of game
        if not ps.empty:
            gold_per_team = ps.groupby(["matchId", "teamId"])["goldEarned"].sum().reset_index()
            gold_diff = gold_per_team.groupby("matchId")["goldEarned"].agg(["min", "max"]).reset_index()
            gold_diff["diff"] = gold_diff["max"] - gold_diff["min"]
            if not gold_diff.empty:
                closest_id = gold_diff.loc[gold_diff["diff"].idxmin(), "matchId"]
                closest_val = int(gold_diff["diff"].min())
                superlatives.append(("Closest Gold", f"{closest_val:,}g diff", _game_label(closest_id, ms)))

        # Most one-sided (biggest gold diff)
        if not gold_diff.empty and len(gold_diff) > 1:
            stomp_id = gold_diff.loc[gold_diff["diff"].idxmax(), "matchId"]
            stomp_val = int(gold_diff["diff"].max())
            superlatives.append(("Biggest Stomp", f"{stomp_val:,}g diff", _game_label(stomp_id, ms)))

    if not superlatives:
        return _base("Game Superlatives", height=180)

    # Build as a styled horizontal indicator chart
    labels = [s[0] for s in superlatives]
    values = [s[1] for s in superlatives]
    contexts = [s[2] for s in superlatives]

    fig = _base("Game Superlatives", height=max(180, 50 * len(superlatives) + 60))

    colors = [ACCENT_GOLD, ACCENT_TEAL, ACCENT_RED, ACCENT_CYAN, ACCENT_BLUE]

    fig.add_trace(go.Bar(
        y=labels[::-1],
        x=[1] * len(labels),
        orientation="h",
        marker_color=[colors[i % len(colors)] for i in range(len(labels))][::-1],
        marker_line_width=0,
        opacity=0.15,
        hoverinfo="skip",
        showlegend=False,
    ))

    for i, (label, val, ctx) in enumerate(reversed(superlatives)):
        fig.add_annotation(
            x=0.02, y=i,
            text=f"<b>{val}</b>  <span style='color:{TEXT_MUTED}'>{ctx}</span>",
            font=dict(size=14, family="Barlow Condensed, sans-serif", color=TEXT_MAIN),
            showarrow=False, xanchor="left", xref="paper",
        )

    fig.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, range=[0, 1]),
        yaxis=dict(tickfont=dict(size=13, family="Oswald, sans-serif", color=ACCENT_GOLD)),
        margin=dict(l=10, r=10, t=56, b=10),
        bargap=0.3,
    )
    return fig


def _game_label(match_id, matches_df: pd.DataFrame) -> str:
    """Get a readable label for a match like 'Team A vs Team B'."""
    if matches_df.empty:
        return ""
    row = matches_df[matches_df["id"].astype(str) == str(match_id)]
    if row.empty:
        return ""
    r = row.iloc[0]
    t1 = r.get("team1Name", "?")
    t2 = r.get("team2Name", "?")
    return f"{t1} vs {t2}"


# -- Ban Effectiveness --------------------------------------------------------

def chart_ban_effectiveness(ban_df: pd.DataFrame,
                            champion_df: pd.DataFrame,
                            n: int = 12) -> go.Figure:
    """Show most banned champions with their win rate when NOT banned (let through).

    High ban rate + high unbanned WR = justified ban. High ban rate + low WR = wasted ban.
    """
    if ban_df.empty or champion_df.empty:
        return _base("Ban Effectiveness", height=300)

    # Champion win rates (when they get through bans)
    if "division" in champion_df.columns:
        wr_agg = champion_df.groupby("championName").agg(
            games=("games", "sum"), wins=("wins", "sum")
        ).reset_index()
    else:
        wr_agg = champion_df[["championName", "games", "wins"]].copy()
    wr_agg["wr_when_open"] = wr_agg["wins"] / wr_agg["games"]

    merged = ban_df.merge(wr_agg, on="championName", how="left")
    merged = merged.dropna(subset=["wr_when_open"])
    merged = merged.sort_values("bans", ascending=False).head(n)

    if merged.empty:
        return _base("Ban Effectiveness", height=300)

    merged = merged.sort_values("bans", ascending=True)

    fig = _base("Ban Effectiveness", height=max(300, 30 * len(merged) + 70))

    # Ban rate bars
    fig.add_trace(go.Bar(
        y=merged["championName"],
        x=merged["ban_rate"] * 100,
        orientation="h",
        name="Ban Rate %",
        marker_color=ACCENT_RED,
        opacity=0.7,
        marker_line_width=0,
        text=[f"{br*100:.0f}% banned" for br in merged["ban_rate"]],
        textposition="outside",
        textfont=dict(size=11, family="Barlow Condensed", color=TEXT_SEC),
        hovertemplate="<b>%{y}</b><br>Ban rate: %{x:.0f}%<extra></extra>",
    ))

    # WR when open as markers on secondary axis
    fig.add_trace(go.Scatter(
        y=merged["championName"],
        x=merged["wr_when_open"] * 100,
        mode="markers+text",
        name="WR When Open",
        marker=dict(
            size=12,
            color=[WIN_COLOR if wr > 0.5 else LOSS_COLOR for wr in merged["wr_when_open"]],
            symbol="diamond",
            line=dict(width=1, color=TEXT_DIM),
        ),
        text=[f"{wr*100:.0f}%" for wr in merged["wr_when_open"]],
        textposition="middle right",
        textfont=dict(size=10, family="Barlow Condensed", color=TEXT_SEC),
        xaxis="x2",
        hovertemplate="<b>%{y}</b><br>WR when open: %{x:.0f}%<extra></extra>",
    ))

    fig.update_layout(
        xaxis=dict(range=[0, 130], showticklabels=False, showgrid=False,
                   title=dict(text="Ban Rate %", font=dict(size=10, color=TEXT_MUTED))),
        xaxis2=dict(range=[0, 100], overlaying="x", side="top",
                    showticklabels=False, showgrid=False,
                    title=dict(text="WR When Open", font=dict(size=10, color=TEXT_MUTED))),
        yaxis=dict(tickfont=dict(size=12)),
        margin=dict(l=10, r=40, t=56, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0.5, xanchor="center",
                    font=dict(size=10)),
    )
    return fig


# -- Team Identity Profiles ---------------------------------------------------

def chart_team_identities(records_df: pd.DataFrame,
                          team_colors: dict = None) -> go.Figure:
    """Clean team identity chart: one tag per team showing their most
    distinctive trait, sorted by win%. Easy to read at a glance.

    Each team gets labeled with what makes them *different* from the league.
    """
    if records_df.empty:
        return _base("Team Identities", height=300)

    team_colors = team_colors or {}
    df = records_df.copy()

    traits = [
        ("avg_dragons", "Dragon Prioritizers", ACCENT_TEAL),
        ("avg_barons", "Baron Callers", ACCENT_GOLD),
        ("avg_turrets", "Siege Specialists", ACCENT_BLUE),
        ("avg_kills", "Bloodthirsty", ACCENT_RED),
        ("avg_duration_s", "Late-Game Scalers", ACCENT_CYAN),
    ]

    for col, label, color in traits:
        if col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        mean = df[col].mean()
        std = df[col].std()
        df[f"z_{col}"] = ((df[col] - mean) / std).round(2) if std > 0 else 0.0

    # For each team, find their most extreme trait
    identity_labels = []
    identity_colors = []
    identity_values = []
    for _, row in df.iterrows():
        best_z = 0
        best_label = "Balanced"
        best_color = TEXT_MUTED
        best_val = ""
        for col, label, color in traits:
            z = row.get(f"z_{col}", 0)
            # For game length, negative z = "Early Closers" (also interesting)
            if col == "avg_duration_s" and z < -best_z:
                m, s = divmod(int(row[col]), 60)
                best_z = abs(z)
                best_label = "Early Closers"
                best_color = "#a78bfa"  # purple
                best_val = f"avg {m}:{s:02d}"
            elif abs(z) > abs(best_z):
                best_z = abs(z)
                best_label = label
                best_color = color
                if col == "avg_duration_s":
                    m, s = divmod(int(row[col]), 60)
                    best_val = f"avg {m}:{s:02d}"
                elif col == "avg_kills":
                    best_val = f"{row[col]:.0f} kills/g"
                else:
                    best_val = f"{row[col]:.1f}/g"
        identity_labels.append(best_label)
        identity_colors.append(best_color)
        identity_values.append(best_val)

    df["identity"] = identity_labels
    df["id_color"] = identity_colors
    df["id_value"] = identity_values

    # Sort by win_pct
    if "win_pct" in df.columns:
        df = df.sort_values("win_pct", ascending=True)
    else:
        df = df.sort_values("series_wins", ascending=True)

    n_teams = len(df)
    height = max(300, 36 * n_teams + 70)

    fig = _base("Team Identities", height=height)

    # Win rate bars (background context)
    fig.add_trace(go.Bar(
        y=df["name"],
        x=df["win_pct"] * 100 if "win_pct" in df.columns else df["series_wins"],
        orientation="h",
        marker_color=[team_colors.get(str(tid), TEXT_DIM)
                      for tid in df["teamId"]],
        marker_line_width=0,
        opacity=0.6,
        text=[f'{row["identity"]}  ({row["id_value"]})'
              for _, row in df.iterrows()],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed, sans-serif",
                      color=[row["id_color"] for _, row in df.iterrows()]),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Win Rate: %{x:.0f}%<br>"
            "%{text}<extra></extra>"
        ),
        showlegend=False,
    ))

    fig.update_layout(
        xaxis=dict(range=[0, 130],
                   title=dict(text="Win %", font=dict(size=10, color=TEXT_MUTED)),
                   showgrid=False, showticklabels=False),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed")),
        margin=dict(l=10, r=100, t=56, b=30),
    )
    fig.add_vline(x=50, line_dash="dot", line_color=TEXT_DIM, line_width=1)
    return fig


def chart_champion_presence(ban_df: pd.DataFrame,
                            champion_df: pd.DataFrame,
                            n: int = 15) -> go.Figure:
    """Stacked horizontal bar: pick count + ban count = total presence.

    Champions sorted by total presence (picked + banned). Shows who is
    truly dominating the draft phase.
    """
    if champion_df.empty:
        return _base("Champion Presence", height=300)

    # Aggregate pick counts
    if champion_df.empty or "championName" not in champion_df.columns:
        return _base("Champion Presence", height=300)

    if "games" in champion_df.columns:
        if "division" in champion_df.columns:
            picks = champion_df.groupby("championName").agg(
                picks=("games", "sum")
            ).reset_index()
        else:
            picks = champion_df[["championName", "games"]].copy()
            picks = picks.rename(columns={"games": "picks"})
    elif "win" in champion_df.columns:
        # Raw player_stats rows — count appearances
        picks = champion_df.groupby("championName").size().reset_index(name="picks")
    else:
        return _base("Champion Presence", height=300)

    # Merge with bans
    if not ban_df.empty and "championName" in ban_df.columns:
        bans = ban_df[["championName", "bans"]].copy()
        merged = picks.merge(bans, on="championName", how="outer").fillna(0)
    else:
        merged = picks.copy()
        merged["bans"] = 0

    merged["picks"] = merged["picks"].astype(int)
    merged["bans"] = merged["bans"].astype(int)
    merged["presence"] = merged["picks"] + merged["bans"]
    merged = merged.sort_values("presence", ascending=True).tail(n)

    if merged.empty:
        return _base("Champion Presence", height=300)

    fig = _base("Champion Presence (Pick + Ban)", height=max(300, 28 * len(merged) + 70))

    fig.add_trace(go.Bar(
        y=merged["championName"], x=merged["picks"], orientation="h",
        name="Picked", marker_color=ACCENT_TEAL, marker_line_width=0, opacity=0.85,
        text=[f"{int(p)}" for p in merged["picks"]],
        textposition="inside",
        textfont=dict(size=11, family="Barlow Condensed", color="#fff"),
        hovertemplate="<b>%{y}</b><br>Picked: %{x}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=merged["championName"], x=merged["bans"], orientation="h",
        name="Banned", marker_color=ACCENT_RED, marker_line_width=0, opacity=0.75,
        text=[f"{int(b)}" if b > 0 else "" for b in merged["bans"]],
        textposition="inside",
        textfont=dict(size=11, family="Barlow Condensed", color="#fff"),
        hovertemplate="<b>%{y}</b><br>Banned: %{x}<extra></extra>",
    ))

    fig.update_layout(
        barmode="stack",
        xaxis=dict(showticklabels=False, showgrid=False,
                   title=dict(text="Total Presence (picks + bans)",
                              font=dict(size=10, color=TEXT_MUTED))),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center",
                    font=dict(size=10)),
        margin=dict(l=10, r=20, t=72, b=30),
    )
    return fig


def chart_item_quick_hits(item_df: pd.DataFrame,
                          min_games: int = 5,
                          n: int = 5) -> go.Figure:
    """Combined OP + Grief items chart (used in analytics tabs)."""
    if item_df.empty:
        return _base("Item Quick Hits", height=300)
    df = item_df[item_df["games"] >= min_games].copy()
    if df.empty:
        return _base("Item Quick Hits", height=300)
    df = df[~df["item_name"].str.contains("Mejai", case=False, na=False)]
    best = df.sort_values("win_rate", ascending=False).head(n)
    worst = df.sort_values("win_rate", ascending=True).head(n)
    combined = pd.concat([worst.assign(category="GRIEF"), best.assign(category="OP")])
    combined = combined.sort_values(["category", "win_rate"], ascending=[False, True])
    colors = [LOSS_COLOR if c == "GRIEF" else WIN_COLOR for c in combined["category"]]
    fig = _base("Item Quick Hits: OP vs Grief", height=max(300, 30 * len(combined) + 80))
    fig.add_trace(go.Bar(
        y=combined["item_name"], x=combined["win_rate"] * 100, orientation="h",
        marker_color=colors, marker_line_width=0, opacity=0.85,
        text=[f"{wr*100:.0f}% ({int(g)} games)"
              for wr, g in zip(combined["win_rate"], combined["games"])],
        textposition="outside",
        textfont=dict(size=11, family="Barlow Condensed", color=TEXT_SEC),
        hovertemplate="<b>%{y}</b><br>Win Rate: %{x:.0f}%<extra></extra>",
    ))
    fig.add_vline(x=50, line_dash="dot", line_color=TEXT_DIM, line_width=1)
    fig.update_layout(
        xaxis=dict(range=[0, 105], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=12, family="Barlow Condensed")),
        margin=dict(l=10, r=80, t=56, b=10),
    )
    return fig


def chart_item_op(item_df: pd.DataFrame, min_games: int = 5, n: int = 3) -> go.Figure:
    """Top N items by win rate. Clean green bars."""
    if item_df.empty:
        return _base("OP Builds", height=200)
    df = item_df[item_df["games"] >= min_games].copy()
    if df.empty:
        return _base("OP Builds", height=200)
    df = df[~df["item_name"].str.contains("Mejai", case=False, na=False)]
    best = df.sort_values("win_rate", ascending=True).tail(n)
    fig = _base("OP Builds", height=max(180, 36 * n + 60))
    fig.add_trace(go.Bar(
        y=best["item_name"], x=best["win_rate"] * 100, orientation="h",
        marker_color=WIN_COLOR, marker_line_width=0, opacity=0.85,
        text=[f"{wr*100:.0f}% ({int(g)} games)"
              for wr, g in zip(best["win_rate"], best["games"])],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed"),
        hovertemplate="<b>%{y}</b><br>Win Rate: %{x:.0f}%<extra></extra>",
    ))
    fig.add_vline(x=50, line_dash="dot", line_color=TEXT_DIM, line_width=1)
    fig.update_layout(
        xaxis=dict(range=[0, 110], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=13, family="Barlow Condensed")),
        margin=dict(l=10, r=80, t=56, b=10),
    )
    return fig


def chart_item_grief(item_df: pd.DataFrame, min_games: int = 5, n: int = 3) -> go.Figure:
    """Bottom N items by win rate. Clean red bars."""
    if item_df.empty:
        return _base("Grief Builds", height=200)
    df = item_df[item_df["games"] >= min_games].copy()
    if df.empty:
        return _base("Grief Builds", height=200)
    worst = df.sort_values("win_rate", ascending=False).tail(n)
    fig = _base("Grief Builds", height=max(180, 36 * n + 60))
    fig.add_trace(go.Bar(
        y=worst["item_name"], x=worst["win_rate"] * 100, orientation="h",
        marker_color=LOSS_COLOR, marker_line_width=0, opacity=0.85,
        text=[f"{wr*100:.0f}% ({int(g)} games)"
              for wr, g in zip(worst["win_rate"], worst["games"])],
        textposition="outside",
        textfont=dict(size=12, family="Barlow Condensed"),
        hovertemplate="<b>%{y}</b><br>Win Rate: %{x:.0f}%<extra></extra>",
    ))
    fig.add_vline(x=50, line_dash="dot", line_color=TEXT_DIM, line_width=1)
    fig.update_layout(
        xaxis=dict(range=[0, 110], showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=13, family="Barlow Condensed")),
        margin=dict(l=10, r=80, t=56, b=10),
    )
    return fig


def generate_team_identity_notes(records_df: pd.DataFrame) -> list[dict]:
    """Generate narrative notes about each team's identity from their stats.

    Returns list of {team, identity, detail} dicts sorted by most distinctive trait.
    """
    if records_df.empty:
        return []

    df = records_df.copy()
    for col in ["avg_dragons", "avg_barons", "avg_turrets", "avg_kills", "avg_duration_s"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    notes = []
    for _, row in df.iterrows():
        name = row["name"]
        identities = []

        # Dragon prioritizer
        if "avg_dragons" in df.columns:
            dragon_rank = (df["avg_dragons"] >= row["avg_dragons"]).sum()
            if dragon_rank <= max(2, len(df) // 4):
                identities.append(("Dragon Prioritizer", f"{row['avg_dragons']:.1f} drakes/game"))

        # Baron caller
        if "avg_barons" in df.columns:
            baron_rank = (df["avg_barons"] >= row["avg_barons"]).sum()
            if baron_rank <= max(2, len(df) // 4):
                identities.append(("Baron Caller", f"{row['avg_barons']:.1f} barons/game"))

        # Tower pressure / split push
        if "avg_turrets" in df.columns:
            turret_rank = (df["avg_turrets"] >= row["avg_turrets"]).sum()
            if turret_rank <= max(2, len(df) // 4):
                identities.append(("Siege Specialists", f"{row['avg_turrets']:.1f} turrets/game"))

        # Bloodthirsty / fight-heavy
        if "avg_kills" in df.columns:
            kill_rank = (df["avg_kills"] >= row["avg_kills"]).sum()
            if kill_rank <= max(2, len(df) // 4):
                identities.append(("Bloodthirsty", f"{row['avg_kills']:.1f} kills/game"))

        # Marathon games / scaling
        if "avg_duration_s" in df.columns:
            dur_rank = (df["avg_duration_s"] >= row["avg_duration_s"]).sum()
            if dur_rank <= max(2, len(df) // 4):
                m, s = divmod(int(row["avg_duration_s"]), 60)
                identities.append(("Late-Game Scalers", f"avg {m}:{s:02d} games"))

            # Short games / early aggression
            short_rank = (df["avg_duration_s"] <= row["avg_duration_s"]).sum()
            if short_rank <= max(2, len(df) // 4) and row["avg_duration_s"] < df["avg_duration_s"].median():
                m, s = divmod(int(row["avg_duration_s"]), 60)
                identities.append(("Early Closers", f"avg {m}:{s:02d} games"))

        if identities:
            notes.append({
                "team": name,
                "identity": identities[0][0],
                "detail": identities[0][1],
                "all_identities": identities,
            })

    return notes

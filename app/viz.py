"""
Beer League Stats — presentation layer (v2).

HTML components (standings table, cards, forecast rows) and Plotly figures
that share one visual grammar:

  * text always wears ink tokens; colour is carried by the mark beside it
  * thin marks, rounded ends, recessive axes, direct value labels
  * one hue for magnitude (gold ramp), blue ↔ red for two-sided comparisons
    (validated for colour-blind separation on the dark surface)
  * team colours come from the league site and only ever identify a team
"""
from __future__ import annotations

import html
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.league import ROLES, ROLE_SHORT, champ_name
from app.styling import (
    apply_template, TEAM_PALETTE, ACCENT_GOLD, TEXT_MAIN, TEXT_SEC, TEXT_MUTED, TEXT_DIM,
    CARD_BG, BORDER_CLR, SURFACE,
)

BLUE = "#4f8ff7"      # blue side / positive / "model"
RED = "#e5484d"       # red side / negative
GOOD = "#2fbf8f"
WARN = "#f59e0b"
NEUTRAL = "#334155"
GOLD_RAMP = [[0.0, "#141b2b"], [0.3, "#3d3410"], [0.6, "#6b580f"], [0.8, "#8a7110"], [1.0, "#FFD700"]]
ROLE_COLORS = {"TOP": "#e5484d", "JUNGLE": "#2fbf8f", "MIDDLE": "#4f8ff7",
               "BOTTOM": "#f59e0b", "SUPPORT": "#a78bfa"}
FONT_HEAD = "Oswald, 'Barlow Condensed', sans-serif"
FONT_BODY = "'Barlow Condensed', Barlow, sans-serif"

PLOT_CFG = {"displayModeBar": False, "responsive": True}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _valid_hex(c) -> bool:
    if not isinstance(c, str) or not c.startswith("#") or len(c) not in (4, 7):
        return False
    try:
        int(c[1:], 16)
        return True
    except ValueError:
        return False


def _lum(c: str) -> float:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def team_colors(teams_df: pd.DataFrame) -> dict:
    """team_id -> a colour that is readable on the dark surface. Site colours
    are kept when usable; near-black ones are swapped for a palette slot."""
    out, k = {}, 0
    for r in teams_df.itertuples():
        c = r.color if _valid_hex(r.color) else None
        if c is None or _lum(c) < 0.12:
            c = TEAM_PALETTE[k % len(TEAM_PALETTE)]
            k += 1
        out[r.teamId] = c
    return out


def fmt_time(seconds) -> str:
    if seconds is None or (isinstance(seconds, float) and math.isnan(seconds)):
        return "–"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def pct(v, digits=0) -> str:
    return "–" if v is None or pd.isna(v) else f"{v * 100:.{digits}f}%"


# ── HTML components ──────────────────────────────────────────────────────────

def kpi(label, value, sub="", tone="") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi {tone}"><div class="kpi-label">{esc(label)}</div>'
            f'<div class="kpi-value">{value}</div>{sub_html}</div>')


def kpi_row(items) -> str:
    return f'<div class="kpi-row">{"".join(items)}</div>'


def h2(title, sub="") -> str:
    sub_html = f'<span class="h2-sub">{sub}</span>' if sub else ""
    return f'<div class="h2"><span class="h2-bar"></span><span class="h2-text">{esc(title)}</span>{sub_html}</div>'


def note(text) -> str:
    return f'<div class="note">{text}</div>'


def story_cards(stories, limit=6) -> str:
    if not stories:
        return note("Nothing unusual to report — a chalk week.")
    cards = "".join(
        f'<div class="story"><div class="story-tag">{esc(tag)}</div><div class="story-text">{text}</div></div>'
        for tag, text, _ in stories[:limit])
    return f'<div class="story-grid">{cards}</div>'


def _form_pills(form: str) -> str:
    return "".join(f'<span class="pill {"w" if ch == "W" else "l"}">{ch}</span>' for ch in form)


def _prob_cell(p) -> str:
    if p is None or pd.isna(p):
        return '<td class="num muted">–</td>'
    if p >= 0.9995:
        return '<td class="num"><span class="tag in">IN</span></td>'
    if p <= 0.0005:
        return '<td class="num"><span class="tag out">OUT</span></td>'
    w = max(4, round(p * 100))
    label = "&lt;1%" if p < 0.01 else "&gt;99%" if p > 0.99 else f"{p * 100:.0f}%"
    return (f'<td class="num"><div class="pbar"><div class="pbar-fill" style="width:{w}%"></div>'
            f'<span>{label}</span></div></td>')


def standings_table(st: pd.DataFrame, colors: dict, cut: int | None = None,
                    ratings: dict | None = None, probs: dict | None = None,
                    sos: dict | None = None, seed_labels: dict | None = None,
                    compact: bool = False, show_games: bool = True,
                    show_streak: bool = True) -> str:
    """The league table, laid out like the website's (series W-L, then games)."""
    head = ['<th class="num">#</th>', "<th>Team</th>", '<th class="num">Series</th>']
    if show_games:
        head.append('<th class="num">Games</th>')
    if not compact:
        head.append("<th>Last 5</th>")
        if show_streak:
            head.append('<th class="num">Streak</th>')
        if ratings:
            head.append('<th class="num" title="Glicko-2 power rating">Rating</th>')
        if sos:
            head.append('<th class="num" title="Average series win% of opponents played so far">SoS</th>')
    if probs is not None:
        head.append('<th class="num" title="Share of simulations in which the team makes the playoffs">Playoffs</th>')
    rows = []
    for r in st.itertuples():
        tid = r.team_id
        dot = f'<span class="dot" style="background:{colors.get(tid, "#64748b")}"></span>'
        if r.dropped:
            span = len(head) - 2
            rows.append(f'<tr class="dropped"><td class="num">–</td><td>{dot}{esc(r.team)}</td>'
                        f'<td colspan="{span}" class="muted">Dropped</td></tr>')
            continue
        rank = int(r.rank)
        cls = []
        if cut and rank == cut:
            cls.append("cutline")
        if cut and rank > cut:
            cls.append("below")
        seed = f'<span class="seed">{esc(seed_labels[tid])}</span>' if seed_labels and tid in seed_labels else ""
        tie = (' <span class="tie" title="Still tied after series wins, game wins and head-to-head">=</span>'
               if r.tied and cut and rank <= cut + 1 else "")
        cells = [f'<td class="num rank">{rank}</td>',
                 f'<td class="team">{dot}{esc(r.team)}{seed}{tie}</td>',
                 f'<td class="num strong">{r.series_w}–{r.series_l}</td>']
        if show_games:
            cells.append(f'<td class="num">{r.game_w}–{r.game_l}</td>')
        if not compact:
            sk = r.streak or "–"
            skc = "w" if sk.startswith("W") else "l" if sk.startswith("L") else ""
            cells.append(f'<td>{_form_pills(r.form)}</td>')
            if show_streak:
                cells.append(f'<td class="num streak {skc}">{sk}</td>')
            if ratings:
                cells.append(f'<td class="num">{ratings.get(tid, float("nan")):.0f}</td>')
            if sos:
                v = sos.get(tid)
                cells.append(f'<td class="num">{"–" if v is None or pd.isna(v) else f"{v:.3f}".lstrip("0")}</td>')
        if probs is not None:
            cells.append(_prob_cell(probs.get(tid)))
        rows.append(f'<tr class="{" ".join(cls)}">{"".join(cells)}</tr>')
    return (f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def result_card(t1, t2, s1, s2, c1, c2, badge="", sub="") -> str:
    w1, w2 = s1 > s2, s2 > s1
    b = f'<span class="rc-badge">{esc(badge)}</span>' if badge else ""
    sub_html = f'<div class="rc-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="rc">{b}<div class="rc-row">'
        f'<div class="rc-team {"win" if w1 else ""}"><span class="dot" style="background:{c1}"></span>{esc(t1)}</div>'
        f'<div class="rc-score"><span class="{"win" if w1 else ""}">{s1}</span>'
        f'<span class="{"win" if w2 else ""}">{s2}</span></div>'
        f'<div class="rc-team right {"win" if w2 else ""}">{esc(t2)}<span class="dot" style="background:{c2}"></span></div>'
        f'</div>{sub_html}</div>')


def duel_bar(label, p1, n_label="") -> str:
    """One two-sided probability bar (team 1 share on the left)."""
    if p1 is None or pd.isna(p1):
        return (f'<div class="duel"><div class="duel-label">{esc(label)}</div>'
                f'<div class="duel-empty">{esc(n_label or "no picks yet")}</div></div>')
    a = round(p1 * 100)
    return (f'<div class="duel"><div class="duel-label">{esc(label)}</div>'
            f'<div class="duel-track"><div class="duel-a" style="width:{max(a, 6)}%">{a}%</div>'
            f'<div class="duel-b">{100 - a}%</div></div>'
            f'<div class="duel-n">{esc(n_label)}</div></div>')


def forecast_card(t1, t2, c1, c2, p_model, p_crowd, n_picks, tag="", foot="") -> str:
    tag_html = f'<span class="rc-badge">{esc(tag)}</span>' if tag else ""
    crowd_note = f"{n_picks} picks" if n_picks else ""
    return (
        f'<div class="fc">{tag_html}<div class="fc-teams">'
        f'<div class="fc-team"><span class="dot" style="background:{c1}"></span>{esc(t1)}</div>'
        f'<div class="fc-vs">vs</div>'
        f'<div class="fc-team right">{esc(t2)}<span class="dot" style="background:{c2}"></span></div></div>'
        f'{duel_bar("Model", p_model, foot)}'
        f'{duel_bar("Crowd", p_crowd if n_picks >= 3 else None, crowd_note if n_picks >= 3 else "not enough picks")}'
        f'</div>')


def pct_bars(rows) -> str:
    """rows: [(label, value_text, percentile 0-1)] → a compact profile panel."""
    out = []
    for label, val, p in rows:
        if p is None or pd.isna(p):
            continue
        w = max(3, round(p * 100))
        tone = "hi" if p >= 0.75 else "lo" if p <= 0.25 else ""
        out.append(f'<div class="pb"><div class="pb-l">{esc(label)}</div>'
                   f'<div class="pb-t"><div class="pb-f {tone}" style="width:{w}%"></div></div>'
                   f'<div class="pb-v">{val}</div><div class="pb-p">{round(p * 100)}</div></div>')
    return f'<div class="pb-wrap">{"".join(out)}</div>'


# ── Plotly base ──────────────────────────────────────────────────────────────

def _base(title="", height=360, sub="") -> go.Figure:
    fig = go.Figure()
    apply_template(fig)
    text = f"{title}<br><span style='font-size:12px;color:{TEXT_MUTED};font-family:{FONT_BODY}'>{sub}</span>" if sub else title
    # Title sits in the top margin, anchored to the plot area, so short
    # charts never clip it (the template's container-relative y did).
    fig.update_layout(height=height, showlegend=False,
                      margin=dict(l=8, r=24, t=70 if sub else 48, b=8),
                      title=dict(text=text, font=dict(size=17), y=1, yref="paper",
                                 yanchor="bottom", pad=dict(b=14, t=0)))
    return fig


def empty(msg="No data yet", height=220) -> go.Figure:
    fig = _base("", height)
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=TEXT_MUTED, size=14),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
    return fig


def bars(labels, values, title="", sub="", text=None, color=ACCENT_GOLD, colors=None,
         hover=None, height=None, xfmt=None, ref=None, ref_label="") -> go.Figure:
    """Ranked horizontal bars with direct value labels (largest on top)."""
    n = len(labels)
    fig = _base(title, height or max(200, 34 * n + 76), sub)
    fig.add_bar(y=list(labels), x=list(values), orientation="h",
                marker=dict(color=colors or color, cornerradius=4, line=dict(width=0)),
                text=text if text is not None else [f"{v:,.1f}" for v in values],
                textposition="outside", cliponaxis=False,
                textfont=dict(color=TEXT_MAIN, size=13, family=FONT_BODY),
                hovertext=hover, hoverinfo="text" if hover is not None else "x+y", width=0.62)
    vmax = max([abs(v) for v in values if pd.notna(v)] or [1])
    vmin = min([v for v in values if pd.notna(v)] or [0])
    fig.update_xaxes(visible=False, range=[min(0, vmin * 1.25), vmax * 1.22], tickformat=xfmt)
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=13, color=TEXT_SEC), ticksuffix="  ")
    if ref is not None:
        fig.add_vline(x=ref, line=dict(color=TEXT_DIM, width=1, dash="dot"),
                      annotation_text=ref_label, annotation_position="top",
                      annotation_font=dict(color=TEXT_MUTED, size=11))
    return fig


def diverging_bars(labels, values, title="", sub="", fmt="{:+.0f}", height=None, hover=None) -> go.Figure:
    """Signed horizontal bars around zero: blue = ahead, red = behind."""
    n = len(labels)
    fig = _base(title, height or max(200, 30 * n + 76), sub)
    fig.add_bar(y=list(labels), x=list(values), orientation="h",
                marker=dict(color=[BLUE if v >= 0 else RED for v in values], cornerradius=4),
                text=[fmt.format(v) for v in values], textposition="outside", cliponaxis=False,
                textfont=dict(color=TEXT_MAIN, size=13, family=FONT_BODY),
                hovertext=hover, hoverinfo="text" if hover is not None else "x+y", width=0.62)
    m = max([abs(v) for v in values] or [1]) * 1.3
    fig.update_xaxes(visible=False, range=[-m, m])
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=13, color=TEXT_SEC), ticksuffix="  ")
    fig.add_vline(x=0, line=dict(color=TEXT_DIM, width=1))
    return fig


# ── Specific charts ──────────────────────────────────────────────────────────

def ladder_history(history: pd.DataFrame, colors: dict, focus: list | None = None,
                   max_regular_week: int | None = None, height=440) -> go.Figure:
    """Rating by week. Focus teams are drawn in colour and labelled at the
    right edge; everyone else stays as quiet context."""
    if history is None or history.empty:
        return empty("Ratings appear after week 1")
    fig = _base("Rating by week", height, "Glicko-2 · every team starts on its salary seed")
    focus = set(focus or [])
    last_week = history["week"].max()
    ends = []
    for tid, d in history.groupby("team_id"):
        d = d.sort_values("week")
        on = tid in focus
        fig.add_scatter(
            x=d["week"], y=d["elo"], mode="lines+markers" if on else "lines",
            line=dict(color=colors.get(tid, "#64748b") if on else "rgba(100,116,139,0.28)",
                      width=2.6 if on else 1.1, shape="spline", smoothing=0.5),
            marker=dict(size=6), name=d["name"].iloc[0],
            hovertemplate="%{fullData.name}<br>Week %{x}: %{y:.0f}<extra></extra>")
        if on:
            ends.append((float(d["elo"].iloc[-1]), d["name"].iloc[0], colors.get(tid, "#64748b")))
    # de-collide right-edge labels
    ends.sort(reverse=True)
    lo, hi = history["elo"].min(), history["elo"].max()
    gap = (hi - lo) * 0.045 or 1
    placed = []
    for y, name, c in ends:
        yy = y if not placed else min(y, placed[-1] - gap)
        placed.append(yy)
        fig.add_annotation(x=last_week, y=yy, text=f"<span style='color:{c}'>●</span> {esc(name)}",
                           showarrow=False, xanchor="left", xshift=8,
                           font=dict(size=12, color=TEXT_MAIN, family=FONT_BODY))
    ticks = sorted(history["week"].unique())
    lab = ["Seed" if w == 0 else ("Playoffs" if max_regular_week and w > max_regular_week else f"W{w}")
           for w in ticks]
    fig.update_xaxes(tickvals=ticks, ticktext=lab, range=[-0.2, last_week + 0.3])
    fig.update_yaxes(showgrid=True, gridcolor="rgba(30,41,59,0.6)", tickfont=dict(size=12, color=TEXT_MUTED))
    fig.update_layout(margin=dict(l=8, r=190, t=70, b=8), hovermode="closest")
    return fig


def seed_heatmap(probs: pd.DataFrame, names: dict, spots: int, seed_labels: dict | None = None) -> go.Figure:
    """Team × seed probability grid, one hue, darker = less likely."""
    if probs is None or probs.empty:
        return empty()
    d = probs.sort_values("avg_seed").reset_index(drop=True)
    d = d[(d["make_playoffs"] > 0) | (d.index < spots + 3)]
    cols = [f"seed_{k}" for k in range(1, spots + 1)] + ["miss"]
    z = d[cols].to_numpy() * 100
    xl = [(seed_labels or {}).get(k, f"{k}") for k in range(1, spots + 1)] + ["Miss"]
    yl = [names.get(t, t) for t in d["team_id"]]
    text = [[("" if v < 0.5 else f"{v:.0f}") for v in row] for row in z]
    fig = _base("Where each team finishes — % of simulations by playoff seed",
                max(260, 30 * len(d) + 110))
    fig.add_heatmap(z=z, x=xl, y=yl, colorscale=GOLD_RAMP, zmin=0, zmax=100, showscale=False,
                    text=text, texttemplate="%{text}", xgap=3, ygap=3,
                    textfont=dict(size=12, family=FONT_BODY),
                    hovertemplate="%{y}<br>Seed %{x}: %{z:.1f}%<extra></extra>")
    fig.update_xaxes(side="top", type="category", tickfont=dict(size=12, color=TEXT_SEC))
    fig.update_yaxes(autorange="reversed", type="category", tickfont=dict(size=13, color=TEXT_SEC), ticksuffix="  ")
    fig.update_layout(margin=dict(l=8, r=8, t=84, b=8), title_pad=dict(b=38))
    return fig


def calibration_chart(cal_model: pd.DataFrame, cal_crowd: pd.DataFrame) -> go.Figure:
    fig = _base("Did the favourites deliver?", 340,
                "When a side was called an X% favourite, how often it won the series")
    fig.add_scatter(x=[50, 100], y=[50, 100], mode="lines", showlegend=False,
                    line=dict(color=TEXT_DIM, width=1, dash="dot"), hoverinfo="skip")
    fig.add_annotation(x=97, y=97, text="perfectly calibrated", showarrow=False, xanchor="right",
                       yshift=12, font=dict(size=11, color=TEXT_MUTED))
    for d, name, c in ((cal_model, "Model", BLUE), (cal_crowd, "Crowd", ACCENT_GOLD)):
        if d is None or d.empty:
            continue
        fig.add_scatter(x=d["said"] * 100, y=d["actual"] * 100, mode="lines+markers", name=name,
                        line=dict(color=c, width=2),
                        marker=dict(size=np.clip(np.sqrt(d["n"]) * 3.2, 8, 22), color=c,
                                    line=dict(color=SURFACE, width=2)),
                        customdata=d["n"],
                        hovertemplate=name + " said %{x:.0f}% → won %{y:.0f}% (%{customdata} series)<extra></extra>")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"))
    fig.update_xaxes(title_text="Favourite's stated chance", ticksuffix="%", range=[48, 102], showgrid=True)
    fig.update_yaxes(title_text="Actually won", ticksuffix="%", range=[30, 104], showgrid=True)
    fig.update_layout(margin=dict(l=8, r=16, t=84, b=8))
    return fig


def lead_chart(lead: pd.DataFrame) -> go.Figure:
    if lead is None or lead.empty:
        return empty("No 15-minute data for this season")
    fig = _base("Is a lead at 15:00 safe?", 300, "Win rate of the team ahead on gold at 15 minutes")
    fig.add_bar(x=lead["bucket"].astype(str), y=lead["wr"] * 100,
                marker=dict(color=ACCENT_GOLD, cornerradius=4), width=0.55,
                text=[f"{w * 100:.0f}%" for w in lead["wr"]], textposition="outside",
                textfont=dict(color=TEXT_MAIN, size=14, family=FONT_BODY), cliponaxis=False,
                customdata=lead["games"], hovertemplate="Lead %{x}: %{y:.0f}% (%{customdata} games)<extra></extra>")
    fig.add_hline(y=50, line=dict(color=TEXT_DIM, width=1, dash="dot"))
    fig.update_yaxes(visible=False, range=[0, 118])
    fig.update_xaxes(title_text="Gold lead at 15:00", type="category")
    return fig


def champion_scatter(ch: pd.DataFrame, min_picks: int) -> go.Figure:
    d = ch[ch["picks"] >= min_picks].copy()
    if d.empty:
        return empty("No champions meet the minimum")
    fig = _base("Contested vs. winning", 430,
                "Presence = picked or banned · bubble = games played · labelled: most contested and biggest outliers")
    d["dev"] = (d["win_rate"] - 0.5).abs() * np.sqrt(d["picks"])
    lab = set(d.nlargest(8, "presence")["champion"]) | set(d.nlargest(6, "dev")["champion"])
    fig.add_scatter(
        x=d["presence"] * 100, y=d["win_rate"] * 100, mode="markers+text",
        text=[c if c in lab else "" for c in d["champion"]], textposition="top center",
        textfont=dict(size=11, color=TEXT_SEC, family=FONT_BODY),
        marker=dict(size=np.clip(np.sqrt(d["picks"]) * 4.2, 7, 40),
                    color=[BLUE if w >= 0.5 else RED for w in d["win_rate"]], opacity=0.8,
                    line=dict(color=SURFACE, width=2)),
        customdata=np.stack([d["champion"], d["picks"], d["bans"], d["wins"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[3]}W in %{customdata[1]} games (%{y:.0f}%)"
                      "<br>%{customdata[2]} bans · %{x:.0f}% presence<extra></extra>")
    fig.add_hline(y=50, line=dict(color=TEXT_DIM, width=1, dash="dot"))
    fig.update_xaxes(title_text="Presence (pick + ban)", ticksuffix="%", showgrid=True, rangemode="tozero")
    fig.update_yaxes(title_text="Win rate", ticksuffix="%", showgrid=True, range=[-4, 104])
    return fig


def role_slot_heatmap(role_slot: pd.DataFrame) -> go.Figure:
    """When does each role get picked? Share of that role's picks per draft slot."""
    if role_slot is None or role_slot.empty:
        return empty("No draft-tool data for this season")
    p = role_slot.pivot_table(index="role", columns="pick_no", values="n", fill_value=0)
    p = p.reindex(ROLES).fillna(0)
    share = p.div(p.sum(axis=1).replace(0, 1), axis=0) * 100
    slots = [int(c) for c in share.columns]
    side = ["B", "R", "R", "B", "B", "R", "R", "B", "B", "R"]
    xl = [f"{s}<br><span style='color:{BLUE if side[s - 1] == 'B' else RED}'>{side[s - 1]}</span>" for s in slots]
    fig = _base("Which roles get locked first", 300,
                "Share of each role's picks by draft slot · B = blue side, R = red side")
    fig.add_heatmap(z=share.to_numpy(), x=xl, y=[ROLE_SHORT[r] for r in share.index],
                    colorscale=GOLD_RAMP, showscale=False, xgap=3, ygap=3, zmin=0,
                    text=[[f"{v:.0f}" if v >= 1 else "" for v in row] for row in share.to_numpy()],
                    texttemplate="%{text}", textfont=dict(size=12, family=FONT_BODY),
                    hovertemplate="%{y} · pick %{x}: %{z:.0f}% of that role's picks<extra></extra>")
    fig.update_xaxes(type="category", side="bottom", tickfont=dict(size=12))
    fig.update_yaxes(autorange="reversed", ticksuffix="  ")
    return fig


def side_chart(by_week: pd.DataFrame, overall: float) -> go.Figure:
    if by_week is None or by_week.empty:
        return empty()
    fig = _base("Blue side win rate by week", 300, f"Season: {overall * 100:.0f}% · blue side has first pick")
    fig.add_scatter(x=by_week["week"], y=by_week["blue"] * 100, mode="lines+markers",
                    line=dict(color=BLUE, width=2), marker=dict(size=8, color=BLUE, line=dict(color=SURFACE, width=2)),
                    customdata=by_week["games"],
                    hovertemplate="Week %{x}: %{y:.0f}% blue (%{customdata} games)<extra></extra>")
    fig.add_hline(y=50, line=dict(color=TEXT_DIM, width=1, dash="dot"))
    fig.update_xaxes(tickprefix="W", dtick=1)
    fig.update_yaxes(ticksuffix="%", range=[0, 100], showgrid=True)
    return fig


def value_scatter(pl: pd.DataFrame, highlight: set | None = None) -> go.Figure:
    """Salary vs. season Impact, with the league trend line: above = bargain."""
    d = pl.dropna(subset=["salary", "avg_if"])
    d = d[d["salary"] > 0]
    if len(d) < 6:
        return empty("Not enough players with a salary on file")
    slope, icpt = np.polyfit(d["salary"], d["avg_if"], 1)
    xs = np.array([d["salary"].min(), d["salary"].max()])
    fig = _base("Price vs. production", 430,
                "Each dot is a player · line = what the league gets for that salary · above the line = bargain")
    fig.add_scatter(x=xs, y=slope * xs + icpt, mode="lines",
                    line=dict(color=TEXT_DIM, width=1.5, dash="dot"), hoverinfo="skip")
    resid = d["avg_if"] - (slope * d["salary"] + icpt)
    lab = set(d.loc[resid.nlargest(5).index, "player"]) | set(d.loc[resid.nsmallest(3).index, "player"])
    lab |= (highlight or set())
    fig.add_scatter(
        x=d["salary"], y=d["avg_if"], mode="markers+text",
        text=[p if p in lab else "" for p in d["player"]], textposition="top center",
        textfont=dict(size=11, color=TEXT_SEC, family=FONT_BODY),
        marker=dict(size=9, color=[ROLE_COLORS.get(r, "#64748b") for r in d["role"]],
                    line=dict(color=SURFACE, width=1.5), opacity=0.9),
        customdata=np.stack([d["player"], d["team"], d["role"].map(ROLE_SHORT).fillna("?"), d["games"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b> · %{customdata[2]} · %{customdata[1]}"
                      "<br>Salary %{x:g} · Impact %{y:.0f} · %{customdata[3]} games<extra></extra>")
    for i, r in enumerate(ROLES):
        fig.add_annotation(xref="paper", yref="paper", x=0.0 + i * 0.075, y=-0.19, showarrow=False,
                           xanchor="left", text=f"<span style='color:{ROLE_COLORS[r]}'>●</span> {ROLE_SHORT[r]}",
                           font=dict(size=12, color=TEXT_SEC))
    fig.update_xaxes(title_text="Salary", showgrid=True)
    fig.update_yaxes(title_text="Season Impact (0–100, within role)", showgrid=True)
    fig.update_layout(margin=dict(l=8, r=16, t=70, b=56))
    return fig


def team_quadrant(tt: pd.DataFrame, colors: dict, x="gd15", y="win_pct") -> go.Figure:
    d = tt.dropna(subset=[x, y])
    if d.empty:
        return empty("No 15-minute data for this season")
    fig = _base("Early game vs. results", 420,
                "Average team gold difference at 15:00 against game win rate — who closes, who throws")
    fig.add_scatter(
        x=d[x], y=d[y] * 100, mode="markers+text", text=d["team"], textposition="top center",
        textfont=dict(size=11, color=TEXT_SEC, family=FONT_BODY),
        marker=dict(size=13, color=[colors.get(t, "#64748b") for t in d["team_id"]],
                    line=dict(color=SURFACE, width=2)),
        customdata=np.stack([d["team"], d["games"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{x:+,.0f} gold at 15 · %{y:.0f}% wins "
                      "(%{customdata[1]} games)<extra></extra>")
    fig.add_hline(y=50, line=dict(color=TEXT_DIM, width=1, dash="dot"))
    fig.add_vline(x=0, line=dict(color=TEXT_DIM, width=1, dash="dot"))
    for (ax, ay, t, xa) in ((0.99, 0.02, "Wins lane, loses game", "right"), (0.01, 0.98, "Behind early, wins anyway", "left")):
        fig.add_annotation(xref="paper", yref="paper", x=ax, y=ay, text=t, showarrow=False,
                           xanchor=xa, font=dict(size=11, color=TEXT_MUTED))
    fig.update_xaxes(title_text="Gold difference at 15:00", showgrid=True, zeroline=False)
    fig.update_yaxes(title_text="Game win rate", ticksuffix="%", showgrid=True)
    return fig


def duration_strip(games: pd.DataFrame, colors: dict) -> go.Figure:
    """Every game of the week as a dot on a time axis (winner's colour)."""
    d = games.dropna(subset=["duration"])
    if d.empty:
        return empty("No game durations recorded")
    avg = d["duration"].mean() / 60
    fig = _base("Game lengths", 190, f"Each dot is one game · average {fmt_time(d['duration'].mean())}")
    rng = np.random.default_rng(7)
    fig.add_scatter(
        x=d["duration"] / 60, y=rng.uniform(-0.28, 0.28, len(d)), mode="markers",
        marker=dict(size=13, color=[colors.get(t, "#64748b") for t in d["winnerId"]],
                    line=dict(color=SURFACE, width=2)),
        customdata=np.stack([d["winnerName"], d["loserName"], [fmt_time(x) for x in d["duration"]],
                             d["gameNumber"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b> beat %{customdata[1]} (game %{customdata[3]})"
                      "<br>%{customdata[2]}<extra></extra>")
    fig.add_vline(x=avg, line=dict(color=TEXT_DIM, width=1, dash="dot"))
    fig.update_yaxes(visible=False, range=[-1, 1])
    fig.update_xaxes(ticksuffix=" min", showgrid=True)
    return fig


def win_conditions(team_games: pd.DataFrame, week_ids: set | None = None) -> go.Figure:
    """How often the team that 'won' each early/objective race won the game."""
    d = team_games if week_ids is None else team_games[team_games["matchId"].isin(week_ids)]
    if d.empty:
        return empty()
    rows = []
    def add(label, mask):
        sub = d[mask]
        if len(sub) >= 5:
            rows.append((label, sub["win"].mean(), len(sub)))
    add("Got first blood", d["fb"] > 0)
    add("Got first tower", d["ft"] > 0)
    if d["gd15"].notna().any():
        add("Ahead on gold at 15:00", d["gd15"] > 0)
    for col, label in (("dragons", "More dragons"), ("barons", "More barons"), ("turrets", "More turrets")):
        if col in d.columns and d[col].notna().any():
            other = d.groupby("matchId")[col].transform("sum") - d[col]
            add(label, d[col] > other)
    if not rows:
        return empty()
    rows.sort(key=lambda r: -r[1])
    return bars([r[0] for r in rows], [r[1] * 100 for r in rows],
                "What wins games here", "Win rate of the team that got each edge",
                text=[f"{r[1] * 100:.0f}%" for r in rows],
                hover=[f"{r[0]}: won {r[1] * 100:.0f}% of {r[2]} games" for r in rows],
                ref=50, ref_label="coin flip")

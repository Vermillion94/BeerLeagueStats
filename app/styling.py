"""
Beer League Stats — Broadcast Visual Theme
ESPN/LCS-inspired dark theme optimized for 1920x1080 screen recording.
"""

# -- Color palette ---------------------------------------------------------------

DARK_BG      = "#080b12"      # deepest background
SURFACE      = "#0d1117"      # main content area
CARD_BG      = "#111827"      # card / panel background
CARD_BG_ALT  = "#151d2e"      # alternating row / subtle lift
BORDER_CLR   = "#1e293b"      # subtle borders
BORDER_LIGHT = "#2a3a52"      # slightly more visible borders

TEXT_MAIN    = "#f1f5f9"      # primary text — near white
TEXT_SEC     = "#94a3b8"      # secondary text
TEXT_MUTED   = "#64748b"      # muted / caption text
TEXT_DIM     = "#475569"      # very dim labels

ACCENT_GOLD  = "#FFD700"      # primary accent — electric gold
ACCENT_TEAL  = "#00d4aa"      # positive / win
ACCENT_RED   = "#ef4444"      # negative / loss
ACCENT_BLUE  = "#3b82f6"      # informational
ACCENT_CYAN  = "#22d3ee"      # secondary accent

LITE_COLOR   = "#38bdf8"      # sky blue — Lite league
STOUT_COLOR  = "#f59e0b"      # amber — Stout league

WIN_COLOR    = "#10b981"      # emerald green
LOSS_COLOR   = "#ef4444"      # red

# Fallback team color palette (used when team.color is NULL)
TEAM_PALETTE = [
    "#ef4444", "#3b82f6", "#10b981", "#f59e0b",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
    "#06b6d4", "#a855f7", "#84cc16", "#e11d48",
    "#6366f1", "#22d3ee", "#eab308", "#fb923c",
]

def team_color(team_row: dict, idx: int = 0) -> str:
    """Return team.color or fall back to the palette."""
    c = team_row.get("color") if isinstance(team_row, dict) else None
    return c if c else TEAM_PALETTE[idx % len(TEAM_PALETTE)]


# -- Plotly template (broadcast style) ------------------------------------------

PLOTLY_TEMPLATE = {
    "layout": {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {
            "color": TEXT_SEC,
            "family": "'Barlow Condensed', 'Barlow', 'Inter', sans-serif",
            "size": 13,
        },
        "title": {
            "font": {
                "size": 20,
                "color": TEXT_MAIN,
                "family": "'Oswald', 'Barlow Condensed', sans-serif",
            },
            "x": 0.0, "xanchor": "left",
            "y": 0.98, "yanchor": "top",
            "pad": {"t": 4, "b": 8},
        },
        "colorway": [ACCENT_TEAL, ACCENT_GOLD, ACCENT_RED, ACCENT_BLUE,
                     "#a855f7", "#f97316", "#14b8a6", "#eab308"],
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "font": {"color": TEXT_SEC, "size": 12,
                     "family": "'Barlow Condensed', sans-serif"},
        },
        "xaxis": {
            "gridcolor": "rgba(30,41,59,0.5)",
            "gridwidth": 1,
            "linecolor": "rgba(0,0,0,0)",
            "tickcolor": "rgba(0,0,0,0)",
            "tickfont": {"color": TEXT_MUTED, "size": 12,
                         "family": "'Barlow Condensed', sans-serif"},
            "zerolinecolor": "rgba(30,41,59,0.5)",
            "title": {"font": {"size": 12, "color": TEXT_MUTED}},
            "showgrid": False,
        },
        "yaxis": {
            "gridcolor": "rgba(30,41,59,0.5)",
            "gridwidth": 1,
            "linecolor": "rgba(0,0,0,0)",
            "tickcolor": "rgba(0,0,0,0)",
            "tickfont": {"color": TEXT_SEC, "size": 13,
                         "family": "'Barlow Condensed', sans-serif"},
            "zerolinecolor": "rgba(30,41,59,0.5)",
            "title": {"font": {"size": 12, "color": TEXT_MUTED}},
            "showgrid": False,
        },
        "polar": {
            "bgcolor": "rgba(0,0,0,0)",
            "radialaxis": {
                "gridcolor": "rgba(30,41,59,0.4)",
                "linecolor": "rgba(0,0,0,0)",
                "tickfont": {"color": TEXT_DIM, "size": 10},
            },
            "angularaxis": {
                "gridcolor": "rgba(30,41,59,0.4)",
                "linecolor": "rgba(30,41,59,0.6)",
            },
        },
        "margin": {"l": 10, "r": 40, "t": 56, "b": 10},
        "hoverlabel": {
            "bgcolor": "#1e293b",
            "bordercolor": BORDER_LIGHT,
            "font": {"color": TEXT_MAIN, "size": 13,
                     "family": "'Barlow Condensed', sans-serif"},
        },
    }
}


def apply_template(fig):
    """Apply the broadcast dark theme to a Plotly figure and return it."""
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


# -- Global CSS (broadcast design system) ----------------------------------------

GLOBAL_CSS = """
<style>
/* ---- Google Fonts ---- */
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Barlow+Condensed:wght@300;400;500;600;700&family=Barlow:wght@300;400;500;600;700&display=swap');

/* ---- Reset Streamlit chrome ---- */
#MainMenu {visibility: hidden !important;}
footer {visibility: hidden !important;}
[data-testid="stDecoration"] {display: none !important;}
[data-testid="stStatusWidget"] {display: none !important;}

/* ---- Base ---- */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background-color: #080b12 !important;
    color: #f1f5f9;
    font-family: 'Barlow', 'Inter', 'Segoe UI', sans-serif;
}
[data-testid="stAppViewBlockContainer"] {
    max-width: 1400px;
    padding: 1rem 2rem 3rem 2rem;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a0f1a 0%, #080b12 100%) !important;
    border-right: 1px solid #1e293b;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'Oswald', sans-serif;
    color: #FFD700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 600;
}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] label {
    color: #94a3b8;
    font-family: 'Barlow Condensed', sans-serif;
    letter-spacing: 0.3px;
}
[data-testid="stSidebar"] hr {
    border-color: #1e293b !important;
    opacity: 0.4;
}

/* ---- Tabs (broadcast channel selector) ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: #0d1117;
    border-bottom: 3px solid #FFD700;
    border-radius: 0;
    padding: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 14px 28px;
    font-family: 'Oswald', sans-serif;
    font-weight: 500;
    font-size: 0.95rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    transition: all 0.15s ease;
    border-bottom: 3px solid transparent;
    margin-bottom: -3px;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #f1f5f9;
    background: rgba(255,215,0,0.04);
}
.stTabs [aria-selected="true"] {
    background: rgba(255,215,0,0.08) !important;
    color: #FFD700 !important;
    border-bottom: 3px solid #FFD700 !important;
}

/* ---- Broadcast Header Banner ---- */
.broadcast-header {
    background: linear-gradient(135deg, #0d1117 0%, #111827 50%, #0d1117 100%);
    border: 1px solid #1e293b;
    border-left: 4px solid #FFD700;
    padding: 1.2rem 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.broadcast-header .title {
    font-family: 'Oswald', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: #FFD700;
    text-transform: uppercase;
    letter-spacing: 3px;
    line-height: 1;
}
.broadcast-header .subtitle {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-top: 4px;
}
.broadcast-header .week-badge {
    background: #FFD700;
    color: #080b12;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 1.1rem;
    padding: 8px 24px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}

/* ---- Stat Chyrons (broadcast lower-third style) ---- */
.chyron-row {
    display: flex;
    gap: 12px;
    margin: 1rem 0 1.5rem 0;
}
.chyron {
    flex: 1;
    background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
    border: 1px solid #1e293b;
    border-top: 3px solid #FFD700;
    padding: 1rem 1.2rem 0.8rem;
    position: relative;
    overflow: hidden;
}
.chyron::after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 60px;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,215,0,0.03));
}
.chyron .label {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.7rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    margin-bottom: 4px;
}
.chyron .value {
    font-family: 'Oswald', sans-serif;
    font-size: 2.2rem;
    font-weight: 700;
    color: #FFD700;
    line-height: 1.1;
}
.chyron .value.teal { color: #10b981; }
.chyron .value.white { color: #f1f5f9; }
.chyron .value.red { color: #ef4444; }

/* ---- Sunfire Counter (special card) ---- */
.sunfire-counter {
    background: linear-gradient(135deg, #1a0a00 0%, #2d1200 40%, #1a0a00 100%);
    border: 2px solid #f97316;
    border-top: 4px solid #f97316;
    padding: 1.5rem;
    margin: 1rem 0;
    position: relative;
    overflow: hidden;
}
.sunfire-counter::before {
    content: '';
    position: absolute;
    top: -40%;
    left: -40%;
    width: 180%;
    height: 180%;
    background: radial-gradient(circle at 30% 30%, rgba(249,115,22,0.08) 0%, transparent 50%);
    pointer-events: none;
}
.sunfire-counter .sc-title {
    font-family: 'Oswald', sans-serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: #f97316;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 4px;
}
.sunfire-counter .sc-subtitle {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.75rem;
    color: #94a3b8;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 12px;
}
.sunfire-counter .sc-stats {
    display: flex;
    gap: 24px;
    align-items: flex-end;
}
.sunfire-counter .sc-big {
    font-family: 'Oswald', sans-serif;
    font-size: 3rem;
    font-weight: 700;
    color: #f97316;
    line-height: 1;
    text-shadow: 0 0 20px rgba(249,115,22,0.3);
}
.sunfire-counter .sc-stat {
    text-align: center;
}
.sunfire-counter .sc-stat-val {
    font-family: 'Oswald', sans-serif;
    font-size: 1.4rem;
    font-weight: 700;
    color: #f1f5f9;
    line-height: 1.2;
}
.sunfire-counter .sc-stat-label {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.65rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}
.sunfire-counter .sc-builders {
    margin-top: 12px;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.85rem;
    color: #94a3b8;
    line-height: 1.6;
}
.sunfire-counter .sc-builders .win { color: #10b981; }
.sunfire-counter .sc-builders .loss { color: #ef4444; }

/* ---- Broadcast Panel (card container) ---- */
.broadcast-panel {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 2px;
    padding: 0;
    margin-bottom: 1rem;
    overflow: hidden;
}
.broadcast-panel .panel-header {
    background: linear-gradient(90deg, #1e293b 0%, #111827 100%);
    padding: 10px 16px;
    border-bottom: 1px solid #1e293b;
    display: flex;
    align-items: center;
    gap: 10px;
}
.broadcast-panel .panel-title {
    font-family: 'Oswald', sans-serif;
    font-size: 0.85rem;
    font-weight: 600;
    color: #f1f5f9;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}
.broadcast-panel .panel-accent {
    width: 4px;
    height: 16px;
    background: #FFD700;
    flex-shrink: 0;
}
.broadcast-panel .panel-body {
    padding: 12px 16px;
}

/* ---- Matchup Card (series results) ---- */
.matchup-card {
    background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
    border: 1px solid #1e293b;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    position: relative;
    overflow: hidden;
}
.matchup-card .team {
    flex: 1;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
}
.matchup-card .team-name {
    font-family: 'Oswald', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #94a3b8;
}
.matchup-card .team-name.winner {
    color: #f1f5f9;
}
.matchup-card .score-box {
    display: flex;
    align-items: center;
    gap: 0;
    flex-shrink: 0;
}
.matchup-card .score {
    font-family: 'Oswald', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    width: 44px;
    text-align: center;
    padding: 10px 0;
}
.matchup-card .score.winner {
    background: #FFD700;
    color: #080b12;
}
.matchup-card .score.loser {
    background: #1e293b;
    color: #64748b;
}
.matchup-card .score-divider {
    width: 2px;
    height: 100%;
    background: #080b12;
}
.matchup-card .win-indicator {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: #FFD700;
}
.matchup-card.left-wins .win-indicator { left: 0; }
.matchup-card.right-wins .win-indicator { left: auto; right: 0; }

/* ---- Section header (gold accent bar) ---- */
.section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 2rem 0 1rem 0;
    padding-bottom: 0;
}
.section-header .gold-bar {
    width: 4px;
    height: 24px;
    background: #FFD700;
    flex-shrink: 0;
}
.section-header .text {
    font-family: 'Oswald', sans-serif;
    font-size: 1.3rem;
    font-weight: 600;
    color: #f1f5f9;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}

/* ---- League / Division badges ---- */
.badge {
    display: inline-block;
    padding: 3px 12px;
    font-family: 'Oswald', sans-serif;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    vertical-align: middle;
    margin-left: 10px;
}
.badge-lite  { background: #38bdf8; color: #080b12; }
.badge-stout { background: #f59e0b; color: #080b12; }
.badge-gold  { background: #FFD700; color: #080b12; }
.badge-week  {
    background: #FFD700;
    color: #080b12;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 0.8rem;
    padding: 4px 16px;
    letter-spacing: 1.5px;
}
.badge-live  {
    background: #ef4444;
    color: #fff;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 0.65rem;
    padding: 3px 10px;
    letter-spacing: 1.5px;
    animation: pulse-live 2s infinite;
}
@keyframes pulse-live {
    0%   { opacity: 1; }
    50%  { opacity: 0.5; }
    100% { opacity: 1; }
}

/* ---- POW Card (Player of the Week) ---- */
.pow-card {
    background: linear-gradient(135deg, #111827 0%, #0f172a 50%, #1a1145 100%);
    border: 1px solid rgba(255,215,0,0.3);
    border-top: 3px solid #FFD700;
    padding: 2rem 1.5rem;
    text-align: center;
    margin-bottom: 1rem;
    position: relative;
    overflow: hidden;
}
.pow-card::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle at center, rgba(255,215,0,0.04) 0%, transparent 50%);
}
.pow-name {
    font-family: 'Oswald', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: #FFD700;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 0.5rem 0;
}
.pow-champ {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1rem;
    color: #10b981;
    font-weight: 500;
    letter-spacing: 0.5px;
}
.pow-score {
    font-family: 'Oswald', sans-serif;
    font-size: 3.2rem;
    font-weight: 700;
    color: #ffffff;
    text-shadow: 0 0 30px rgba(255,215,0,0.3);
    line-height: 1.1;
    margin-top: 0.3rem;
}

/* ---- Upset / Close matchup alert ---- */
.upset-alert {
    background: #ef4444;
    font-family: 'Oswald', sans-serif;
    padding: 4px 14px;
    font-weight: 600;
    font-size: 0.7rem;
    color: #fff;
    display: inline-block;
    margin-bottom: 6px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

/* ---- Narrative callouts ---- */
.narrative-callout {
    border-left: 3px solid #FFD700;
    background: linear-gradient(90deg, rgba(255,215,0,0.08) 0%, transparent 60%);
    padding: 6px 14px;
    margin: 4px 0;
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 0.85rem;
    color: #e2e8f0;
    letter-spacing: 0.3px;
}
.narrative-callout .narrative-type {
    font-family: 'Oswald', sans-serif;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #FFD700;
    margin-right: 8px;
}

/* ---- Metric cards (Streamlit default override) ---- */
[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid #1e293b;
    border-top: 3px solid #FFD700;
    border-radius: 0;
    padding: 1rem 1.2rem;
}
[data-testid="stMetricValue"] {
    color: #FFD700 !important;
    font-family: 'Oswald', sans-serif !important;
    font-size: 2rem !important;
    font-weight: 700 !important;
}
[data-testid="stMetricLabel"] {
    color: #64748b !important;
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}
[data-testid="stMetricDelta"] {
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 0.85rem !important;
}

/* ---- Dataframe ---- */
[data-testid="stDataFrame"] {
    background: #111827 !important;
    border: 1px solid #1e293b;
    border-radius: 0;
}

/* ---- Dividers ---- */
hr {
    border-color: #1e293b !important;
    margin: 2rem 0;
    opacity: 0.3;
}

/* ---- Expander ---- */
[data-testid="stExpander"] {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 0;
}
[data-testid="stExpander"] summary {
    font-family: 'Barlow Condensed', sans-serif;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #94a3b8;
}

/* ---- Plotly chart containers ---- */
[data-testid="stPlotlyChart"] {
    border-radius: 0;
    overflow: hidden;
}

/* ---- Selectbox / multiselect ---- */
[data-baseweb="select"] {
    border-radius: 0 !important;
}
[data-baseweb="select"] > div {
    background: #111827 !important;
    border-color: #1e293b !important;
    font-family: 'Barlow Condensed', sans-serif !important;
}

/* ---- Radio buttons ---- */
[data-testid="stRadio"] label {
    font-family: 'Barlow Condensed', sans-serif;
    letter-spacing: 0.3px;
}

/* ---- Number input ---- */
[data-testid="stNumberInput"] input {
    background: #111827 !important;
    border-color: #1e293b !important;
    color: #f1f5f9 !important;
}

/* ---- Text input ---- */
[data-testid="stTextInput"] input {
    background: #111827 !important;
    border-color: #1e293b !important;
    color: #f1f5f9 !important;
    font-family: 'Barlow Condensed', sans-serif;
}

/* ---- Slider ---- */
[data-testid="stSlider"] {
    font-family: 'Barlow Condensed', sans-serif;
}

/* ---- Gold accent divider (thin line) ---- */
.gold-divider {
    height: 1px;
    background: linear-gradient(90deg, #FFD700, transparent);
    margin: 1.5rem 0;
    opacity: 0.4;
}

/* ---- Scrollbar ---- */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #080b12;
}
::-webkit-scrollbar-thumb {
    background: #1e293b;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: #334155;
}

/* ---- Multiselect tags ---- */
[data-baseweb="tag"] {
    background: #1e293b !important;
    border-color: #FFD700 !important;
    font-family: 'Barlow Condensed', sans-serif;
}
</style>
"""


def apply_theme():
    """Inject global CSS. Call once at app startup."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def section_header(title: str, badge_html: str = "") -> str:
    """Return HTML for a broadcast-style section header with gold accent bar."""
    return (
        f'<div class="section-header">'
        f'<div class="gold-bar"></div>'
        f'<div class="text">{title}</div>'
        f'{badge_html}'
        f'</div>'
    )


def league_badge(league_name: str) -> str:
    """Return HTML badge for a league name."""
    cls = "badge-lite" if "lite" in league_name.lower() else "badge-stout"
    return f'<span class="badge {cls}">{league_name}</span>'


def broadcast_header(title: str, subtitle: str = "", badge: str = "") -> str:
    """Return HTML for a top-of-tab broadcast header banner."""
    badge_html = f'<div class="week-badge">{badge}</div>' if badge else ""
    return (
        f'<div class="broadcast-header">'
        f'<div>'
        f'<div class="title">{title}</div>'
        f'<div class="subtitle">{subtitle}</div>'
        f'</div>'
        f'{badge_html}'
        f'</div>'
    )


def stat_chyron(label: str, value: str, color_class: str = "") -> str:
    """Return HTML for a single broadcast stat chyron."""
    cls = f" {color_class}" if color_class else ""
    return (
        f'<div class="chyron">'
        f'<div class="label">{label}</div>'
        f'<div class="value{cls}">{value}</div>'
        f'</div>'
    )


def chyron_row(chyrons: list[str]) -> str:
    """Wrap multiple chyron HTMLs in a flex row."""
    inner = "".join(chyrons)
    return f'<div class="chyron-row">{inner}</div>'


def matchup_card(
    team1_name: str, team1_score: int,
    team2_name: str, team2_score: int,
    winner_name: str = "",
) -> str:
    """Return HTML for a broadcast-style matchup result card."""
    t1_winner = winner_name == team1_name
    t2_winner = winner_name == team2_name
    side_class = "left-wins" if t1_winner else "right-wins" if t2_winner else ""
    t1_name_cls = "team-name winner" if t1_winner else "team-name"
    t2_name_cls = "team-name winner" if t2_winner else "team-name"
    s1_cls = "score winner" if t1_winner else "score loser"
    s2_cls = "score winner" if t2_winner else "score loser"
    indicator = '<div class="win-indicator"></div>' if winner_name else ""

    return (
        f'<div class="matchup-card {side_class}">'
        f'{indicator}'
        f'<div class="team"><div class="{t1_name_cls}">{team1_name}</div></div>'
        f'<div class="score-box">'
        f'<div class="{s1_cls}">{team1_score}</div>'
        f'<div class="score-divider"></div>'
        f'<div class="{s2_cls}">{team2_score}</div>'
        f'</div>'
        f'<div class="team" style="justify-content:flex-end">'
        f'<div class="{t2_name_cls}">{team2_name}</div>'
        f'</div>'
        f'</div>'
    )


def narrative_callout(text: str, narrative_type: str = "streak") -> str:
    """Return HTML for a narrative callout card."""
    type_labels = {
        "streak": "STREAK",
        "record": "STANDOUT",
        "trend": "TRENDING",
        "upset": "DRAMA",
    }
    label = type_labels.get(narrative_type, narrative_type.upper())
    return (
        f'<div class="narrative-callout">'
        f'<span class="narrative-type">{label}</span> {text}'
        f'</div>'
    )


def champion_icon(champion_name: str, size: int = 28) -> str:
    """Return an HTML <img> tag for a champion's Data Dragon square icon."""
    from app.data_loader import champion_icon_url
    url = champion_icon_url(champion_name)
    if not url:
        return ""
    return (
        f'<img src="{url}" alt="{champion_name}" '
        f'style="width:{size}px;height:{size}px;border-radius:4px;'
        f'vertical-align:middle;margin-right:6px;border:1px solid {BORDER_CLR}">'
    )


# Rank tier colors (for badges)
_RANK_COLORS = {
    "CHALLENGER": ("#F4C874", "#1a1400"),
    "GRANDMASTER": ("#EF4444", "#1a0000"),
    "MASTER": ("#A855F7", "#1a0020"),
    "DIAMOND": ("#60A5FA", "#001a33"),
    "EMERALD": ("#34D399", "#001a12"),
    "PLATINUM": ("#22D3EE", "#001a20"),
    "GOLD": ("#F59E0B", "#1a1000"),
    "SILVER": ("#94A3B8", "#1a1a1a"),
    "BRONZE": ("#CD7F32", "#1a0e00"),
    "IRON": ("#6B7280", "#111"),
}


def rank_badge(tier: str, label: str) -> str:
    """Return an inline HTML badge for a solo queue rank."""
    fg, bg = _RANK_COLORS.get(tier, (TEXT_MUTED, CARD_BG))
    return (
        f'<span style="display:inline-block;padding:1px 8px;'
        f'font-family:Barlow Condensed,sans-serif;font-size:0.65rem;'
        f'font-weight:600;letter-spacing:0.8px;'
        f'color:{fg};background:{bg};border:1px solid {fg}33;'
        f'border-radius:2px;vertical-align:middle;margin-left:6px">'
        f'{label}</span>'
    )


def gold_divider() -> str:
    """Return HTML for a thin gold gradient divider."""
    return '<div class="gold-divider"></div>'


def segment_divider(number: int, title: str, subtitle: str = "") -> str:
    """Return HTML for a broadcast segment transition divider."""
    sub_html = (
        f'<div style="font-family:Barlow Condensed,sans-serif;font-size:0.8rem;'
        f'color:{TEXT_MUTED};letter-spacing:1px;text-transform:uppercase;'
        f'margin-top:2px">{subtitle}</div>'
    ) if subtitle else ""
    return (
        f'<div style="margin:2.5rem 0 1.5rem 0;padding:1rem 0 0.8rem 0;'
        f'border-top:2px solid {ACCENT_GOLD};position:relative">'
        f'<div style="display:flex;align-items:baseline;gap:14px">'
        f'<span style="font-family:Oswald,sans-serif;font-size:2.4rem;'
        f'font-weight:700;color:{ACCENT_GOLD};line-height:1;opacity:0.25">'
        f'{number:02d}</span>'
        f'<div>'
        f'<div style="font-family:Oswald,sans-serif;font-size:1.3rem;'
        f'font-weight:600;color:{TEXT_MAIN};text-transform:uppercase;'
        f'letter-spacing:2px">{title}</div>'
        f'{sub_html}'
        f'</div></div></div>'
    )


def talking_point(text: str) -> str:
    """Return HTML for a presenter talking-point card."""
    return (
        f'<div style="border-left:3px solid {ACCENT_GOLD};'
        f'background:linear-gradient(90deg,rgba(255,215,0,0.06) 0%,transparent 80%);'
        f'padding:10px 16px;margin:8px 0 16px 0;'
        f'font-family:Barlow Condensed,sans-serif;font-size:0.95rem;'
        f'color:{TEXT_MAIN};letter-spacing:0.3px;line-height:1.5">'
        f'<span style="font-family:Oswald,sans-serif;font-size:0.6rem;'
        f'color:{ACCENT_GOLD};text-transform:uppercase;letter-spacing:1.5px;'
        f'display:block;margin-bottom:4px">TALKING POINT</span>'
        f'{text}</div>'
    )


def sunfire_counter(total: int, wins: int, losses: int, win_rate: float,
                    builders: list[dict] = None) -> str:
    """Return HTML for the Slamurai's Sunfire Counter card."""
    wr_color = "#10b981" if win_rate > 0.5 else "#ef4444" if win_rate < 0.45 else "#f59e0b"
    wr_pct = f"{win_rate * 100:.0f}%"

    builders_html = ""
    if builders:
        entries = []
        for b in builders:
            cls = "win" if b["win"] else "loss"
            result = "W" if b["win"] else "L"
            entries.append(
                f'<span class="{cls}">{b["player"]}</span> ({b["champion"]}) '
                f'<span class="{cls}">[{result}]</span>'
            )
        builders_html = (
            f'<div class="sc-builders">'
            f'{"&nbsp;&nbsp;|&nbsp;&nbsp;".join(entries)}'
            f'</div>'
        )

    return (
        f'<div class="sunfire-counter">'
        f'<div class="sc-title">Slamurai\'s Sunfire Counter</div>'
        f'<div class="sc-subtitle">"This item is grief" - Slamurai, probably</div>'
        f'<div class="sc-stats">'
        f'<div class="sc-big">{total}</div>'
        f'<div class="sc-stat"><div class="sc-stat-val" style="color:{wr_color}">{wr_pct}</div>'
        f'<div class="sc-stat-label">Win Rate</div></div>'
        f'<div class="sc-stat"><div class="sc-stat-val" style="color:#10b981">{wins}</div>'
        f'<div class="sc-stat-label">Wins</div></div>'
        f'<div class="sc-stat"><div class="sc-stat-val" style="color:#ef4444">{losses}</div>'
        f'<div class="sc-stat-label">Losses</div></div>'
        f'<div style="flex:1"></div>'
        f'<div class="sc-stat"><div class="sc-stat-label" style="font-size:0.8rem;color:#f97316">'
        f'TIMES BUILT</div></div>'
        f'</div>'
        f'{builders_html}'
        f'</div>'
    )


# ── Broadcast v2 — Story-driven talking point types ─────────────────────────

def host_hook(text: str) -> str:
    """Large gold question/claim to open a segment. The headline."""
    return (
        f'<div style="text-align:center;margin:1.5rem 0 1rem 0;padding:0.8rem 1rem">'
        f'<div style="font-family:Oswald,sans-serif;font-size:1.6rem;font-weight:600;'
        f'color:{ACCENT_GOLD};line-height:1.3;letter-spacing:0.5px">'
        f'{text}</div></div>'
    )


def host_read(text: str) -> str:
    """Main talking point block the host reads verbatim. Teleprompter style."""
    return (
        f'<div style="border-left:3px solid {ACCENT_GOLD};'
        f'background:linear-gradient(90deg,rgba(255,215,0,0.06) 0%,transparent 80%);'
        f'padding:12px 18px;margin:10px 0 14px 0;'
        f'font-family:Barlow Condensed,sans-serif;font-size:1.05rem;'
        f'color:{TEXT_MAIN};letter-spacing:0.3px;line-height:1.7">'
        f'{text}</div>'
    )


def host_transition(text: str) -> str:
    """One-liner bridge to the next segment. Small, muted, italic."""
    return (
        f'<div style="font-family:Barlow Condensed,sans-serif;font-size:0.85rem;'
        f'color:{TEXT_MUTED};font-style:italic;letter-spacing:0.3px;'
        f'margin:6px 0 20px 0;padding-left:6px">'
        f'{text}</div>'
    )

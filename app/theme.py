"""Beer League Stats — v2 component styles (nav, tables, cards), layered on
top of the broadcast theme in app/styling.py."""

V2_CSS = """
<style>
[data-testid="stAppViewBlockContainer"], [data-testid="stMainBlockContainer"] {
    max-width: 1320px; padding: 1.2rem 2rem 4rem 2rem;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ---- Masthead ---- */
.mast { display:flex; align-items:flex-end; justify-content:space-between; gap:16px;
        border-bottom:1px solid #1e293b; padding-bottom:12px; margin-bottom:4px; flex-wrap:wrap; }
.mast-title { font-family:'Oswald',sans-serif; font-weight:700; font-size:1.9rem; line-height:1;
              letter-spacing:2px; text-transform:uppercase; color:#f1f5f9; }
.mast-title b { color:#FFD700; font-weight:700; }
.mast-sub { font-family:'Barlow Condensed',sans-serif; color:#94a3b8; letter-spacing:1.5px;
            text-transform:uppercase; font-size:0.9rem; margin-top:6px; }
.mast-meta { font-family:'Barlow Condensed',sans-serif; color:#64748b; font-size:0.85rem;
             letter-spacing:0.5px; text-align:right; }
.mast-meta b { color:#94a3b8; font-weight:500; }

/* ---- Page nav (horizontal radio dressed as a tab bar) ---- */
.st-key-nav [role="radiogroup"] { gap:0; border-bottom:2px solid #1e293b; flex-wrap:wrap; }
.st-key-nav [role="radiogroup"] > label { margin:0; padding:10px 18px 9px; border-bottom:3px solid transparent;
    margin-bottom:-2px; cursor:pointer; background:transparent; }
.st-key-nav [role="radiogroup"] > label > div:first-child { display:none; }
.st-key-nav [role="radiogroup"] > label p { font-family:'Oswald',sans-serif; font-size:0.92rem;
    letter-spacing:1.3px; text-transform:uppercase; color:#64748b; font-weight:500; }
.st-key-nav [role="radiogroup"] > label:hover p { color:#f1f5f9; }
.st-key-nav [role="radiogroup"] > label:has(input:checked) { border-bottom-color:#FFD700; background:rgba(255,215,0,0.06); }
.st-key-nav [role="radiogroup"] > label:has(input:checked) p { color:#FFD700; }

/* ---- Section heading ---- */
.h2 { display:flex; align-items:baseline; gap:10px; margin:1.6rem 0 0.7rem 0; }
.h2-bar { width:4px; height:18px; background:#FFD700; align-self:center; flex-shrink:0; }
.h2-text { font-family:'Oswald',sans-serif; font-size:1.15rem; font-weight:600; color:#f1f5f9;
           text-transform:uppercase; letter-spacing:1.5px; }
.h2-sub { font-family:'Barlow Condensed',sans-serif; color:#64748b; font-size:0.9rem; letter-spacing:0.4px; }
.note { font-family:'Barlow Condensed',sans-serif; color:#64748b; font-size:0.9rem; letter-spacing:0.3px;
        line-height:1.45; margin:0.3rem 0 0.8rem 0; }
.note b { color:#94a3b8; font-weight:500; }

/* ---- KPI tiles ---- */
.kpi-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:0.9rem 0 0.4rem 0; }
.kpi { background:#111827; border:1px solid #1e293b; border-top:2px solid #FFD700; padding:12px 14px 10px; min-width:0; }
.kpi-label { font-family:'Barlow Condensed',sans-serif; font-size:0.72rem; font-weight:600; color:#64748b;
             text-transform:uppercase; letter-spacing:1.6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.kpi-value { font-family:'Oswald',sans-serif; font-size:1.75rem; font-weight:600; color:#f1f5f9; line-height:1.2;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.kpi-sub { font-family:'Barlow Condensed',sans-serif; font-size:0.84rem; color:#94a3b8; letter-spacing:0.3px;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.kpi.gold .kpi-value { color:#FFD700; }

/* ---- League table ---- */
.tbl-wrap { overflow-x:auto; border:1px solid #1e293b; background:#0d1117; }
table.tbl { width:100%; border-collapse:collapse; font-family:'Barlow Condensed',sans-serif; font-size:0.98rem; }
table.tbl th { font-family:'Oswald',sans-serif; font-weight:500; font-size:0.7rem; letter-spacing:1.4px;
               text-transform:uppercase; color:#64748b; text-align:left; padding:8px 10px;
               border-bottom:1px solid #1e293b; background:#111827; white-space:nowrap; }
table.tbl td { padding:7px 9px; border-bottom:1px solid #151d2e; color:#cbd5e1; white-space:nowrap; }
table.tbl tr:last-child td { border-bottom:none; }
table.tbl tr:hover td { background:rgba(255,215,0,0.035); }
table.tbl .num { text-align:right; font-variant-numeric:tabular-nums; }
table.tbl th.num { text-align:right; }
table.tbl td.rank { color:#64748b; width:28px; }
table.tbl td.team { color:#f1f5f9; font-weight:500; letter-spacing:0.3px; max-width:230px;
                    overflow:hidden; text-overflow:ellipsis; }
table.tbl td.strong { color:#f1f5f9; font-weight:600; }
table.tbl td.muted, table.tbl .muted { color:#475569; }
table.tbl tr.cutline td { border-bottom:2px dashed #FFD70088; }
table.tbl tr.below td.team { color:#94a3b8; }
table.tbl tr.dropped td { color:#475569; font-style:italic; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin:0 8px 1px 0; vertical-align:middle; flex-shrink:0; }
.seed { font-size:0.7rem; color:#64748b; margin-left:8px; letter-spacing:0.8px; }
.tie { color:#f59e0b; font-weight:700; cursor:help; }
.pill { display:inline-block; width:17px; height:17px; line-height:17px; text-align:center; font-size:0.66rem;
        font-weight:700; margin-right:3px; border-radius:3px; font-family:'Oswald',sans-serif; }
.pill.w { background:#4f8ff7; color:#06101f; }
.pill.l { background:#1e293b; color:#94a3b8; }
.streak.w { color:#7fb0ff; } .streak.l { color:#f0787c; }
.tag { font-family:'Oswald',sans-serif; font-size:0.66rem; letter-spacing:1.3px; padding:2px 9px; }
.tag.in { background:#FFD700; color:#080b12; } .tag.out { background:#1e293b; color:#64748b; }
.pbar { position:relative; display:inline-block; width:74px; height:18px; background:#151d2e; vertical-align:middle; }
.pbar-fill { position:absolute; left:0; top:0; bottom:0; background:#7a6410; }
.pbar span { position:relative; display:block; text-align:right; padding-right:6px; font-size:0.85rem; color:#f1f5f9; line-height:18px; }

/* ---- Story cards ---- */
.story-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:10px; }
.story { background:#111827; border:1px solid #1e293b; border-left:3px solid #FFD700; padding:10px 14px 12px; }
.story-tag { font-family:'Oswald',sans-serif; font-size:0.66rem; letter-spacing:1.6px; color:#FFD700; margin-bottom:3px; }
.story-text { font-family:'Barlow Condensed',sans-serif; font-size:1.02rem; color:#cbd5e1; line-height:1.4; letter-spacing:0.2px; }
.story-text b { color:#f1f5f9; font-weight:600; }

/* ---- Result + forecast cards ---- */
.card-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:10px; }
.rc, .fc { background:#111827; border:1px solid #1e293b; padding:10px 14px; position:relative; min-width:0; }
.rc-row, .fc-teams { display:flex; align-items:center; gap:10px; }
.rc-team, .fc-team { flex:1; min-width:0; font-family:'Oswald',sans-serif; font-size:0.95rem; letter-spacing:0.6px;
    text-transform:uppercase; color:#94a3b8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rc-team.right, .fc-team.right { text-align:right; }
.rc-team.right .dot, .fc-team.right .dot { margin:0 0 1px 8px; }
.rc-team.win, .fc-team { color:#f1f5f9; }
.rc-score { display:flex; gap:2px; flex-shrink:0; }
.rc-score span { font-family:'Oswald',sans-serif; font-weight:700; font-size:1.15rem; width:30px; text-align:center;
    padding:2px 0; background:#1e293b; color:#64748b; }
.rc-score span.win { background:#FFD700; color:#080b12; }
.rc-sub { font-family:'Barlow Condensed',sans-serif; font-size:0.86rem; color:#64748b; margin-top:6px; letter-spacing:0.3px; }
.rc-sub b { color:#94a3b8; font-weight:500; }
.rc-badge { position:absolute; top:-1px; right:-1px; background:#e5484d; color:#fff; font-family:'Oswald',sans-serif;
    font-size:0.6rem; letter-spacing:1.4px; padding:1px 8px; }
.fc-vs { font-family:'Barlow Condensed',sans-serif; color:#475569; font-size:0.8rem; text-transform:uppercase; }
.duel { display:grid; grid-template-columns:48px 1fr 74px; gap:8px; align-items:center; margin-top:7px; }
.duel-label { font-family:'Oswald',sans-serif; font-size:0.66rem; letter-spacing:1.3px; text-transform:uppercase; color:#64748b; }
.duel-track { display:flex; height:20px; gap:2px; font-family:'Barlow Condensed',sans-serif; font-size:0.85rem; font-weight:600; }
.duel-a { background:#4f8ff7; color:#06101f; padding-left:6px; line-height:20px; border-radius:3px 0 0 3px; min-width:34px; }
.duel-b { background:#e5484d; color:#fff; flex:1; text-align:right; padding-right:6px; line-height:20px; border-radius:0 3px 3px 0; min-width:34px; }
.duel-n, .duel-empty { font-family:'Barlow Condensed',sans-serif; font-size:0.78rem; color:#64748b; white-space:nowrap; }
.duel-empty { grid-column:2 / span 2; }

/* ---- Percentile profile ---- */
.pb-wrap { background:#111827; border:1px solid #1e293b; padding:10px 14px; }
.pb { display:grid; grid-template-columns:130px 1fr 78px 30px; gap:10px; align-items:center; padding:4px 0; }
.pb-l { font-family:'Barlow Condensed',sans-serif; color:#94a3b8; font-size:0.92rem; letter-spacing:0.3px; white-space:nowrap; }
.pb-t { height:8px; background:#1e293b; border-radius:4px; overflow:hidden; }
.pb-f { height:100%; background:#64748b; border-radius:4px; }
.pb-f.hi { background:#4f8ff7; } .pb-f.lo { background:#e5484d; }
.pb-v { font-family:'Barlow Condensed',sans-serif; color:#f1f5f9; font-size:0.95rem; text-align:right; font-variant-numeric:tabular-nums; }
.pb-p { font-family:'Barlow Condensed',sans-serif; color:#64748b; font-size:0.78rem; text-align:right; }

/* ---- Hero card (player / team) ---- */
.hero { background:linear-gradient(135deg,#111827 0%,#0f172a 60%,#17142e 100%); border:1px solid #1e293b;
        border-top:3px solid #FFD700; padding:16px 18px; }
.hero-kicker { font-family:'Oswald',sans-serif; font-size:0.68rem; letter-spacing:1.8px; color:#FFD700; text-transform:uppercase; }
.hero-name { font-family:'Oswald',sans-serif; font-size:1.7rem; font-weight:700; color:#f1f5f9; letter-spacing:0.8px;
             line-height:1.2; text-transform:uppercase; overflow-wrap:anywhere; }
.hero-meta { font-family:'Barlow Condensed',sans-serif; color:#94a3b8; font-size:0.98rem; letter-spacing:0.4px; margin-top:2px; }
.hero-stats { display:flex; gap:22px; flex-wrap:wrap; margin-top:12px; }
.hero-stat .v { font-family:'Oswald',sans-serif; font-size:1.35rem; color:#f1f5f9; font-weight:600; line-height:1.1; }
.hero-stat .l { font-family:'Barlow Condensed',sans-serif; font-size:0.7rem; color:#64748b; letter-spacing:1.4px; text-transform:uppercase; }

/* ---- Bracket preview ---- */
.bk { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:10px; }
.bk-m { background:#111827; border:1px solid #1e293b; padding:8px 12px; }
.bk-h { font-family:'Oswald',sans-serif; font-size:0.62rem; letter-spacing:1.5px; color:#64748b; text-transform:uppercase; margin-bottom:4px; }
.bk-t { font-family:'Barlow Condensed',sans-serif; font-size:1rem; color:#f1f5f9; display:flex; align-items:center; padding:2px 0; }
.bk-t .s { color:#FFD700; font-family:'Oswald',sans-serif; font-size:0.72rem; width:30px; flex-shrink:0; }
.bk-t.bye { color:#64748b; font-style:italic; }

[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-size:0.98rem; }
@media (max-width: 760px) {
  [data-testid="stAppViewBlockContainer"], [data-testid="stMainBlockContainer"] { padding:1rem 0.8rem 3rem; }
  .mast-title { font-size:1.4rem; }
  .pb { grid-template-columns:96px 1fr 64px 24px; }
}
</style>
"""


def apply_theme_v2():
    """Base broadcast theme + v2 components."""
    import streamlit as st
    from app.styling import GLOBAL_CSS
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(V2_CSS, unsafe_allow_html=True)

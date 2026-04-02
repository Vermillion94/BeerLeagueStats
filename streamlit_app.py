"""
Beer League Stats — Streamlit Dashboard
Run: streamlit run streamlit_app.py
"""
import streamlit as st
import pandas as pd

from app.styling import (
    apply_theme, section_header, league_badge,
    broadcast_header, stat_chyron, chyron_row, matchup_card, gold_divider,
    sunfire_counter, champion_icon, rank_badge,
    LITE_COLOR, STOUT_COLOR, ACCENT_GOLD, ACCENT_TEAL, ACCENT_RED,
    TEXT_MUTED, TEXT_SEC, TEXT_MAIN, WIN_COLOR, LOSS_COLOR,
)
from app.data_loader import (
    get_db_paths, load_seasons, load_teams_for_season, load_all_teams,
    season_has_data, load_completed_weeks, load_week_data, load_series_for_week,
    load_all_completed_matches, load_all_completed_matches_named,
    load_all_player_stats, load_head_to_head,
    load_champion_stats, load_champion_presence, load_upcoming_series,
    load_all_series, load_ban_stats, load_peak_ranks,
    load_role_mapping, load_team_records, load_draft_diversity, load_early_game_stats,
    load_item_stats, load_sunfire_stats,
)
from app.elo import compute_elo_through_week, salary_seeding, win_probability, STARTING_ELO
from app.impact_factor import compute_impact_factors, player_of_the_week, weight_breakdown
from app.config import (
    UPSET_THRESHOLD, CLOSE_MATCHUP_THRESHOLD, DEFAULT_RD,
    CHAMP_MIN_GAMES_DEFAULT, CHAMP_MIN_GAMES_MAX,
    TRENDING_WEEKS_LOOKBACK, MIN_WEEKS_FOR_TRENDING,
)
from app import charts

# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Beer League Stats",
    page_icon="🍺",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


# -- Cached data helpers -------------------------------------------------------

@st.cache_data
def _seasons(db):
    return load_seasons(db)

@st.cache_data
def _teams(db, sid):
    return load_teams_for_season(db, sid)

@st.cache_data
def _all_teams(db):
    return load_all_teams(db)

@st.cache_data
def _completed_weeks(db, sid):
    return load_completed_weeks(db, sid)

@st.cache_data
def _week_data(db, week, sid):
    return load_week_data(db, week, sid)

@st.cache_data
def _all_matches(db, sid):
    return load_all_completed_matches(db, sid)

@st.cache_data
def _all_matches_named(db, sid):
    return load_all_completed_matches_named(db, sid)

@st.cache_data
def _all_player_stats(db, sid):
    return load_all_player_stats(db, sid)

@st.cache_data
def _champion_stats(db, sids_tuple):
    return load_champion_stats(db, list(sids_tuple))

@st.cache_data
def _champion_presence(db, sids_tuple):
    return load_champion_presence(db, list(sids_tuple))

@st.cache_data
def _ban_stats(db, sids_tuple):
    return load_ban_stats(db, list(sids_tuple))

@st.cache_data
def _upcoming(db, sid):
    return load_upcoming_series(db, sid)

@st.cache_data
def _all_series(db, sid):
    return load_all_series(db, sid)

@st.cache_data
def _role_map(db, sid):
    return load_role_mapping(db, sid)

@st.cache_data
def _elo(db, sid, through_week):
    matches = _all_matches(db, sid)
    teams = _teams(db, sid)
    name_map = dict(zip(teams["teamId"].astype(str), teams["name"]))
    salary_map = dict(zip(teams["teamId"].astype(str),
                          pd.to_numeric(teams["salaryTotal"], errors="coerce").fillna(0)))
    return compute_elo_through_week(matches, through_week, name_map, salary_map)

@st.cache_data
def _team_records(db, sid):
    return load_team_records(db, sid)

@st.cache_data
def _draft_diversity(db, sid):
    return load_draft_diversity(db, sid)

@st.cache_data
def _early_game(db, sid):
    return load_early_game_stats(db, sid)

@st.cache_data
def _item_stats(db, sid):
    return load_item_stats(db, sid)

@st.cache_data
def _sunfire_stats(db, sid):
    return load_sunfire_stats(db, sid)

@st.cache_data
def _peak_ranks(db):
    return load_peak_ranks(db)


# -- Helper: build team color map ----------------------------------------------

def _build_team_colors(db, sid):
    teams_df = _teams(db, sid)
    from app.styling import team_color as _tc
    return {
        str(t["teamId"]): _tc(t.to_dict(), i)
        for i, (_, t) in enumerate(teams_df.iterrows())
    }


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## BEER LEAGUE STATS")
    st.markdown("---")

    # DB selector
    db_paths = get_db_paths()
    if not db_paths:
        st.error("No .db files found in ./data/")
        st.stop()

    db_labels = [p.name for p in db_paths]
    selected_db_label = st.selectbox("Database Snapshot", db_labels,
                                      help="Drop new .db files into ./data/ to update")
    DB = str(next(p for p in db_paths if p.name == selected_db_label))

    # Season selector
    seasons_df = _seasons(DB)
    active_seasons = seasons_df[seasons_df["status"] == "ACTIVE"].copy()

    if active_seasons.empty:
        st.warning("No active/completed seasons in DB.")
        st.stop()

    season_opts = {row["name"]: row["id"] for _, row in active_seasons.iterrows()}
    default_sel = list(season_opts.keys())
    sel_names = st.multiselect("Seasons", list(season_opts.keys()), default=default_sel,
                                help="Filter which leagues to show")
    if not sel_names:
        st.warning("Select at least one season.")
        st.stop()

    SEL_IDS = [season_opts[n] for n in sel_names]

    st.markdown("---")
    st.markdown("### WEEKLY RECAP")

    all_weeks_set = set()
    for sid in SEL_IDS:
        for w in _completed_weeks(DB, sid):
            all_weeks_set.add(w)

    if all_weeks_set:
        available_weeks = sorted(all_weeks_set)
        sel_week = st.selectbox(
            "Recap Week",
            options=available_weeks,
            index=len(available_weeks) - 1,
            format_func=lambda w: f"Week {w}",
        )
    else:
        sel_week = None
        st.info("No completed weeks yet.")

    st.markdown("---")
    st.markdown("### ELO SIMULATION")

    if all_weeks_set and len(available_weeks) > 1:
        elo_max_week = st.slider(
            "Simulate through week",
            min_value=min(available_weeks),
            max_value=max(available_weeks),
            value=max(available_weeks),
        )
    elif all_weeks_set:
        elo_max_week = max(available_weeks)
        st.caption(f"Week {elo_max_week} (only week with data)")
    else:
        elo_max_week = None

    st.markdown("---")
    st.caption("Beer League Stats")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT — Broadcast mode or tabbed mode
# ══════════════════════════════════════════════════════════════════════════════

TAB_NAMES = ["WEEKLY RECAP", "PLAYER OF THE WEEK", "SEASON OVERVIEW",
             "CHAMPION ANALYTICS", "POWER RANKINGS", "MATCHUPS"]
tabs = st.tabs(TAB_NAMES)


# ---------------------------------------------------------------------------
# TAB 1 — WEEKLY RECAP
# ---------------------------------------------------------------------------

with tabs[0]:
    if sel_week is None:
        st.info("No completed games yet. Check back after Week 1!")
    else:
        # Broadcast banner
        st.markdown(
            broadcast_header(
                "Weekly Recap",
                "Beer League Stats",
                f"WEEK {sel_week}",
            ),
            unsafe_allow_html=True,
        )

        for sid in SEL_IDS:
            if not season_has_data(DB, sid):
                continue

            season_row = active_seasons[active_seasons["id"] == sid].iloc[0]
            div = "Lite" if "lite" in season_row["name"].lower() else "Stout"
            badge = league_badge(div)

            st.markdown(
                section_header(season_row["name"], badge),
                unsafe_allow_html=True,
            )

            wd = _week_data(DB, sel_week, sid)
            if wd["matches"].empty:
                st.info(f"No completed matches in Week {sel_week} for this league.")
                continue

            matches   = wd["matches"]
            team_stats = wd["team_stats"]
            ps        = wd["player_stats"]
            series_df = wd["series"]

            # -- KPI chyrons (broadcast lower-thirds) --------------------------
            winner_map = dict(zip(matches["id"].astype(str), matches["winnerId"].astype(str)))
            ts = team_stats.copy()
            ts["matchId"] = ts["matchId"].astype(str)
            ts["teamId"]  = ts["teamId"].astype(str)
            ts["is_winner"] = ts.apply(
                lambda r: winner_map.get(r["matchId"]) == r["teamId"], axis=1)

            n_games = len(matches)

            dragon_lead = 0
            for mid in matches["id"].astype(str):
                w_row = ts[(ts["matchId"] == mid) & (ts["is_winner"])]
                l_row = ts[(ts["matchId"] == mid) & (~ts["is_winner"])]
                if not w_row.empty and not l_row.empty:
                    if w_row.iloc[0]["dragons"] > l_row.iloc[0]["dragons"]:
                        dragon_lead += 1

            fb_rows  = ps[ps["firstBloodKill"] > 0]
            fb_wins  = int(fb_rows["win"].sum()) if not fb_rows.empty else 0
            fb_total = len(fb_rows)

            durations = ps.groupby("matchId")["gameDuration"].first()
            avg_dur_s = durations.mean() if not durations.empty else 0
            m, s = divmod(int(avg_dur_s), 60)

            st.markdown(
                chyron_row([
                    stat_chyron("Games Played", str(n_games), "white"),
                    stat_chyron("Avg Duration", f"{m}:{s:02d}", "white"),
                    stat_chyron("Dragon Lead Win Rate",
                                f"{dragon_lead/n_games*100:.0f}%" if n_games else "N/A",
                                "teal"),
                    stat_chyron("First Blood Win Rate",
                                f"{fb_wins/fb_total*100:.0f}%" if fb_total else "N/A",
                                "teal"),
                ]),
                unsafe_allow_html=True,
            )

            # -- Series results (matchup cards) + Objectives side by side ------
            col_sc, col_obj = st.columns([1, 2])
            with col_sc:
                # Render matchup cards as HTML
                cards_html = ""
                for _, r in series_df.iterrows():
                    t1 = r["team1Name"]
                    t2 = r["team2Name"]
                    t1w = int(r.get("team1Wins", 0))
                    t2w = int(r.get("team2Wins", 0))
                    wn = r.get("winnerName", "")
                    cards_html += matchup_card(t1, t1w, t2, t2w, wn)

                st.markdown(
                    f'<div style="padding: 4px 0">{cards_html}</div>',
                    unsafe_allow_html=True,
                )

            with col_obj:
                st.plotly_chart(
                    charts.chart_objectives_winners_vs_losers(team_stats, matches),
                    width="stretch",
                )

            # -- Kill scatter + multi-kill table --------------------------------
            col_kd, col_mk = st.columns([3, 2])
            with col_kd:
                st.plotly_chart(
                    charts.chart_kill_scatter(team_stats, matches, ps),
                    width="stretch",
                )
            with col_mk:
                st.plotly_chart(
                    charts.chart_multikill_table(ps),
                    width="stretch",
                )

            # -- Game durations ------------------------------------------------
            st.plotly_chart(
                charts.chart_game_durations(ps, matches),
                width="stretch",
            )

            # -- What Winners Do + Role Impact ---------------------------------
            role_map = _role_map(DB, sid)

            col_wwd, col_ri = st.columns(2)
            with col_wwd:
                st.plotly_chart(
                    charts.chart_what_winners_do(team_stats, matches, ps),
                    width="stretch",
                )
            with col_ri:
                st.plotly_chart(
                    charts.chart_role_impact(ps, role_map),
                    width="stretch",
                )

            # -- Popular Champions by Role -------------------------------------
            st.plotly_chart(
                charts.chart_champions_by_role(ps, role_map),
                width="stretch",
            )

            # -- Gold Economy + Damage Composition side by side ------------------
            col_ge, col_dc = st.columns(2)
            with col_ge:
                st.plotly_chart(
                    charts.chart_gold_economy(ps, role_map),
                    width="stretch",
                )
            with col_dc:
                st.plotly_chart(
                    charts.chart_damage_composition(ps, team_stats, matches),
                    width="stretch",
                )

            # -- Weekly Superlatives + Ping Stats side by side -------------------
            col_sup, col_ping = st.columns([3, 2])
            with col_sup:
                st.plotly_chart(
                    charts.chart_weekly_superlatives(ps),
                    width="stretch",
                )
            with col_ping:
                st.plotly_chart(
                    charts.chart_ping_stats(ps),
                    width="stretch",
                )

            st.markdown(gold_divider(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# TAB 2 — PLAYER OF THE WEEK
# ---------------------------------------------------------------------------

with tabs[1]:
    if sel_week is None:
        st.info("No completed games yet. Check back after Week 1!")
    else:
        st.markdown(
            broadcast_header(
                "Player of the Week",
                "Impact Factor Rankings",
                f"WEEK {sel_week}",
            ),
            unsafe_allow_html=True,
        )

        pow_data = {}
        for sid in SEL_IDS:
            if not season_has_data(DB, sid):
                continue
            season_row = active_seasons[active_seasons["id"] == sid].iloc[0]
            div = "Lite" if "lite" in season_row["name"].lower() else "Stout"
            wd = _week_data(DB, sel_week, sid)
            if wd["player_stats"].empty:
                continue
            top5 = player_of_the_week(wd["player_stats"])
            pow_data[season_row["name"]] = (top5, div)

        if not pow_data:
            st.info("No player data available for this week.")
        else:
            cols = st.columns(len(pow_data))
            for col, (season_name, (top5, div)) in zip(cols, pow_data.items()):
                with col:
                    badge = league_badge(div)
                    st.markdown(
                        section_header(season_name, badge),
                        unsafe_allow_html=True,
                    )

                    if top5.empty:
                        st.info("Not enough data.")
                        continue

                    pow_player = top5.iloc[0]
                    pow_name = pow_player.get("riotId") or pow_player.get("username") or "?"
                    pow_uname = pow_player.get("username") or ""
                    pow_champ = pow_player.get("championName", "?")
                    pow_score = pow_player.get("avg_if", 0)
                    champ_img = champion_icon(pow_champ, size=48)
                    ranks = _peak_ranks(DB)
                    rank_html = ""
                    if pow_uname in ranks:
                        r = ranks[pow_uname]
                        rank_html = rank_badge(r["tier"], r["label"])
                    st.markdown(f"""
                        <div class="pow-card">
                            <div style="color:{TEXT_MUTED};font-size:0.75rem;font-family:'Oswald',sans-serif;text-transform:uppercase;letter-spacing:2px">Player of the Week</div>
                            <div class="pow-name">{pow_name}{rank_html}</div>
                            <div class="pow-champ">{champ_img}{pow_champ}</div>
                            <div style="margin:0.5rem 0;color:{TEXT_MUTED};font-family:'Barlow Condensed',sans-serif;font-size:0.8rem;text-transform:uppercase;letter-spacing:1.5px">Impact Factor</div>
                            <div class="pow-score">{pow_score:.1f}</div>
                        </div>
                    """, unsafe_allow_html=True)

                    st.plotly_chart(
                        charts.chart_impact_factor_bar(top5, div),
                        width="stretch",
                    )
                    st.plotly_chart(
                        charts.chart_pow_radar(top5, div),
                        width="stretch",
                    )

            with st.expander("HOW IS IMPACT FACTOR CALCULATED?"):
                rows = weight_breakdown()
                df_w = pd.DataFrame(rows, columns=["Metric", "Weight", "Rationale"])
                st.dataframe(df_w, width="stretch", hide_index=True)
                st.markdown(f"**Win bonus:** x{1.15} if the player's team won.")
                st.markdown("All metrics normalized 0-1 within the week's player pool before weighting.")


# ---------------------------------------------------------------------------
# TAB 3 — SEASON OVERVIEW
# ---------------------------------------------------------------------------

with tabs[2]:
    st.markdown(
        broadcast_header("Season Overview", "Full Season Statistics"),
        unsafe_allow_html=True,
    )

    data_seasons_so = [sid for sid in SEL_IDS if season_has_data(DB, sid)]
    if not data_seasons_so:
        st.info("No game data yet. Season overview will appear once games are played.")
    else:
        for sid in data_seasons_so:
            season_row = active_seasons[active_seasons["id"] == sid].iloc[0]
            div = "Lite" if "lite" in season_row["name"].lower() else "Stout"
            badge = league_badge(div)
            st.markdown(section_header(season_row["name"], badge), unsafe_allow_html=True)

            team_colors_map = _build_team_colors(DB, sid)

            # Team Records
            records = _team_records(DB, sid)
            if not records.empty:
                st.plotly_chart(
                    charts.chart_team_records(records, team_colors_map),
                    width="stretch",
                )

            # POW History: compute POW for each completed week
            completed_wks = _completed_weeks(DB, sid)
            pow_hist = []
            for wk in completed_wks:
                wk_data = _week_data(DB, wk, sid)
                if wk_data["player_stats"].empty:
                    continue
                top5 = player_of_the_week(wk_data["player_stats"])
                if not top5.empty:
                    winner = top5.iloc[0]
                    pow_hist.append({
                        "week": wk,
                        "player_name": winner.get("riotId") or winner.get("username") or "?",
                        "champion": winner.get("championName", "?"),
                        "score": winner.get("avg_if", 0),
                    })
            if pow_hist:
                st.plotly_chart(
                    charts.chart_pow_history(pow_hist),
                    width="stretch",
                )

            # Player Leaderboards + Early Game side by side
            all_ps = _all_player_stats(DB, sid)
            role_map = _role_map(DB, sid)

            col_lb, col_eg = st.columns(2)
            with col_lb:
                st.plotly_chart(
                    charts.chart_player_leaderboard(all_ps, role_map),
                    width="stretch",
                )
            with col_eg:
                early = _early_game(DB, sid)
                if not early.empty:
                    st.plotly_chart(
                        charts.chart_early_game(early, team_colors_map),
                        width="stretch",
                    )

            # Draft Diversity
            diversity = _draft_diversity(DB, sid)
            if not diversity.empty:
                st.plotly_chart(
                    charts.chart_draft_diversity(diversity, team_colors_map),
                    width="stretch",
                )

            # Item Analytics
            item_stats = _item_stats(DB, sid)
            if not item_stats.empty:
                col_built, col_wr = st.columns(2)
                with col_built:
                    st.plotly_chart(
                        charts.chart_most_built_items(item_stats),
                        width="stretch",
                    )
                with col_wr:
                    st.plotly_chart(
                        charts.chart_item_winrates(item_stats),
                        width="stretch",
                    )

            # Slamurai's Sunfire Counter
            sf = _sunfire_stats(DB, sid)
            st.markdown(
                sunfire_counter(
                    sf["total_builds"], sf["wins"], sf["losses"],
                    sf["win_rate"], sf["builders"],
                ),
                unsafe_allow_html=True,
            )

            st.markdown(gold_divider(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# TAB 4 — CHAMPION ANALYTICS
# ---------------------------------------------------------------------------

with tabs[3]:
    st.markdown(
        broadcast_header("Champion Analytics", "Pick Rates, Win Rates & Trends"),
        unsafe_allow_html=True,
    )

    data_seasons = [sid for sid in SEL_IDS if season_has_data(DB, sid)]
    if not data_seasons:
        st.info("No game data yet. Champion analytics will appear once games are played.")
    else:
        fc1, fc2, fc3 = st.columns([2, 1, 2])
        with fc1:
            div_filter = st.radio(
                "Division", ["Both", "Lite", "Stout"], horizontal=True
            )
        with fc2:
            min_games_filter = st.number_input("Min games", min_value=1, max_value=CHAMP_MIN_GAMES_MAX, value=CHAMP_MIN_GAMES_DEFAULT)
        with fc3:
            champ_search = st.text_input("Search champion", placeholder="Jinx, Malphite...")

        champ_df = _champion_stats(DB, tuple(data_seasons))

        if not champ_df.empty:
            if div_filter != "Both":
                champ_df = champ_df[champ_df["division"] == div_filter]
            if champ_search.strip():
                champ_df = champ_df[
                    champ_df["championName"].str.lower().str.contains(
                        champ_search.strip().lower(), na=False)
                ]

        if champ_df.empty:
            st.info("No champion data matching your filters.")
        else:
            col_sc, col_wr, col_cwr = st.columns([3, 2, 2])
            with col_sc:
                st.plotly_chart(
                    charts.chart_champion_pickrate_scatter(champ_df, min_games=int(min_games_filter)),
                    width="stretch",
                )
            with col_wr:
                st.plotly_chart(
                    charts.chart_champion_winrates(champ_df, min_games=int(min_games_filter)),
                    width="stretch",
                )
            with col_cwr:
                st.plotly_chart(
                    charts.chart_champion_confidence_winrates(champ_df, min_games=int(min_games_filter)),
                    width="stretch",
                )

            if all_weeks_set and max(all_weeks_set) >= MIN_WEEKS_FOR_TRENDING:
                recent_wks = sorted(all_weeks_set)[-TRENDING_WEEKS_LOOKBACK:]
                recent_ps  = pd.concat([
                    _week_data(DB, w, sid)["player_stats"]
                    for sid in data_seasons for w in recent_wks
                    if season_has_data(DB, sid)
                ], ignore_index=True)

                if not recent_ps.empty:
                    recent_champ_df = recent_ps.groupby("championName").agg(
                        games=("win", "count"), wins=("win", "sum")
                    ).reset_index()
                    recent_champ_df["win_rate"] = recent_champ_df["wins"] / recent_champ_df["games"]

                    all_time_agg = champ_df.groupby("championName").agg(
                        games=("games", "sum"), wins=("wins", "sum")
                    ).reset_index()

                    st.plotly_chart(
                        charts.chart_trending_champions(all_time_agg, recent_champ_df),
                        width="stretch",
                    )

            if len(data_seasons) > 1:
                presence_df = _champion_presence(DB, tuple(data_seasons))
                col_p, col_space = st.columns([2, 1])
                with col_p:
                    st.plotly_chart(
                        charts.chart_champion_presence(champ_df, presence_df),
                        width="stretch",
                    )

        # Ban analytics (only shown when data exists)
        ban_df = _ban_stats(DB, tuple(data_seasons))
        if not ban_df.empty:
            st.markdown(
                section_header("Draft Bans", league_badge("Stout")),
                unsafe_allow_html=True,
            )
            col_bans, col_overlap = st.columns(2)
            with col_bans:
                st.plotly_chart(
                    charts.chart_ban_rates(ban_df),
                    width="stretch",
                )
            with col_overlap:
                st.plotly_chart(
                    charts.chart_ban_overlap(ban_df, champ_df),
                    width="stretch",
                )
        else:
            st.caption("Ban data not yet available for these seasons.")


# ---------------------------------------------------------------------------
# TAB 5 — ELO STANDINGS
# ---------------------------------------------------------------------------

with tabs[4]:
    st.markdown(
        broadcast_header("Power Rankings", "Bayesian Glicko-2 Ratings"),
        unsafe_allow_html=True,
    )

    for sid in SEL_IDS:
        season_row = active_seasons[active_seasons["id"] == sid].iloc[0]
        div = "Lite" if "lite" in season_row["name"].lower() else "Stout"
        badge = league_badge(div)
        st.markdown(section_header(season_row["name"], badge), unsafe_allow_html=True)

        team_colors_map = _build_team_colors(DB, sid)

        if not season_has_data(DB, sid):
            st.info("No games played yet — showing salary-based seeding.")
            standings = salary_seeding(_teams(DB, sid))
            st.plotly_chart(
                charts.chart_elo_standings(standings, team_colors_map),
                width="stretch",
            )
            st.caption("Elo values derived from team salary totals. "
                       "Will update to real Elo once games are played.")
        else:
            through_week = elo_max_week or max(_completed_weeks(DB, sid))
            standings, history = _elo(DB, sid, through_week)

            # Compute previous week standings for delta
            prev_standings = None
            completed_weeks = _completed_weeks(DB, sid)
            if through_week > min(completed_weeks):
                prev_week = max(w for w in completed_weeks if w < through_week)
                prev_standings, _ = _elo(DB, sid, prev_week)

            col_bar, col_tbl = st.columns([3, 2])
            with col_bar:
                st.plotly_chart(
                    charts.chart_elo_standings_with_delta(
                        standings, prev_standings, team_colors_map),
                    width="stretch",
                )
            with col_tbl:
                tbl = standings[["name", "elo", "games_played"]].copy()
                # Show rating range (elo +/- 2*RD = ~95% confidence)
                if "rd" in standings.columns:
                    tbl["Range"] = standings.apply(
                        lambda r: f"{r['elo'] - 2*r['rd']:.0f}-{r['elo'] + 2*r['rd']:.0f}",
                        axis=1)
                if prev_standings is not None and not prev_standings.empty:
                    prev_map = dict(zip(
                        prev_standings["team_id"].astype(str), prev_standings["elo"]))
                    tbl["delta"] = standings["team_id"].map(
                        lambda tid: standings.loc[
                            standings["team_id"] == tid, "elo"].iloc[0] - prev_map.get(tid, 1200))
                    tbl["Trend"] = tbl["delta"].apply(
                        lambda d: f"+{d:.0f}" if d > 0 else f"{d:.0f}" if d != 0 else "-")
                    tbl = tbl.drop(columns=["delta"])
                else:
                    tbl["Trend"] = "-"
                tbl = tbl.rename(columns={
                    "name": "Team", "elo": "Rating", "games_played": "Games"
                })
                st.dataframe(tbl, width="stretch", hide_index=True)

            # History chart
            if not history.empty:
                all_names = sorted(history["name"].unique())
                visible = st.multiselect(
                    "Teams to show in trend",
                    options=all_names,
                    default=all_names,
                    key=f"elo_filter_{sid}",
                )
                st.plotly_chart(
                    charts.chart_elo_history(history, team_colors_map, visible_teams=visible),
                    width="stretch",
                )

        st.markdown(gold_divider(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# TAB 6 — MATCHUPS & PREDICTIONS
# ---------------------------------------------------------------------------

with tabs[5]:
    st.markdown(
        broadcast_header("Matchups", "Results & Bayesian Predictions"),
        unsafe_allow_html=True,
    )

    seeding_method = st.radio(
        "Win probability based on",
        ["Elo (if available)", "Salary seeding"],
        horizontal=True,
    )

    # Only show active seasons in this tab (completed seasons have no upcoming)
    active_sids = [sid for sid in SEL_IDS
                   if active_seasons[active_seasons["id"] == sid].iloc[0]["status"] == "ACTIVE"]

    if not active_sids:
        st.info("No active seasons selected. This tab shows matchups for in-progress seasons.")
    else:
        # Pre-load data for each active season
        _mu_data = {}  # sid -> {series_df, team_colors, rating_map, rd_map, rating_label, div, name}
        all_weeks = set()
        for sid in active_sids:
            season_row = active_seasons[active_seasons["id"] == sid].iloc[0]
            div = "Lite" if "lite" in season_row["name"].lower() else "Stout"
            series_df = _all_series(DB, sid)
            team_colors_map = _build_team_colors(DB, sid)

            if seeding_method == "Elo (if available)" and season_has_data(DB, sid):
                through_week = max(_completed_weeks(DB, sid))
                standings_up, _ = _elo(DB, sid, through_week)
                rating_map = dict(zip(standings_up["team_id"].astype(str), standings_up["elo"]))
                rd_map = dict(zip(standings_up["team_id"].astype(str), standings_up["rd"]))
                rating_label = "Glicko-2"
            else:
                sal_standings = salary_seeding(_teams(DB, sid))
                rating_map = dict(zip(sal_standings["team_id"].astype(str), sal_standings["elo"]))
                rd_map = dict(zip(sal_standings["team_id"].astype(str), sal_standings["rd"]))
                rating_label = "Salary seed"

            _mu_data[sid] = {
                "series": series_df, "colors": team_colors_map,
                "ratings": rating_map, "rds": rd_map,
                "label": rating_label, "div": div, "name": season_row["name"],
            }
            if not series_df.empty:
                all_weeks.update(series_df["week"].dropna().unique())

        # Helper to render one league's matchups for a given week
        def _render_league_week(sid, wk):
            d = _mu_data[sid]
            series_df = d["series"]
            if series_df.empty:
                return
            week_series = series_df[series_df["week"] == wk]
            if week_series.empty:
                st.caption("No matchups this week")
                return

            completed = week_series[week_series["status"] == "COMPLETED"]
            scheduled = week_series[week_series["status"] == "SCHEDULED"]
            rating_map = d["ratings"]
            rd_map = d["rds"]
            team_colors_map = d["colors"]
            rating_label = d["label"]

            # Completed series: compact matchup cards
            if not completed.empty:
                cards_html = ""
                for _, row in completed.iterrows():
                    t1id, t2id = str(row["team1Id"]), str(row["team2Id"])
                    t1, t2 = row["team1Name"], row["team2Name"]
                    wn = row.get("winnerName", "") or ""
                    t1w, t2w = int(row.get("team1Wins", 0)), int(row.get("team2Wins", 0))

                    r1 = rating_map.get(t1id, STARTING_ELO)
                    r2 = rating_map.get(t2id, STARTING_ELO)
                    rd1 = rd_map.get(t1id, DEFAULT_RD)
                    rd2 = rd_map.get(t2id, DEFAULT_RD)
                    prob_a = win_probability(r1, r2, rd1, rd2)
                    winner_id = str(row.get("winnerId", ""))
                    is_upset = (
                        (winner_id == t1id and prob_a < UPSET_THRESHOLD) or
                        (winner_id == t2id and prob_a > (1.0 - UPSET_THRESHOLD))
                    )
                    if is_upset:
                        cards_html += '<span class="upset-alert">UPSET</span>'
                    cards_html += matchup_card(t1, t1w, t2, t2w, wn)

                st.markdown(cards_html, unsafe_allow_html=True)

            # Scheduled series: compact prediction bars
            if not scheduled.empty:
                for _, row in scheduled.iterrows():
                    t1id, t2id = str(row["team1Id"]), str(row["team2Id"])
                    t1, t2 = row["team1Name"], row["team2Name"]
                    r1 = rating_map.get(t1id, STARTING_ELO)
                    r2 = rating_map.get(t2id, STARTING_ELO)
                    rd1 = rd_map.get(t1id, DEFAULT_RD)
                    rd2 = rd_map.get(t2id, DEFAULT_RD)
                    prob_a = win_probability(r1, r2, rd1, rd2)
                    is_close = CLOSE_MATCHUP_THRESHOLD <= prob_a <= (1.0 - CLOSE_MATCHUP_THRESHOLD)

                    c1 = team_colors_map.get(t1id, "#3b82f6")
                    c2 = team_colors_map.get(t2id, "#ef4444")

                    if is_close:
                        st.markdown(
                            '<span class="upset-alert">CLOSE MATCHUP</span>',
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        f'<div style="font-family:Barlow Condensed,sans-serif;color:{TEXT_SEC};'
                        f'font-size:0.8rem;letter-spacing:0.5px;margin-bottom:2px">'
                        f'<b>{t1}</b> vs <b>{t2}</b>  '
                        f'<span style="color:{TEXT_MUTED};font-size:0.7rem">'
                        f'({rating_label}: {r1:.0f} vs {r2:.0f})</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(
                        charts.chart_win_probability(t1, t2, prob_a, c1, c2),
                        width="stretch",
                        key=f"wp_{sid}_{wk}_{row['seriesId']}",
                    )

        # Render week-by-week with leagues side-by-side
        for wk in sorted(all_weeks):
            st.markdown(
                f'<div style="font-family:Oswald,sans-serif;font-size:1.2rem;color:{ACCENT_GOLD};'
                f'text-transform:uppercase;letter-spacing:2px;margin:1.2rem 0 0.3rem 0;'
                f'border-bottom:1px solid {ACCENT_GOLD}33;padding-bottom:4px">'
                f'Week {int(wk)}</div>',
                unsafe_allow_html=True,
            )

            if len(active_sids) > 1:
                cols = st.columns(len(active_sids))
                for col, sid in zip(cols, active_sids):
                    with col:
                        d = _mu_data[sid]
                        badge = league_badge(d["div"])
                        st.markdown(
                            f'<div style="font-family:Oswald,sans-serif;font-size:0.9rem;'
                            f'margin-bottom:0.3rem">{badge} {d["name"]}</div>',
                            unsafe_allow_html=True,
                        )
                        _render_league_week(sid, wk)
            else:
                _render_league_week(active_sids[0], wk)

        st.markdown(gold_divider(), unsafe_allow_html=True)

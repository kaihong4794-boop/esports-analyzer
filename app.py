import streamlit as st

st.title("运动期望值分析器 🏆")

tab1, tab2, tab3 = st.tabs(["⚔️ 电竞", "⚽ 足球", "🏀 篮球"])

# ==================== 电竞 ====================
with tab1:
    st.header("电竞期望值分析器")

    score_weights_esports = {
        "2-0 赢": 1.0,
        "2-1 赢": 0.7,
        "1-2 输": 0.4,
        "0-2 输": 0.2
    }

    col1, col2 = st.columns(2)
    with col1:
        e_home_name = st.text_input("主队名字", "主队", key="e_home_name")
        e_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="e_home_odds")
    with col2:
        e_away_name = st.text_input("客队名字", "客队", key="e_away_name")
        e_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="e_away_odds")

    st.divider()
    num_matches_e = st.slider("最近几场比赛？", 1, 5, 5, key="e_slider")

    col3, col4 = st.columns(2)
    e_home_vars = []
    e_away_vars = []

    with col3:
        st.subheader(f"{e_home_name} 最近{num_matches_e}场")
        for i in range(num_matches_e):
            v = st.selectbox(f"第{i+1}场", list(score_weights_esports.keys()), key=f"eh{i}")
            e_home_vars.append(v)

    with col4:
        st.subheader(f"{e_away_name} 最近{num_matches_e}场")
        for i in range(num_matches_e):
            v = st.selectbox(f"第{i+1}场", list(score_weights_esports.keys()), key=f"ea{i}")
            e_away_vars.append(v)

    if st.button("计算", key="e_calc", type="primary"):
        def e_winrate(vars, weights):
            total_w = win_w = 0
            for i, v in enumerate(vars):
                base = 1.0 - (i * 0.1)
                total_w += base
                win_w += (1 if "赢" in v else 0) * weights[v] * base
            return win_w / total_w

        h_wr = e_winrate(e_home_vars, score_weights_esports)
        a_wr = e_winrate(e_away_vars, score_weights_esports)
        h_ev = (h_wr*(e_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(e_away_odds-1)*100) - ((1-a_wr)*100)

        col5, col6 = st.columns(2)
        with col5:
            st.subheader(e_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/e_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/e_home_odds:+.1%}")
            st.metric("期望值(RM100)", f"RM{h_ev:.2f}")
            st.success("✅ 正期望值") if h_ev > 0 else st.error("❌ 负期望值")
        with col6:
            st.subheader(e_away_name)
            st.metric("加权胜率", f"{a_wr:.1%}")
            st.metric("隐含概率", f"{1/e_away_odds:.1%}")
            st.metric("优势差距", f"{a_wr - 1/e_away_odds:+.1%}")
            st.metric("期望值(RM100)", f"RM{a_ev:.2f}")
            st.success("✅ 正期望值") if a_ev > 0 else st.error("❌ 负期望值")

# ==================== 足球 ====================
with tab2:
    st.header("足球期望值分析器")

    col1, col2 = st.columns(2)
    with col1:
        f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
        f_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="f_home_odds")
    with col2:
        f_away_name = st.text_input("客队名字", "客队", key="f_away_name")
        f_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="f_away_odds")

    st.divider()

    venue = st.radio("这场比赛场地", ["主队主场", "客队主场", "中立场"], horizontal=True, key="f_venue")

    def goal_diff_weight(scored, conceded):
        diff = scored - conceded
        if diff >= 3: return 1.0
        elif diff >= 1: return 0.7
        elif diff == 0: return 0.3
        elif diff >= -2: return 0.15
        else: return 0.05

    def f_winrate_combined(home_scores, away_scores, is_home_team, venue):
        if venue == "主队主场":
            w_home, w_away = (0.7, 0.3) if is_home_team else (0.3, 0.7)
        elif venue == "客队主场":
            w_home, w_away = (0.3, 0.7) if is_home_team else (0.7, 0.3)
        else:
            w_home, w_away = 0.5, 0.5

        def calc(scores):
            if not scores: return 0
            total_w = win_w = 0
            for i, (g, c) in enumerate(scores):
                base = 1.0 - (i * 0.15)
                weight = goal_diff_weight(g, c)
                is_win = 1 if g > c else 0
                total_w += base
                win_w += is_win * weight * base
            return win_w / total_w if total_w > 0 else 0

        home_wr = calc(home_scores)
        away_wr = calc(away_scores)

        if not home_scores: return away_wr
        if not away_scores: return home_wr
        return (home_wr * w_home) + (away_wr * w_away)

    # 主队输入
    st.subheader(f"📊 {f_home_name} 比赛记录")
    col3, col4 = st.columns(2)

    fh_home_scores = []
    fh_away_scores = []

    with col3:
        st.write("🏠 主场比赛")
        num_fh_home = st.slider("几场？", 0, 5, 3, key="fh_home_slider")
        for i in range(num_fh_home):
            c1, c2 = st.columns(2)
            with c1:
                g1 = st.number_input(f"第{i+1}场 进", min_value=0, value=0, key=f"fhh_g{i}")
            with c2:
                g2 = st.number_input(f"第{i+1}场 失", min_value=0, value=0, key=f"fhh_c{i}")
            fh_home_scores.append((g1, g2))

    with col4:
        st.write("✈️ 客场比赛")
        num_fh_away = st.slider("几场？", 0, 5, 3, key="fh_away_slider")
        for i in range(num_fh_away):
            c1, c2 = st.columns(2)
            with c1:
                g1 = st.number_input(f"第{i+1}场 进", min_value=0, value=0, key=f"fha_g{i}")
            with c2:
                g2 = st.number_input(f"第{i+1}场 失", min_value=0, value=0, key=f"fha_c{i}")
            fh_away_scores.append((g1, g2))

    st.divider()

    # 客队输入
    st.subheader(f"📊 {f_away_name} 比赛记录")
    col5, col6 = st.columns(2)

    fa_home_scores = []
    fa_away_scores = []

    with col5:
        st.write("🏠 主场比赛")
        num_fa_home = st.slider("几场？", 0, 5, 3, key="fa_home_slider")
        for i in range(num_fa_home):
            c1, c2 = st.columns(2)
            with c1:
                g1 = st.number_input(f"第{i+1}场 进", min_value=0, value=0, key=f"fah_g{i}")
            with c2:
                g2 = st.number_input(f"第{i+1}场 失", min_value=0, value=0, key=f"fah_c{i}")
            fa_home_scores.append((g1, g2))

    with col6:
        st.write("✈️ 客场比赛")
        num_fa_away = st.slider("几场？", 0, 5, 3, key="fa_away_slider")
        for i in range(num_fa_away):
            c1, c2 = st.columns(2)
            with c1:
                g1 = st.number_input(f"第{i+1}场 进", min_value=0, value=0, key=f"faa_g{i}")
            with c2:
                g2 = st.number_input(f"第{i+1}场 失", min_value=0, value=0, key=f"faa_c{i}")
            fa_away_scores.append((g1, g2))

    if st.button("计算", key="f_calc", type="primary"):
        h_wr = f_winrate_combined(fh_home_scores, fh_away_scores, True, venue)
        a_wr = f_winrate_combined(fa_home_scores, fa_away_scores, False, venue)
        h_ev = (h_wr*(f_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(f_away_odds-1)*100) - ((1-a_wr)*100)

        col7, col8 = st.columns(2)
        with col7:
            st.subheader(f_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/f_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/f_home_odds:+.1%}")
            st.metric("期望值(RM100)", f"RM{h_ev:.2f}")
            st.success("✅ 正期望值") if h_ev > 0 else st.error("❌ 负期望值")
        with col8:
            st.subheader(f_away_name)
            st.metric("加权胜率", f"{a_wr:.1%}")
            st.metric("隐含概率", f"{1/f_away_odds:.1%}")
            st.metric("优势差距", f"{a_wr - 1/f_away_odds:+.1%}")
            st.metric("期望值(RM100)", f"RM{a_ev:.2f}")
            st.success("✅ 正期望值") if a_ev > 0 else st.error("❌ 负期望值")
# ==================== 篮球 ====================
with tab3:
    st.header("篮球期望值分析器")

    col1, col2 = st.columns(2)
    with col1:
        b_home_name = st.text_input("主队名字", "主队", key="b_home_name")
        b_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="b_home_odds")
    with col2:
        b_away_name = st.text_input("客队名字", "客队", key="b_away_name")
        b_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="b_away_odds")

    st.divider()
    num_matches_b = st.slider("最近几场比赛？", 1, 5, 5, key="b_slider")

    score_weights_basketball = {
        "大胜 (+15以上)": 1.0,
        "小胜 (+1到+14)": 0.7,
        "小负 (-1到-14)": 0.4,
        "大负 (-15以上)": 0.2
    }

    col3, col4 = st.columns(2)
    b_home_vars = []
    b_away_vars = []

    with col3:
        st.subheader(f"{b_home_name} 最近{num_matches_b}场")
        for i in range(num_matches_b):
            v = st.selectbox(f"第{i+1}场", list(score_weights_basketball.keys()), key=f"bh{i}")
            b_home_vars.append(v)

    with col4:
        st.subheader(f"{b_away_name} 最近{num_matches_b}场")
        for i in range(num_matches_b):
            v = st.selectbox(f"第{i+1}场", list(score_weights_basketball.keys()), key=f"ba{i}")
            b_away_vars.append(v)

    def b_winrate(vars, weights):
        total_w = win_w = 0
        for i, v in enumerate(vars):
            base = 1.0 - (i * 0.1)
            total_w += base
            win_w += (1 if "胜" in v else 0) * weights[v] * base
        return win_w / total_w

    if st.button("计算", key="b_calc", type="primary"):
        h_wr = b_winrate(b_home_vars, score_weights_basketball)
        a_wr = b_winrate(b_away_vars, score_weights_basketball)
        h_ev = (h_wr*(b_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(b_away_odds-1)*100) - ((1-a_wr)*100)

        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/b_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/b_home_odds:+.1%}")
            st.metric("期望值(RM100)", f"RM{h_ev:.2f}")
            st.success("✅ 正期望值") if h_ev > 0 else st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率", f"{a_wr:.1%}")
            st.metric("隐含概率", f"{1/b_away_odds:.1%}")
            st.metric("优势差距", f"{a_wr - 1/b_away_odds:+.1%}")
            st.metric("期望值(RM100)", f"RM{a_ev:.2f}")
            st.success("✅ 正期望值") if a_ev > 0 else st.error("❌ 负期望值")

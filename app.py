import streamlit as st
import pandas as pd
from datetime import date

st.title("运动期望值分析器 🏆")

if "records" not in st.session_state:
    st.session_state["records"] = []

tab1, tab2, tab3, tab4 = st.tabs(["⚔️ 电竞", "⚽ 足球", "🏀 篮球", "📋 记录"])

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

        st.session_state["e_result"] = {
            "h_wr": h_wr, "a_wr": a_wr,
            "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": e_home_odds, "a_odds": e_away_odds,
            "h_name": e_home_name, "a_name": e_away_name
        }

        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(e_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/e_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/e_home_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{h_ev:.2f}")
            if h_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")
        with col6:
            st.subheader(e_away_name)
            st.metric("加权胜率", f"{a_wr:.1%}")
            st.metric("隐含概率", f"{1/e_away_odds:.1%}")
            st.metric("优势差距", f"{a_wr - 1/e_away_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{a_ev:.2f}")
            if a_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")

    if "e_result" in st.session_state:
        r = st.session_state["e_result"]
        st.divider()
        st.subheader("💾 保存记录")
        col7, col8, col9 = st.columns(3)
        with col7:
            e_stake = st.number_input("注额 (RM)", min_value=0, value=100, key="e_stake")
        with col8:
            e_bet = st.selectbox("押注队伍", [r["h_name"], r["a_name"]], key="e_bet")
        with col9:
            e_res = st.selectbox("实际结果", ["待定", "赢", "输", "平"], key="e_res")

        if st.button("保存记录", key="e_save"):
            odds_used = r["h_odds"] if e_bet == r["h_name"] else r["a_odds"]
            pnl = (odds_used-1)*e_stake if e_res == "赢" else (-e_stake if e_res == "输" else 0)
            st.session_state["records"].append({
                "日期": str(date.today()),
                "运动": "电竞",
                "主队": r["h_name"],
                "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}",
                "注额(RM)": e_stake,
                "押注队伍": e_bet,
                "实际结果": e_res,
                "盈亏(RM)": pnl
            })
            st.success("✅ 记录已保存！去📋记录查看")

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

        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr,
            "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds,
            "h_name": f_home_name, "a_name": f_away_name
        }

        st.divider()
        col7, col8 = st.columns(2)
        with col7:
            st.subheader(f_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/f_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/f_home_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{h_ev:.2f}")
            if h_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")
        with col8:
            st.subheader(f_away_name)
            st.metric("加权胜率", f"{a_wr:.1%}")
            st.metric("隐含概率", f"{1/f_away_odds:.1%}")
            st.metric("优势差距", f"{a_wr - 1/f_away_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{a_ev:.2f}")
            if a_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")

    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()
        st.subheader("💾 保存记录")
        col9, col10, col11 = st.columns(3)
        with col9:
            f_stake = st.number_input("注额 (RM)", min_value=0, value=100, key="f_stake")
        with col10:
            f_bet = st.selectbox("押注队伍", [r["h_name"], r["a_name"]], key="f_bet")
        with col11:
            f_res = st.selectbox("实际结果", ["待定", "赢", "输", "平"], key="f_res")

        if st.button("保存记录", key="f_save"):
            odds_used = r["h_odds"] if f_bet == r["h_name"] else r["a_odds"]
            pnl = (odds_used-1)*f_stake if f_res == "赢" else (-f_stake if f_res == "输" else 0)
            st.session_state["records"].append({
                "日期": str(date.today()),
                "运动": "足球",
                "主队": r["h_name"],
                "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}",
                "注额(RM)": f_stake,
                "押注队伍": f_bet,
                "实际结果": f_res,
                "盈亏(RM)": pnl
            })
            st.success("✅ 记录已保存！去📋记录查看")

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

        st.session_state["b_result"] = {
            "h_wr": h_wr, "a_wr": a_wr,
            "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": b_home_odds, "a_odds": b_away_odds,
            "h_name": b_home_name, "a_name": b_away_name
        }

        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/b_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/b_home_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{h_ev:.2f}")
            if h_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率", f"{a_wr:.1%}")
            st.metric("隐含概率", f"{1/b_away_odds:.1%}")
            st.metric("优势差距", f"{a_wr - 1/b_away_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{a_ev:.2f}")
            if a_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")

    if "b_result" in st.session_state:
        r = st.session_state["b_result"]
        st.divider()
        st.subheader("💾 保存记录")
        col7, col8, col9 = st.columns(3)
        with col7:
            b_stake = st.number_input("注额 (RM)", min_value=0, value=100, key="b_stake")
        with col8:
            b_bet = st.selectbox("押注队伍", [r["h_name"], r["a_name"]], key="b_bet")
        with col9:
            b_res = st.selectbox("实际结果", ["待定", "赢", "输"], key="b_res")

        if st.button("保存记录", key="b_save"):
            odds_used = r["h_odds"] if b_bet == r["h_name"] else r["a_odds"]
            pnl = (odds_used-1)*b_stake if b_res == "赢" else (-b_stake if b_res == "输" else 0)
            st.session_state["records"].append({
                "日期": str(date.today()),
                "运动": "篮球",
                "主队": r["h_name"],
                "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}",
                "注额(RM)": b_stake,
                "押注队伍": b_bet,
                "实际结果": b_res,
                "盈亏(RM)": pnl
            })
            st.success("✅ 记录已保存！去📋记录查看")

# ==================== 记录 ====================
with tab4:
    st.header("📋 历史记录")

    if len(st.session_state["records"]) == 0:
        st.info("还没有记录，去分析一场比赛然后保存吧！")
    else:
        df = pd.DataFrame(st.session_state["records"])

        # 统计（只算已知结果）
        known = df[df["实际结果"] != "待定"]
        total = len(df)
        wins = len(known[known["实际结果"] == "赢"])
        losses = len(known[known["实际结果"] == "输"])
        pending = len(df[df["实际结果"] == "待定"])
        total_pnl = known["盈亏(RM)"].sum()

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("总记录", total)
        with col2:
            st.metric("胜场", wins)
        with col3:
            st.metric("负场", losses)
        with col4:
            st.metric("待定", pending)
        with col5:
            st.metric("总盈亏", f"RM{total_pnl:.2f}")

        st.divider()
        st.dataframe(df, use_container_width=True)

        # 编辑待定记录
        pending_df = df[df["实际结果"] == "待定"]
        if len(pending_df) > 0:
            st.divider()
            st.subheader("✏️ 更新待定记录")
            pending_options = [f"{row['日期']} | {row['主队']} vs {row['客队']}" for _, row in pending_df.iterrows()]
            selected = st.selectbox("选择要更新的比赛", pending_options)
            new_result = st.selectbox("实际结果", ["赢", "输", "平"], key="edit_result")

            if st.button("更新结果", key="edit_save"):
                idx = pending_options.index(selected)
                actual_idx = pending_df.index[idx]
                record = st.session_state["records"][actual_idx]
                record["实际结果"] = new_result
                if new_result == "赢":
                    odds = record["注额(RM)"]
                    record["盈亏(RM)"] = (float(record["主队期望值"]) if record["押注队伍"] == record["主队"] else float(record["客队期望值"]))
                elif new_result == "输":
                    record["盈亏(RM)"] = -record["注额(RM)"]
                else:
                    record["盈亏(RM)"] = 0
                st.success("✅ 记录已更新！")
                st.rerun()

        st.divider()
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 下载记录", csv, "records.csv", "text/csv")

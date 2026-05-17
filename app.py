import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import pandas as pd
from datetime import date

SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
HEADERS = ["日期","运动","主队","客队","主队加权胜率","客队加权胜率","主队期望值","平局期望值","客队期望值","注额(RM)","押注选项","实际结果","盈亏(RM)"]

def get_sheet():
    import json
    credentials_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def save_to_sheet(record):
    try:
        sheet = get_sheet()
        if sheet.row_count <= 1 and not sheet.cell(1,1).value:
            sheet.append_row(HEADERS)
        sheet.append_row([record.get(h, "") for h in HEADERS])
    except Exception as e:
        st.error(f"Google Sheets 保存失败: {e}")

def load_from_sheet():
    try:
        sheet = get_sheet()
        data = sheet.get_all_records()
        return pd.DataFrame(data) if data else pd.DataFrame(columns=HEADERS)
    except:
        return pd.DataFrame(columns=HEADERS)

def update_sheet_row(row_idx, result, pnl):
    try:
        sheet = get_sheet()
        sheet.update_cell(row_idx + 2, HEADERS.index("实际结果") + 1, result)
        sheet.update_cell(row_idx + 2, HEADERS.index("盈亏(RM)") + 1, pnl)
    except Exception as e:
        st.error(f"更新失败: {e}")

st.title("运动期望值分析器 🏆")

tab1, tab2, tab3, tab4 = st.tabs(["⚔️ 电竞", "⚽ 足球", "🏀 篮球", "📋 记录"])

with tab1:
    st.header("电竞期望值分析器")
    score_weights_esports = {
        "2-0 赢": 1.0, "2-1 赢": 0.7, "1-2 输": 0.4, "0-2 输": 0.2
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
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
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
            e_res = st.selectbox("实际结果", ["待定", "赢", "输"], key="e_res")
        if st.button("保存记录", key="e_save"):
            odds_used = r["h_odds"] if e_bet == r["h_name"] else r["a_odds"]
            pnl = (odds_used-1)*e_stake if e_res == "赢" else (-e_stake if e_res == "输" else 0)
            record = {
                "日期": str(date.today()), "运动": "电竞",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}", "注额(RM)": e_stake,
                "押注选项": e_bet, "实际结果": e_res, "盈亏(RM)": pnl
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

with tab2:
    st.header("足球期望值分析器")
    football_results = {
        "🏠 主场大胜": {"weight": 1.0, "is_win": 1, "is_draw": 0, "is_home": True},
        "🏠 主场小胜": {"weight": 0.75, "is_win": 1, "is_draw": 0, "is_home": True},
        "🏠 主场平局": {"weight": 0.5, "is_win": 0, "is_draw": 1, "is_home": True},
        "🏠 主场小负": {"weight": 0.25, "is_win": 0, "is_draw": 0, "is_home": True},
        "🏠 主场大负": {"weight": 0.05, "is_win": 0, "is_draw": 0, "is_home": True},
        "✈️ 客场大胜": {"weight": 1.0, "is_win": 1, "is_draw": 0, "is_home": False},
        "✈️ 客场小胜": {"weight": 0.75, "is_win": 1, "is_draw": 0, "is_home": False},
        "✈️ 客场平局": {"weight": 0.5, "is_win": 0, "is_draw": 1, "is_home": False},
        "✈️ 客场小负": {"weight": 0.25, "is_win": 0, "is_draw": 0, "is_home": False},
        "✈️ 客场大负": {"weight": 0.05, "is_win": 0, "is_draw": 0, "is_home": False},
    }
    col1, col2, col3 = st.columns(3)
    with col1:
        f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
    with col2:
        st.write("")
    with col3:
        f_away_name = st.text_input("客队名字", "客队", key="f_away_name")
    col4, col5, col6 = st.columns(3)
    with col4:
        f_home_odds = st.number_input("主队赔率", min_value=1.01, value=2.0, step=0.01, key="f_home_odds")
    with col5:
        f_draw_odds = st.number_input("平局赔率", min_value=1.01, value=3.0, step=0.01, key="f_draw_odds")
    with col6:
        f_away_odds = st.number_input("客队赔率", min_value=1.01, value=3.5, step=0.01, key="f_away_odds")
    st.divider()
    venue = st.radio("这场比赛场地", ["主队主场", "客队主场", "中立场"], horizontal=True, key="f_venue")
    num_matches_f = st.slider("最近几场比赛？", 1, 5, 5, key="f_slider")

    def calc_football_winrate(matches, is_playing_home, venue):
        if venue == "主队主场":
            home_boost = 1.2 if is_playing_home else 0.8
        elif venue == "客队主场":
            home_boost = 0.8 if is_playing_home else 1.2
        else:
            home_boost = 1.0
        total_w = win_w = draw_w = 0
        for i, result in enumerate(matches):
            info = football_results[result]
            base = 1.0 - (i * 0.1)
            venue_multiplier = 1.2 if info["is_home"] else 0.8
            final_weight = base * info["weight"] * venue_multiplier * home_boost
            total_w += base
            win_w += info["is_win"] * final_weight
            draw_w += info["is_draw"] * final_weight * 0.5
        win_rate = win_w / total_w if total_w > 0 else 0
        draw_rate = draw_w / total_w if total_w > 0 else 0
        return win_rate, draw_rate

    col7, col8 = st.columns(2)
    f_home_vars = []
    f_away_vars = []
    with col7:
        st.subheader(f"{f_home_name} 最近{num_matches_f}场")
        for i in range(num_matches_f):
            v = st.selectbox(f"第{i+1}场", list(football_results.keys()), key=f"fh{i}")
            f_home_vars.append(v)
    with col8:
        st.subheader(f"{f_away_name} 最近{num_matches_f}场")
        for i in range(num_matches_f):
            v = st.selectbox(f"第{i+1}场", list(football_results.keys()), key=f"fa{i}")
            f_away_vars.append(v)

    if st.button("计算", key="f_calc", type="primary"):
        h_wr, h_dr = calc_football_winrate(f_home_vars, True, venue)
        a_wr, a_dr = calc_football_winrate(f_away_vars, False, venue)
        draw_prob = (h_dr + a_dr) / 2
        h_ev = (h_wr*(f_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(f_away_odds-1)*100) - ((1-a_wr)*100)
        d_ev = (draw_prob*(f_draw_odds-1)*100) - ((1-draw_prob)*100)
        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "draw_prob": draw_prob,
            "h_ev": h_ev, "a_ev": a_ev, "d_ev": d_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds, "d_odds": f_draw_odds,
            "h_name": f_home_name, "a_name": f_away_name
        }
        st.divider()
        col9, col10, col11 = st.columns(3)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/f_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/f_home_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{h_ev:.2f}")
            if h_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")
        with col10:
            st.subheader("平局")
            st.metric("平局概率", f"{draw_prob:.1%}")
            st.metric("隐含概率", f"{1/f_draw_odds:.1%}")
            st.metric("优势差距", f"{draw_prob - 1/f_draw_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{d_ev:.2f}")
            if d_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")
        with col11:
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
        col12, col13, col14 = st.columns(3)
        with col12:
            f_stake = st.number_input("注额 (RM)", min_value=0, value=100, key="f_stake")
        with col13:
            f_bet = st.selectbox("押注选项", [r["h_name"], "平局", r["a_name"]], key="f_bet")
        with col14:
            f_res = st.selectbox("实际结果", ["待定", "主队赢", "平局", "客队赢"], key="f_res")
        if st.button("保存记录", key="f_save"):
            if f_bet == r["h_name"]:
                odds_used = r["h_odds"]
                win_condition = "主队赢"
            elif f_bet == "平局":
                odds_used = r["d_odds"]
                win_condition = "平局"
            else:
                odds_used = r["a_odds"]
                win_condition = "客队赢"
            if f_res == "待定":
                pnl = 0
            elif f_res == win_condition:
                pnl = (odds_used-1)*f_stake
            else:
                pnl = -f_stake
            record = {
                "日期": str(date.today()), "运动": "足球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": f"{r['d_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}", "注额(RM)": f_stake,
                "押注选项": f_bet, "实际结果": f_res, "盈亏(RM)": pnl
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

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
    score_weights_b = {
        "大胜 (+15以上)": 1.0, "小胜 (+1到+14)": 0.7,
        "小负 (-1到-14)": 0.4, "大负 (-15以上)": 0.2
    }
    col3, col4 = st.columns(2)
    b_home_vars = []
    b_away_vars = []
    with col3:
        st.subheader(f"{b_home_name} 最近{num_matches_b}场")
        for i in range(num_matches_b):
            v = st.selectbox(f"第{i+1}场", list(score_weights_b.keys()), key=f"bh{i}")
            b_home_vars.append(v)
    with col4:
        st.subheader(f"{b_away_name} 最近{num_matches_b}场")
        for i in range(num_matches_b):
            v = st.selectbox(f"第{i+1}场", list(score_weights_b.keys()), key=f"ba{i}")
            b_away_vars.append(v)

    def b_winrate(vars, weights):
        total_w = win_w = 0
        for i, v in enumerate(vars):
            base = 1.0 - (i * 0.1)
            total_w += base
            win_w += (1 if "胜" in v else 0) * weights[v] * base
        return win_w / total_w

    if st.button("计算", key="b_calc", type="primary"):
        h_wr = b_winrate(b_home_vars, score_weights_b)
        a_wr = b_winrate(b_away_vars, score_weights_b)
        h_ev = (h_wr*(b_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(b_away_odds-1)*100) - ((1-a_wr)*100)
        st.session_state["b_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
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
            record = {
                "日期": str(date.today()), "运动": "篮球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}", "注额(RM)": b_stake,
                "押注选项": b_bet, "实际结果": b_res, "盈亏(RM)": pnl
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

with tab4:
    st.header("📋 历史记录")
    if st.button("🔄 刷新记录", key="refresh"):
        st.rerun()
    df = load_from_sheet()
    if df.empty:
        st.info("还没有记录，去分析一场比赛然后保存吧！")
    else:
        known = df[df["实际结果"] != "待定"]
        total = len(df)
        pending = len(df[df["实际结果"] == "待定"])
        total_pnl = pd.to_numeric(known["盈亏(RM)"], errors="coerce").sum()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总记录", total)
        with col2:
            st.metric("已结算", len(known))
        with col3:
            st.metric("待定", pending)
        with col4:
            st.metric("总盈亏", f"RM{total_pnl:.2f}")
        st.divider()
        st.dataframe(df, use_container_width=True)
        pending_df = df[df["实际结果"] == "待定"]
        if len(pending_df) > 0:
            st.divider()
            st.subheader("✏️ 更新待定记录")
            options = [f"{row['日期']} | {row['主队']} vs {row['客队']}" for _, row in pending_df.iterrows()]
            selected = st.selectbox("选择比赛", options, key="edit_select")
            new_result = st.selectbox("实际结果", ["主队赢", "平局", "客队赢", "赢", "输"], key="edit_result")
            if st.button("更新结果", key="edit_save"):
                idx = options.index(selected)
                actual_idx = pending_df.index[idx]
                row = df.iloc[actual_idx]
                stake = float(row["注额(RM)"])
                bet = row["押注选项"]
                if new_result in ["赢", "主队赢"] and bet == row["主队"]:
                    pnl = (float(str(row["主队期望值"]).replace("%","")) - 1 + 1) * stake
                elif new_result == "平局" and bet == "平局":
                    pnl = (float(str(row["平局期望值"]).replace("%","")) - 1 + 1) * stake
                elif new_result in ["客队赢"] and bet == row["客队"]:
                    pnl = (float(str(row["客队期望值"]).replace("%","")) - 1 + 1) * stake
                else:
                    pnl = -stake
                update_sheet_row(actual_idx, new_result, pnl)
                st.success("✅ 已更新！按刷新查看")
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 下载记录", csv, "records.csv", "text/csv")

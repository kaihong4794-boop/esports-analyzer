import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import pandas as pd
from datetime import date

# ==================== Google Sheets ====================
SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
HEADERS = ["日期","运动","主队","客队","主队加权胜率","客队加权胜率","主队期望值","客队期望值","注额(RM)","押注队伍","实际结果","盈亏(RM)"]

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

# ==================== App ====================
st.title("运动期望值分析器 🏆")

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
            record = {
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
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

# ==================== 足球 ====================
with tab2:
    st.header("足球期望值分析器")

    # 足球比赛结果选项和权重
    football_results = {
        "🏠 主场大胜": {"weight": 1.0, "is_win": 1, "is_home": True},
        "🏠 主场小胜": {"weight": 0.75, "is_win": 1, "is_home": True},
        "🏠 主场平局": {"weight": 0.5, "is_win": 0, "is_home": True},
        "🏠 主场小负": {"weight": 0.25, "is_win": 0, "is_home": True},
        "🏠 主场大负": {"weight": 0.05, "is_win": 0, "is_home": True},
        "✈️ 客场大胜": {"weight": 1.0, "is_win": 1, "is_home": False},
        "✈️ 客场小胜": {"weight": 0.75, "is_win": 1, "is_home": False},
        "✈️ 客场平局": {"weight": 0.5, "is_win": 0, "is_home": False},
        "✈️ 客场小负": {"weight": 0.25, "is_win": 0, "is_home": False},
        "✈️ 客场大负": {"weight": 0.05, "is_win": 0, "is_home": False},
    }

    col1, col2 = st.columns(2)
    with col1:
        f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
        f_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="f_home_odds")
    with col2:
        f_away_name = st.text_input("客队名字", "客队", key="f_away_name")
        f_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="f_away_odds")

    st.divider()
    venue = st.radio("这场比赛场地", ["主队主场", "客队主场", "中立场"], horizontal=True, key="f_venue")
    num_matches_f = st.slider("最近几场比赛？", 1, 5, 5, key="f_slider")

    def calc_football_winrate(matches, is_playing_home, venue):
        # 主客场调整系数
        if venue == "主队主场":
            home_boost = 1.2 if is_playing_home else 0.8
        elif venue == "客队主场":
            home_boost = 0.8 if is_playing_home else 1.2
        else:
            home_boost = 1.0

        total_w = win_w = 0
        for i, result in enumerate(matches):
            info = football_results[result]
            base = 1.0 - (i * 0.1)
            # 主场比赛加成
            venue_multiplier = 1.2 if info["is_home"] else 0.8
            # 今天比赛场地加成
            final_weight = base * info["weight"] * venue_multiplier * home_boost
            total_w += base
            win_w += info["is_win"] * final_weight
        return win_w / total_w if total_w > 0 else 0

    col3, col4 = st.columns(2)
    f_home_vars = []
    f_away_vars = []

    with col3:
        st.subheader(f"{f_home_name} 最近{num_matches_f}场")
        for i in range(num_matches_f):
            v = st.selectbox(f"第{i+1}场", list(football_results.keys()), key=f"fh{i}")
            f_home_vars.append(v)

    with col4:
        st.subheader(f"{f_away_name} 最近{num_matches_f}场")
        for i in range(num_matches_f):
            v = st.selectbox(f"第{i+1}场", list(football_results.keys()), key=f"fa{i}")
            f_away_vars.append(v)

    if st.button("计算", key="f_calc", type="primary"):
        h_wr = calc_football_winrate(f_home_vars, True, venue)
        a_wr = calc_football_winrate(f_away_vars, False, venue)
        h_ev = (h_wr*(f_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(f_away_odds-1)*100) - ((1-a_wr)*100)

        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr,
            "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds,
            "h_name": f_home_name, "a_name": f_away_name
        }

        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(f_home_name)
            st.metric("加权胜率", f"{h_wr:.1%}")
            st.metric("隐含概率", f"{1/f_home_odds:.1%}")
            st.metric("优势差距", f"{h_wr - 1/f_home_odds:+.1%}")
            st.metric("期望值 (RM100)", f"RM{h_ev:.2f}")
            if h_ev > 0:
                st.success("✅ 正期望值")
            else:
                st.error("❌ 负期望值")
        with col6:
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
        col7, col8, col9 = st.columns(3)
        with col7:
            f_stake = st.number_input("注额 (RM)", min_value=0, value=100, key="f_stake")
        with col8:
            f_bet = st.selectbox("押注队伍", [r["h_name"], r["a_name"]], key="f_bet")
        with col9:
            f_res = st.selectbox("实际结果", ["待定", "赢", "输", "平"], key="f_res")

        if st.button("保存记录", key="f_save"):
            odds_used = r["h_odds"] if f_bet == r["h_name"] else r["a_odds"]
            pnl = (odds_used-1)*f_stake if f_res == "赢" else (-f_stake if f_res == "输" else 0)
            record = {
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
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

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

    score_weights_b = {
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
            pnl = (odds_used-1)*b_stake if b_res == "赢" else -b_stake
            record = {
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
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

# ==================== 记录 ====================
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
        wins = len(known[known["实际结果"] == "赢"])
        losses = len(known[known["实际结果"] == "输"])
        pending = len(df[df["实际结果"] == "待定"])
        total_pnl = pd.to_numeric(known["盈亏(RM)"], errors="coerce").sum()

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

        pending_df = df[df["实际结果"] == "待定"]
        if len(pending_df) > 0:
            st.divider()
            st.subheader("✏️ 更新待定记录")
            options = [f"{row['日期']} | {row['主队']} vs {row['客队']}" for _, row in pending_df.iterrows()]
            selected = st.selectbox("选择比赛", options, key="edit_select")
            new_result = st.selectbox("实际结果", ["赢", "输", "平"], key="edit_result")

            if st.button("更新结果", key="edit_save"):
                idx = options.index(selected)
                actual_idx = pending_df.index[idx]
                row = df.iloc[actual_idx]
                stake = float(row["注额(RM)"])
                odds_used = float(str(row["主队期望值"])) if row["押注队伍"] == row["主队"] else float(str(row["客队期望值"]))
                pnl = (odds_used - 1) * stake if new_result == "赢" else (-stake if new_result == "输" else 0)
                update_sheet_row(actual_idx, new_result, pnl)
                st.success("✅ 已更新！按刷新查看")

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 下载记录", csv, "records.csv", "text/csv")

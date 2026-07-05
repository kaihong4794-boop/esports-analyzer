import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import pandas as pd
from datetime import date
import re

SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
HEADERS = [
    "日期", "运动", "主队", "客队",
    "主队加权胜率", "平局加权胜率", "客队加权胜率",
    "主队期望值", "平局期望值", "客队期望值",
    "主队隐含概率", "平局隐含概率", "客队隐含概率",
    "主队优势差距", "平局优势差距", "客队优势差距",
    "比赛结果", "甜蜜点", "建议下注", "押注方向", "投注结果"
]

def get_sheet():
    import json
    credentials_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def save_to_sheet(record):
    try:
        sheet = get_sheet()
        if sheet.row_count <= 1 and not sheet.cell(1, 1).value:
            sheet.append_row(HEADERS)
        sheet.append_row([record.get(h, "") for h in HEADERS])
        load_from_sheet.clear()
    except Exception as e:
        st.error(f"Google Sheets 保存失败: {e}")

@st.cache_data(ttl=60)
def load_from_sheet():
    try:
        sheet = get_sheet()
        actual_headers = sheet.row_values(1)
        data = sheet.get_all_records(expected_headers=actual_headers)
        df = pd.DataFrame(data) if data else pd.DataFrame(columns=HEADERS)
        for h in HEADERS:
            if h not in df.columns:
                df[h] = ""
        return df
    except Exception as e:
        st.session_state["_load_sheet_error"] = str(e)
        return pd.DataFrame(columns=HEADERS)

def _parse_pct(val):
    if val is None or val == "": return None
    if isinstance(val, (int, float)): return float(val)
    s = str(val).strip().replace("%", "").replace("+", "")
    try: return float(s)
    except: return None

def _parse_ev(val):
    if val is None or val == "": return None
    if isinstance(val, (int, float)): return float(val)
    try: return float(str(val).strip())
    except: return None

def find_similar_matches(df, sport, match_val, match_col, dist_label, top_n=15, sec_val=None, sec_col=None, h_wr_val=None, a_wr_val=None, d_wr_val=None):
    if df.empty: return []
    candidates = df[df["运动"] == sport].copy()
    if candidates.empty: return []
    rows = []
    for _, row in candidates.iterrows():
        result = str(row.get("比赛结果", "")).strip()
        if not result or result in ("nan", "None", "—", "CANCEL"): continue
        c_val = _parse_pct(row.get(match_col))
        if c_val is None: continue
        c_h_wp = _parse_pct(row.get("主队加权胜率"))
        c_a_wp = _parse_pct(row.get("客队加权胜率"))
        c_d_wp = _parse_pct(row.get("平局加权胜率"))
        c_h_ev = _parse_ev(row.get("主队期望值"))
        c_a_ev = _parse_ev(row.get("客队期望值"))
        sec_dist = 0
        if sec_val is not None and sec_col is not None:
            c_sec = _parse_ev(row.get(sec_col)) if "EV" in sec_col or "期望值" in sec_col else _parse_pct(row.get(sec_col))
            sec_dist = abs(c_sec - sec_val) if c_sec is not None else 9999
        h_wr_dist = abs(c_h_wp - h_wr_val) if h_wr_val is not None and c_h_wp is not None else 0
        a_wr_dist = abs(c_a_wp - a_wr_val) if a_wr_val is not None and c_a_wp is not None else 0
        d_wr_dist = abs(c_d_wp - d_wr_val) if d_wr_val is not None and c_d_wp is not None else 0
        combined_wp_dist = round(abs(c_val - match_val) + h_wr_dist + a_wr_dist, 1)
        rows.append({
            dist_label: combined_wp_dist, "_sec_dist": sec_dist, "_d_dist": d_wr_dist,
            "日期": row.get("日期", ""), "主队": row.get("主队", ""), "客队": row.get("客队", ""),
            "主队WP": c_h_wp, "平局WP": c_d_wp, "客队WP": c_a_wp,
            "主队EV": c_h_ev, "客队EV": c_a_ev,
            match_col: f"{c_val:.1f}%", "比赛结果": result,
        })
    rows.sort(key=lambda x: (float(x["_d_dist"]), float(x[dist_label]), float(x["_sec_dist"])))
    return rows[:top_n]

def show_similar_table(similar, sport="足球", session_key="similar_stats"):
    if not similar:
        st.info("暂无足够的历史数据（需要有比赛结果的记录）")
        st.session_state[session_key] = ""
        return
    base_cols = ["日期","主队","客队","主队WP","平局WP","客队WP","主队EV","客队EV","比赛结果"]
    extra_cols = [c for c in similar[0].keys() if c not in base_cols and not c.startswith("_")]
    show_df = pd.DataFrame(similar)[base_cols + extra_cols]
    st.dataframe(show_df, use_container_width=True, hide_index=True)
    h_win = draw = a_win = unknown = 0
    for m in similar:
        score = str(m["比赛结果"]).strip()
        mm = re.match(r"^(\d+)\s*-\s*(\d+)$", score)
        if not mm: unknown += 1; continue
        hs, as_ = int(mm.group(1)), int(mm.group(2))
        if hs > as_: h_win += 1
        elif hs < as_: a_win += 1
        else: draw += 1
    n = h_win + draw + a_win
    stats_str = ""
    if n > 0:
        st.divider()
        if sport == "足球":
            c1, c2, c3 = st.columns(3)
            c1.metric("🏠 主队胜", f"{h_win}/{n}  ({h_win/n:.0%})")
            c2.metric("🤝 平局",   f"{draw}/{n}  ({draw/n:.0%})")
            c3.metric("✈️ 客队胜", f"{a_win}/{n}  ({a_win/n:.0%})")
            stats_str = f"主胜{h_win/n:.0%} 平{draw/n:.0%} 客胜{a_win/n:.0%}（{n}场）"
            h_win1 = h_win2plus = a_win1 = a_win2plus = 0
            for m in similar:
                score = str(m["比赛结果"]).strip()
                mm = re.match(r"^(\d+)\s*-\s*(\d+)$", score)
                if not mm: continue
                hs, as_ = int(mm.group(1)), int(mm.group(2))
                diff = hs - as_
                if diff == 1: h_win1 += 1
                elif diff >= 2: h_win2plus += 1
                elif diff == -1: a_win1 += 1
                elif diff <= -2: a_win2plus += 1
            st.caption("比分细分（赢几球）")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("主胜1球", f"{h_win1}/{n} ({h_win1/n:.0%})")
            d2.metric("主胜2+球", f"{h_win2plus}/{n} ({h_win2plus/n:.0%})")
            d3.metric("客胜1球", f"{a_win1}/{n} ({a_win1/n:.0%})")
            d4.metric("客胜2+球", f"{a_win2plus}/{n} ({a_win2plus/n:.0%})")
            stats_str += f" | 主胜1球{h_win1/n:.0%} 主胜2+{h_win2plus/n:.0%} 客胜1球{a_win1/n:.0%} 客胜2+{a_win2plus/n:.0%}"
        else:
            c1, c2 = st.columns(2)
            c1.metric("🏠 主队胜", f"{h_win}/{n}  ({h_win/n:.0%})")
            c2.metric("✈️ 客队胜", f"{a_win}/{n}  ({a_win/n:.0%})")
            stats_str = f"主胜{h_win/n:.0%} 客胜{a_win/n:.0%}（{n}场）"
        if unknown > 0: st.caption(f"另有 {unknown} 场结果格式无法识别（未计入）")
    st.session_state[session_key] = stats_str

football_results = {
    "大胜": {"weight": 1.0,  "is_win": 1, "is_draw": 0},
    "小胜": {"weight": 0.75, "is_win": 1, "is_draw": 0},
    "平局": {"weight": 0.5,  "is_win": 0, "is_draw": 1},
    "小负": {"weight": 0.25, "is_win": 0, "is_draw": 0},
    "大负": {"weight": 0.05, "is_win": 0, "is_draw": 0},
}

score_weights_esports = {
    "1-0 赢": 0.85, "0-1 输": 0.2,  "1-1 平": 0.5,
    "2-0 赢": 1.0,  "2-1 赢": 0.7,  "1-2 输": 0.4,  "0-2 输": 0.2,
    "3-0 赢": 1.0,  "3-1 赢": 0.75, "3-2 赢": 0.6,
    "2-3 输": 0.4,  "1-3 输": 0.3,  "0-3 输": 0.2,
}

result_emoji_esports = {
    "1-0 赢": "🏆 BO1 赢",   "0-1 输": "💀 BO1 输",  "1-1 平": "➖ BO2 平局",
    "2-0 赢": "🏆 2-0 大胜", "2-1 赢": "✅ 2-1 小胜", "1-2 输": "❌ 1-2 小负",
    "0-2 输": "💀 0-2 大负", "3-0 赢": "🏆 3-0 大胜", "3-1 赢": "✅ 3-1 小胜",
    "3-2 赢": "✅ 3-2 小胜", "2-3 输": "❌ 2-3 小负", "1-3 输": "❌ 1-3 小负",
    "0-3 输": "💀 0-3 大负",
}

def score_to_football_result(score_str):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str): return None
    try: my_score, opp_score = map(int, score_str.split('-'))
    except: return None
    diff = abs(my_score - opp_score)
    if my_score > opp_score: return "大胜" if diff >= 3 else "小胜"
    elif my_score == opp_score: return "平局"
    else: return "大负" if diff >= 3 else "小负"

def score_to_esports_result(score_str):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str): return None
    try: a, b = map(int, score_str.split('-'))
    except: return None
    if a == b: key = f"{a}-{b} 平"
    elif a > b: key = f"{a}-{b} 赢"
    else: key = f"{a}-{b} 输"
    return key if key in score_weights_esports else None

st.title("运动期望值分析器 🏆")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["❌ 电竞", "⚽ 足球", "🏀 篮球", "⚾ 棒球", "📋 记录", "🎯 让球盘"])

with tab1:
    st.header("电竞期望值分析器")
    col1, col2 = st.columns(2)
    with col1:
        e_home_name = st.text_input("主队名字", "主队", key="e_home_name")
        e_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="e_home_odds")
    with col2:
        e_away_name = st.text_input("客队名字", "客队", key="e_away_name")
        e_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="e_away_odds")
    st.divider()
    num_matches_e = st.slider("最近几场比赛？", 1, 5, 5, key="e_slider")
    st.caption("支持 BO1 (1-0/0-1) · BO3 (2-0/2-1/1-2/0-2) · BO5 (3-0/3-1/3-2/2-3/1-3/0-3)")
    col3, col4 = st.columns(2)
    e_home_vars, e_away_vars = [], []
    with col3:
        st.markdown(f"**{e_home_name}**")
        for i in range(num_matches_e):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="2-1 / 1-0 / 3-2", key=f"eh_{i}")
            result = score_to_esports_result(score_input)
            if result: st.caption(f"→ {result_emoji_esports.get(result, result)}"); e_home_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 请填有效比分")
                e_home_vars.append("2-1 赢")
    with col4:
        st.markdown(f"**{e_away_name}**")
        for i in range(num_matches_e):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="2-1 / 1-0 / 3-2", key=f"ea_{i}")
            result = score_to_esports_result(score_input)
            if result: st.caption(f"→ {result_emoji_esports.get(result, result)}"); e_away_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 请填有效比分")
                e_away_vars.append("2-1 赢")
    if st.button("⚡ 计算", key="e_calc", type="primary"):
        def e_winrate(vars, weights):
            total_w = win_w = 0
            for i, v in enumerate(vars):
                base = 1.0 - (i * 0.1); total_w += base
                win_w += (1 if "赢" in v else (0.5 if "平" in v else 0)) * weights[v] * base
            return win_w / total_w if total_w > 0 else 0
        h_wr = e_winrate(e_home_vars, score_weights_esports)
        a_wr = e_winrate(e_away_vars, score_weights_esports)
        h_ev = (h_wr * (e_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (e_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        st.session_state["e_result"] = {"h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev, "h_odds": e_home_odds, "a_odds": e_away_odds, "h_name": e_home_name, "a_name": e_away_name}
    if "e_result" in st.session_state:
        r = st.session_state["e_result"]
        st.divider()
        h_impl = (1/r["h_odds"])*100; a_impl = (1/r["a_odds"])*100
        h_adv = r["h_wr"]*100 - h_impl; a_adv = r["a_wr"]*100 - a_impl
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"]); st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}"); st.metric("隐含概率", f"{h_impl:.1f}%")
        with col6:
            st.subheader(r["a_name"]); st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}"); st.metric("隐含概率", f"{a_impl:.1f}%")
        st.divider()
        if r["a_ev"] >= 100: st.success(f"🔄 EV逆向信号（强）：客队EV = {r['a_ev']:.1f} ≥ 100 → 参考押 **{r['h_name']}** 独赢（历史约70%）")
        elif r["a_ev"] >= 50: st.info(f"🔄 EV逆向信号：客队EV = {r['a_ev']:.1f} ≥ 50 → 参考押 **{r['h_name']}** 独赢（历史约64%）")
        elif r["h_ev"] >= 100: st.success(f"🔄 EV逆向信号（强）：主队EV = {r['h_ev']:.1f} ≥ 100 → 参考押 **{r['a_name']}** 独赢（历史约70%）")
        elif r["h_ev"] >= 50: st.info(f"🔄 EV逆向信号：主队EV = {r['h_ev']:.1f} ≥ 50 → 参考押 **{r['a_name']}** 独赢（历史约64%）")
        else: st.warning("⚪ 无EV逆向信号（主客队EV均低于50）")
        st.divider(); st.subheader("📊 相似历史比赛参考"); st.caption("根据相似指标找出历史上最接近的15场比赛，仅供参考")
        history_df = load_from_sheet()
        similar = find_similar_matches(history_df, "电竞", match_val=r["a_wr"]*100, match_col="客队加权胜率", dist_label="距离(WP差)", top_n=15, h_wr_val=r["h_wr"]*100)
        show_similar_table(similar, sport="电竞", session_key="e_similar_stats")
        st.divider()
        if st.button("💾 保存记录", key="e_save"):
            record = {"日期": str(date.today()), "运动": "电竞", "主队": r["h_name"], "客队": r["a_name"], "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A", "客队加权胜率": f"{r['a_wr']:.1%}", "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A", "客队期望值": f"{r['a_ev']:.2f}", "主队隐含概率": f"{h_impl:.1f}%", "平局隐含概率": "N/A", "客队隐含概率": f"{a_impl:.1f}%", "主队优势差距": f"{h_adv:+.1f}%", "平局优势差距": "N/A", "客队优势差距": f"{a_adv:+.1f}%", "比赛结果": "", "甜蜜点": st.session_state.get("e_similar_stats", ""), "建议下注": "", "押注方向": "", "投注结果": ""}
            save_to_sheet(record); st.success("✅ 记录已保存！")

with tab2:
    st.header("足球期望值分析器")
    col1, col2 = st.columns(2)
    with col1: f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
    with col2: f_away_name = st.text_input("客队名字", "客队", key="f_away_name")
    col3, col4, col5 = st.columns(3)
    with col3: f_home_odds = st.number_input("主队赔率", min_value=1.01, value=2.0, step=0.01, key="f_home_odds")
    with col4: f_draw_odds = st.number_input("平局赔率", min_value=1.01, value=3.0, step=0.01, key="f_draw_odds")
    with col5: f_away_odds = st.number_input("客队赔率", min_value=1.01, value=3.5, step=0.01, key="f_away_odds")
    st.divider()
    num_matches_f = st.slider("最近几场比赛？", 1, 15, 5, key="f_slider")
    st.caption("填实际比分（自己得分-对手得分）| 球差≥3=3-0/0-3  球差2=2-0/0-2  球差1=2-1/1-2  平局=1-1")
    def score_to_football_esports(score_str):
        score_str = score_str.strip()
        if not re.match(r'^\d+-\d+$', score_str): return None
        try: my, opp = map(int, score_str.split('-'))
        except: return None
        diff = my - opp
        if diff >= 3: return "3-0 赢"
        elif diff == 2: return "2-0 赢"
        elif diff == 1: return "2-1 赢"
        elif diff == 0: return "1-1 平"
        elif diff == -1: return "1-2 输"
        elif diff == -2: return "0-2 输"
        else: return "0-3 输"
    col_h2, col_a2 = st.columns(2)
    f_home_vars, f_away_vars = [], []
    with col_h2:
        st.markdown(f"**{f_home_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="自己-对手 如 2-1", key=f"fh_{i}")
            result = score_to_football_esports(score_input)
            if result: st.caption(f"→ {result_emoji_esports.get(result, result)}"); f_home_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误")
                f_home_vars.append("2-1 赢")
    with col_a2:
        st.markdown(f"**{f_away_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="自己-对手 如 2-1", key=f"fa_{i}")
            result = score_to_football_esports(score_input)
            if result: st.caption(f"→ {result_emoji_esports.get(result, result)}"); f_away_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误")
                f_away_vars.append("2-1 赢")
    if st.button("⚡ 计算", key="f_calc", type="primary"):
        def f_winrate(vars, weights):
            # 2026-07-05更新：改用指数衰减(0.93^i)取代线性衰减，支持15场窗口且不会变负数
            total_w = win_w = 0
            for i, v in enumerate(vars):
                base = 0.93 ** i; total_w += base
                win_w += (1 if "赢" in v else (0.5 if "平" in v else 0)) * weights[v] * base
            return win_w / total_w if total_w > 0 else 0
        h_wr_raw = f_winrate(f_home_vars, score_weights_esports)
        a_wr_raw = f_winrate(f_away_vars, score_weights_esports)
        # 归一化：强制主客队WP合计=100%，去除平局造成的噪音，风格对齐电竞公式
        wr_total = h_wr_raw + a_wr_raw
        if wr_total > 0:
            h_wr = h_wr_raw / wr_total
            a_wr = a_wr_raw / wr_total
        else:
            h_wr = a_wr = 0.5
        h_ev = (h_wr * (f_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr * (f_away_odds-1)*100) - ((1-a_wr)*100)
        st.session_state["f_result"] = {"h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev, "h_odds": f_home_odds, "a_odds": f_away_odds, "d_odds": f_draw_odds, "h_name": f_home_name, "a_name": f_away_name}
    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()
        h_impl = (1/r["h_odds"])*100; a_impl = (1/r["a_odds"])*100
        h_adv = r["h_wr"]*100 - h_impl; a_adv = r["a_wr"]*100 - a_impl
        col9, col11 = st.columns(2)
        with col9:
            st.subheader(f_home_name); st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}"); st.metric("隐含概率", f"{h_impl:.1f}%")
        with col11:
            st.subheader(f_away_name); st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}"); st.metric("隐含概率", f"{a_impl:.1f}%")
        st.caption(f"平局赔率参考：{r['d_odds']}（隐含概率 {1/r['d_odds']*100:.1f}%）")
        st.divider()
        if r["a_ev"] >= 100: st.success(f"🔄 EV逆向信号（强）：客队EV = {r['a_ev']:.1f} ≥ 100 → 参考押 **{f_home_name}** 独赢（历史约70%）")
        elif r["a_ev"] >= 50: st.info(f"🔄 EV逆向信号：客队EV = {r['a_ev']:.1f} ≥ 50 → 参考押 **{f_home_name}** 独赢（历史约64%）")
        elif r["h_ev"] >= 100: st.success(f"🔄 EV逆向信号（强）：主队EV = {r['h_ev']:.1f} ≥ 100 → 参考押 **{f_away_name}** 独赢（历史约70%）")
        elif r["h_ev"] >= 50: st.info(f"🔄 EV逆向信号：主队EV = {r['h_ev']:.1f} ≥ 50 → 参考押 **{f_away_name}** 独赢（历史约64%）")
        else: st.warning("⚪ 无EV逆向信号（主客队EV均低于50）")
        st.divider(); st.subheader("📊 相似历史比赛参考"); st.caption("根据相似指标找出历史上最接近的15场比赛，仅供参考")
        history_df = load_from_sheet()
        similar = find_similar_matches(history_df, "足球", match_val=r["a_wr"]*100, match_col="客队加权胜率", dist_label="距离(WP差)", top_n=15, h_wr_val=r["h_wr"]*100)
        show_similar_table(similar, sport="足球", session_key="f_similar_stats")
        st.divider()
        if st.button("💾 保存记录", key="f_save"):
            record = {"日期": str(date.today()), "运动": "足球", "主队": r["h_name"], "客队": r["a_name"], "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A", "客队加权胜率": f"{r['a_wr']:.1%}", "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A", "客队期望值": f"{r['a_ev']:.2f}", "主队隐含概率": f"{h_impl:.1f}%", "平局隐含概率": f"{1/r['d_odds']*100:.1f}%", "客队隐含概率": f"{a_impl:.1f}%", "主队优势差距": f"{h_adv:+.1f}%", "平局优势差距": "N/A", "客队优势差距": f"{a_adv:+.1f}%", "比赛结果": "", "甜蜜点": st.session_state.get("f_similar_stats", ""), "建议下注": "", "押注方向": "", "投注结果": ""}
            save_to_sheet(record); st.success("✅ 记录已保存！")

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
    score_weights_b = {"大胜 (+15以上)": 1.0, "小胜 (+1到+14)": 0.7, "小负 (-1到-14)": 0.4, "大负 (-15以上)": 0.2}
    col3, col4 = st.columns(2)
    b_home_vars, b_away_vars = [], []
    with col3:
        st.subheader(f"{b_home_name} 最近{num_matches_b}场")
        for i in range(num_matches_b):
            v = st.selectbox(f"第{i+1}场", list(score_weights_b.keys()), key=f"bh{i}"); b_home_vars.append(v)
    with col4:
        st.subheader(f"{b_away_name} 最近{num_matches_b}场")
        for i in range(num_matches_b):
            v = st.selectbox(f"第{i+1}场", list(score_weights_b.keys()), key=f"ba{i}"); b_away_vars.append(v)
    def b_winrate(vars, weights):
        total_w = win_w = 0
        for i, v in enumerate(vars):
            base = 1.0 - (i * 0.1); total_w += base
            win_w += (1 if "胜" in v else 0) * weights[v] * base
        return win_w / total_w if total_w > 0 else 0
    if st.button("计算", key="b_calc", type="primary"):
        h_wr = b_winrate(b_home_vars, score_weights_b); a_wr = b_winrate(b_away_vars, score_weights_b)
        h_ev = (h_wr*(b_home_odds-1)*100) - ((1-h_wr)*100); a_ev = (a_wr*(b_away_odds-1)*100) - ((1-a_wr)*100)
        st.session_state["b_result"] = {"h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev, "h_odds": b_home_odds, "a_odds": b_away_odds, "h_name": b_home_name, "a_name": b_away_name}
    if "b_result" in st.session_state:
        r = st.session_state["b_result"]; st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name); st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}"); st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            if r["h_ev"] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name); st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}"); st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            if r["a_ev"] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        st.divider()
        if st.button("💾 保存记录", key="b_save"):
            record = {"日期": str(date.today()), "运动": "篮球", "主队": r["h_name"], "客队": r["a_name"], "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A", "客队加权胜率": f"{r['a_wr']:.1%}", "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A", "客队期望值": f"{r['a_ev']:.2f}", "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": "N/A", "客队隐含概率": f"{1/r['a_odds']:.1%}", "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": "N/A", "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}", "比赛结果": "", "甜蜜点": "", "建议下注": "—", "押注方向": "—", "投注结果": ""}
            save_to_sheet(record); st.success("✅ 记录已保存！")

with tab4:
    st.header("⚾ 棒球期望值分析器")
    MLB_TEAMS = ["Arizona Diamondbacks","Atlanta Braves","Baltimore Orioles","Boston Red Sox","Chicago Cubs","Chicago White Sox","Cincinnati Reds","Cleveland Guardians","Colorado Rockies","Detroit Tigers","Houston Astros","Kansas City Royals","Los Angeles Angels","Los Angeles Dodgers","Miami Marlins","Milwaukee Brewers","Minnesota Twins","New York Mets","New York Yankees","Oakland Athletics","Philadelphia Phillies","Pittsburgh Pirates","San Diego Padres","San Francisco Giants","Seattle Mariners","St. Louis Cardinals","Tampa Bay Rays","Texas Rangers","Toronto Blue Jays","Washington Nationals"]
    col1, col2 = st.columns(2)
    with col1:
        bb_home_name = st.selectbox("主队", MLB_TEAMS, key="bb_home_name")
        bb_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.90, step=0.01, key="bb_home_odds")
    with col2:
        bb_away_name = st.selectbox("客队", MLB_TEAMS, index=1, key="bb_away_name")
        bb_away_odds = st.number_input("客队赔率", min_value=1.01, value=1.90, step=0.01, key="bb_away_odds")
    st.divider(); st.subheader("⚾ 先发投手战绩"); st.caption("填本季战绩，格式：胜场-负场（如 3-2）")
    col3, col4 = st.columns(2)
    with col3: bb_home_pitcher = st.text_input(f"{bb_home_name} 投手", placeholder="如 3-2", key="bb_home_pitcher")
    with col4: bb_away_pitcher = st.text_input(f"{bb_away_name} 投手", placeholder="如 1-1", key="bb_away_pitcher")
    def parse_pitcher(record_str):
        record_str = record_str.strip()
        for prefix in ["W,","L,","W ","L ","W","L"]:
            if record_str.upper().startswith(prefix.upper()): record_str = record_str[len(prefix):].strip()
        if not re.match(r'^\d+-\d+$', record_str): return None, 0
        try:
            w, l = map(int, record_str.split('-')); total = w + l
            return (w / total if total > 0 else 0.5), total
        except: return None, 0
    def pitcher_weight(total_games):
        if total_games <= 2: return 0.10
        elif total_games <= 4: return 0.15
        elif total_games <= 7: return 0.20
        else: return 0.25
    st.divider(); st.subheader("📊 近期比赛记录（最近5场）"); st.caption("最新的填第1场，从新到旧")
    col5, col6 = st.columns(2)
    bb_home_vars, bb_away_vars = [], []
    with col5:
        st.markdown(f"**🏠 {bb_home_name}**")
        for i in range(5):
            label = "最新" if i == 0 else f"第{i+1}场"
            result = st.selectbox(label, ["赢", "输"], key=f"bbh_{i}"); bb_home_vars.append(result)
    with col6:
        st.markdown(f"**✈️ {bb_away_name}**")
        for i in range(5):
            label = "最新" if i == 0 else f"第{i+1}场"
            result = st.selectbox(label, ["赢", "输"], key=f"bba_{i}"); bb_away_vars.append(result)
    def calc_baseball_wp(match_results, pitcher_str, is_home):
        weights = [1.0, 0.9, 0.8, 0.7, 0.6]; total_w = win_w = 0
        for i, r in enumerate(match_results):
            w = weights[i]; total_w += w; win_w += w if r == "赢" else 0
        team_wr = win_w / total_w if total_w > 0 else 0.5
        if is_home: team_wr = min(team_wr * 1.08, 0.99)
        p_wr, p_games = parse_pitcher(pitcher_str)
        if p_wr is not None and p_games > 0:
            p_w = pitcher_weight(p_games); return (team_wr * (1 - p_w)) + (p_wr * p_w)
        return team_wr
    if st.button("⚡ 计算", key="bb_calc", type="primary"):
        h_wr = calc_baseball_wp(bb_home_vars, bb_home_pitcher, True); a_wr = calc_baseball_wp(bb_away_vars, bb_away_pitcher, False)
        h_ev = (h_wr*(bb_home_odds-1)*100) - ((1-h_wr)*100); a_ev = (a_wr*(bb_away_odds-1)*100) - ((1-a_wr)*100)
        h_p_wr, h_p_games = parse_pitcher(bb_home_pitcher); a_p_wr, a_p_games = parse_pitcher(bb_away_pitcher)
        st.session_state["bb_result"] = {"h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev, "h_odds": bb_home_odds, "a_odds": bb_away_odds, "h_name": bb_home_name, "a_name": bb_away_name, "h_p_wr": h_p_wr, "h_p_games": h_p_games, "a_p_wr": a_p_wr, "a_p_games": a_p_games}
    if "bb_result" in st.session_state:
        r = st.session_state["bb_result"]; st.divider()
        h_impl = 1/r["h_odds"]*100; a_impl = 1/r["a_odds"]*100
        col7, col8 = st.columns(2)
        with col7:
            st.subheader(f"🏠 {r['h_name']}"); st.metric("综合胜率 (WP)", f"{r['h_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}"); st.metric("隐含概率", f"{h_impl:.1f}%")
            if r["h_p_wr"] is not None: st.caption(f"投手胜率 {r['h_p_wr']:.0%}（{r['h_p_games']}场，权重{pitcher_weight(r['h_p_games']):.0%}）")
            if r["h_ev"] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col8:
            st.subheader(f"✈️ {r['a_name']}"); st.metric("综合胜率 (WP)", f"{r['a_wr']:.1%}"); st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}"); st.metric("隐含概率", f"{a_impl:.1f}%")
            if r["a_p_wr"] is not None: st.caption(f"投手胜率 {r['a_p_wr']:.0%}（{r['a_p_games']}场，权重{pitcher_weight(r['a_p_games']):.0%}）")
            if r["a_ev"] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        st.divider()
        if r["a_ev"] >= 100: st.success(f"🔄 EV逆向信号（强）：客队EV = {r['a_ev']:.1f} ≥ 100 → 参考押 **{r['h_name']}** 独赢（历史约70%）")
        elif r["a_ev"] >= 50: st.info(f"🔄 EV逆向信号：客队EV = {r['a_ev']:.1f} ≥ 50 → 参考押 **{r['h_name']}** 独赢（历史约64%）")
        elif r["h_ev"] >= 100: st.success(f"🔄 EV逆向信号（强）：主队EV = {r['h_ev']:.1f} ≥ 100 → 参考押 **{r['a_name']}** 独赢（历史约70%）")
        elif r["h_ev"] >= 50: st.info(f"🔄 EV逆向信号：主队EV = {r['h_ev']:.1f} ≥ 50 → 参考押 **{r['a_name']}** 独赢（历史约64%）")
        else: st.warning("⚪ 无EV逆向信号（主客队EV均低于50）")
        st.divider(); st.subheader("📊 相似历史比赛参考")
        history_df = load_from_sheet()
        similar = find_similar_matches(history_df, "棒球", match_val=r["a_wr"]*100, match_col="客队加权胜率", dist_label="距离(WP差)", top_n=15, h_wr_val=r["h_wr"]*100)
        show_similar_table(similar, sport="棒球", session_key="bb_similar_stats")
        st.divider()
        if st.button("💾 保存记录", key="bb_save"):
            record = {"日期": str(date.today()), "运动": "棒球", "主队": r["h_name"], "客队": r["a_name"], "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A", "客队加权胜率": f"{r['a_wr']:.1%}", "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A", "客队期望值": f"{r['a_ev']:.2f}", "主队隐含概率": f"{h_impl:.1f}%", "平局隐含概率": "N/A", "客队隐含概率": f"{a_impl:.1f}%", "主队优势差距": f"{r['h_wr']*100-h_impl:+.1f}%", "平局优势差距": "N/A", "客队优势差距": f"{r['a_wr']*100-a_impl:+.1f}%", "比赛结果": "", "甜蜜点": st.session_state.get("bb_similar_stats", ""), "建议下注": "", "押注方向": "", "投注结果": ""}
            save_to_sheet(record); st.success("✅ 记录已保存！")

with tab5:
    st.header("📋 历史记录")
    if st.button("🔄 刷新记录", key="refresh"): st.rerun()
    df = load_from_sheet()
    if df.empty: st.info("还没有记录！")
    else:
        col1, col2 = st.columns(2)
        with col1: st.metric("总记录", len(df))
        with col2: st.metric("今日记录", len(df[df["日期"] == str(date.today())]))
        st.divider(); st.subheader("✏️ 填写比赛结果"); st.caption("填写比分后，这场比赛会成为日后「相似比赛参考」的数据来源")
        missing = df[(df["比赛结果"].astype(str).str.strip() == "") | (df["比赛结果"].isna())]
        if missing.empty: st.success("所有记录都已填写结果！")
        else:
            st.caption(f"还有 {len(missing)} 场记录未填写结果")
            for idx, row in missing.tail(20).iloc[::-1].iterrows():
                with st.expander(f"{row['日期']} | {row['运动']} | {row['主队']} vs {row['客队']}"):
                    score_input = st.text_input("比赛结果（格式：主队比分-客队比分，如 2-1）", value="", key=f"result_fill_{idx}")
                    if st.button("保存结果", key=f"save_result_{idx}"):
                        if re.match(r"^\d+\s*-\s*\d+$", score_input.strip()):
                            try:
                                sheet = get_sheet(); col_idx = HEADERS.index("比赛结果") + 1
                                sheet.update_cell(idx + 2, col_idx, score_input.strip()); st.success("✅ 已保存！"); st.rerun()
                            except Exception as e: st.error(f"保存失败: {e}")
                        else: st.warning("格式错误，请输入「数字-数字」，如 2-1")
        st.divider(); st.subheader("📄 完整记录"); st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8"); st.download_button("⬇️ 下载记录", csv, "records.csv", "text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# 让球盘 Sheet2
# ══════════════════════════════════════════════════════════════════════════════
HANDICAP_HEADERS = [
    "日期", "赛事",
    "电竞版_方向", "电竞版_主WP", "电竞版_客WP", "电竞版_历史参考",
    "足球版_方向", "足球版_主WP", "足球版_客WP", "足球版_历史参考",
    "实际结果", "赢/输", "信号"
]

def get_sheet2():
    import json
    credentials_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)
    try:
        return spreadsheet.worksheet("让球盘")
    except:
        ws = spreadsheet.add_worksheet(title="让球盘", rows=1000, cols=20)
        ws.append_row(HANDICAP_HEADERS)
        return ws

def save_to_sheet2(record):
    try:
        ws = get_sheet2()
        ws.append_row([record.get(h, "") for h in HANDICAP_HEADERS])
        load_from_sheet2.clear()
    except Exception as e:
        st.error(f"保存失败: {e}")

@st.cache_data(ttl=60)
def load_from_sheet2():
    try:
        ws = get_sheet2()
        data = ws.get_all_records()
        df = pd.DataFrame(data) if data else pd.DataFrame(columns=HANDICAP_HEADERS)
        for h in HANDICAP_HEADERS:
            if h not in df.columns:
                df[h] = ""
        return df
    except:
        return pd.DataFrame(columns=HANDICAP_HEADERS)

def _ref_direction(score_str):
    score_str = str(score_str).strip()
    if not re.match(r'^\d+-\d+$', score_str): return None
    h, a = map(int, score_str.split('-'))
    if h > a: return "F"
    elif a > h: return "C"
    else: return "D"

def _ref_goals(score_str):
    score_str = str(score_str).strip()
    if not re.match(r'^\d+-\d+$', score_str): return None
    h, a = map(int, score_str.split('-'))
    return h + a

def _wp_consistency_signal(sport, e_h, e_a, f_h, f_a):
    """
    电竞公式 vs 足球公式 WP 归一化一致性检查
    电竞公式主客=零和(主+客=100)，足球公式因含平局，主+客通常<100，
    直接比较原始差距不公平，需先把足球公式归一化到同一量尺再比较方向。

    电竞差距 = 主WP - 客WP（正=主队优势，负=客队优势）
    足球相对差距 = (主WP-客WP) / (主WP+客WP) * 100，同样正负号规则

    2026-07-03研究结论（纯符号判定，足球73场 / 电竞16场）：
    足球比赛：
      - 两公式方向一致 → 优势方胜率69.0%（n=42），买优势方
      - 两公式打架     → 优势方胜率仅35.5%，即劣势方64.5%（n=31），反买劣势方
    电竞比赛：
      - 两公式方向一致 → 优势方胜率仅36.4%，即劣势方63.6%（n=11），反买劣势方
      - 两公式打架     → 优势方胜率仅20.0%，即劣势方80.0%（n=5），强烈反买劣势方
      - 电竞WP精确=60/40（不分主客）→ 劣势方胜率100%（n=7，样本小但方向极一致）
    电竞规律与足球完全相反：足球信号越"一致"越可信优势方，电竞反而是越"一致"越该反买劣势方。
    """
    signals = []

    # 电竞60/40专项：优先检查，这是目前样本内最强的单一信号
    if sport == "电竞" and {round(e_h), round(e_a)} == {60, 40}:
        team_40 = "主队" if e_h == 40 else "客队"
        signals.append({
            "level": "gold",
            "msg": f"🎯 电竞WP精确=60/40 → 买【{team_40}】(WP=40%那队)，历史胜率100%（n=7小样本）",
            "rate": "100%(反买)"
        })

    e_gap = e_h - e_a
    f_total = f_h + f_a
    if f_total == 0 or e_gap == 0:
        signals.append({
            "level": "neutral",
            "msg": "➖ 电竞或足球公式打平，无法判断一致性",
            "rate": "N/A"
        })
        return signals

    f_gap_norm = (f_h - f_a) / f_total * 100
    if f_gap_norm == 0:
        signals.append({
            "level": "neutral",
            "msg": "➖ 足球公式打平，无法判断一致性",
            "rate": "N/A"
        })
        return signals

    same_sign = (e_gap > 0) == (f_gap_norm > 0)
    fav_team = "主队" if e_gap > 0 else "客队"   # 电竞公式判定的优势方(以电竞公式方向为准)
    dog_team = "客队" if e_gap > 0 else "主队"   # 电竞公式判定的劣势方

    if sport == "足球":
        if same_sign:
            signals.append({
                "level": "good",
                "msg": f"✅ 两公式方向一致（电竞{e_gap:+.0f} / 足球归一化{f_gap_norm:+.1f}）→ 买【{fav_team}】(优势方)，历史胜率69.0%",
                "rate": "69.0%"
            })
        else:
            signals.append({
                "level": "warn",
                "msg": f"🔄 两公式打架（电竞{e_gap:+.0f} / 足球归一化{f_gap_norm:+.1f}）→ 买【{dog_team}】(劣势方，反买)，历史胜率64.5%",
                "rate": "64.5%(反买)"
            })
    else:  # 电竞
        if same_sign:
            signals.append({
                "level": "warn",
                "msg": f"🔄 电竞两公式一致（电竞{e_gap:+.0f} / 足球归一化{f_gap_norm:+.1f}）→ 电竞规律与足球相反，买【{dog_team}】(劣势方，反买)，历史胜率63.6%",
                "rate": "63.6%(反买)"
            })
        else:
            signals.append({
                "level": "gold",
                "msg": f"🎯 电竞两公式打架（电竞{e_gap:+.0f} / 足球归一化{f_gap_norm:+.1f}）→ 买【{dog_team}】(劣势方，反买)，历史胜率80.0%，强烈建议",
                "rate": "80.0%(反买)"
            })

    return signals


def analyze_handicap_signals(sport, e_dir, f_dir, e_ref, f_ref, e_h=None, e_a=None, f_h=None, f_a=None):
    """
    e_dir: 电竞版方向 F/C（暂未使用，保留参数兼容旧调用）
    f_dir: 足球版方向 F/C（暂未使用，保留参数兼容旧调用）
    e_ref: 电竞版历史参考比分（暂未使用，保留参数兼容旧调用）
    f_ref: 足球版历史参考比分（暂未使用，保留参数兼容旧调用）

    2026-07-03 更新说明：
    原本这里有一套"电竞公式 vs 足球公式 WP归一化一致性检查"，
    但后来发现"足球版WP"这个输入框实际来源是「相似历史比赛参考(15场)」
    的胜率统计（跟已判定不可靠的"甜蜜点"系统同源），不是真正独立的
    加权公式计算结果。另外，比赛场地多为中立场，不该有主客场调整，
    所以电竞公式和足球公式本来就不该是两套独立体系。
    因此该信号的统计基础不成立，已撤除，避免继续误导下注判断。
    如需参考，请回到原本验证过的方法：WP + EV 双条件、以及样本量足够大的
    历史统计规则，不要依赖本函数。
    """
    return [{
        "level": "neutral",
        "msg": "⚪ WP一致性检查已撤除（数据来源存疑，详见代码注释），请参考原本的WP+EV方法自行判断",
        "rate": "N/A"
    }]



with tab6:
    st.header("🎯 让球盘分析记录")
    st.caption("记录F/C让球盘数据，两个版本对比，自动统计胜率")
    st.subheader("➕ 新增记录")

    col1, col2 = st.columns(2)
    with col1:
        hc_sport = st.selectbox("赛事", ["足球", "电竞"], key="hc_sport")
        hc_date = st.date_input("日期", value=date.today(), key="hc_date")

    st.divider()
    if st.button("🔄 一键带入 Tab1(电竞)/Tab2(足球) 最新计算结果", key="hc_autofill"):
        filled_any = False
        if "e_result" in st.session_state:
            er = st.session_state["e_result"]
            st.session_state["hc_e_h"] = round(er["h_wr"] * 100)
            st.session_state["hc_e_a"] = round(er["a_wr"] * 100)
            filled_any = True
        if "f_result" in st.session_state:
            fr = st.session_state["f_result"]
            st.session_state["hc_f_h"] = round(fr["h_wr"] * 100)
            st.session_state["hc_f_a"] = round(fr["a_wr"] * 100)
            filled_any = True
        if filled_any:
            st.success("✅ 已带入！请检查下方数字，确认无误后再保存记录")
        else:
            st.warning("⚠️ 还没有可带入的结果，请先去 Tab1 或 Tab2 点「⚡计算」")

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**⚡ 电竞版**")
        hc_e_main = st.selectbox("主队是", ["F（让球方）", "C（吃球方）"], key="hc_e_main")
        hc_e_h = st.number_input("主队 WP%", 0, 100, 50, key="hc_e_h")
        hc_e_a = st.number_input("客队 WP%", 0, 100, 50, key="hc_e_a")
        hc_e_ref = st.text_input("电竞版历史参考比分", placeholder="如 1-0", key="hc_e_ref")
        e_dir = "F" if "F" in hc_e_main else "C"
        st.caption(f"→ {e_dir}方向  主{hc_e_h}% vs 客{hc_e_a}%")

    with col4:
        st.markdown("**⚽ 足球版**")
        hc_f_main = st.selectbox("主队是", ["F（让球方）", "C（吃球方）"], key="hc_f_main")
        hc_f_h = st.number_input("主队 WP%", 0, 100, 50, key="hc_f_h")
        hc_f_a = st.number_input("客队 WP%", 0, 100, 50, key="hc_f_a")
        hc_f_ref = st.text_input("足球版历史参考比分", placeholder="如 2-1", key="hc_f_ref")
        f_dir = "F" if "F" in hc_f_main else "C"
        st.caption(f"→ {f_dir}方向  主{hc_f_h}% vs 客{hc_f_a}%")

    # 实时信号分析
    st.divider()
    st.subheader("🔍 信号分析")
    signals = analyze_handicap_signals(
        hc_sport, e_dir, f_dir, hc_e_ref, hc_f_ref,
        e_h=hc_e_h, e_a=hc_e_a, f_h=hc_f_h, f_a=hc_f_a
    )
    signal_texts = []
    for sig in signals:
        if sig["level"] == "gold": st.success(sig["msg"])
        elif sig["level"] == "good": st.info(sig["msg"])
        elif sig["level"] == "warn": st.warning(sig["msg"])
        elif sig["level"] == "skip": st.error(sig["msg"])
        else: st.info(sig["msg"])
        signal_texts.append(sig["msg"])

    if e_dir == f_dir:
        st.info(f"✅ 两版本方向一致（均为{f_dir}）")
    else:
        st.warning(f"⚠️ 两版本方向不一致（电竞{e_dir} vs 足球{f_dir}）→ 信号冲突，谨慎")

    if st.button("💾 保存记录", key="hc_save", type="primary"):
        signal_summary = " | ".join(signal_texts)
        record = {
            "日期": str(hc_date), "赛事": hc_sport,
            "电竞版_方向": e_dir,
            "电竞版_主WP": f"{hc_e_h}%", "电竞版_客WP": f"{hc_e_a}%",
            "电竞版_历史参考": hc_e_ref,
            "足球版_方向": f_dir,
            "足球版_主WP": f"{hc_f_h}%", "足球版_客WP": f"{hc_f_a}%",
            "足球版_历史参考": hc_f_ref,
            "实际结果": "", "赢/输": "",
            "信号": signal_summary
        }
        save_to_sheet2(record)
        st.success("✅ 已保存！信号分析也已记录，比赛结束后回来填实际结果。")

    # 填写实际结果
    st.divider()
    st.subheader("✏️ 填写实际结果")
    hc_df = load_from_sheet2()
    if not hc_df.empty:
        missing = hc_df[hc_df["实际结果"].astype(str).str.strip() == ""]
        if missing.empty:
            st.success("所有记录都已填写结果！")
        else:
            st.caption(f"还有 {len(missing)} 场未填写")
            for idx, row in missing.iloc[::-1].iterrows():
                e_ref_show = row.get("电竞版_历史参考", "")
                f_ref_show = row.get("足球版_历史参考", "")
                sig_show = str(row.get("信号", ""))[:40]
                label = f"{row['日期']} | {row['赛事']} | 电竞{row['电竞版_方向']} | 足球{row['足球版_方向']} | 电{e_ref_show}/足{f_ref_show}"
                with st.expander(label):
                    if sig_show:
                        st.caption(f"信号：{sig_show}...")
                    res_input = st.text_input("实际结果（如 2-1）", key=f"hc_res_{idx}")
                    if st.button("保存", key=f"hc_save_res_{idx}"):
                        if re.match(r"^\d+-\d+$", res_input.strip()):
                            s1, s2 = map(int, res_input.split("-"))
                            direction = row["足球版_方向"]
                            win_loss = "F" if s1 > s2 else "C"  # 平局也算C
                            try:
                                ws = get_sheet2()
                                sheet_row = idx + 2
                                res_col = HANDICAP_HEADERS.index("实际结果") + 1
                                wl_col = HANDICAP_HEADERS.index("赢/输") + 1
                                ws.update_cell(sheet_row, res_col, res_input.strip())
                                ws.update_cell(sheet_row, wl_col, win_loss)
                                load_from_sheet2.clear()
                                result_label = "✓ 赢" if win_loss == direction else "✗ 输"
                                st.success(f"✅ 已保存！{result_label}（{win_loss}）")
                                st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")
                        else:
                            st.warning("格式错误，请输入如 2-1")

    # 胜率统计
    st.divider()
    st.subheader("📊 胜率统计")
    hc_df = load_from_sheet2()
    completed = hc_df[hc_df["赢/输"].astype(str).isin(["F", "C"])].copy()

    if completed.empty:
        st.info("还没有完成的记录，继续加油记录！")
    else:
        completed["_win"] = completed.apply(lambda r: r["赢/输"] == r["足球版_方向"], axis=1)
        n = len(completed); wins = completed["_win"].sum()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总场次", len(hc_df))
        c2.metric("✓ 赢", int(wins))
        c3.metric("✗ 输", n - int(wins))
        c4.metric("胜率", f"{wins/n:.1%}" if n > 0 else "—")

        st.divider()
        f_rows = completed[completed["足球版_方向"] == "F"]
        c_rows = completed[completed["足球版_方向"] == "C"]
        col_fc1, col_fc2 = st.columns(2)
        with col_fc1:
            if len(f_rows) > 0:
                fw = f_rows["_win"].sum()
                st.metric("F方向胜率", f"{fw/len(f_rows):.1%}", f"{int(fw)}/{len(f_rows)}场")
        with col_fc2:
            if len(c_rows) > 0:
                cw = c_rows["_win"].sum()
                st.metric("C方向胜率", f"{cw/len(c_rows):.1%}", f"{int(cw)}/{len(c_rows)}场")
                if len(c_rows) >= 5:
                    st.caption(f"💡 C反押F胜率：{1 - cw/len(c_rows):.1%}")

        st.divider()
        # 三重确认统计
        triple_rows = []
        for _, row in completed.iterrows():
            ed = str(row.get("电竞版_方向", ""))
            fd = str(row.get("足球版_方向", ""))
            erd = _ref_direction(str(row.get("电竞版_历史参考", "")))
            frd = _ref_direction(str(row.get("足球版_历史参考", "")))
            if ed == fd == erd == frd and fd not in ("", "D"):
                triple_rows.append(row)
        if triple_rows:
            tdf = pd.DataFrame(triple_rows)
            tdf["_win"] = tdf.apply(lambda r: r["赢/输"] == r["足球版_方向"], axis=1)
            tw = tdf["_win"].sum()
            st.metric("🏆 三重确认胜率", f"{tw/len(tdf):.1%}", f"{int(tw)}/{len(tdf)}场")

        # F+大球统计
        fb_rows = []
        for _, row in completed.iterrows():
            if str(row.get("足球版_方向", "")) != "F": continue
            g1 = _ref_goals(str(row.get("电竞版_历史参考", "")))
            g2 = _ref_goals(str(row.get("足球版_历史参考", "")))
            if g1 is not None and g2 is not None and (g1 + g2) / 2 > 3:
                fb_rows.append(row)
        if fb_rows:
            fbdf = pd.DataFrame(fb_rows)
            fbdf["_win"] = fbdf.apply(lambda r: r["赢/输"] == r["足球版_方向"], axis=1)
            fbw = fbdf["_win"].sum()
            st.metric("⚽ F+大球(>3)胜率", f"{fbw/len(fbdf):.1%}", f"{int(fbw)}/{len(fbdf)}场")

        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(hc_df, use_container_width=True, hide_index=True)
        csv2 = hc_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ 下载让球盘记录", csv2, "handicap_records.csv", "text/csv")

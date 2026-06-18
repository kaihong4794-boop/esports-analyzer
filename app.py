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

# ─── Google Sheets ────────────────────────────────────────────────────────────
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
        # 确保所有HEADERS列都存在，缺的补空字符串
        for h in HEADERS:
            if h not in df.columns:
                df[h] = ""
        return df
    except Exception as e:
        st.session_state["_load_sheet_error"] = str(e)
        return pd.DataFrame(columns=HEADERS)

# ─── 相似比赛匹配 ──────────────────────────────────────────────────────────────
def _parse_pct(val):
    """把 '45.2%' / '+12.3%' / 45.2 这种格式转成 float（百分比数值，不除100）"""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("%", "").replace("+", "")
    try:
        return float(s)
    except:
        return None

def _parse_ev(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except:
        return None

def find_similar_matches(df, sport, match_val, match_col, dist_label, top_n=15, sec_val=None, sec_col=None, h_wr_val=None):
    """
    在历史数据df中找出最接近的场次。
    match_col: 主排序列（如"客队加权胜率"、"平局加权胜率"）
    sec_col:   次排序列（如"主队期望值"），可选
    """
    if df.empty:
        return []

    candidates = df[df["运动"] == sport].copy()
    if candidates.empty:
        return []

    rows = []
    for _, row in candidates.iterrows():
        result = str(row.get("比赛结果", "")).strip()
        if not result or result in ("nan", "None", "—", "CANCEL"):
            continue

        c_val = _parse_pct(row.get(match_col))
        if c_val is None:
            continue

        c_h_wp  = _parse_pct(row.get("主队加权胜率"))
        c_a_wp  = _parse_pct(row.get("客队加权胜率"))
        c_h_ev  = _parse_ev(row.get("主队期望值"))
        c_a_ev  = _parse_ev(row.get("客队期望值"))

        sec_dist = 0
        if sec_val is not None and sec_col is not None:
            c_sec = _parse_ev(row.get(sec_col)) if "EV" in sec_col or "期望值" in sec_col else _parse_pct(row.get(sec_col))
            sec_dist = abs(c_sec - sec_val) if c_sec is not None else 9999

        # 主队WP距离（若提供）
        h_wr_dist = 0
        if h_wr_val is not None:
            h_wr_dist = abs(c_h_wp - h_wr_val) if c_h_wp is not None else 9999

        combined_wp_dist = round(abs(c_val - match_val) + h_wr_dist, 1)
        rows.append({
            dist_label: combined_wp_dist,
            "_sec_dist": sec_dist,
            "日期": row.get("日期", ""),
            "主队": row.get("主队", ""),
            "客队": row.get("客队", ""),
            "主队WP": c_h_wp, "客队WP": c_a_wp,
            "主队EV": c_h_ev, "客队EV": c_a_ev,
            match_col: f"{c_val:.1f}%",
            "比赛结果": result,
        })

    rows.sort(key=lambda x: (float(x[dist_label]), float(x["_sec_dist"])))
    return rows[:top_n]

def show_similar_table(similar, sport="足球", session_key="similar_stats"):
    """显示相似比赛表格 + 胜平负统计，并把统计存入session_state"""
    if not similar:
        st.info("暂无足够的历史数据（需要有比赛结果的记录）")
        st.session_state[session_key] = ""
        return

    # 动态列：把固定列 + 额外列（匹配字段、距离）合并显示
    base_cols = ["日期","主队","客队","主队WP","客队WP","主队EV","客队EV","比赛结果"]
    extra_cols = [c for c in similar[0].keys() if c not in base_cols and not c.startswith("_")]
    show_df = pd.DataFrame(similar)[base_cols + extra_cols]
    st.dataframe(show_df, use_container_width=True, hide_index=True)

    # 统计胜平负
    h_win = draw = a_win = unknown = 0
    for m in similar:
        score = str(m["比赛结果"]).strip()
        mm = re.match(r"^(\d+)\s*-\s*(\d+)$", score)
        if not mm:
            unknown += 1
            continue
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
        else:
            c1, c2 = st.columns(2)
            c1.metric("🏠 主队胜", f"{h_win}/{n}  ({h_win/n:.0%})")
            c2.metric("✈️ 客队胜", f"{a_win}/{n}  ({a_win/n:.0%})")
            stats_str = f"主胜{h_win/n:.0%} 客胜{a_win/n:.0%}（{n}场）"
        if unknown > 0:
            st.caption(f"另有 {unknown} 场结果格式无法识别（未计入）")

    st.session_state[session_key] = stats_str


# ─── 比赛结果权重 ──────────────────────────────────────────────────────────────
football_results = {
    "🏠 主场大胜": {"weight": 1.0,  "is_win": 1, "is_draw": 0, "is_home": True},
    "🏠 主场小胜": {"weight": 0.75, "is_win": 1, "is_draw": 0, "is_home": True},
    "🏠 主场平局": {"weight": 0.5,  "is_win": 0, "is_draw": 1, "is_home": True},
    "🏠 主场小负": {"weight": 0.25, "is_win": 0, "is_draw": 0, "is_home": True},
    "🏠 主场大负": {"weight": 0.05, "is_win": 0, "is_draw": 0, "is_home": True},
    "✈️ 客场大胜": {"weight": 1.0,  "is_win": 1, "is_draw": 0, "is_home": False},
    "✈️ 客场小胜": {"weight": 0.75, "is_win": 1, "is_draw": 0, "is_home": False},
    "✈️ 客场平局": {"weight": 0.5,  "is_win": 0, "is_draw": 1, "is_home": False},
    "✈️ 客场小负": {"weight": 0.25, "is_win": 0, "is_draw": 0, "is_home": False},
    "✈️ 客场大负": {"weight": 0.05, "is_win": 0, "is_draw": 0, "is_home": False},
}

score_weights_esports = {
    "1-0 赢": 0.85, "0-1 输": 0.2,  "1-1 平": 0.5,
    "2-0 赢": 1.0,  "2-1 赢": 0.7,  "1-2 输": 0.4,  "0-2 输": 0.2,
    "3-0 赢": 1.0,  "3-1 赢": 0.75, "3-2 赢": 0.6,
    "2-3 输": 0.4,  "1-3 输": 0.3,  "0-3 输": 0.2,
}

result_emoji_football = {
    "🏠 主场大胜": "🏆 主场大胜 (≥+3)", "🏠 主场小胜": "✅ 主场小胜 (+1/+2)",
    "🏠 主场平局": "➖ 主场平局",        "🏠 主场小负": "❌ 主场小负 (-1/-2)",
    "🏠 主场大负": "💀 主场大负 (≤-3)", "✈️ 客场大胜": "🏆 客场大胜 (≥+3)",
    "✈️ 客场小胜": "✅ 客场小胜 (+1/+2)", "✈️ 客场平局": "➖ 客场平局",
    "✈️ 客场小负": "❌ 客场小负 (-1/-2)", "✈️ 客场大负": "💀 客场大负 (≤-3)",
}

result_emoji_esports = {
    "1-0 赢": "🏆 BO1 赢",   "0-1 输": "💀 BO1 输",  "1-1 平": "➖ BO2 平局",
    "2-0 赢": "🏆 2-0 大胜", "2-1 赢": "✅ 2-1 小胜", "1-2 输": "❌ 1-2 小负",
    "0-2 输": "💀 0-2 大负", "3-0 赢": "🏆 3-0 大胜", "3-1 赢": "✅ 3-1 小胜",
    "3-2 赢": "✅ 3-2 小胜", "2-3 输": "❌ 2-3 小负", "1-3 输": "❌ 1-3 小负",
    "0-3 输": "💀 0-3 大负",
}

# ─── 比分转换 ─────────────────────────────────────────────────────────────────
def score_to_football_result(score_str, is_home):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str): return None
    try:
        home_score, away_score = map(int, score_str.split('-'))
    except: return None
    my_score  = home_score if is_home else away_score
    opp_score = away_score if is_home else home_score
    diff  = abs(my_score - opp_score)
    venue = "🏠 主场" if is_home else "✈️ 客场"
    if my_score > opp_score:   return f"{venue}大胜" if diff >= 3 else f"{venue}小胜"
    elif my_score == opp_score: return f"{venue}平局"
    else:                       return f"{venue}大负" if diff >= 3 else f"{venue}小负"

def score_to_esports_result(score_str):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str): return None
    try: a, b = map(int, score_str.split('-'))
    except: return None
    if a == b:   key = f"{a}-{b} 平"
    elif a > b:  key = f"{a}-{b} 赢"
    else:        key = f"{a}-{b} 输"
    return key if key in score_weights_esports else None

# ══════════════════════════════════════════════════════════════════════════════
# App
# ══════════════════════════════════════════════════════════════════════════════
st.title("运动期望值分析器 🏆")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["❌ 电竞", "⚽ 足球", "🏀 篮球", "⚾ 棒球", "📋 记录"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: 电竞
# ══════════════════════════════════════════════════════════════════════════════
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
            if result:
                st.caption(f"→ {result_emoji_esports.get(result, result)}")
                e_home_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 请填有效比分")
                e_home_vars.append("2-1 赢")

    with col4:
        st.markdown(f"**{e_away_name}**")
        for i in range(num_matches_e):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="2-1 / 1-0 / 3-2", key=f"ea_{i}")
            result = score_to_esports_result(score_input)
            if result:
                st.caption(f"→ {result_emoji_esports.get(result, result)}")
                e_away_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 请填有效比分")
                e_away_vars.append("2-1 赢")

    if st.button("⚡ 计算", key="e_calc", type="primary"):
        def e_winrate(vars, weights):
            total_w = win_w = 0
            for i, v in enumerate(vars):
                base    = 1.0 - (i * 0.1)
                total_w += base
                win_w   += (1 if "赢" in v else (0.5 if "平" in v else 0)) * weights[v] * base
            return win_w / total_w if total_w > 0 else 0
        h_wr = e_winrate(e_home_vars, score_weights_esports)
        a_wr = e_winrate(e_away_vars, score_weights_esports)
        h_ev = (h_wr * (e_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (e_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        st.session_state["e_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": e_home_odds, "a_odds": e_away_odds,
            "h_name": e_home_name, "a_name": e_away_name,
        }

    if "e_result" in st.session_state:
        r = st.session_state["e_result"]
        st.divider()
        h_impl = (1/r["h_odds"])*100
        a_impl = (1/r["a_odds"])*100
        h_adv = r["h_wr"]*100 - h_impl
        a_adv = r["a_wr"]*100 - a_impl

        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"])
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",       f"{h_impl:.1f}%")
        with col6:
            st.subheader(r["a_name"])
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",       f"{a_impl:.1f}%")

        # ── EV逆向信号 ────────────────────────────────────────────────────
        st.divider()
        if r["a_ev"] >= 100:
            st.success(f"🔄 EV逆向信号（强）：客队EV = {r['a_ev']:.1f} ≥ 100 → 参考押 **{r['h_name']}** 独赢（历史约70%）")
        elif r["a_ev"] >= 50:
            st.info(f"🔄 EV逆向信号：客队EV = {r['a_ev']:.1f} ≥ 50 → 参考押 **{r['h_name']}** 独赢（历史约64%）")
        elif r["h_ev"] >= 100:
            st.success(f"🔄 EV逆向信号（强）：主队EV = {r['h_ev']:.1f} ≥ 100 → 参考押 **{r['a_name']}** 独赢（历史约70%）")
        elif r["h_ev"] >= 50:
            st.info(f"🔄 EV逆向信号：主队EV = {r['h_ev']:.1f} ≥ 50 → 参考押 **{r['a_name']}** 独赢（历史约64%）")
        else:
            st.warning("⚪ 无EV逆向信号（主客队EV均低于50）")

        # ── 相似历史比赛 ──────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 相似历史比赛参考")
        st.caption("根据相似指标找出历史上最接近的15场比赛，仅供参考")

        history_df = load_from_sheet()
        similar = find_similar_matches(history_df, "电竞", match_val=r["a_wr"]*100, match_col="客队加权胜率", dist_label="距离(WP差)", top_n=15, h_wr_val=r["h_wr"]*100)

        show_similar_table(similar, sport="电竞", session_key="e_similar_stats")


        st.divider()
        if st.button("💾 保存记录", key="e_save"):
            record = {
                "日期": str(date.today()), "运动": "电竞",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{h_impl:.1f}%", "平局隐含概率": "N/A",
                "客队隐含概率": f"{a_impl:.1f}%",
                "主队优势差距": f"{h_adv:+.1f}%", "平局优势差距": "N/A",
                "客队优势差距": f"{a_adv:+.1f}%",
                "比赛结果": "", "甜蜜点": st.session_state.get("e_similar_stats", ""),
                "建议下注": "", "押注方向": "", "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！比赛结束后请回来填写比赛结果，方便日后做相似比赛参考。")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: 足球
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("足球期望值分析器")
    col1, col2 = st.columns(2)
    with col1: f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
    with col2: f_away_name = st.text_input("客队名字", "客队", key="f_away_name")

    col3, col4, col5, col6 = st.columns([2, 2, 2, 2])
    with col3: f_home_odds = st.number_input("主队赔率", min_value=1.01, value=2.0, step=0.01, key="f_home_odds")
    with col4: f_draw_odds = st.number_input("平局赔率", min_value=1.01, value=3.0, step=0.01, key="f_draw_odds")
    with col5: f_away_odds = st.number_input("客队赔率", min_value=1.01, value=3.5, step=0.01, key="f_away_odds")
    with col6: venue = st.selectbox("场地", ["主队主场", "客队主场", "中立场"], key="f_venue")

    st.divider()
    num_matches_f = st.slider("最近几场比赛？", 1, 5, 5, key="f_slider")

    def calc_football_winrate(matches, is_playing_home, venue):
        if venue == "主队主场":   home_boost = 1.2 if is_playing_home else 0.8
        elif venue == "客队主场": home_boost = 0.8 if is_playing_home else 1.2
        else:                     home_boost = 1.0
        total_w = win_w = draw_w = 0
        for i, result in enumerate(matches):
            info = football_results[result]
            base = 1.0 - (i * 0.1)
            venue_multiplier = 1.2 if info["is_home"] else 0.8
            final_weight = base * info["weight"] * venue_multiplier * home_boost
            total_w += base
            win_w   += info["is_win"]  * final_weight
            draw_w  += info["is_draw"] * final_weight * 0.5
        return (win_w/total_w if total_w > 0 else 0), (draw_w/total_w if total_w > 0 else 0)

    st.subheader("近期比赛记录")
    st.caption("填实际比分（主队得分-客队得分）+ 选该队是主场还是客场 | 大胜/大负 = 差距≥3球")

    valid_keys = list(football_results.keys())
    col_h2, col_a2 = st.columns(2)
    f_home_vars, f_away_vars = [], []

    with col_h2:
        st.markdown(f"**🏠 {f_home_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            c1, c2 = st.columns([2, 1])
            with c1: score_input = st.text_input(label, value="", placeholder="主队-客队 如 2-1", key=f"fh_{i}")
            with c2: venue_sel = st.selectbox("", ["主场🏠", "客场✈️"], key=f"fh_venue_{i}", label_visibility="collapsed")
            result = score_to_football_result(score_input, "主场" in venue_sel)
            if result and result in valid_keys:
                st.caption(f"→ {result_emoji_football.get(result, result)}")
                f_home_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误")
                f_home_vars.append("🏠 主场小胜")

    with col_a2:
        st.markdown(f"**✈️ {f_away_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            c1, c2 = st.columns([2, 1])
            with c1: score_input = st.text_input(label, value="", placeholder="主队-客队 如 2-1", key=f"fa_{i}")
            with c2: venue_sel = st.selectbox("", ["主场🏠", "客场✈️"], index=1, key=f"fa_venue_{i}", label_visibility="collapsed")
            result = score_to_football_result(score_input, "主场" in venue_sel)
            if result and result in valid_keys:
                st.caption(f"→ {result_emoji_football.get(result, result)}")
                f_away_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误")
                f_away_vars.append("✈️ 客场小胜")

    if st.button("⚡ 计算", key="f_calc", type="primary"):
        h_wr, h_dr = calc_football_winrate(f_home_vars, True,  venue)
        a_wr, a_dr = calc_football_winrate(f_away_vars, False, venue)
        draw_prob  = (h_dr + a_dr) / 2
        h_ev = (h_wr * (f_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr * (f_away_odds-1)*100) - ((1-a_wr)*100)
        d_ev = (draw_prob * (f_draw_odds-1)*100) - ((1-draw_prob)*100)
        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "draw_prob": draw_prob,
            "h_ev": h_ev, "a_ev": a_ev, "d_ev": d_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds, "d_odds": f_draw_odds,
            "h_name": f_home_name, "a_name": f_away_name,
        }

    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()
        h_impl = (1/r["h_odds"])*100
        a_impl = (1/r["a_odds"])*100
        h_adv = r["h_wr"]*100 - h_impl
        a_adv = r["a_wr"]*100 - a_impl

        col9, col10, col11 = st.columns(3)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",       f"{h_impl:.1f}%")
        with col10:
            st.subheader("平局")
            st.metric("平局概率",       f"{r['draw_prob']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['d_ev']:.2f}")
            st.metric("隐含概率",       f"{1/r['d_odds']:.1%}")
            if r["d_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")
        with col11:
            st.subheader(f_away_name)
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",       f"{a_impl:.1f}%")

        # ── EV逆向信号 ────────────────────────────────────────────────────
        st.divider()
        if r["a_ev"] >= 100:
            st.success(f"🔄 EV逆向信号（强）：客队EV = {r['a_ev']:.1f} ≥ 100 → 参考押 **{f_home_name}** 独赢（历史约70%）")
        elif r["a_ev"] >= 50:
            st.info(f"🔄 EV逆向信号：客队EV = {r['a_ev']:.1f} ≥ 50 → 参考押 **{f_home_name}** 独赢（历史约64%）")
        elif r["h_ev"] >= 100:
            st.success(f"🔄 EV逆向信号（强）：主队EV = {r['h_ev']:.1f} ≥ 100 → 参考押 **{f_away_name}** 独赢（历史约70%）")
        elif r["h_ev"] >= 50:
            st.info(f"🔄 EV逆向信号：主队EV = {r['h_ev']:.1f} ≥ 50 → 参考押 **{f_away_name}** 独赢（历史约64%）")
        else:
            st.warning("⚪ 无EV逆向信号（主客队EV均低于50）")

        # ── 相似历史比赛 ──────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 相似历史比赛参考")
        st.caption("根据相似指标找出历史上最接近的15场比赛，仅供参考")

        history_df = load_from_sheet()
        similar = find_similar_matches(history_df, "足球", match_val=r["draw_prob"]*100, match_col="平局加权胜率", dist_label="距离(平局WP差)", top_n=15)

        show_similar_table(similar, sport="足球", session_key="f_similar_stats")

        st.divider()
        if st.button("💾 保存记录", key="f_save"):
            record = {
                "日期": str(date.today()), "运动": "足球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": f"{r['draw_prob']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": f"{r['d_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{h_impl:.1f}%", "平局隐含概率": f"{1/r['d_odds']*100:.1f}%",
                "客队隐含概率": f"{a_impl:.1f}%",
                "主队优势差距": f"{h_adv:+.1f}%",
                "平局优势差距": f"{r['draw_prob']*100 - 1/r['d_odds']*100:+.1f}%",
                "客队优势差距": f"{a_adv:+.1f}%",
                "比赛结果": "", "甜蜜点": st.session_state.get("f_similar_stats", ""),
                "建议下注": "", "押注方向": "", "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！比赛结束后请回来填写比赛结果，方便日后做相似比赛参考。")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: 篮球
# ══════════════════════════════════════════════════════════════════════════════
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
        "小负 (-1到-14)": 0.4, "大负 (-15以上)": 0.2,
    }
    col3, col4 = st.columns(2)
    b_home_vars, b_away_vars = [], []
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
            base = 1.0 - (i * 0.1); total_w += base
            win_w += (1 if "胜" in v else 0) * weights[v] * base
        return win_w / total_w if total_w > 0 else 0

    if st.button("计算", key="b_calc", type="primary"):
        h_wr = b_winrate(b_home_vars, score_weights_b)
        a_wr = b_winrate(b_away_vars, score_weights_b)
        h_ev = (h_wr*(b_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(b_away_odds-1)*100) - ((1-a_wr)*100)
        st.session_state["b_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": b_home_odds, "a_odds": b_away_odds,
            "h_name": b_home_name, "a_name": b_away_name,
        }

    if "b_result" in st.session_state:
        r = st.session_state["b_result"]
        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name)
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",       f"{1/r['h_odds']:.1%}")
            if r["h_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",       f"{1/r['a_odds']:.1%}")
            if r["a_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")
        st.divider()
        if st.button("💾 保存记录", key="b_save"):
            record = {
                "日期": str(date.today()), "运动": "篮球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": "N/A",
                "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": "N/A",
                "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": "", "建议下注": "—", "押注方向": "—", "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: 棒球
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("⚾ 棒球期望值分析器")

    MLB_TEAMS = [
        "Arizona Diamondbacks", "Atlanta Braves", "Baltimore Orioles",
        "Boston Red Sox", "Chicago Cubs", "Chicago White Sox",
        "Cincinnati Reds", "Cleveland Guardians", "Colorado Rockies",
        "Detroit Tigers", "Houston Astros", "Kansas City Royals",
        "Los Angeles Angels", "Los Angeles Dodgers", "Miami Marlins",
        "Milwaukee Brewers", "Minnesota Twins", "New York Mets",
        "New York Yankees", "Oakland Athletics", "Philadelphia Phillies",
        "Pittsburgh Pirates", "San Diego Padres", "San Francisco Giants",
        "Seattle Mariners", "St. Louis Cardinals", "Tampa Bay Rays",
        "Texas Rangers", "Toronto Blue Jays", "Washington Nationals",
    ]

    col1, col2 = st.columns(2)
    with col1:
        bb_home_name = st.selectbox("主队", MLB_TEAMS, key="bb_home_name")
        bb_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.90, step=0.01, key="bb_home_odds")
    with col2:
        bb_away_name = st.selectbox("客队", MLB_TEAMS, index=1, key="bb_away_name")
        bb_away_odds = st.number_input("客队赔率", min_value=1.01, value=1.90, step=0.01, key="bb_away_odds")

    st.divider()
    st.subheader("⚾ 先发投手战绩")
    st.caption("填本季战绩，格式：胜场-负场（如 3-2）")
    col3, col4 = st.columns(2)
    with col3:
        bb_home_pitcher = st.text_input(f"{bb_home_name} 投手", placeholder="如 3-2", key="bb_home_pitcher")
    with col4:
        bb_away_pitcher = st.text_input(f"{bb_away_name} 投手", placeholder="如 1-1", key="bb_away_pitcher")

    def parse_pitcher(record_str):
        """解析投手战绩，返回 (胜率, 总场数)"""
        record_str = record_str.strip()
        # 去掉 W/L 前缀
        for prefix in ["W,", "L,", "W ", "L ", "W", "L"]:
            if record_str.upper().startswith(prefix.upper()):
                record_str = record_str[len(prefix):].strip()
        if not re.match(r'^\d+-\d+$', record_str):
            return None, 0
        try:
            w, l = map(int, record_str.split('-'))
            total = w + l
            return (w / total if total > 0 else 0.5), total
        except:
            return None, 0

    def pitcher_weight(total_games):
        """动态投手权重"""
        if total_games <= 2:   return 0.10
        elif total_games <= 4: return 0.15
        elif total_games <= 7: return 0.20
        else:                  return 0.25

    st.divider()
    st.subheader("📊 近期比赛记录（最近5场）")
    st.caption("最新的填第1场，从新到旧")

    col5, col6 = st.columns(2)
    bb_home_vars, bb_away_vars = [], []

    with col5:
        st.markdown(f"**🏠 {bb_home_name}**")
        for i in range(5):
            label = "最新" if i == 0 else f"第{i+1}场"
            result = st.selectbox(label, ["赢", "输"], key=f"bbh_{i}")
            bb_home_vars.append(result)

    with col6:
        st.markdown(f"**✈️ {bb_away_name}**")
        for i in range(5):
            label = "最新" if i == 0 else f"第{i+1}场"
            result = st.selectbox(label, ["赢", "输"], key=f"bba_{i}")
            bb_away_vars.append(result)

    def calc_baseball_wp(match_results, pitcher_str, is_home):
        """计算棒球综合WP"""
        # 队伍近期胜率（递减权重）
        weights = [1.0, 0.9, 0.8, 0.7, 0.6]
        total_w = win_w = 0
        for i, r in enumerate(match_results):
            w = weights[i]
            total_w += w
            win_w   += w if r == "赢" else 0
        team_wr = win_w / total_w if total_w > 0 else 0.5

        # 主场加成
        if is_home:
            team_wr = min(team_wr * 1.08, 0.99)

        # 投手加成
        p_wr, p_games = parse_pitcher(pitcher_str)
        if p_wr is not None and p_games > 0:
            p_w = pitcher_weight(p_games)
            final_wr = (team_wr * (1 - p_w)) + (p_wr * p_w)
        else:
            final_wr = team_wr

        return final_wr

    if st.button("⚡ 计算", key="bb_calc", type="primary"):
        h_wr = calc_baseball_wp(bb_home_vars, bb_home_pitcher, True)
        a_wr = calc_baseball_wp(bb_away_vars, bb_away_pitcher, False)
        h_ev = (h_wr * (bb_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (bb_away_odds - 1) * 100) - ((1 - a_wr) * 100)

        # 投手信息解析（显示用）
        h_p_wr, h_p_games = parse_pitcher(bb_home_pitcher)
        a_p_wr, a_p_games = parse_pitcher(bb_away_pitcher)

        st.session_state["bb_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": bb_home_odds, "a_odds": bb_away_odds,
            "h_name": bb_home_name, "a_name": bb_away_name,
            "h_p_wr": h_p_wr, "h_p_games": h_p_games,
            "a_p_wr": a_p_wr, "a_p_games": a_p_games,
            "h_pitcher": bb_home_pitcher, "a_pitcher": bb_away_pitcher,
        }

    if "bb_result" in st.session_state:
        r = st.session_state["bb_result"]
        st.divider()
        h_impl = 1 / r["h_odds"] * 100
        a_impl = 1 / r["a_odds"] * 100

        col7, col8 = st.columns(2)
        with col7:
            st.subheader(f"🏠 {r['h_name']}")
            st.metric("综合胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",       f"{h_impl:.1f}%")
            if r["h_p_wr"] is not None:
                pw = pitcher_weight(r["h_p_games"])
                st.caption(f"投手胜率 {r['h_p_wr']:.0%}（{r['h_p_games']}场，权重{pw:.0%}）")
            if r["h_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")

        with col8:
            st.subheader(f"✈️ {r['a_name']}")
            st.metric("综合胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",       f"{a_impl:.1f}%")
            if r["a_p_wr"] is not None:
                pw = pitcher_weight(r["a_p_games"])
                st.caption(f"投手胜率 {r['a_p_wr']:.0%}（{r['a_p_games']}场，权重{pw:.0%}）")
            if r["a_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")

        # ── EV逆向信号 ────────────────────────────────────────────────────
        st.divider()
        if r["a_ev"] >= 100:
            st.success(f"🔄 EV逆向信号（强）：客队EV = {r['a_ev']:.1f} ≥ 100 → 参考押 **{r['h_name']}** 独赢（历史约70%）")
        elif r["a_ev"] >= 50:
            st.info(f"🔄 EV逆向信号：客队EV = {r['a_ev']:.1f} ≥ 50 → 参考押 **{r['h_name']}** 独赢（历史约64%）")
        elif r["h_ev"] >= 100:
            st.success(f"🔄 EV逆向信号（强）：主队EV = {r['h_ev']:.1f} ≥ 100 → 参考押 **{r['a_name']}** 独赢（历史约70%）")
        elif r["h_ev"] >= 50:
            st.info(f"🔄 EV逆向信号：主队EV = {r['h_ev']:.1f} ≥ 50 → 参考押 **{r['a_name']}** 独赢（历史约64%）")
        else:
            st.warning("⚪ 无EV逆向信号（主客队EV均低于50）")

        # ── 相似历史比赛 ──────────────────────────────────────────────────
        st.divider()
        st.subheader("📊 相似历史比赛参考")
        st.caption("根据相似指标找出历史上最接近的15场比赛，仅供参考")

        history_df = load_from_sheet()
        similar = find_similar_matches(history_df, "棒球", match_val=r["a_wr"]*100, match_col="客队加权胜率", dist_label="距离(WP差)", top_n=15, h_wr_val=r["h_wr"]*100)

        show_similar_table(similar, sport="棒球", session_key="bb_similar_stats")

        st.divider()
        if st.button("💾 保存记录", key="bb_save"):
            record = {
                "日期": str(date.today()), "运动": "棒球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{h_impl:.1f}%", "平局隐含概率": "N/A",
                "客队隐含概率": f"{a_impl:.1f}%",
                "主队优势差距": f"{r['h_wr']*100 - h_impl:+.1f}%", "平局优势差距": "N/A",
                "客队优势差距": f"{r['a_wr']*100 - a_impl:+.1f}%",
                "比赛结果": "", "甜蜜点": st.session_state.get("bb_similar_stats", ""),
                "建议下注": "", "押注方向": "", "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！比赛结束后请回来填写比赛结果，方便日后做相似比赛参考。")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: 记录
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("📋 历史记录")
    if st.button("🔄 刷新记录", key="refresh"): st.rerun()

    df = load_from_sheet()
    if df.empty:
        st.info("还没有记录！")
    else:
        col1, col2 = st.columns(2)
        with col1: st.metric("总记录", len(df))
        with col2: st.metric("今日记录", len(df[df["日期"] == str(date.today())]))

        st.divider()
        st.subheader("✏️ 填写比赛结果")
        st.caption("填写比分后，这场比赛会成为日后「相似比赛参考」的数据来源")

        missing = df[(df["比赛结果"].astype(str).str.strip() == "") | (df["比赛结果"].isna())]
        if missing.empty:
            st.success("所有记录都已填写结果！")
        else:
            st.caption(f"还有 {len(missing)} 场记录未填写结果")
            # 最多显示最近20场待填写
            missing_recent = missing.tail(20)
            for idx, row in missing_recent.iloc[::-1].iterrows():
                with st.expander(f"{row['日期']} | {row['运动']} | {row['主队']} vs {row['客队']}"):
                    score_input = st.text_input(
                        "比赛结果（格式：主队比分-客队比分，如 2-1）",
                        value="", key=f"result_fill_{idx}"
                    )
                    if st.button("保存结果", key=f"save_result_{idx}"):
                        if re.match(r"^\d+\s*-\s*\d+$", score_input.strip()):
                            try:
                                sheet = get_sheet()
                                # +2: 第1行是表头，DataFrame索引从0开始 → sheet行号 = idx + 2
                                col_idx = HEADERS.index("比赛结果") + 1
                                sheet.update_cell(idx + 2, col_idx, score_input.strip())
                                st.success("✅ 已保存！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")
                        else:
                            st.warning("格式错误，请输入「数字-数字」，如 2-1")

        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ 下载记录", csv, "records.csv", "text/csv")

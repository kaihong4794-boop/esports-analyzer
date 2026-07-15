import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import pandas as pd
from datetime import date
import re
import uuid

SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# ══════════════════════════════════════════════════════════════════════════════
# 新记录结构（2026-07-16 重新设计）
# 核心变化：
#   1. 百分比/EV 一律存数字，不存 "61.4%" 这种字符串，方便pandas直接算
#   2. 新增"赛事级别"（联赛/杯赛/国家队大赛），解决国家队比赛拖累整体命中率的问题
#   3. 新增"历史参考样本数"+"样本置信度"，样本<10自动标记低置信度，避免小样本被当真
#   4. "预测方向"由系统按WP自动算出，不是人工选
#   5. "预测命中"是公式列：填了比赛结果之后自动计算，不再靠人工判断/事后回忆
#   6. 撤除旧的 _wp_consistency_signal 死代码（未使用、含未经验证的硬编码胜率数字）
# ══════════════════════════════════════════════════════════════════════════════

HEADERS = [
    "比赛ID", "日期", "运动", "赛事级别", "主队", "客队",
    "主WP", "平WP", "客WP",
    "主EV", "平EV", "客EV",
    "主隐含概率", "平隐含概率", "客隐含概率",
    "历史参考样本数", "样本置信度",
    "甜蜜点触发", "预测方向",
    "比赛结果", "预测命中",
]

HANDICAP_HEADERS = [
    "比赛ID", "日期", "赛事", "赛事级别",
    "电竞方向", "电竞主WP", "电竞客WP", "电竞历史参考",
    "足球方向", "足球主WP", "足球客WP", "足球历史参考",
    "方向一致",
    "比赛结果", "预测命中",
]

EVENT_LEVELS = ["联赛", "杯赛", "国家队大赛"]
LOW_CONFIDENCE_THRESHOLD = 10  # 历史参考样本数低于此值 → 标记为低置信度


# ══════════════════════════════════════════════════════════════════════════════
# Google Sheets 读写
# ══════════════════════════════════════════════════════════════════════════════

def _get_client():
    import json
    credentials_info = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet():
    return _get_client().open_by_key(SHEET_ID).sheet1


def get_sheet2():
    spreadsheet = _get_client().open_by_key(SHEET_ID)
    try:
        return spreadsheet.worksheet("让球盘")
    except Exception:
        ws = spreadsheet.add_worksheet(title="让球盘", rows=2000, cols=20)
        ws.append_row(HANDICAP_HEADERS)
        return ws


def save_to_sheet(record):
    try:
        sheet = get_sheet()
        if sheet.row_count <= 1 and not sheet.cell(1, 1).value:
            sheet.append_row(HEADERS)
        sheet.append_row([record.get(h, "") for h in HEADERS])
        load_from_sheet.clear()
    except Exception as e:
        st.error(f"Google Sheets 保存失败: {e}")


def save_to_sheet2(record):
    try:
        ws = get_sheet2()
        ws.append_row([record.get(h, "") for h in HANDICAP_HEADERS])
        load_from_sheet2.clear()
    except Exception as e:
        st.error(f"保存失败: {e}")


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
    except Exception:
        return pd.DataFrame(columns=HANDICAP_HEADERS)


def new_match_id():
    return uuid.uuid4().hex[:8]


# ══════════════════════════════════════════════════════════════════════════════
# 数值解析工具（新结构存的是数字，但兼容旧sheet里可能还带 % 的历史行）
# ══════════════════════════════════════════════════════════════════════════════

def _parse_pct(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("%", "").replace("+", "")
    try:
        return float(s)
    except Exception:
        return None


def _parse_ev(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except Exception:
        return None


def _parse_score(score_str):
    score_str = str(score_str).strip()
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", score_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def result_direction(score_str):
    """H / D / A，解析不了返回 None"""
    parsed = _parse_score(score_str)
    if parsed is None:
        return None
    h, a = parsed
    if h > a:
        return "H"
    elif h < a:
        return "A"
    return "D"


def predicted_direction(h_wp, d_wp, a_wp):
    """按WP最高的一方给出预测方向，d_wp可能是None(无平局盘口)"""
    options = [("H", h_wp), ("A", a_wp)]
    if d_wp is not None:
        options.append(("D", d_wp))
    options = [(k, v) for k, v in options if v is not None]
    if not options:
        return None
    return max(options, key=lambda x: x[1])[0]


def is_sweet_spot(wp, ev):
    """甜蜜点定义：WP > 40% 且 EV > 20，任一方向满足即触发"""
    if wp is None or ev is None:
        return False
    return wp > 40 and ev > 20


# ══════════════════════════════════════════════════════════════════════════════
# 相似历史比赛查找（新增：赛事级别过滤 + 样本量诚实展示）
# ══════════════════════════════════════════════════════════════════════════════

def find_similar_matches(df, sport, match_val, match_col, dist_label,
                          top_n=15, h_wr_val=None, a_wr_val=None,
                          event_level=None, restrict_level=False):
    """
    restrict_level=True 时，只在同一"赛事级别"里找参考比赛
    （比如国家队大赛只跟国家队大赛比，避免拿俱乐部联赛历史去参考世界杯）
    """
    if df.empty:
        return [], 0

    candidates = df[df["运动"] == sport].copy()
    if restrict_level and event_level:
        candidates = candidates[candidates["赛事级别"] == event_level]
    if candidates.empty:
        return [], 0

    rows = []
    for _, row in candidates.iterrows():
        result = str(row.get("比赛结果", "")).strip()
        if not result or result in ("nan", "None", "—", "CANCEL"):
            continue
        c_val = _parse_pct(row.get(match_col))
        if c_val is None:
            continue
        c_h_wp = _parse_pct(row.get("主WP"))
        c_a_wp = _parse_pct(row.get("客WP"))
        c_h_ev = _parse_ev(row.get("主EV"))
        c_a_ev = _parse_ev(row.get("客EV"))

        h_wr_dist = abs(c_h_wp - h_wr_val) if h_wr_val is not None and c_h_wp is not None else 0
        a_wr_dist = abs(c_a_wp - a_wr_val) if a_wr_val is not None and c_a_wp is not None else 0
        combined_dist = round(abs(c_val - match_val) + h_wr_dist + a_wr_dist, 1)

        rows.append({
            dist_label: combined_dist,
            "日期": row.get("日期", ""), "主队": row.get("主队", ""), "客队": row.get("客队", ""),
            "主WP": c_h_wp, "客WP": c_a_wp, "主EV": c_h_ev, "客EV": c_a_ev,
            match_col: f"{c_val:.1f}%", "比赛结果": result,
        })

    rows.sort(key=lambda x: float(x[dist_label]))
    total_found = len(rows)
    return rows[:top_n], total_found


def show_similar_table(similar, total_found, sport="足球", session_key="similar_stats"):
    if not similar:
        st.info("暂无足够的历史数据（需要有比赛结果的记录）")
        st.session_state[session_key] = {"stats_str": "", "n": 0, "low_confidence": True}
        return

    low_confidence = total_found < LOW_CONFIDENCE_THRESHOLD
    if low_confidence:
        st.warning(f"⚠️ 只找到 {total_found} 场符合条件的历史比赛（少于{LOW_CONFIDENCE_THRESHOLD}场）"
                    f"——以下统计**样本量不足，仅供参考，不建议作为下注依据**")
    else:
        st.caption(f"共找到 {total_found} 场符合条件的历史比赛，取最接近的 {len(similar)} 场")

    base_cols = ["日期", "主队", "客队", "主WP", "客WP", "主EV", "客EV", "比赛结果"]
    show_df = pd.DataFrame(similar)[base_cols]
    st.dataframe(show_df, use_container_width=True, hide_index=True)

    h_win = draw = a_win = unknown = 0
    for m in similar:
        d = result_direction(m["比赛结果"])
        if d == "H":
            h_win += 1
        elif d == "A":
            a_win += 1
        elif d == "D":
            draw += 1
        else:
            unknown += 1
    n = h_win + draw + a_win
    stats_str = ""
    if n > 0:
        st.divider()
        if sport == "足球":
            c1, c2, c3 = st.columns(3)
            c1.metric("🏠 主队胜", f"{h_win}/{n}  ({h_win/n:.0%})")
            c2.metric("🤝 平局", f"{draw}/{n}  ({draw/n:.0%})")
            c3.metric("✈️ 客队胜", f"{a_win}/{n}  ({a_win/n:.0%})")
            stats_str = f"主胜{h_win/n:.0%} 平{draw/n:.0%} 客胜{a_win/n:.0%}（{n}场，{'低置信度' if low_confidence else '样本充分'}）"
        else:
            c1, c2 = st.columns(2)
            c1.metric("🏠 主队胜", f"{h_win}/{n}  ({h_win/n:.0%})")
            c2.metric("✈️ 客队胜", f"{a_win}/{n}  ({a_win/n:.0%})")
            stats_str = f"主胜{h_win/n:.0%} 客胜{a_win/n:.0%}（{n}场，{'低置信度' if low_confidence else '样本充分'}）"
        if unknown > 0:
            st.caption(f"另有 {unknown} 场结果格式无法识别（未计入）")
    st.session_state[session_key] = {"stats_str": stats_str, "n": total_found, "low_confidence": low_confidence}


# ══════════════════════════════════════════════════════════════════════════════
# 胜率计算用的权重表（保留原逻辑）
# ══════════════════════════════════════════════════════════════════════════════

score_weights_esports = {
    "1-0 赢": 0.85, "0-1 输": 0.2, "1-1 平": 0.5,
    "2-0 赢": 1.0, "2-1 赢": 0.7, "1-2 输": 0.4, "0-2 输": 0.2,
    "3-0 赢": 1.0, "3-1 赢": 0.75, "3-2 赢": 0.6,
    "2-3 输": 0.4, "1-3 输": 0.3, "0-3 输": 0.2,
}

result_emoji_esports = {
    "1-0 赢": "🏆 BO1 赢", "0-1 输": "💀 BO1 输", "1-1 平": "➖ BO2 平局",
    "2-0 赢": "🏆 2-0 大胜", "2-1 赢": "✅ 2-1 小胜", "1-2 输": "❌ 1-2 小负",
    "0-2 输": "💀 0-2 大负", "3-0 赢": "🏆 3-0 大胜", "3-1 赢": "✅ 3-1 小胜",
    "3-2 赢": "✅ 3-2 小胜", "2-3 输": "❌ 2-3 小负", "1-3 输": "❌ 1-3 小负",
    "0-3 输": "💀 0-3 大负",
}


def score_to_esports_result(score_str):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str):
        return None
    try:
        a, b = map(int, score_str.split('-'))
    except Exception:
        return None
    if a == b:
        key = f"{a}-{b} 平"
    elif a > b:
        key = f"{a}-{b} 赢"
    else:
        key = f"{a}-{b} 输"
    return key if key in score_weights_esports else None


def score_to_football_esports(score_str):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str):
        return None
    try:
        my, opp = map(int, score_str.split('-'))
    except Exception:
        return None
    diff = my - opp
    if diff >= 3:
        return "3-0 赢"
    elif diff == 2:
        return "2-0 赢"
    elif diff == 1:
        return "2-1 赢"
    elif diff == 0:
        return "1-1 平"
    elif diff == -1:
        return "1-2 输"
    elif diff == -2:
        return "0-2 输"
    else:
        return "0-3 输"


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

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
    e_event_level = st.selectbox("赛事级别", EVENT_LEVELS, key="e_event_level")
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
                if score_input:
                    st.caption("⚠️ 请填有效比分")
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
                if score_input:
                    st.caption("⚠️ 请填有效比分")
                e_away_vars.append("2-1 赢")

    if st.button("⚡ 计算", key="e_calc", type="primary"):
        def e_winrate(vars_, weights):
            total_w = win_w = 0
            for i, v in enumerate(vars_):
                base = 1.0 - (i * 0.1)
                total_w += base
                win_w += (1 if "赢" in v else (0.5 if "平" in v else 0)) * weights[v] * base
            return win_w / total_w if total_w > 0 else 0

        h_wr = e_winrate(e_home_vars, score_weights_esports)
        a_wr = e_winrate(e_away_vars, score_weights_esports)
        h_ev = (h_wr * (e_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (e_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        st.session_state["e_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": e_home_odds, "a_odds": e_away_odds,
            "h_name": e_home_name, "a_name": e_away_name, "event_level": e_event_level,
        }

    if "e_result" in st.session_state:
        r = st.session_state["e_result"]
        st.divider()
        h_impl = (1 / r["h_odds"]) * 100
        a_impl = (1 / r["a_odds"]) * 100
        h_adv = r["h_wr"] * 100 - h_impl
        a_adv = r["a_wr"] * 100 - a_impl
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"])
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{h_impl:.1f}%")
        with col6:
            st.subheader(r["a_name"])
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{a_impl:.1f}%")
        st.divider()

        h_wp_pct, a_wp_pct = r["h_wr"] * 100, r["a_wr"] * 100
        sweet_home = is_sweet_spot(h_wp_pct, r["h_ev"])
        sweet_away = is_sweet_spot(a_wp_pct, r["a_ev"])
        if sweet_home or sweet_away:
            who = r["h_name"] if sweet_home else r["a_name"]
            st.success(f"🎯 甜蜜点触发：{who}（WP>40% 且 EV>20）")
        else:
            st.warning("⚪ 未触发甜蜜点条件（WP>40% 且 EV>20）")

        pred_dir = predicted_direction(h_wp_pct, None, a_wp_pct)
        st.info(f"📌 系统预测方向：{'主队 ' + r['h_name'] if pred_dir == 'H' else '客队 ' + r['a_name']}（按WP最高方自动判定）")

        st.divider()
        st.subheader("📊 相似历史比赛参考")
        st.caption("默认只在同一「赛事级别」内查找，避免用联赛数据参考国家队比赛")
        restrict = st.checkbox("限定同一赛事级别查找", value=True, key="e_restrict_level")
        history_df = load_from_sheet()
        similar, total_found = find_similar_matches(
            history_df, "电竞", match_val=a_wp_pct, match_col="客WP", dist_label="距离(WP差)",
            top_n=15, h_wr_val=h_wp_pct, event_level=r["event_level"], restrict_level=restrict,
        )
        show_similar_table(similar, total_found, sport="电竞", session_key="e_similar_stats")

        st.divider()
        if st.button("💾 保存记录", key="e_save"):
            stats = st.session_state.get("e_similar_stats", {"stats_str": "", "n": 0, "low_confidence": True})
            record = {
                "比赛ID": new_match_id(), "日期": str(date.today()), "运动": "电竞",
                "赛事级别": r["event_level"], "主队": r["h_name"], "客队": r["a_name"],
                "主WP": round(h_wp_pct, 1), "平WP": "", "客WP": round(a_wp_pct, 1),
                "主EV": round(r["h_ev"], 2), "平EV": "", "客EV": round(r["a_ev"], 2),
                "主隐含概率": round(h_impl, 1), "平隐含概率": "", "客隐含概率": round(a_impl, 1),
                "历史参考样本数": stats["n"], "样本置信度": "低" if stats["low_confidence"] else "高",
                "甜蜜点触发": sweet_home or sweet_away, "预测方向": pred_dir,
                "比赛结果": "", "预测命中": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

with tab2:
    st.header("足球期望值分析器")
    col1, col2 = st.columns(2)
    with col1:
        f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
    with col2:
        f_away_name = st.text_input("客队名字", "客队", key="f_away_name")
    col3, col4, col5 = st.columns(3)
    with col3:
        f_home_odds = st.number_input("主队赔率", min_value=1.01, value=2.0, step=0.01, key="f_home_odds")
    with col4:
        f_draw_odds = st.number_input("平局赔率", min_value=1.01, value=3.0, step=0.01, key="f_draw_odds")
    with col5:
        f_away_odds = st.number_input("客队赔率", min_value=1.01, value=3.5, step=0.01, key="f_away_odds")
    f_event_level = st.selectbox("赛事级别", EVENT_LEVELS, key="f_event_level",
                                  help="国家队大赛历史参考样本天然偏少，系统会自动提示置信度")
    st.divider()
    num_matches_f = st.slider("最近几场比赛？", 1, 5, 5, key="f_slider")
    st.caption("填实际比分（自己得分-对手得分）| 球差≥3=3-0/0-3  球差2=2-0/0-2  球差1=2-1/1-2  平局=1-1")
    col_h2, col_a2 = st.columns(2)
    f_home_vars, f_away_vars = [], []
    with col_h2:
        st.markdown(f"**{f_home_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="自己-对手 如 2-1", key=f"fh_{i}")
            result = score_to_football_esports(score_input)
            if result:
                st.caption(f"→ {result_emoji_esports.get(result, result)}")
                f_home_vars.append(result)
            else:
                if score_input:
                    st.caption("⚠️ 格式错误")
                f_home_vars.append("2-1 赢")
    with col_a2:
        st.markdown(f"**{f_away_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            score_input = st.text_input(label, value="", placeholder="自己-对手 如 2-1", key=f"fa_{i}")
            result = score_to_football_esports(score_input)
            if result:
                st.caption(f"→ {result_emoji_esports.get(result, result)}")
                f_away_vars.append(result)
            else:
                if score_input:
                    st.caption("⚠️ 格式错误")
                f_away_vars.append("2-1 赢")

    if st.button("⚡ 计算", key="f_calc", type="primary"):
        def f_winrate(vars_, weights):
            total_w = win_w = 0
            for i, v in enumerate(vars_):
                base = 0.93 ** i
                total_w += base
                win_w += (1 if "赢" in v else (0.5 if "平" in v else 0)) * weights[v] * base
            return win_w / total_w if total_w > 0 else 0

        h_wr_raw = f_winrate(f_home_vars, score_weights_esports)
        a_wr_raw = f_winrate(f_away_vars, score_weights_esports)
        wr_total = h_wr_raw + a_wr_raw
        if wr_total > 0:
            h_wr = h_wr_raw / wr_total
            a_wr = a_wr_raw / wr_total
        else:
            h_wr = a_wr = 0.5
        h_ev = (h_wr * (f_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (f_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds, "d_odds": f_draw_odds,
            "h_name": f_home_name, "a_name": f_away_name, "event_level": f_event_level,
        }

    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()
        h_impl = (1 / r["h_odds"]) * 100
        a_impl = (1 / r["a_odds"]) * 100
        d_impl = (1 / r["d_odds"]) * 100
        col9, col11 = st.columns(2)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{h_impl:.1f}%")
        with col11:
            st.subheader(f_away_name)
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{a_impl:.1f}%")
        st.caption(f"平局赔率参考：{r['d_odds']}（隐含概率 {d_impl:.1f}%）")
        st.divider()

        h_wp_pct, a_wp_pct = r["h_wr"] * 100, r["a_wr"] * 100
        sweet_home = is_sweet_spot(h_wp_pct, r["h_ev"])
        sweet_away = is_sweet_spot(a_wp_pct, r["a_ev"])
        if sweet_home or sweet_away:
            who = f_home_name if sweet_home else f_away_name
            st.success(f"🎯 甜蜜点触发：{who}（WP>40% 且 EV>20）")
        else:
            st.warning("⚪ 未触发甜蜜点条件（WP>40% 且 EV>20）")

        pred_dir = predicted_direction(h_wp_pct, None, a_wp_pct)
        st.info(f"📌 系统预测方向：{'主队 ' + f_home_name if pred_dir == 'H' else '客队 ' + f_away_name}（按WP最高方自动判定，暂不含平局WP）")

        st.divider()
        st.subheader("📊 相似历史比赛参考")
        restrict = st.checkbox("限定同一赛事级别查找", value=True, key="f_restrict_level")
        history_df = load_from_sheet()
        similar, total_found = find_similar_matches(
            history_df, "足球", match_val=a_wp_pct, match_col="客WP", dist_label="距离(WP差)",
            top_n=15, h_wr_val=h_wp_pct, event_level=r["event_level"], restrict_level=restrict,
        )
        show_similar_table(similar, total_found, sport="足球", session_key="f_similar_stats")

        st.divider()
        if st.button("💾 保存记录", key="f_save"):
            stats = st.session_state.get("f_similar_stats", {"stats_str": "", "n": 0, "low_confidence": True})
            record = {
                "比赛ID": new_match_id(), "日期": str(date.today()), "运动": "足球",
                "赛事级别": r["event_level"], "主队": r["h_name"], "客队": r["a_name"],
                "主WP": round(h_wp_pct, 1), "平WP": "", "客WP": round(a_wp_pct, 1),
                "主EV": round(r["h_ev"], 2), "平EV": "", "客EV": round(r["a_ev"], 2),
                "主隐含概率": round(h_impl, 1), "平隐含概率": round(d_impl, 1), "客隐含概率": round(a_impl, 1),
                "历史参考样本数": stats["n"], "样本置信度": "低" if stats["low_confidence"] else "高",
                "甜蜜点触发": sweet_home or sweet_away, "预测方向": pred_dir,
                "比赛结果": "", "预测命中": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

with tab3:
    st.header("篮球期望值分析器")
    col1, col2 = st.columns(2)
    with col1:
        b_home_name = st.text_input("主队名字", "主队", key="b_home_name")
        b_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="b_home_odds")
    with col2:
        b_away_name = st.text_input("客队名字", "客队", key="b_away_name")
        b_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="b_away_odds")
    b_event_level = st.selectbox("赛事级别", EVENT_LEVELS, key="b_event_level")
    st.divider()
    num_matches_b = st.slider("最近几场比赛？", 1, 5, 5, key="b_slider")
    score_weights_b = {"大胜 (+15以上)": 1.0, "小胜 (+1到+14)": 0.7, "小负 (-1到-14)": 0.4, "大负 (-15以上)": 0.2}
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

    def b_winrate(vars_, weights):
        total_w = win_w = 0
        for i, v in enumerate(vars_):
            base = 1.0 - (i * 0.1)
            total_w += base
            win_w += (1 if "胜" in v else 0) * weights[v] * base
        return win_w / total_w if total_w > 0 else 0

    if st.button("计算", key="b_calc", type="primary"):
        h_wr = b_winrate(b_home_vars, score_weights_b)
        a_wr = b_winrate(b_away_vars, score_weights_b)
        h_ev = (h_wr * (b_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (b_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        st.session_state["b_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": b_home_odds, "a_odds": b_away_odds,
            "h_name": b_home_name, "a_name": b_away_name, "event_level": b_event_level,
        }

    if "b_result" in st.session_state:
        r = st.session_state["b_result"]
        st.divider()
        h_impl, a_impl = 1 / r["h_odds"] * 100, 1 / r["a_odds"] * 100
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name)
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{h_impl:.1f}%")
            st.success("✅ 正期望值") if r["h_ev"] > 0 else st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{a_impl:.1f}%")
            st.success("✅ 正期望值") if r["a_ev"] > 0 else st.error("❌ 负期望值")
        st.divider()
        pred_dir = predicted_direction(r["h_wr"] * 100, None, r["a_wr"] * 100)
        if st.button("💾 保存记录", key="b_save"):
            record = {
                "比赛ID": new_match_id(), "日期": str(date.today()), "运动": "篮球",
                "赛事级别": r["event_level"], "主队": r["h_name"], "客队": r["a_name"],
                "主WP": round(r["h_wr"] * 100, 1), "平WP": "", "客WP": round(r["a_wr"] * 100, 1),
                "主EV": round(r["h_ev"], 2), "平EV": "", "客EV": round(r["a_ev"], 2),
                "主隐含概率": round(h_impl, 1), "平隐含概率": "", "客隐含概率": round(a_impl, 1),
                "历史参考样本数": "", "样本置信度": "",
                "甜蜜点触发": is_sweet_spot(r["h_wr"] * 100, r["h_ev"]) or is_sweet_spot(r["a_wr"] * 100, r["a_ev"]),
                "预测方向": pred_dir, "比赛结果": "", "预测命中": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

with tab4:
    st.header("⚾ 棒球期望值分析器")
    MLB_TEAMS = ["Arizona Diamondbacks", "Atlanta Braves", "Baltimore Orioles", "Boston Red Sox",
                 "Chicago Cubs", "Chicago White Sox", "Cincinnati Reds", "Cleveland Guardians",
                 "Colorado Rockies", "Detroit Tigers", "Houston Astros", "Kansas City Royals",
                 "Los Angeles Angels", "Los Angeles Dodgers", "Miami Marlins", "Milwaukee Brewers",
                 "Minnesota Twins", "New York Mets", "New York Yankees", "Oakland Athletics",
                 "Philadelphia Phillies", "Pittsburgh Pirates", "San Diego Padres", "San Francisco Giants",
                 "Seattle Mariners", "St. Louis Cardinals", "Tampa Bay Rays", "Texas Rangers",
                 "Toronto Blue Jays", "Washington Nationals"]
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
        record_str = record_str.strip()
        for prefix in ["W,", "L,", "W ", "L ", "W", "L"]:
            if record_str.upper().startswith(prefix.upper()):
                record_str = record_str[len(prefix):].strip()
        if not re.match(r'^\d+-\d+$', record_str):
            return None, 0
        try:
            w, l = map(int, record_str.split('-'))
            total = w + l
            return (w / total if total > 0 else 0.5), total
        except Exception:
            return None, 0

    def pitcher_weight(total_games):
        if total_games <= 2:
            return 0.10
        elif total_games <= 4:
            return 0.15
        elif total_games <= 7:
            return 0.20
        return 0.25

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
        weights = [1.0, 0.9, 0.8, 0.7, 0.6]
        total_w = win_w = 0
        for i, r in enumerate(match_results):
            w = weights[i]
            total_w += w
            win_w += w if r == "赢" else 0
        team_wr = win_w / total_w if total_w > 0 else 0.5
        if is_home:
            team_wr = min(team_wr * 1.08, 0.99)
        p_wr, p_games = parse_pitcher(pitcher_str)
        if p_wr is not None and p_games > 0:
            p_w = pitcher_weight(p_games)
            return (team_wr * (1 - p_w)) + (p_wr * p_w)
        return team_wr

    if st.button("⚡ 计算", key="bb_calc", type="primary"):
        h_wr = calc_baseball_wp(bb_home_vars, bb_home_pitcher, True)
        a_wr = calc_baseball_wp(bb_away_vars, bb_away_pitcher, False)
        h_ev = (h_wr * (bb_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (bb_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        h_p_wr, h_p_games = parse_pitcher(bb_home_pitcher)
        a_p_wr, a_p_games = parse_pitcher(bb_away_pitcher)
        st.session_state["bb_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": bb_home_odds, "a_odds": bb_away_odds,
            "h_name": bb_home_name, "a_name": bb_away_name,
            "h_p_wr": h_p_wr, "h_p_games": h_p_games, "a_p_wr": a_p_wr, "a_p_games": a_p_games,
        }

    if "bb_result" in st.session_state:
        r = st.session_state["bb_result"]
        st.divider()
        h_impl, a_impl = 1 / r["h_odds"] * 100, 1 / r["a_odds"] * 100
        col7, col8 = st.columns(2)
        with col7:
            st.subheader(f"🏠 {r['h_name']}")
            st.metric("综合胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{h_impl:.1f}%")
            if r["h_p_wr"] is not None:
                st.caption(f"投手胜率 {r['h_p_wr']:.0%}（{r['h_p_games']}场，权重{pitcher_weight(r['h_p_games']):.0%}）")
            st.success("✅ 正期望值") if r["h_ev"] > 0 else st.error("❌ 负期望值")
        with col8:
            st.subheader(f"✈️ {r['a_name']}")
            st.metric("综合胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{a_impl:.1f}%")
            if r["a_p_wr"] is not None:
                st.caption(f"投手胜率 {r['a_p_wr']:.0%}（{r['a_p_games']}场，权重{pitcher_weight(r['a_p_games']):.0%}）")
            st.success("✅ 正期望值") if r["a_ev"] > 0 else st.error("❌ 负期望值")
        st.divider()
        pred_dir = predicted_direction(r["h_wr"] * 100, None, r["a_wr"] * 100)
        if st.button("💾 保存记录", key="bb_save"):
            record = {
                "比赛ID": new_match_id(), "日期": str(date.today()), "运动": "棒球",
                "赛事级别": "联赛", "主队": r["h_name"], "客队": r["a_name"],
                "主WP": round(r["h_wr"] * 100, 1), "平WP": "", "客WP": round(r["a_wr"] * 100, 1),
                "主EV": round(r["h_ev"], 2), "平EV": "", "客EV": round(r["a_ev"], 2),
                "主隐含概率": round(h_impl, 1), "平隐含概率": "", "客隐含概率": round(a_impl, 1),
                "历史参考样本数": "", "样本置信度": "",
                "甜蜜点触发": is_sweet_spot(r["h_wr"] * 100, r["h_ev"]) or is_sweet_spot(r["a_wr"] * 100, r["a_ev"]),
                "预测方向": pred_dir, "比赛结果": "", "预测命中": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

with tab5:
    st.header("📋 历史记录")
    if st.button("🔄 刷新记录", key="refresh"):
        st.rerun()
    df = load_from_sheet()
    if df.empty:
        st.info("还没有记录！")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总记录", len(df))
        with col2:
            st.metric("今日记录", len(df[df["日期"] == str(date.today())]))
        with col3:
            has_result = df[df["比赛结果"].astype(str).str.strip() != ""]
            if not has_result.empty and "预测命中" in has_result.columns:
                hit_col = has_result["预测命中"].astype(str)
                hit_n = (hit_col == "True").sum()
                total_n = len(has_result)
                st.metric("整体命中率", f"{hit_n/total_n:.1%}" if total_n else "—", f"{hit_n}/{total_n}场")

        st.divider()
        st.subheader("✏️ 填写比赛结果")
        st.caption("填写比分后，「预测命中」会自动计算，不用手动判断")
        missing = df[(df["比赛结果"].astype(str).str.strip() == "") | (df["比赛结果"].isna())]
        if missing.empty:
            st.success("所有记录都已填写结果！")
        else:
            st.caption(f"还有 {len(missing)} 场记录未填写结果")
            for idx, row in missing.tail(20).iloc[::-1].iterrows():
                label = f"{row['日期']} | {row['运动']} | {row.get('赛事级别','')} | {row['主队']} vs {row['客队']}"
                with st.expander(label):
                    score_input = st.text_input("比赛结果（格式：主队比分-客队比分，如 2-1）", value="", key=f"result_fill_{idx}")
                    if st.button("保存结果", key=f"save_result_{idx}"):
                        if re.match(r"^\d+\s*-\s*\d+$", score_input.strip()):
                            actual = result_direction(score_input.strip())
                            pred = str(row.get("预测方向", "")).strip() or None
                            hit = (actual == pred) if pred else ""
                            try:
                                sheet = get_sheet()
                                res_col = HEADERS.index("比赛结果") + 1
                                hit_col = HEADERS.index("预测命中") + 1
                                sheet.update_cell(idx + 2, res_col, score_input.strip())
                                sheet.update_cell(idx + 2, hit_col, str(hit))
                                load_from_sheet.clear()
                                st.success(f"✅ 已保存！预测{'命中' if hit is True else ('未命中' if hit is False else '（无预测方向）')}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")
                        else:
                            st.warning("格式错误，请输入「数字-数字」，如 2-1")

        st.divider()
        st.subheader("📊 按赛事级别拆分命中率")
        st.caption("解决\"国家队/杯赛拖累整体命中率\"问题：分开看才知道模型在哪种场景真的有效")
        has_result = df[(df["比赛结果"].astype(str).str.strip() != "") & (df["预测命中"].astype(str) != "")]
        if not has_result.empty:
            for level in EVENT_LEVELS:
                sub = has_result[has_result["赛事级别"] == level]
                if len(sub) == 0:
                    continue
                hit = (sub["预测命中"].astype(str) == "True").sum()
                st.write(f"**{level}**：{hit}/{len(sub)} = {hit/len(sub):.1%}")
        else:
            st.info("还没有足够已完成+已判定的记录")

        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ 下载记录", csv, "records.csv", "text/csv")


with tab6:
    st.header("🎯 让球盘分析记录")
    st.caption("记录F/C让球盘数据，两个版本对比，自动统计胜率")
    st.subheader("➕ 新增记录")

    col1, col2, col3 = st.columns(3)
    with col1:
        hc_sport = st.selectbox("赛事", ["足球", "电竞"], key="hc_sport")
    with col2:
        hc_date = st.date_input("日期", value=date.today(), key="hc_date")
    with col3:
        hc_event_level = st.selectbox("赛事级别", EVENT_LEVELS, key="hc_event_level")

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

    st.divider()
    if e_dir == f_dir:
        st.info(f"✅ 两版本方向一致（均为{f_dir}）——注意：过去数据显示这两个方向公式高度相关，"
                f"「一致」本身不代表独立验证，请勿单独当作加强信号")
    else:
        st.warning(f"⚠️ 两版本方向不一致（电竞{e_dir} vs 足球{f_dir}）")

    if st.button("💾 保存记录", key="hc_save", type="primary"):
        record = {
            "比赛ID": new_match_id(), "日期": str(hc_date), "赛事": hc_sport, "赛事级别": hc_event_level,
            "电竞方向": e_dir, "电竞主WP": hc_e_h, "电竞客WP": hc_e_a, "电竞历史参考": hc_e_ref,
            "足球方向": f_dir, "足球主WP": hc_f_h, "足球客WP": hc_f_a, "足球历史参考": hc_f_ref,
            "方向一致": e_dir == f_dir,
            "比赛结果": "", "预测命中": "",
        }
        save_to_sheet2(record)
        st.success("✅ 已保存！比赛结束后回来填实际结果。")

    st.divider()
    st.subheader("✏️ 填写实际结果")
    hc_df = load_from_sheet2()
    if not hc_df.empty:
        missing = hc_df[hc_df["比赛结果"].astype(str).str.strip() == ""]
        if missing.empty:
            st.success("所有记录都已填写结果！")
        else:
            st.caption(f"还有 {len(missing)} 场未填写")
            for idx, row in missing.iloc[::-1].iterrows():
                label = f"{row['日期']} | {row['赛事']} | {row.get('赛事级别','')} | 电竞{row['电竞方向']} | 足球{row['足球方向']}"
                with st.expander(label):
                    res_input = st.text_input("实际结果（如 2-1）", key=f"hc_res_{idx}")
                    if st.button("保存", key=f"hc_save_res_{idx}"):
                        if re.match(r"^\d+-\d+$", res_input.strip()):
                            s1, s2 = map(int, res_input.split("-"))
                            actual_dir = "F" if s1 > s2 else "C"  # 平局算C，跟原逻辑一致
                            hit = actual_dir == row["足球方向"]
                            try:
                                ws = get_sheet2()
                                sheet_row = idx + 2
                                res_col = HANDICAP_HEADERS.index("比赛结果") + 1
                                hit_col = HANDICAP_HEADERS.index("预测命中") + 1
                                ws.update_cell(sheet_row, res_col, res_input.strip())
                                ws.update_cell(sheet_row, hit_col, str(hit))
                                load_from_sheet2.clear()
                                st.success(f"✅ 已保存！{'✓ 命中' if hit else '✗ 未命中'}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")
                        else:
                            st.warning("格式错误，请输入如 2-1")

    st.divider()
    st.subheader("📊 胜率统计")
    hc_df = load_from_sheet2()
    completed = hc_df[hc_df["预测命中"].astype(str).isin(["True", "False"])].copy()

    if completed.empty:
        st.info("还没有完成的记录，继续加油记录！")
    else:
        completed["_win"] = completed["预测命中"].astype(str) == "True"
        n = len(completed)
        wins = completed["_win"].sum()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总场次", len(hc_df))
        c2.metric("✓ 命中", int(wins))
        c3.metric("✗ 未命中", n - int(wins))
        c4.metric("命中率", f"{wins/n:.1%}" if n > 0 else "—")

        st.divider()
        st.caption("按赛事级别拆分（避免国家队大赛拖累整体数字）")
        for level in EVENT_LEVELS:
            sub = completed[completed["赛事级别"] == level]
            if len(sub) == 0:
                continue
            w = sub["_win"].sum()
            st.write(f"**{level}**：{int(w)}/{len(sub)} = {w/len(sub):.1%}")

        st.divider()
        f_rows = completed[completed["足球方向"] == "F"]
        c_rows = completed[completed["足球方向"] == "C"]
        col_fc1, col_fc2 = st.columns(2)
        with col_fc1:
            if len(f_rows) > 0:
                fw = f_rows["_win"].sum()
                st.metric("F方向命中率", f"{fw/len(f_rows):.1%}", f"{int(fw)}/{len(f_rows)}场")
        with col_fc2:
            if len(c_rows) > 0:
                cw = c_rows["_win"].sum()
                st.metric("C方向命中率", f"{cw/len(c_rows):.1%}", f"{int(cw)}/{len(c_rows)}场")

        st.divider()
        agree_rows = completed[completed["方向一致"].astype(str) == "True"]
        disagree_rows = completed[completed["方向一致"].astype(str) == "False"]
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            if len(agree_rows) > 0:
                aw = agree_rows["_win"].sum()
                st.metric("方向一致时命中率", f"{aw/len(agree_rows):.1%}", f"{int(aw)}/{len(agree_rows)}场")
        with col_a2:
            if len(disagree_rows) > 0:
                dw = disagree_rows["_win"].sum()
                st.metric("方向不一致时命中率", f"{dw/len(disagree_rows):.1%}", f"{int(dw)}/{len(disagree_rows)}场")
            else:
                st.caption("⚠️ 目前没有\"方向不一致\"的样本——电竞版和足球版公式高度相关，"
                           "这本身就是需要修复的已知问题（详见对话记录）")

        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(hc_df, use_container_width=True, hide_index=True)
        csv2 = hc_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ 下载让球盘记录", csv2, "handicap_records.csv", "text/csv")

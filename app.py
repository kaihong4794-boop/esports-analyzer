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
    "比赛结果", "甜蜜点", "投注结果"
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
    except Exception as e:
        st.error(f"Google Sheets 保存失败: {e}")

def load_from_sheet():
    try:
        sheet = get_sheet()
        data = sheet.get_all_records()
        return pd.DataFrame(data) if data else pd.DataFrame(columns=HEADERS)
    except:
        return pd.DataFrame(columns=HEADERS)

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
    if not re.match(r'^\d+-\d+$', score_str):
        return None
    try:
        home_score, away_score = map(int, score_str.split('-'))
    except:
        return None
    my_score  = home_score if is_home else away_score
    opp_score = away_score if is_home else home_score
    diff  = abs(my_score - opp_score)
    venue = "🏠 主场" if is_home else "✈️ 客场"
    if my_score > opp_score:
        return f"{venue}大胜" if diff >= 3 else f"{venue}小胜"
    elif my_score == opp_score:
        return f"{venue}平局"
    else:
        return f"{venue}大负" if diff >= 3 else f"{venue}小负"

def score_to_esports_result(score_str):
    score_str = score_str.strip()
    if not re.match(r'^\d+-\d+$', score_str):
        return None
    try:
        a, b = map(int, score_str.split('-'))
    except:
        return None
    if a == b:   key = f"{a}-{b} 平"
    elif a > b:  key = f"{a}-{b} 赢"
    else:        key = f"{a}-{b} 输"
    return key if key in score_weights_esports else None

# ─── 甜蜜点检查 ───────────────────────────────────────────────────────────────
def check_football_spots(h_wp, a_wp, h_ev, a_ev):
    spots = []

    # ── F1强化版：WP≥50% + EV -40~-20（逐场验证 11场/90.9%）────────────────
    if h_wp >= 50 and -40 <= h_ev <= -20:
        spots.append("F1主")
    # ── F1标准版：WP≥40% + EV -40~-20（原始条件 24场/75%）──────────────────
    elif h_wp >= 40 and -40 <= h_ev <= -20:
        spots.append("F1主")
    # ── F2：WP 30~39% + EV -40~-20（维持原条件）────────────────────────────
    elif h_wp >= 30 and -40 <= h_ev <= -20:
        spots.append("F2主")

    if a_wp >= 50 and -40 <= a_ev <= -20:
        spots.append("F1客")
    elif a_wp >= 40 and -40 <= a_ev <= -20:
        spots.append("F1客")
    elif a_wp >= 30 and -40 <= a_ev <= -20:
        spots.append("F2客")

    # ── F3：两队总WP ≥ 110%（维持原条件）────────────────────────────────────
    if h_wp + a_wp >= 110:
        spots.append(f"F3({h_wp + a_wp:.0f}%)")

    # ── W1↩ 足球（逐场验证修正方向）─────────────────────────────────────────
    # 客队EV > 60 → 反买押主队赢（42场/66.7%）
    if a_ev > 60:
        spots.append(f"W1↩主({a_ev:.0f})")
    # 主队EV > 100 → 反买押客队赢（11场/54.5%，仅参考）
    if h_ev > 100:
        spots.append(f"W1↩客({h_ev:.0f})")

    # ── W2↩：EV=-100 反买（保留参考）────────────────────────────────────────
    if h_ev <= -99.9 and 10 <= a_wp <= 29:
        spots.append(f"W2↩客({a_wp:.0f}%)")
    if a_ev <= -99.9 and 10 <= h_wp <= 29:
        spots.append(f"W2↩主({h_wp:.0f}%)")

    return spots


def check_esports_spots(h_wp, a_wp, h_ev, a_ev):
    spots = []
    diff_h = h_wp - a_wp
    diff_a = a_wp - h_wp

    # ── E1：WP≥60% + EV -50~0（放宽后 15场/80%）────────────────────────────
    if h_wp >= 60 and -50 <= h_ev <= 0:
        spots.append("E1主")
    if a_wp >= 60 and -50 <= a_ev <= 0:
        spots.append("E1客")

    # ── E2：WP≥55% + EV -50~-10（E1优先，放宽后 12场/83%）──────────────────
    if h_wp >= 55 and -50 <= h_ev <= -10 and not (h_wp >= 60 and -50 <= h_ev <= 0):
        spots.append("E2主")
    if a_wp >= 55 and -50 <= a_ev <= -10 and not (a_wp >= 60 and -50 <= a_ev <= 0):
        spots.append("E2客")

    # ── E3：WP≥50% + 差距≥10%（44场/75%）E3优先于E4 ────────────────────────
    e3_triggered = False
    if h_wp >= 50 and diff_h >= 10:
        spots.append(f"E3主(+{diff_h:.0f}%)")
        e3_triggered = True
    if a_wp >= 50 and diff_a >= 10:
        spots.append(f"E3客(+{diff_a:.0f}%)")
        e3_triggered = True

    # ── E4：低WP爆冷（E3不触发时才生效，10场/80%）──────────────────────────
    # 电竞无主客场，E3和E4方向相反会冲突，E3优先避免矛盾
    if not e3_triggered:
        low_wp  = min(h_wp, a_wp)
        high_wp = max(h_wp, a_wp)
        gap = high_wp - low_wp
        if 30 <= low_wp <= 49 and gap <= 20:
            if h_wp == low_wp and h_ev < 0:
                spots.append("E4主")
            elif a_wp == low_wp and a_ev < 0:
                spots.append("E4客")

    # ── W1↩ 电竞（逐场验证修正）────────────────────────────────────────────
    # 强队WP≥60% + EV负 + 差距≥15% → 押强队（9场/88.9%）已由E3覆盖
    # 主队EV > 40 → 反买押客队赢
    if h_ev > 40:
        spots.append(f"W1↩客({h_ev:.0f})")
    # 客队EV > 30 → 反买押主队赢
    if a_ev > 30:
        spots.append(f"W1↩主({a_ev:.0f})")

    # ── W2↩：EV=-100 反买（保留参考）────────────────────────────────────────
    if h_ev <= -99.9 and 10 <= a_wp <= 29:
        spots.append(f"W2↩客({a_wp:.0f}%)")
    if a_ev <= -99.9 and 10 <= h_wp <= 29:
        spots.append(f"W2↩主({h_wp:.0f}%)")

    return spots


# ─── 分级注额资金管理 ────────────────────────────────────────────────────────
def get_spot_winrate(spot):
    """根据甜蜜点代号返回历史胜率"""
    if "F1精准" in spot: return 0.91
    if "F1" in spot:     return 0.75
    if "F2" in spot:     return 0.53
    if "F3" in spot:     return 0.65
    if "E1" in spot:     return 0.84
    if "E2" in spot:     return 0.83
    if "E3" in spot:     return 0.75
    if "E4" in spot:     return 0.80
    if "W1↩" in spot:    return 0.67
    if "W2↩" in spot:    return 0.50
    return 0.60

def tiered_bet(odds):
    """
    分级注额：根据赔率决定下注额
    赔率越高 → 下注越多（跟凯利方向一致）
    """
    if odds < 1.50:   return 30
    elif odds < 1.80: return 50
    elif odds < 2.21: return 70
    else:             return 100

def kelly_suggestion(spots, odds, bankroll):
    """
    根据甜蜜点和赔率，返回建议下注额和说明
    使用分级注额策略
    """
    if not spots:
        return None

    best_wr = max(get_spot_winrate(s) for s in spots)
    bet = tiered_bet(odds)
    break_even = 1 / odds * 100
    expected_positive = best_wr * 100 > break_even

    # 赔率档位说明
    if odds < 1.50:   tier = "低赔率档（<1.50）"
    elif odds < 1.80: tier = "标准档（1.50~1.79）"
    elif odds < 2.21: tier = "高赔率档（1.80~2.20）"
    else:             tier = "超高赔率档（>2.20）"

    return {
        "胜率":     f"{best_wr*100:.0f}%",
        "建议下注": bet,
        "盈亏平衡": f"{break_even:.1f}%",
        "正期望":   expected_positive,
        "档位":     tier,
    }


# ─── 甜蜜点显示标签 ───────────────────────────────────────────────────────────
SPOT_LABELS = {
    "F1主": "🎯 F1 足球甜蜜点 主队（历史75-91%）",
    "F1客": "🎯 F1 足球甜蜜点 客队（历史75-91%）",
    "F2主": "🎯 F2 足球次级 主队（历史40%）",
    "F2客": "🎯 F2 足球次级 客队（历史40%）",
    "E1主": "🎯 E1 电竞甜蜜点 主队（历史80%）",
    "E1客": "🎯 E1 电竞甜蜜点 客队（历史80%）",
    "E2主": "🎯 E2 电竞次级 主队（历史83%）",
    "E2客": "🎯 E2 电竞次级 客队（历史83%）",
    "E4主": "🎯 E4 电竞低WP爆冷 主队（历史86%）",
    "E4客": "🎯 E4 电竞低WP爆冷 客队（历史86%）",
}

def spot_display(spot):
    if spot in SPOT_LABELS:
        return SPOT_LABELS[spot]
    if spot.startswith("F3"):
        return f"🎯 F3 足球双强 {spot}（历史65%）"
    if spot.startswith("E3"):
        return f"🎯 E3 电竞差距 {spot}（历史85%）"
    if "W1↩" in spot:
        return f"🔄 {spot}（反买！历史67-74%）"
    if "W2↩" in spot:
        return f"🔄 W2 {spot} EV=-100反买（参考）"
    return spot


# ─── 甜蜜点统计 ───────────────────────────────────────────────────────────────
def calc_sweet_spot_stats(df):
    sweet_df = df[df["甜蜜点"].astype(str).str.strip() != ""].copy()
    if sweet_df.empty:
        return None
    if "投注结果" not in sweet_df.columns:
        sweet_df["投注结果"] = ""

    spot_types = [
        ("F1",  "F1 足球甜蜜点"),
        ("F2",  "F2 足球次级"),
        ("F3",  "F3 足球双强"),
        ("E1",  "E1 电竞甜蜜点"),
        ("E2",  "E2 电竞次级"),
        ("E3",  "E3 电竞差距"),
        ("E4",  "E4 电竞低WP爆冷"),
        ("W1",  "W1 反买"),
        ("W2",  "W2 反买(EV=-100)"),
    ]

    results = []
    for key, label in spot_types:
        subset = sweet_df[sweet_df["甜蜜点"].astype(str).str.contains(key, na=False)]
        if subset.empty:
            continue
        total = len(subset)
        wins = losses = refunds = 0
        for _, row in subset.iterrows():
            br = str(row.get("投注结果", "")).strip()
            if br in ["✅ 赢", "赢"]:         wins    += 1
            elif br in ["❌ 输", "输"]:        losses  += 1
            elif br in ["🔄 退水", "退水"]:    refunds += 1
        settled  = wins + losses + refunds
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else None
        results.append({
            "甜蜜点": label, "总记录": total, "已结算": settled,
            "赢": wins, "输": losses, "退水": refunds,
            "命中率": f"{win_rate:.1f}%" if win_rate is not None else "—",
        })
    return results


# ══════════════════════════════════════════════════════════════════════════════
# App
# ══════════════════════════════════════════════════════════════════════════════
st.title("运动期望值分析器 🏆")
tab1, tab2, tab3, tab4 = st.tabs(["❌ 电竞", "⚽ 足球", "🏀 篮球", "📋 记录"])


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
        spots = check_esports_spots(r["h_wr"] * 100, r["a_wr"] * 100, r["h_ev"], r["a_ev"])
        sweet_combined = " | ".join(spots)  # 提前定义，保存按钮可以用
        for s in spots:
            if "W1" in s or "W2" in s: st.error(spot_display(s))
            else:                       st.success(spot_display(s))

        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"])
            st.metric("加权胜率 (WP)",      f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            if not spots:
                if r["h_ev"] > 0: st.success("✅ 正期望值")
                else:             st.error("❌ 负期望值")
        with col6:
            st.subheader(r["a_name"])
            st.metric("加权胜率 (WP)",      f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            if not spots:
                if r["a_ev"] > 0: st.success("✅ 正期望值")
                else:             st.error("❌ 负期望值")

        st.divider()
        # ── 分级注额建议 ──────────────────────────────────────────────
        if spots:
            st.subheader("💰 分级注额建议")

            bet_on_home = any("主" in s and "W1↩" not in s for s in spots)
            bet_on_away = any("客" in s and "W1↩" not in s for s in spots)
            w1_home = any("W1↩主" in s for s in spots)
            w1_away = any("W1↩客" in s for s in spots)

            if bet_on_home or w1_home:
                bet_odds = r["h_odds"]
                bet_dir  = r["h_name"]
            elif bet_on_away or w1_away:
                bet_odds = r["a_odds"]
                bet_dir  = r["a_name"]
            else:
                bet_odds = min(r["h_odds"], r["a_odds"])
                bet_dir  = "待定"

            kelly = kelly_suggestion(spots, bet_odds, 1000)
            if kelly:
                ck1, ck2, ck3 = st.columns(3)
                ck1.metric("建议下注",  f"{kelly['建议下注']}块")
                ck2.metric("历史胜率",  kelly["胜率"])
                ck3.metric("盈亏平衡",  kelly["盈亏平衡"])
                if kelly["正期望"]:
                    st.success(f"✅ 正期望！建议押 **{bet_dir}**，下注 **{kelly['建议下注']}块**（{kelly['档位']}）")
                else:
                    st.warning(f"⚠️ 赔率太低，期望值为负，谨慎下注！")

        st.divider()
        if st.button("💾 保存记录", key="e_save"):
            record = {
                "日期": str(date.today()), "运动": "电竞",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": "N/A",
                "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": "N/A",
                "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": sweet_combined, "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: 足球
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("足球期望值分析器")
    col1, col2 = st.columns(2)
    with col1:
        f_home_name = st.text_input("主队名字", "主队", key="f_home_name")
    with col2:
        f_away_name = st.text_input("客队名字", "客队", key="f_away_name")

    col3, col4, col5, col6 = st.columns([2, 2, 2, 2])
    with col3: f_home_odds = st.number_input("主队赔率", min_value=1.01, value=2.0, step=0.01, key="f_home_odds")
    with col4: f_draw_odds = st.number_input("平局赔率", min_value=1.01, value=3.0, step=0.01, key="f_draw_odds")
    with col5: f_away_odds = st.number_input("客队赔率", min_value=1.01, value=3.5, step=0.01, key="f_away_odds")
    with col6: venue = st.selectbox("场地", ["主队主场", "客队主场", "中立场"], key="f_venue")

    st.divider()
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
            win_w   += info["is_win"]  * final_weight
            draw_w  += info["is_draw"] * final_weight * 0.5
        win_rate  = win_w  / total_w if total_w > 0 else 0
        draw_rate = draw_w / total_w if total_w > 0 else 0
        return win_rate, draw_rate

    st.subheader("近期比赛记录")
    st.caption("填实际比分（主队得分-客队得分）+ 选该队是主场还是客场 | 大胜/大负 = 差距≥3球")

    valid_keys  = list(football_results.keys())
    col_h2, col_a2 = st.columns(2)
    f_home_vars, f_away_vars = [], []

    with col_h2:
        st.markdown(f"**🏠 {f_home_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            c1, c2 = st.columns([2, 1])
            with c1:
                score_input = st.text_input(label, value="", placeholder="主队-客队 如 2-1", key=f"fh_{i}")
            with c2:
                venue_sel = st.selectbox("", ["主场🏠", "客场✈️"], key=f"fh_venue_{i}", label_visibility="collapsed")
            result = score_to_football_result(score_input, "主场" in venue_sel)
            if result and result in valid_keys:
                st.caption(f"→ {result_emoji_football.get(result, result)}")
                f_home_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误，请填如 2-1")
                f_home_vars.append("🏠 主场小胜")

    with col_a2:
        st.markdown(f"**✈️ {f_away_name}**")
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            c1, c2 = st.columns([2, 1])
            with c1:
                score_input = st.text_input(label, value="", placeholder="主队-客队 如 2-1", key=f"fa_{i}")
            with c2:
                venue_sel = st.selectbox("", ["主场🏠", "客场✈️"], index=1, key=f"fa_venue_{i}", label_visibility="collapsed")
            result = score_to_football_result(score_input, "主场" in venue_sel)
            if result and result in valid_keys:
                st.caption(f"→ {result_emoji_football.get(result, result)}")
                f_away_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误，请填如 2-1")
                f_away_vars.append("✈️ 客场小胜")

    if st.button("⚡ 计算", key="f_calc", type="primary"):
        h_wr, h_dr = calc_football_winrate(f_home_vars, True,  venue)
        a_wr, a_dr = calc_football_winrate(f_away_vars, False, venue)
        draw_prob  = (h_dr + a_dr) / 2
        h_ev = (h_wr * (f_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (f_away_odds - 1) * 100) - ((1 - a_wr) * 100)
        d_ev = (draw_prob * (f_draw_odds - 1) * 100) - ((1 - draw_prob) * 100)
        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "draw_prob": draw_prob,
            "h_ev": h_ev, "a_ev": a_ev, "d_ev": d_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds, "d_odds": f_draw_odds,
            "h_name": f_home_name, "a_name": f_away_name,
        }

    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()
        spots = check_football_spots(r["h_wr"] * 100, r["a_wr"] * 100, r["h_ev"], r["a_ev"])
        sweet_val = " | ".join(spots)  # 提前定义，保存按钮可以用
        for s in spots:
            if "W1" in s or "W2" in s: st.error(spot_display(s))
            else:                       st.success(spot_display(s))

        col9, col10, col11 = st.columns(3)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率 (WP)",      f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            if not spots:
                if r["h_ev"] > 0: st.success("✅ 正期望值")
                else:             st.error("❌ 负期望值")
        with col10:
            st.subheader("平局")
            st.metric("平局概率",            f"{r['draw_prob']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['d_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['d_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['draw_prob'] - 1/r['d_odds']:+.1%}")
            if r["d_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")
        with col11:
            st.subheader(f_away_name)
            st.metric("加权胜率 (WP)",      f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            if not spots:
                if r["a_ev"] > 0: st.success("✅ 正期望值")
                else:             st.error("❌ 负期望值")

        st.divider()
        # ── 分级注额建议 ──────────────────────────────────────────────
        if spots:
            st.subheader("💰 分级注额建议")

            is_draw_spot = any("F2" in s for s in spots)
            is_home_spot = any("主" in s and "W1↩" not in s and "F2" not in s for s in spots)
            is_away_spot = any("客" in s and "W1↩" not in s and "F2" not in s for s in spots)
            w1_home = any("W1↩主" in s for s in spots)
            w1_away = any("W1↩客" in s for s in spots)

            if is_draw_spot:
                bet_odds = r["d_odds"]
                bet_dir  = "平局"
            elif is_home_spot or w1_home:
                bet_odds = r["h_odds"]
                bet_dir  = r["h_name"]
            elif is_away_spot or w1_away:
                bet_odds = r["a_odds"]
                bet_dir  = r["a_name"]
            else:
                bet_odds = r["h_odds"]
                bet_dir  = r["h_name"]

            kelly = kelly_suggestion(spots, bet_odds, 1000)
            if kelly:
                fk1, fk2, fk3 = st.columns(3)
                fk1.metric("建议下注",  f"{kelly['建议下注']}块")
                fk2.metric("历史胜率",  kelly["胜率"])
                fk3.metric("盈亏平衡",  kelly["盈亏平衡"])
                if kelly["正期望"]:
                    st.success(f"✅ 正期望！建议押 **{bet_dir}**，下注 **{kelly['建议下注']}块**（{kelly['档位']}）")
                else:
                    st.warning(f"⚠️ 赔率太低，期望值为负，谨慎下注！")

        st.divider()
        if st.button("💾 保存记录", key="f_save"):
            record = {
                "日期": str(date.today()), "运动": "足球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}",
                "平局加权胜率": f"{r['draw_prob']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}",
                "平局期望值": f"{r['d_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}",
                "平局隐含概率": f"{1/r['d_odds']:.1%}",
                "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}",
                "平局优势差距": f"{r['draw_prob'] - 1/r['d_odds']:+.1%}",
                "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": sweet_val, "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")


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
        "大胜 (+15以上)": 1.0,
        "小胜 (+1到+14)": 0.7,
        "小负 (-1到-14)": 0.4,
        "大负 (-15以上)": 0.2,
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
            base    = 1.0 - (i * 0.1)
            total_w += base
            win_w   += (1 if "胜" in v else 0) * weights[v] * base
        return win_w / total_w if total_w > 0 else 0

    if st.button("计算", key="b_calc", type="primary"):
        h_wr = b_winrate(b_home_vars, score_weights_b)
        a_wr = b_winrate(b_away_vars, score_weights_b)
        h_ev = (h_wr * (b_home_odds - 1) * 100) - ((1 - h_wr) * 100)
        a_ev = (a_wr * (b_away_odds - 1) * 100) - ((1 - a_wr) * 100)
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
            st.metric("加权胜率 (WP)",      f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            if r["h_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率 (WP)",      f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",        f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",            f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考",  f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
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
                "比赛结果": "", "甜蜜点": "", "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: 记录
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("📋 历史记录")
    if st.button("🔄 刷新记录", key="refresh"):
        st.rerun()

    df = load_from_sheet()
    if df.empty:
        st.info("还没有记录！")
    else:
        col1, col2 = st.columns(2)
        with col1: st.metric("总记录", len(df))
        with col2: st.metric("今日记录", len(df[df["日期"] == str(date.today())]))

        st.divider()
        st.subheader("🎯 甜蜜点统计")
        stats = calc_sweet_spot_stats(df)
        if stats:
            for s in stats:
                with st.expander(f"{s['甜蜜点']}　命中率 {s['命中率']}　已结算 {s['已结算']}/{s['总记录']}"):
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("总记录",  s["总记录"])
                    c2.metric("已结算",  s["已结算"])
                    c3.metric("赢",      s["赢"])
                    c4.metric("输",      s["输"])
                    c5.metric("命中率",  s["命中率"])
        else:
            st.info("还没有甜蜜点记录。")

        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ 下载记录", csv, "records.csv", "text/csv")

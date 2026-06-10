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

# ─── 甜蜜点检查 ───────────────────────────────────────────────────────────────
def check_football_spots(h_wp, a_wp, h_ev, a_ev, h_impl=None, a_impl=None):
    spots = []

    # ── F★ 精准：WP≥55% + EV -50~-10（15场/86.7%）──────────────────────────
    if h_wp >= 55 and -50 <= h_ev <= -10:
        spots.append("F★主")
    # ── F1：WP≥50% + EV -50~-20（16场/87.5%）───────────────────────────────
    elif h_wp >= 50 and -50 <= h_ev <= -20:
        spots.append("F1主")

    if a_wp >= 55 and -50 <= a_ev <= -10:
        spots.append("F★客")
    elif a_wp >= 50 and -50 <= a_ev <= -20:
        spots.append("F1客")

    # ── F2：WP 30~45% + EV -50~-15 → 押胜平（43场/83.7%）────────────────
    # 赢+平=83.7%  纯平局率~34%，平局赔率高时可直接押平
    if 30 <= h_wp <= 45 and -50 <= h_ev <= -15 and "F★主" not in spots and "F1主" not in spots:
        spots.append("F2主")
    if 30 <= a_wp <= 45 and -50 <= a_ev <= -15 and "F★客" not in spots and "F1客" not in spots:
        spots.append("F2客")

    # ── F4：WP差距<10% + 隐含概率差距>30%（15场/73%）────────────────────────
    if h_impl is not None and a_impl is not None:
        wp_gap   = abs(h_wp - a_wp)
        impl_gap = abs(h_impl - a_impl)
        if wp_gap < 10 and impl_gap > 30:
            if h_impl > a_impl: spots.append("F4主")
            else:               spots.append("F4客")

    # ── W1↩ 足球逆向：客队EV>200 → 押主队（14场/79%）───────────────────────
    if a_ev > 200:
        spots.append(f"W1↩主({a_ev:.0f})")

    # ── FW↩ 冲突处理：F★/F1/F4 + W1↩ 同时触发 → 改买弱队吃球 ──────────────
    has_strong = any(s in spots for s in ["F★主", "F★客", "F1主", "F1客", "F4主", "F4客"])
    has_w1     = any("W1↩" in s for s in spots)
    if has_strong and has_w1:
        # 找出是哪队触发W1↩，弱队就是被逆买的那队
        w1_spots = [s for s in spots if "W1↩" in s]
        fw_dir   = "主" if any("W1↩主" in s for s in w1_spots) else "客"
        # 移除冲突信号，换成FW↩
        spots = [s for s in spots if "F★" not in s and "F1" not in s and "F4" not in s and "W1↩" not in s]
        spots.append(f"FW↩{fw_dir}({a_ev:.0f})")

    return spots


def check_esports_spots(h_wp, a_wp, h_ev, a_ev):
    spots = []
    diff_h = h_wp - a_wp
    diff_a = a_wp - h_wp

    # ── E3主 最强：WP≥50% + 差距≥8%（放宽触发）────────────────────────────
    # 数据最多最稳！WP高且差距大 = 强队优势明显
    e3 = False
    if h_wp >= 50 and diff_h >= 8:
        spots.append(f"E3主(+{diff_h:.0f}%)")
        e3 = True

    # ── E1：WP≥60% + EV -40~0（15场/80%，E3优先）───────────────────────────
    if not e3:
        if h_wp >= 60 and -40 <= h_ev <= 0:
            spots.append("E1主")
        if a_wp >= 60 and -40 <= a_ev <= 0:
            spots.append("E1客")

    # ── E2：WP≥55% + EV -40~-10（E3/E1优先）────────────────────────────────
    if not any("E3" in s or "E1" in s for s in spots):
        if h_wp >= 55 and -40 <= h_ev <= -10:
            spots.append("E2主")
        if a_wp >= 55 and -40 <= a_ev <= -10:
            spots.append("E2客")

    # ── EX 逆向：WP差距<10% + EV差距>50 → 押低EV方（10场/80%）─────────────
    # 逆向逻辑：两队实力接近，但庄家偷偷偏向低赔率那队
    wp_diff = abs(h_wp - a_wp)
    ev_diff = abs(h_ev - a_ev)
    if wp_diff < 10 and ev_diff > 50 and not spots:
        if h_ev < a_ev:  # 主队EV更低（赔率低）→ 押主队
            spots.append(f"EX主(EV差{ev_diff:.0f})")
        else:             # 客队EV更低（赔率低）→ 押客队
            spots.append(f"EX客(EV差{ev_diff:.0f})")

    # ── W1↩ 电竞逆向：主EV>60 → 反买押客队（放宽触发）────────────────────────
    if h_ev > 60:
        spots.append(f"W1↩客({h_ev:.0f})")

    return spots


# ─── 甜蜜点显示标签 ───────────────────────────────────────────────────────────
SPOT_LABELS = {
    "F★主": "🏆 F★ 足球精准甜蜜点 主队（15场/87%）",
    "F★客": "🏆 F★ 足球精准甜蜜点 客队（15场/87%）",
    "F1主": "🎯 F1 足球甜蜜点 主队（16场/87.5%）",
    "F1客": "🎯 F1 足球甜蜜点 客队（16场/87.5%）",
    "F2主": "🎯 F2 足球胜平 主队 → 押胜平！（43场/83.7%）",
    "F2客": "🎯 F2 足球胜平 客队 → 押胜平！（43场/83.7%）",
    "F4主": "🎯 F4 足球庄家信号 主队（15场/73%）",
    "F4客": "🎯 F4 足球庄家信号 客队（15场/73%）",
    "E1主": "🎯 E1 电竞甜蜜点 主队（15场/80%）",
    "E1客": "🎯 E1 电竞甜蜜点 客队（15场/80%）",
    "E2主": "🎯 E2 电竞次级 主队（历史83%）",
    "E2客": "🎯 E2 电竞次级 客队（历史83%）",
}

def spot_display(spot):
    if spot in SPOT_LABELS: return SPOT_LABELS[spot]
    if spot.startswith("E3主"): return f"🏆 E3 电竞最强差距 {spot}（20场/90%）"
    if spot.startswith("E3客"): return f"⚠️ E3客 电竞差距 {spot}（12场/67%，谨慎）"
    if spot.startswith("EX主"): return f"🔄 EX 电竞逆向 {spot} → 押主队（10场/80%）"
    if spot.startswith("EX客"): return f"🔄 EX 电竞逆向 {spot} → 押客队（10场/80%）"
    if spot.startswith("FW↩主"): return f"🔄 FW↩ 信号冲突 → 买弱队吃球！押主队（逆向）{spot}"
    if spot.startswith("FW↩客"): return f"🔄 FW↩ 信号冲突 → 买弱队吃球！押客队（逆向）{spot}"
    if "W1↩" in spot:           return f"🔄 {spot}（逆向反买！历史79%）"
    return spot

# ─── 资金管理 ─────────────────────────────────────────────────────────────────
def get_spot_winrate(spot):
    if "F★" in spot:  return 0.87
    if "F1" in spot:  return 0.875
    if "F2" in spot:  return 0.837
    if "F4" in spot:  return 0.73
    if "FW↩" in spot: return 0.75
    if "E3主" in spot: return 0.90
    if "E3客" in spot: return 0.67
    if "E1" in spot:  return 0.80
    if "E2" in spot:  return 0.83
    if "EX" in spot:  return 0.80
    if "W1↩" in spot: return 0.79
    if "BW↩" in spot: return 0.83
    if "B8" in spot:  return 0.67
    return 0.65

def tiered_bet(odds):
    if odds < 1.50:   return 30
    elif odds < 1.80: return 50
    elif odds < 2.21: return 70
    else:             return 100

def kelly_suggestion(spots, odds, bankroll=1000):
    if not spots: return None
    best_wr = max(get_spot_winrate(s) for s in spots)
    bet = tiered_bet(odds)
    break_even = 1 / odds * 100
    expected_positive = best_wr * 100 > break_even
    if odds < 1.50:   tier = "低赔率档（<1.50）"
    elif odds < 1.80: tier = "标准档（1.50~1.79）"
    elif odds < 2.21: tier = "高赔率档（1.80~2.20）"
    else:             tier = "超高赔率档（>2.20）"
    return {
        "胜率": f"{best_wr*100:.0f}%",
        "建议下注": bet,
        "盈亏平衡": f"{break_even:.1f}%",
        "正期望": expected_positive,
        "档位": tier,
    }

# ─── 甜蜜点统计 ───────────────────────────────────────────────────────────────
def calc_sweet_spot_stats(df):
    sweet_df = df[df["甜蜜点"].astype(str).str.strip() != ""].copy()
    if sweet_df.empty: return None
    spot_types = [
        ("F★", "F★ 足球精准"), ("F1", "F1 足球甜蜜点"),
        ("F2", "F2 足球胜平"), ("F4", "F4 足球庄家信号"),
        ("FW↩", "FW↩ 足球逆向吃球"),
        ("E★", "E★ 电竞最强"), ("E1", "E1 电竞精准"),
        ("E2", "E2 电竞甜蜜点"), ("EX", "EX 电竞逆向"),
        ("W1", "W1 逆向反买"),
        ("B8", "B8 棒球强队"),
        ("BW↩", "BW↩ 棒球逆向"),
    ]
    results = []
    for key, label in spot_types:
        subset = sweet_df[sweet_df["甜蜜点"].astype(str).str.contains(key, na=False)]
        if subset.empty: continue
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
        spots = check_esports_spots(r["h_wr"]*100, r["a_wr"]*100, r["h_ev"], r["a_ev"])
        sweet_combined = " | ".join(spots)
        for s in spots:
            if "W1↩" in s or "EX" in s: st.warning(spot_display(s))
            elif "E★" in s:              st.success(f"🏆 {spot_display(s)}")
            else:                         st.success(spot_display(s))

        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"])
            st.metric("加权胜率 (WP)",     f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",       f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",           f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            if not spots:
                if r["h_ev"] > 0: st.success("✅ 正期望值")
                else:             st.error("❌ 负期望值")
        with col6:
            st.subheader(r["a_name"])
            st.metric("加权胜率 (WP)",     f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",       f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",           f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            if not spots:
                if r["a_ev"] > 0: st.success("✅ 正期望值")
                else:             st.error("❌ 负期望值")

        st.divider()
        if spots:
            st.subheader("💰 分级注额建议")
            bet_on_home = any(("主" in s or "E★主" in s or "E1主" in s or "E2主" in s or "EX主" in s) and "W1↩" not in s for s in spots)
            w1_away = any("W1↩客" in s for s in spots)
            if bet_on_home and not w1_away:
                bet_odds = r["h_odds"]; bet_dir = r["h_name"]
            else:
                bet_odds = r["a_odds"]; bet_dir = r["a_name"]
            kelly = kelly_suggestion(spots, bet_odds)
            if kelly:
                ck1, ck2, ck3 = st.columns(3)
                ck1.metric("建议下注", f"{kelly['建议下注']}块")
                ck2.metric("历史胜率", kelly["胜率"])
                ck3.metric("盈亏平衡", kelly["盈亏平衡"])
                if kelly["正期望"]:
                    st.success(f"✅ 建议押 **{bet_dir}**，下注 **{kelly['建议下注']}块**（{kelly['档位']}）")
                else:
                    st.warning("⚠️ 赔率太低，期望值为负，谨慎下注！")

        st.divider()
        if st.button("💾 保存记录", key="e_save"):
            bet_on_home = any(("主" in s or "E★主" in s or "E1主" in s or "E2主" in s or "EX主" in s) and "W1↩" not in s for s in spots)
            w1_away = any("W1↩客" in s for s in spots)
            if bet_on_home and not w1_away:
                save_odds = r["h_odds"]; save_dir = r["h_name"]
            else:
                save_odds = r["a_odds"]; save_dir = r["a_name"]
            k = kelly_suggestion(spots, save_odds)
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
                "比赛结果": "", "甜蜜点": sweet_combined,
                "建议下注": f"{k['建议下注']}块" if k else "—",
                "押注方向": save_dir, "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

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
        spots = check_football_spots(r["h_wr"]*100, r["a_wr"]*100, r["h_ev"], r["a_ev"], h_impl, a_impl)
        sweet_val = " | ".join(spots)

        for s in spots:
            if "W1↩" in s or "FW↩" in s: st.warning(spot_display(s))
            elif "F★" in s: st.success(f"🏆 {spot_display(s)}")
            elif "F2" in s: st.info(spot_display(s))
            else:            st.success(spot_display(s))

        col9, col10, col11 = st.columns(3)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率 (WP)",     f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",       f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",           f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
        with col10:
            st.subheader("平局")
            st.metric("平局概率",           f"{r['draw_prob']:.1%}")
            st.metric("期望值 (EV)",       f"RM{r['d_ev']:.2f}")
            st.metric("隐含概率",           f"{1/r['d_odds']:.1%}")
            if r["d_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")
        with col11:
            st.subheader(f_away_name)
            st.metric("加权胜率 (WP)",     f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",       f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",           f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")

        # F2特别提示
        if any("F2" in s for s in spots):
            st.info("💡 F2触发：建议押**胜平**（赢或平都算赢）。")
        if any("FO" in s for s in spots):
            st.info("💡 FO触发：两队实力相当，建议买**大球>2.5**！（78%，赔率~1.85）")
        if any("FC大球" in s for s in spots):
            st.info("💡 FC触发：客队EV虚高，主队大胜概率高，建议买**大球>2.5**！（73%）")
        if any("FC-BTTS" in s for s in spots):
            st.info("💡 FC触发：客队EV虚高，双方互攻，建议买**BTTS双方都进球**！（73%）")

        st.divider()
        if spots:
            st.subheader("💰 分级注额建议")
            is_f2   = any("F2" in s for s in spots)
            is_fo   = any("FO" in s or "FC" in s for s in spots)
            is_home = any("主" in s and "W1↩" not in s and "FW↩" not in s for s in spots)
            is_away = any("客" in s and "W1↩" not in s and "FW↩" not in s for s in spots)
            w1_home = any("W1↩主" in s for s in spots)
            fw_home = any("FW↩主" in s for s in spots)
            fw_away = any("FW↩客" in s for s in spots)

            if fw_home or fw_away:
                if fw_home:
                    bet_odds = r["h_odds"]; bet_dir = f"{r['h_name']}（吃球）"
                else:
                    bet_odds = r["a_odds"]; bet_dir = f"{r['a_name']}（吃球）"
            elif is_fo:
                bet_odds = 1.85; bet_dir = "大球>2.5 或 BTTS（请查赔率）"
            elif is_f2:
                if any("F2" in s and "主" in s for s in spots):
                    bet_odds = r["h_odds"]; bet_dir = f"{r['h_name']}（胜平）"
                else:
                    bet_odds = r["a_odds"]; bet_dir = f"{r['a_name']}（胜平）"
            elif is_home or w1_home:
                bet_odds = r["h_odds"]; bet_dir = r["h_name"]
            elif is_away:
                bet_odds = r["a_odds"]; bet_dir = r["a_name"]
            else:
                bet_odds = r["h_odds"]; bet_dir = "待定"

            kelly = kelly_suggestion(spots, bet_odds)
            if kelly:
                fk1, fk2, fk3 = st.columns(3)
                fk1.metric("建议下注", f"{kelly['建议下注']}块")
                fk2.metric("历史胜率", kelly["胜率"])
                fk3.metric("盈亏平衡", kelly["盈亏平衡"])
                if kelly["正期望"]:
                    st.success(f"✅ 建议押 **{bet_dir}**，下注 **{kelly['建议下注']}块**（{kelly['档位']}）")
                else:
                    st.warning("⚠️ 赔率太低，期望值为负，谨慎下注！")

        st.divider()
        if st.button("💾 保存记录", key="f_save"):
            is_f2 = any("F2" in s for s in spots)
            is_home = any("主" in s and "W1↩" not in s for s in spots)
            w1_home = any("W1↩主" in s for s in spots)
            if is_f2:
                if any("F2主" in s for s in spots):
                    save_odds = r["h_odds"]; save_dir = f"{r['h_name']}胜平"
                else:
                    save_odds = r["a_odds"]; save_dir = f"{r['a_name']}胜平"
            elif is_home or w1_home:
                save_odds = r["h_odds"]; save_dir = r["h_name"]
            else:
                save_odds = r["a_odds"]; save_dir = r["a_name"]
            k = kelly_suggestion(spots, save_odds)
            record = {
                "日期": str(date.today()), "运动": "足球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": f"{r['draw_prob']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": f"{r['d_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": f"{1/r['d_odds']:.1%}",
                "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}",
                "平局优势差距": f"{r['draw_prob'] - 1/r['d_odds']:+.1%}",
                "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": sweet_val,
                "建议下注": f"{k['建议下注']}块" if k else "—",
                "押注方向": save_dir, "投注结果": "",
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

        col7, col8 = st.columns(2)
        with col7:
            st.subheader(f"🏠 {r['h_name']}")
            st.metric("综合胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率",       f"{1/r['h_odds']:.1%}")
            st.metric("优势差距",       f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            if r["h_p_wr"] is not None:
                pw = pitcher_weight(r["h_p_games"])
                st.caption(f"投手胜率 {r['h_p_wr']:.0%}（{r['h_p_games']}场，权重{pw:.0%}）")
            if r["h_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")

        with col8:
            st.subheader(f"✈️ {r['a_name']}")
            st.metric("综合胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)",   f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率",       f"{1/r['a_odds']:.1%}")
            st.metric("优势差距",       f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            if r["a_p_wr"] is not None:
                pw = pitcher_weight(r["a_p_games"])
                st.caption(f"投手胜率 {r['a_p_wr']:.0%}（{r['a_p_games']}场，权重{pw:.0%}）")
            if r["a_ev"] > 0: st.success("✅ 正期望值")
            else:             st.error("❌ 负期望值")

        # ── 棒球甜蜜点检测 ────────────────────────────────────────────────────
        st.divider()
        bb_spots = []
        h_impl = 1 / r["h_odds"] * 100
        a_impl = 1 / r["a_odds"] * 100

        # B8：WP≥75% + EV≥+20 → 押高WP队
        if r["h_wr"] * 100 >= 75 and r["h_ev"] >= 20:
            bb_spots.append(f"B8主({r['h_wr']:.0%})")
        if r["a_wr"] * 100 >= 75 and r["a_ev"] >= 20:
            bb_spots.append(f"B8客({r['a_wr']:.0%})")

        # BW↩：客队EV≥+40 + 主队WP≥45% → 逆向押主队
        if r["a_ev"] >= 40 and r["h_wr"] * 100 >= 45:
            bb_spots.append(f"BW↩主(客EV{r['a_ev']:.0f})")

        if bb_spots:
            st.subheader("🎯 棒球甜蜜点触发！")
            for s in bb_spots:
                if "BW↩" in s:
                    st.warning(f"🔄 {s} — 客队EV虚高，逆向押主队！（历史83%）")
                else:
                    st.success(f"⚾ {s} — 强队占优，押高WP队！（历史67%）")

            # 押注方向
            if any("BW↩主" in s for s in bb_spots):
                bb_bet_dir = r["h_name"]
                bb_bet_odds = r["h_odds"]
            elif any("B8主" in s for s in bb_spots):
                bb_bet_dir = r["h_name"]
                bb_bet_odds = r["h_odds"]
            elif any("B8客" in s for s in bb_spots):
                bb_bet_dir = r["a_name"]
                bb_bet_odds = r["a_odds"]
            else:
                bb_bet_dir = "待定"
                bb_bet_odds = r["h_odds"]

            # 简单Kelly建议
            spot_wr = 0.83 if any("BW↩" in s for s in bb_spots) else 0.67
            edge = spot_wr - (1 / bb_bet_odds)
            if edge > 0:
                kelly_frac = edge / (bb_bet_odds - 1)
                suggested = max(10, min(50, round(kelly_frac * 200 / 10) * 10))
                st.success(f"✅ 建议押 **{bb_bet_dir}**，下注约 **{suggested}块**（历史胜率{spot_wr:.0%}）")
        else:
            st.caption("⚾ 今日无棒球甜蜜点触发，仅记录数据")

        if st.button("💾 保存记录", key="bb_save"):
            bb_spot_str = " | ".join(bb_spots) if bb_spots else "—"
            if any("BW↩主" in s for s in bb_spots):
                save_dir = r["h_name"]; save_odds = r["h_odds"]
            elif any("B8主" in s for s in bb_spots):
                save_dir = r["h_name"]; save_odds = r["h_odds"]
            elif any("B8客" in s for s in bb_spots):
                save_dir = r["a_name"]; save_odds = r["a_odds"]
            else:
                save_dir = "—"; save_odds = r["h_odds"]
            spot_wr2 = 0.83 if any("BW↩" in s for s in bb_spots) else 0.67
            edge2 = spot_wr2 - (1 / save_odds) if bb_spots else 0
            if edge2 > 0:
                kelly_frac2 = edge2 / (save_odds - 1)
                save_amount = max(10, min(50, round(kelly_frac2 * 200 / 10) * 10))
            else:
                save_amount = "—"
            record = {
                "日期": str(date.today()), "运动": "棒球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A",
                "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": "N/A",
                "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": "N/A",
                "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": bb_spot_str,
                "建议下注": save_amount,
                "押注方向": save_dir, "投注结果": "",
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存！")

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

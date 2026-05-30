import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import pandas as pd
from datetime import date
import re

SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
HEADERS = ["日期","运动","主队","客队","主队加权胜率","平局加权胜率","客队加权胜率","主队期望值","平局期望值","客队期望值","主队隐含概率","平局隐含概率","客队隐含概率","主队优势差距","平局优势差距","客队优势差距","比赛结果","甜蜜点","投注结果","赔率","投注金额"]

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

# ─── Football Results Config ──────────────────────────────────────────────────

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
    "2-0 赢": 1.0,  "2-1 赢": 0.7,  "1-2 输": 0.4, "0-2 输": 0.2,
    "3-0 赢": 1.0,  "3-1 赢": 0.75, "3-2 赢": 0.6,
    "2-3 输": 0.4,  "1-3 输": 0.3,  "0-3 输": 0.2,
}

result_emoji_football = {
    "🏠 主场大胜": "🏆 主场大胜 (≥+3)", "🏠 主场小胜": "✅ 主场小胜 (+1/+2)",
    "🏠 主场平局": "➖ 主场平局",        "🏠 主场小负": "❌ 主场小负 (-1/-2)",
    "🏠 主场大负": "💀 主场大负 (≤-3)",  "✈️ 客场大胜": "🏆 客场大胜 (≥+3)",
    "✈️ 客场小胜": "✅ 客场小胜 (+1/+2)","✈️ 客场平局": "➖ 客场平局",
    "✈️ 客场小负": "❌ 客场小负 (-1/-2)","✈️ 客场大负": "💀 客场大负 (≤-3)",
}

result_emoji_esports = {
    "1-0 赢": "🏆 BO1 赢",   "0-1 输": "💀 BO1 输",  "1-1 平": "➖ BO2 平局",
    "2-0 赢": "🏆 2-0 大胜", "2-1 赢": "✅ 2-1 小胜","1-2 输": "❌ 1-2 小负",
    "0-2 输": "💀 0-2 大负", "3-0 赢": "🏆 3-0 大胜","3-1 赢": "✅ 3-1 小胜",
    "3-2 赢": "✅ 3-2 小胜", "2-3 输": "❌ 2-3 小负","1-3 输": "❌ 1-3 小负",
    "0-3 输": "💀 0-3 大负",
}

# ─── 比分转换函数 ─────────────────────────────────────────────────────────────

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
    if a == b:
        key = f"{a}-{b} 平"
    elif a > b:
        key = f"{a}-{b} 赢"
    else:
        key = f"{a}-{b} 输"
    return key if key in score_weights_esports else None

# ─── 甜蜜点检查 ───────────────────────────────────────────────────────────────

def check_sweet_spot_football(wp, ev):
    spots = []
    if wp >= 40 and -40 <= ev < -20:
        spots.append("🎯 弱甜蜜点！WP≥40% + EV -40~-20")
    if -61 <= ev <= -19:
        spots.append("🎯 新甜蜜点！EV -19~-61")
    return " | ".join(spots) if spots else None

def check_sweet_spot_over(h_wp, a_wp):
    total_wp = h_wp + a_wp
    if total_wp >= 90:
        return f"⚽ Over 2.5！主+客WP={total_wp:.1f}%≥90%（历史72.7%）"
    return None

def check_sweet_spot_esports(wp, ev, opp_wp):
    spots = []
    if -61 <= ev <= -19:
        spots.append("🎯 新甜蜜点！EV -19~-61")
    return spots

# ─── 甜蜜点统计函数 ───────────────────────────────────────────────────────────

def calc_sweet_spot_stats(df):
    sweet_df = df[df["甜蜜点"].astype(str).str.strip() != ""].copy()
    if sweet_df.empty:
        return None

    for col in ["投注结果", "赔率", "投注金额"]:
        if col not in sweet_df.columns:
            sweet_df[col] = ""

    results = []
    spot_types = ["🎯 弱甜蜜点", "🎯 新甜蜜点", "⚽ Over 2.5"]

    for spot in spot_types:
        subset = sweet_df[sweet_df["甜蜜点"].astype(str).str.contains(spot, na=False)].copy()
        if subset.empty:
            continue

        total        = len(subset)
        wins         = 0
        losses       = 0
        refunds      = 0
        total_bet    = 0.0
        total_return = 0.0

        for _, row in subset.iterrows():
            bet_result = str(row.get("投注结果", "")).strip()
            try:
                odds = float(str(row.get("赔率", "")).strip()) if str(row.get("赔率", "")).strip() else 0.0
            except:
                odds = 0.0
            try:
                bet_amt = float(str(row.get("投注金额", "")).strip()) if str(row.get("投注金额", "")).strip() else 0.0
            except:
                bet_amt = 0.0

            # 兼容有emoji和无emoji两种格式
            is_win    = bet_result in ["✅ 赢", "赢"]
            is_loss   = bet_result in ["❌ 输", "输"]
            is_refund = bet_result in ["↩️ 退水", "退水"]

            if is_win:
                wins += 1
                if bet_amt > 0 and odds > 0:
                    total_bet    += bet_amt
                    total_return += bet_amt * odds
            elif is_loss:
                losses += 1
                if bet_amt > 0:
                    total_bet += bet_amt
            elif is_refund:
                refunds += 1
                if bet_amt > 0:
                    total_bet    += bet_amt
                    total_return += bet_amt  # 退回本金

        settled  = wins + losses + refunds
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else None
        net_pnl  = (total_return - total_bet) if total_bet > 0 else None
        roi      = (net_pnl / total_bet * 100) if total_bet > 0 else None

        results.append({
            "甜蜜点类型": spot,
            "总记录":   total,
            "已结算":   settled,
            "赢":       wins,
            "输":       losses,
            "退水":     refunds,
            "命中率":   f"{win_rate:.1f}%" if win_rate is not None else "—",
            "总投注":   f"RM{total_bet:.0f}" if total_bet > 0 else "—",
            "净盈亏":   f"RM{net_pnl:+.0f}" if net_pnl is not None else "—",
            "ROI":      f"{roi:+.1f}%" if roi is not None else "—",
        })

    return results

# ─── App ──────────────────────────────────────────────────────────────────────

st.title("运动期望值分析器 🏆")

tab1, tab2, tab3, tab4 = st.tabs(["⚔️ 电竞", "⚽ 足球", "🏀 篮球", "📋 记录"])

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
            score_input = st.text_input(label, value="", placeholder="2-1 / 1-0 / 3-2", key=f"eh_score_{i}")
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
            score_input = st.text_input(label, value="", placeholder="2-1 / 1-0 / 3-2", key=f"ea_score_{i}")
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
                base = 1.0 - (i * 0.1)
                total_w += base
                win_w += (1 if "赢" in v else (0.5 if "平" in v else 0)) * weights[v] * base
            return win_w / total_w if total_w > 0 else 0
        h_wr = e_winrate(e_home_vars, score_weights_esports)
        a_wr = e_winrate(e_away_vars, score_weights_esports)
        h_ev = (h_wr*(e_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(e_away_odds-1)*100) - ((1-a_wr)*100)
        st.session_state["e_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "h_ev": h_ev, "a_ev": a_ev,
            "h_odds": e_home_odds, "a_odds": e_away_odds,
            "h_name": e_home_name, "a_name": e_away_name
        }

    if "e_result" in st.session_state:
        r = st.session_state["e_result"]
        st.divider()

        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"])
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            spots = check_sweet_spot_esports(r['h_wr']*100, r['h_ev'], r['a_wr']*100)
            for s in spots: st.success(s)
            if not spots:
                if r['h_ev'] > 0: st.success("✅ 正期望值")
                else: st.error("❌ 负期望值")

        with col6:
            st.subheader(r["a_name"])
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            spots = check_sweet_spot_esports(r['a_wr']*100, r['a_ev'], r['h_wr']*100)
            for s in spots: st.success(s)
            if not spots:
                if r['a_ev'] > 0: st.success("✅ 正期望值")
                else: st.error("❌ 负期望值")

        st.divider()
        st.subheader("💾 保存记录")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            e_bet_result = st.selectbox("投注结果", ["", "✅ 赢", "❌ 输", "↩️ 退水"], key="e_bet_result")
        with col_s2:
            e_bet_odds = st.number_input("实际赔率", min_value=1.01, value=1.64, step=0.01, key="e_bet_odds")
        with col_s3:
            e_bet_amt = st.number_input("投注金额 (RM)", min_value=0.0, value=100.0, step=10.0, key="e_bet_amt")

        if st.button("💾 保存记录", key="e_save"):
            all_spots = (
                check_sweet_spot_esports(r['h_wr']*100, r['h_ev'], r['a_wr']*100) +
                check_sweet_spot_esports(r['a_wr']*100, r['a_ev'], r['h_wr']*100)
            )
            sweet_combined = " | ".join(dict.fromkeys(all_spots))
            record = {
                "日期": str(date.today()), "运动": "电竞",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A", "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A", "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": "N/A", "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": "N/A", "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": sweet_combined,
                "投注结果": e_bet_result, "赔率": e_bet_odds, "投注金额": e_bet_amt
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
            win_w  += info["is_win"]  * final_weight
            draw_w += info["is_draw"] * final_weight * 0.5
        win_rate  = win_w  / total_w if total_w > 0 else 0
        draw_rate = draw_w / total_w if total_w > 0 else 0
        return win_rate, draw_rate

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
            with c1: score_input = st.text_input(label, value="", placeholder="主队-客队 如 2-1", key=f"fh_score_{i}")
            with c2: venue_sel  = st.selectbox("", ["主场🏠", "客场✈️"], key=f"fh_venue_{i}", label_visibility="collapsed")
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
            with c1: score_input = st.text_input(label, value="", placeholder="主队-客队 如 2-1", key=f"fa_score_{i}")
            with c2: venue_sel  = st.selectbox("", ["主场🏠", "客场✈️"], index=1, key=f"fa_venue_{i}", label_visibility="collapsed")
            result = score_to_football_result(score_input, "主场" in venue_sel)
            if result and result in valid_keys:
                st.caption(f"→ {result_emoji_football.get(result, result)}")
                f_away_vars.append(result)
            else:
                if score_input: st.caption("⚠️ 格式错误，请填如 2-1")
                f_away_vars.append("✈️ 客场小胜")

    if st.button("⚡ 计算", key="f_calc", type="primary"):
        h_wr, h_dr = calc_football_winrate(f_home_vars, True, venue)
        a_wr, a_dr = calc_football_winrate(f_away_vars, False, venue)
        draw_prob  = (h_dr + a_dr) / 2
        h_ev = (h_wr*(f_home_odds-1)*100) - ((1-h_wr)*100)
        a_ev = (a_wr*(f_away_odds-1)*100) - ((1-a_wr)*100)
        d_ev = (draw_prob*(f_draw_odds-1)*100) - ((1-draw_prob)*100)
        st.session_state["f_result"] = {
            "h_wr": h_wr, "a_wr": a_wr, "draw_prob": draw_prob,
            "h_ev": h_ev, "a_ev": a_ev, "d_ev": d_ev,
            "h_odds": f_home_odds, "a_odds": f_away_odds, "d_odds": f_draw_odds,
            "h_name": f_home_name, "a_name": f_away_name
        }

    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()

        over_sweet = check_sweet_spot_over(r['h_wr']*100, r['a_wr']*100)
        if over_sweet:
            st.success(over_sweet)

        col9, col10, col11 = st.columns(3)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            sweet = check_sweet_spot_football(r['h_wr']*100, r['h_ev'])
            if sweet: st.success(sweet)
            elif r['h_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")

        with col10:
            st.subheader("平局")
            st.metric("平局概率", f"{r['draw_prob']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['d_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['d_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['draw_prob'] - 1/r['d_odds']:+.1%}")
            if r['d_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")

        with col11:
            st.subheader(f_away_name)
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            sweet = check_sweet_spot_football(r['a_wr']*100, r['a_ev'])
            if sweet: st.success(sweet)
            elif r['a_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")

        st.divider()
        st.subheader("💾 保存记录")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            f_bet_result = st.selectbox("投注结果", ["", "✅ 赢", "❌ 输", "↩️ 退水"], key="f_bet_result")
        with col_s2:
            f_bet_odds = st.number_input("实际赔率", min_value=1.01, value=1.64, step=0.01, key="f_bet_odds")
        with col_s3:
            f_bet_amt = st.number_input("投注金额 (RM)", min_value=0.0, value=100.0, step=10.0, key="f_bet_amt")

        if st.button("💾 保存记录", key="f_save"):
            over_val = check_sweet_spot_over(r['h_wr']*100, r['a_wr']*100) or ""
            win_val  = check_sweet_spot_football(r['h_wr']*100, r['h_ev']) or check_sweet_spot_football(r['a_wr']*100, r['a_ev']) or ""
            sweet_val = " | ".join(filter(None, [win_val, over_val]))
            record = {
                "日期": str(date.today()), "运动": "足球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": f"{r['draw_prob']:.1%}", "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": f"{r['d_ev']:.2f}", "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": f"{1/r['d_odds']:.1%}", "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": f"{r['draw_prob'] - 1/r['d_odds']:+.1%}", "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": sweet_val,
                "投注结果": f_bet_result, "赔率": f_bet_odds, "投注金额": f_bet_amt
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
        "小负 (-1到-14)": 0.4, "大负 (-15以上)": 0.2
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
            base = 1.0 - (i * 0.1)
            total_w += base
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
            "h_name": b_home_name, "a_name": b_away_name
        }

    if "b_result" in st.session_state:
        r = st.session_state["b_result"]
        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name)
            st.metric("加权胜率 (WP)", f"{r['h_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['h_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            if r['h_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率 (WP)", f"{r['a_wr']:.1%}")
            st.metric("期望值 (EV)", f"RM{r['a_ev']:.2f}")
            st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            st.metric("优势差距 ⚠️仅参考", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            if r['a_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        st.divider()
        if st.button("💾 保存记录", key="b_save"):
            record = {
                "日期": str(date.today()), "运动": "篮球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": "N/A", "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": "N/A", "客队期望值": f"{r['a_ev']:.2f}",
                "主队隐含概率": f"{1/r['h_odds']:.1%}", "平局隐含概率": "N/A", "客队隐含概率": f"{1/r['a_odds']:.1%}",
                "主队优势差距": f"{r['h_wr'] - 1/r['h_odds']:+.1%}", "平局优势差距": "N/A", "客队优势差距": f"{r['a_wr'] - 1/r['a_odds']:+.1%}",
                "比赛结果": "", "甜蜜点": "", "投注结果": "", "赔率": "", "投注金额": ""
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

        # ── 甜蜜点统计面板 ──────────────────────────────────────────────────
        st.divider()
        st.subheader("🎯 甜蜜点统计")
        st.caption("在 Google Sheet T列填「投注结果」：✅ 赢 / ❌ 输 / ↩️ 退水，系统自动统计。")

        stats = calc_sweet_spot_stats(df)
        if stats:
            for s in stats:
                with st.expander(f"{s['甜蜜点类型']}　　命中率 {s['命中率']}　已结算 {s['已结算']}/{s['总记录']}"):
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("总记录", s["总记录"])
                    c2.metric("赢", s["赢"])
                    c3.metric("输", s["输"])
                    c4.metric("退水", s["退水"])
                    c5.metric("命中率", s["命中率"])
                    c6, c7, c8 = st.columns(3)
                    c6.metric("总投注", s["总投注"])
                    c7.metric("净盈亏", s["净盈亏"])
                    c8.metric("ROI", s["ROI"])
        else:
            st.info("还没有甜蜜点记录，或甜蜜点栏位为空。")

        # ── 完整记录表 ────────────────────────────────────────────────────────
        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 下载记录", csv, "records.csv", "text/csv")

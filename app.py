import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import pandas as pd
from datetime import date
import re
import requests

SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
HEADERS = ["日期","运动","主队","客队","主队加权胜率","平局加权胜率","客队加权胜率","主队期望值","平局期望值","客队期望值","注额(RM)","押注选项","实际结果","盈亏(RM)"]

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

def update_sheet_row(row_idx, result, pnl):
    try:
        sheet = get_sheet()
        sheet.update_cell(row_idx + 2, HEADERS.index("实际结果") + 1, result)
        sheet.update_cell(row_idx + 2, HEADERS.index("盈亏(RM)") + 1, pnl)
    except Exception as e:
        st.error(f"更新失败: {e}")

# ─── API-Football ─────────────────────────────────────────────────────────────

API_KEY = st.secrets.get("API_SPORTS_KEY", "")
API_BASE = "https://v3.football.api-sports.io"

def api_headers():
    return {"x-apisports-key": API_KEY}

@st.cache_data(ttl=3600)
def search_team(name):
    """搜索球队，返回 [(team_id, team_name, country, logo)] """
    try:
        r = requests.get(f"{API_BASE}/teams", headers=api_headers(), params={"search": name}, timeout=10)
        data = r.json()
        results = []
        for item in data.get("response", []):
            t = item["team"]
            results.append({
                "id": t["id"],
                "name": t["name"],
                "country": t.get("country", ""),
                "logo": t.get("logo", "")
            })
        return results
    except Exception as e:
        st.error(f"搜索失败: {e}")
        return []

@st.cache_data(ttl=3600)
def get_last_5_matches(team_id):
    """抓取球队最近5场比赛结果（免费版用赛季参数）"""
    try:
        from datetime import datetime
        current_year = datetime.now().year
        # 试今年赛季，如果没有就试去年
        for season in [current_year, current_year - 1]:
            r = requests.get(
                f"{API_BASE}/fixtures",
                headers=api_headers(),
                params={"team": team_id, "season": season, "status": "FT"},
                timeout=10
            )
            data = r.json()
            all_fixtures = data.get("response", [])
            if all_fixtures:
                # 按日期排序，取最近5场
                all_fixtures.sort(key=lambda x: x["fixture"]["date"], reverse=True)
                all_fixtures = all_fixtures[:5]
                break
        else:
            all_fixtures = []

        if not all_fixtures:
            st.warning(f"找不到比赛记录。API错误: {data.get('errors', '')}")
            return []

        matches = []
        for fixture in all_fixtures:
            home = fixture["teams"]["home"]
            away = fixture["teams"]["away"]
            goals = fixture["goals"]
            h_goals = goals["home"] if goals["home"] is not None else 0
            a_goals = goals["away"] if goals["away"] is not None else 0
            is_home = home["id"] == team_id
            team_score = h_goals if is_home else a_goals
            opp_score = a_goals if is_home else h_goals
            diff = abs(team_score - opp_score)
            won = home["winner"] if is_home else away["winner"]
            venue = "🏠 主场" if is_home else "✈️ 客场"
            if won is True:
                result = f"{venue}大胜" if diff >= 2 else f"{venue}小胜"
            elif won is False:
                result = f"{venue}大负" if diff >= 2 else f"{venue}小负"
            else:
                result = f"{venue}平局"
            matches.append({
                "result_key": result,
                "score": f"{h_goals}-{a_goals}",
                "home_team": home["name"],
                "away_team": away["name"],
                "date": fixture["fixture"]["date"][:10]
            })
        return matches
    except Exception as e:
        st.error(f"抓取比赛数据失败: {e}")
        return []



def render_team_search(side_label, session_key_prefix):
    """渲染球队搜索 + 自动填入 UI，返回 (team_name, [result_keys])"""
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        search_input = st.text_input(
            f"搜索{side_label}名字",
            key=f"{session_key_prefix}_search_input",
            placeholder="例如: Manchester, Barcelona..."
        )
    with col_btn:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 搜索", key=f"{session_key_prefix}_search_btn", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    if search_clicked and search_input:
        with st.spinner("搜索中..."):
            results = search_team(search_input)
        if results:
            st.session_state[f"{session_key_prefix}_search_results"] = results
        else:
            st.warning("找不到球队，请尝试英文名字")

    # 显示搜索结果让用户选择
    if f"{session_key_prefix}_search_results" in st.session_state:
        results = st.session_state[f"{session_key_prefix}_search_results"]
        options = [f"{r['name']} ({r['country']})" for r in results[:8]]
        selected = st.selectbox(f"选择{side_label}", options, key=f"{session_key_prefix}_team_select")
        selected_idx = options.index(selected)
        selected_team = results[selected_idx]

        if st.button(f"✅ 抓取 {selected_team['name']} 近5场", key=f"{session_key_prefix}_fetch_btn", type="primary"):
            with st.spinner(f"抓取 {selected_team['name']} 比赛记录..."):
                matches = get_last_5_matches(selected_team["id"])
            if matches:
                st.session_state[f"{session_key_prefix}_fetched_name"] = selected_team["name"]
                st.session_state[f"{session_key_prefix}_fetched_matches"] = matches
                result_keys = [m["result_key"] for m in matches]
                st.session_state[f"{session_key_prefix}_result_keys"] = result_keys
                st.success(f"✅ 已抓取 {selected_team['name']} 近{len(matches)}场！")
                # 显示抓取的比赛
                for m in matches:
                    st.caption(f"📅 {m['date']}  {m['home_team']} {m['score']} {m['away_team']}  → {m['result_key']}")
            else:
                st.warning("找不到近期比赛记录")

    fetched_name = st.session_state.get(f"{session_key_prefix}_fetched_name", "")
    fetched_keys = st.session_state.get(f"{session_key_prefix}_result_keys", [])
    return fetched_name, fetched_keys

# ─── Flashscore Parser ────────────────────────────────────────────────────────

def parse_flashscore(raw_text):
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    teams_data = {}
    current_team = None
    pending_match = None

    for line in lines:
        lm = re.match(r'Last matches[:\s]+(.+)', line, re.IGNORECASE)
        if lm:
            current_team = lm.group(1).strip()
            if current_team not in teams_data:
                teams_data[current_team] = []
            pending_match = None
            continue
        if current_team is None:
            continue
        entry = re.match(r'\[(\d{2}\.\d{2}\.\d{2})[A-Z0-9]*(.+?)(\d+)(\d+)\]\(', line)
        if entry:
            raw_inner = entry.group(0)
            score_m = re.search(r'(\d+)(\d+)\]\($', raw_inner.rstrip())
            if not score_m:
                score_m = re.search(r'(\d+)(\d+)\]\(', raw_inner)
            if score_m:
                s1 = int(score_m.group(1))
                s2 = int(score_m.group(2))
                date_str = entry.group(1)
                inner_content = entry.group(2)
                team_lower = current_team.lower()
                content_lower = inner_content.lower()
                pos = content_lower.find(team_lower[:4])
                is_home = pos == 0 or (pos < len(content_lower) // 2)
                pending_match = {
                    'date': date_str, 'raw': inner_content,
                    'home_score': s1, 'away_score': s2, 'is_home': is_home
                }
            continue
        wld_m = re.match(r'\[([WLD])\]\(', line)
        if wld_m and pending_match and current_team:
            if len(teams_data[current_team]) < 5:
                pending_match['wld'] = wld_m.group(1)
                teams_data[current_team].append(pending_match)
            pending_match = None
            continue
    return teams_data

def flashscore_to_football_result(match, is_this_team_home):
    wld = match['wld']
    h = match['home_score']
    a = match['away_score']
    team_score = h if match['is_home'] else a
    opp_score = a if match['is_home'] else h
    diff = abs(team_score - opp_score)
    was_home = match['is_home']
    prefix = "🏠 主场" if was_home else "✈️ 客场"
    if wld == 'W':
        return f"{prefix}大胜" if diff >= 2 else f"{prefix}小胜"
    elif wld == 'D':
        return f"{prefix}平局"
    else:
        return f"{prefix}大负" if diff >= 2 else f"{prefix}小负"

def flashscore_to_esports_result(match):
    wld = match['wld']
    h = match['home_score']
    a = match['away_score']
    team_score = h if match['is_home'] else a
    opp_score = a if match['is_home'] else h
    if wld == 'W':
        return "2-0 赢" if team_score == 2 and opp_score == 0 else "2-1 赢"
    elif wld == 'L':
        return "0-2 输" if team_score == 0 else "1-2 输"
    else:
        return "2-1 赢"

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

# ─── App ──────────────────────────────────────────────────────────────────────

st.title("运动期望值分析器 🏆")

tab1, tab2, tab3, tab4 = st.tabs(["⚔️ 电竞", "⚽ 足球", "🏀 篮球", "📋 记录"])

# ── TAB 1: 电竞 ───────────────────────────────────────────────────────────────
with tab1:
    st.header("电竞期望值分析器")
    score_weights_esports = {
        "2-0 赢": 1.0, "2-1 赢": 0.7, "1-2 输": 0.4, "0-2 输": 0.2
    }

    with st.expander("📋 从 Flashscore 自动填入（可选）"):
        fs_text_e = st.text_area("粘贴 Flashscore 复制内容（包含两队历史）", height=150, key="fs_esports",
            placeholder="Last matches: Team A\n[17.05.26...]\n[W](...)\n...")
        if st.button("🔍 自动识别", key="fs_e_parse"):
            if fs_text_e:
                parsed = parse_flashscore(fs_text_e)
                if parsed:
                    teams = list(parsed.keys())
                    st.session_state['fs_e_teams'] = teams
                    st.session_state['fs_e_data'] = parsed
                    st.success(f"✅ 识别到: {', '.join(teams)}")
                else:
                    st.error("无法识别，请检查格式")
            else:
                st.warning("请先粘贴内容")

        if 'fs_e_data' in st.session_state and st.session_state['fs_e_data']:
            teams = st.session_state['fs_e_teams']
            col_a, col_b = st.columns(2)
            with col_a:
                home_pick = st.selectbox("设为主队", teams, key="fs_e_home_pick")
            with col_b:
                away_options = [t for t in teams if t != home_pick]
                away_pick = st.selectbox("设为客队", away_options if away_options else teams, key="fs_e_away_pick")
            if st.button("✅ 套用到分析器", key="fs_e_apply"):
                st.session_state['e_auto_home_name'] = home_pick
                st.session_state['e_auto_away_name'] = away_pick
                home_matches = st.session_state['fs_e_data'].get(home_pick, [])
                away_matches = st.session_state['fs_e_data'].get(away_pick, [])
                st.session_state['e_auto_home_results'] = [flashscore_to_esports_result(m) for m in home_matches]
                st.session_state['e_auto_away_results'] = [flashscore_to_esports_result(m) for m in away_matches]
                st.success("✅ 已套用！请看下方分析器")
                st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        default_e_home = st.session_state.get('e_auto_home_name', '主队')
        e_home_name = st.text_input("主队名字", default_e_home, key="e_home_name")
        e_home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01, key="e_home_odds")
    with col2:
        default_e_away = st.session_state.get('e_auto_away_name', '客队')
        e_away_name = st.text_input("客队名字", default_e_away, key="e_away_name")
        e_away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01, key="e_away_odds")

    st.divider()
    num_matches_e = st.slider("最近几场比赛？", 1, 5, 5, key="e_slider")
    col3, col4 = st.columns(2)
    e_home_vars = []
    e_away_vars = []
    auto_home_e = st.session_state.get('e_auto_home_results', [])
    auto_away_e = st.session_state.get('e_auto_away_results', [])

    with col3:
        st.subheader(f"{e_home_name} 最近{num_matches_e}场")
        for i in range(num_matches_e):
            default_val = auto_home_e[i] if i < len(auto_home_e) else list(score_weights_esports.keys())[0]
            idx = list(score_weights_esports.keys()).index(default_val) if default_val in score_weights_esports else 0
            v = st.selectbox(f"第{i+1}场", list(score_weights_esports.keys()), index=idx, key=f"eh{i}")
            e_home_vars.append(v)
    with col4:
        st.subheader(f"{e_away_name} 最近{num_matches_e}场")
        for i in range(num_matches_e):
            default_val = auto_away_e[i] if i < len(auto_away_e) else list(score_weights_esports.keys())[0]
            idx = list(score_weights_esports.keys()).index(default_val) if default_val in score_weights_esports else 0
            v = st.selectbox(f"第{i+1}场", list(score_weights_esports.keys()), index=idx, key=f"ea{i}")
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

    if "e_result" in st.session_state:
        r = st.session_state["e_result"]
        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(r["h_name"])
            st.metric("加权胜率", f"{r['h_wr']:.1%}")
            st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            st.metric("优势差距", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['h_ev']:.2f}")
            if r['h_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col6:
            st.subheader(r["a_name"])
            st.metric("加权胜率", f"{r['a_wr']:.1%}")
            st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            st.metric("优势差距", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['a_ev']:.2f}")
            if r['a_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")

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

# ── TAB 2: 足球 ───────────────────────────────────────────────────────────────
with tab2:
    st.header("足球期望值分析器")

    # ── API 自动抓取 ──────────────────────────────────────────────────────────
    with st.expander("🚀 API 自动抓取近5场（推荐）", expanded=True):
        st.caption("输入球队名字搜索，自动抓取近5场战绩")
        col_h, col_a = st.columns(2)

        with col_h:
            st.markdown("**主队**")
            fetched_home_name, fetched_home_keys = render_team_search("主队", "api_home")

        with col_a:
            st.markdown("**客队**")
            fetched_away_name, fetched_away_keys = render_team_search("客队", "api_away")

        if fetched_home_keys and fetched_away_keys:
            if st.button("✅ 套用到分析器", key="api_apply", type="primary"):
                valid_keys = list(football_results.keys())
                home_results = [k if k in valid_keys else valid_keys[0] for k in fetched_home_keys]
                away_results = [k if k in valid_keys else valid_keys[0] for k in fetched_away_keys]
                st.session_state['f_auto_home_name'] = fetched_home_name
                st.session_state['f_auto_away_name'] = fetched_away_name
                st.session_state['f_auto_home_results'] = home_results
                st.session_state['f_auto_away_results'] = away_results
                st.success("✅ 已套用！请看下方分析器")
                st.rerun()

    # ── Flashscore 手动填入（备用）────────────────────────────────────────────
    with st.expander("📋 从 Flashscore 手动填入（备用）"):
        fs_text_f = st.text_area("粘贴 Flashscore 复制内容", height=150, key="fs_football",
            placeholder="Last matches: Brighton\n[17.05.26PLLeedsBrighton10](...)\n[L](...)\n...")
        if st.button("🔍 自动识别", key="fs_f_parse"):
            if fs_text_f:
                parsed = parse_flashscore(fs_text_f)
                if parsed:
                    teams = list(parsed.keys())
                    st.session_state['fs_f_teams'] = teams
                    st.session_state['fs_f_data'] = parsed
                    st.success(f"✅ 识别到: {', '.join(teams)}")
                else:
                    st.error("无法识别，请检查格式")
            else:
                st.warning("请先粘贴内容")

        if 'fs_f_data' in st.session_state and st.session_state['fs_f_data']:
            teams = st.session_state['fs_f_teams']
            col_a, col_b = st.columns(2)
            with col_a:
                home_pick = st.selectbox("设为主队", teams, key="fs_f_home_pick")
            with col_b:
                away_options = [t for t in teams if t != home_pick]
                away_pick = st.selectbox("设为客队", away_options if away_options else teams, key="fs_f_away_pick")
            if st.button("✅ 套用到分析器", key="fs_f_apply"):
                valid_keys = list(football_results.keys())
                home_matches = st.session_state['fs_f_data'].get(home_pick, [])
                away_matches = st.session_state['fs_f_data'].get(away_pick, [])
                home_results = [flashscore_to_football_result(m, True) for m in home_matches]
                away_results = [flashscore_to_football_result(m, False) for m in away_matches]
                home_results = [r if r in valid_keys else valid_keys[0] for r in home_results]
                away_results = [r if r in valid_keys else valid_keys[0] for r in away_results]
                st.session_state['f_auto_home_name'] = home_pick
                st.session_state['f_auto_away_name'] = away_pick
                st.session_state['f_auto_home_results'] = home_results
                st.session_state['f_auto_away_results'] = away_results
                st.success("✅ 已套用！")
                st.rerun()

    # ── 队名 + 赔率 ───────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        default_f_home = st.session_state.get('f_auto_home_name', '主队')
        f_home_name = st.text_input("主队名字", default_f_home, key="f_home_name")
    with col2:
        st.write("")
    with col3:
        default_f_away = st.session_state.get('f_auto_away_name', '客队')
        f_away_name = st.text_input("客队名字", default_f_away, key="f_away_name")

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

    # ── 比赛记录输入 ──────────────────────────────────────────────────────────
    st.subheader("近期比赛记录")
    valid_keys = list(football_results.keys())
    col_h2, col_a2 = st.columns(2)
    f_home_vars = []
    f_away_vars = []

    with col_h2:
        st.markdown(f"**🏠 {f_home_name}**")
        auto_home_f = st.session_state.get('f_auto_home_results', [])
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            default_val = auto_home_f[i] if i < len(auto_home_f) else valid_keys[0]
            idx = valid_keys.index(default_val) if default_val in valid_keys else 0
            v = st.selectbox(label, valid_keys, index=idx, key=f"fh{i}")
            f_home_vars.append(v)

    with col_a2:
        st.markdown(f"**✈️ {f_away_name}**")
        auto_away_f = st.session_state.get('f_auto_away_results', [])
        for i in range(num_matches_f):
            label = "最新" if i == 0 else f"第{i+1}场"
            default_val = auto_away_f[i] if i < len(auto_away_f) else valid_keys[0]
            idx = valid_keys.index(default_val) if default_val in valid_keys else 0
            v = st.selectbox(label, valid_keys, index=idx, key=f"fa{i}")
            f_away_vars.append(v)

    # ── 甜蜜点提示 ────────────────────────────────────────────────────────────
    def check_sweet_spot(wp, ev, sport, opp_wp=None):
        if sport == "足球":
            if wp >= 50 and -50 <= ev < 0:
                return "🎯 甜蜜点！WP≥50% + EV负"
        elif sport == "电竞" and opp_wp is not None:
            diff = abs(wp - opp_wp)
            if wp >= 60 and diff >= 20 and ev < 0:
                return "🎯 甜蜜点！WP≥60% + 差距≥20% + EV负"
        return None

    if st.button("⚡ 计算", key="f_calc", type="primary"):
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

    if "f_result" in st.session_state:
        r = st.session_state["f_result"]
        st.divider()
        col9, col10, col11 = st.columns(3)
        with col9:
            st.subheader(f_home_name)
            st.metric("加权胜率", f"{r['h_wr']:.1%}")
            st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            st.metric("优势差距", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['h_ev']:.2f}")
            sweet = check_sweet_spot(r['h_wr']*100, r['h_ev'], "足球")
            if sweet: st.success(sweet)
            elif r['h_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col10:
            st.subheader("平局")
            st.metric("平局概率", f"{r['draw_prob']:.1%}")
            st.metric("隐含概率", f"{1/r['d_odds']:.1%}")
            st.metric("优势差距", f"{r['draw_prob'] - 1/r['d_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['d_ev']:.2f}")
            if r['d_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col11:
            st.subheader(f_away_name)
            st.metric("加权胜率", f"{r['a_wr']:.1%}")
            st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            st.metric("优势差距", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['a_ev']:.2f}")
            sweet = check_sweet_spot(r['a_wr']*100, r['a_ev'], "足球")
            if sweet: st.success(sweet)
            elif r['a_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")

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
                odds_used = r["h_odds"]; win_condition = "主队赢"
            elif f_bet == "平局":
                odds_used = r["d_odds"]; win_condition = "平局"
            else:
                odds_used = r["a_odds"]; win_condition = "客队赢"
            if f_res == "待定": pnl = 0
            elif f_res == win_condition: pnl = (odds_used-1)*f_stake
            else: pnl = -f_stake
            record = {
                "日期": str(date.today()), "运动": "足球",
                "主队": r["h_name"], "客队": r["a_name"],
                "主队加权胜率": f"{r['h_wr']:.1%}", "平局加权胜率": f"{r['draw_prob']:.1%}",
                "客队加权胜率": f"{r['a_wr']:.1%}",
                "主队期望值": f"{r['h_ev']:.2f}", "平局期望值": f"{r['d_ev']:.2f}",
                "客队期望值": f"{r['a_ev']:.2f}", "注额(RM)": f_stake,
                "押注选项": f_bet, "实际结果": f_res, "盈亏(RM)": pnl
            }
            save_to_sheet(record)
            st.success("✅ 记录已保存到 Google Sheets！")

# ── TAB 3: 篮球 ───────────────────────────────────────────────────────────────
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

    if "b_result" in st.session_state:
        r = st.session_state["b_result"]
        st.divider()
        col5, col6 = st.columns(2)
        with col5:
            st.subheader(b_home_name)
            st.metric("加权胜率", f"{r['h_wr']:.1%}")
            st.metric("隐含概率", f"{1/r['h_odds']:.1%}")
            st.metric("优势差距", f"{r['h_wr'] - 1/r['h_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['h_ev']:.2f}")
            if r['h_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
        with col6:
            st.subheader(b_away_name)
            st.metric("加权胜率", f"{r['a_wr']:.1%}")
            st.metric("隐含概率", f"{1/r['a_odds']:.1%}")
            st.metric("优势差距", f"{r['a_wr'] - 1/r['a_odds']:+.1%}")
            st.metric("期望值 (RM100)", f"RM{r['a_ev']:.2f}")
            if r['a_ev'] > 0: st.success("✅ 正期望值")
            else: st.error("❌ 负期望值")
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

# ── TAB 4: 记录 ───────────────────────────────────────────────────────────────
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
        with col1: st.metric("总记录", total)
        with col2: st.metric("已结算", len(known))
        with col3: st.metric("待定", pending)
        with col4: st.metric("总盈亏", f"RM{total_pnl:.2f}")
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

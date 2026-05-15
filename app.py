import streamlit as st

st.title("电竞期望值分析器")

score_weights = {
    "2-0 赢": 1.0,
    "2-1 赢": 0.7,
    "1-2 输": 0.4,
    "0-2 输": 0.2
}

col1, col2 = st.columns(2)

with col1:
    home_name = st.text_input("主队名字", "主队")
    home_odds = st.number_input("主队赔率", min_value=1.01, value=1.5, step=0.01)

with col2:
    away_name = st.text_input("客队名字", "客队")
    away_odds = st.number_input("客队赔率", min_value=1.01, value=2.0, step=0.01)

st.divider()

col3, col4 = st.columns(2)
home_vars = []
away_vars = []

with col3:
    st.subheader(f"{home_name} 最近5场")
    for i in range(5):
        v = st.selectbox(f"第{i+1}场", list(score_weights.keys()), key=f"h{i}")
        home_vars.append(v)

with col4:
    st.subheader(f"{away_name} 最近5场")
    for i in range(5):
        v = st.selectbox(f"第{i+1}场", list(score_weights.keys()), key=f"a{i}")
        away_vars.append(v)

st.divider()

if st.button("计算", type="primary"):
    def winrate(vars):
        total_w = 0
        win_w = 0
        for i, v in enumerate(vars):
            base_weight = 1.0 - (i * 0.1)
            score_weight = score_weights[v]
            is_win = 1 if "赢" in v else 0
            total_w += base_weight
            win_w += is_win * score_weight * base_weight
        return win_w / total_w

    h_wr = winrate(home_vars)
    a_wr = winrate(away_vars)
    h_ev = (h_wr*(home_odds-1)*100) - ((1-h_wr)*100)
    a_ev = (a_wr*(away_odds-1)*100) - ((1-a_wr)*100)
    h_implied = 1/home_odds
    a_implied = 1/away_odds
    h_edge = h_wr - h_implied
    a_edge = a_wr - a_implied

    col5, col6 = st.columns(2)

    with col5:
        st.subheader(home_name)
        st.metric("加权胜率", f"{h_wr:.1%}")
        st.metric("隐含概率", f"{h_implied:.1%}")
        st.metric("优势差距", f"{h_edge:+.1%}")
        st.metric("期望值 (RM100)", f"RM{h_ev:.2f}")
        if h_ev > 0:
            st.success("✅ 正期望值")
        else:
            st.error("❌ 负期望值")

    with col6:
        st.subheader(away_name)
        st.metric("加权胜率", f"{a_wr:.1%}")
        st.metric("隐含概率", f"{a_implied:.1%}")
        st.metric("优势差距", f"{a_edge:+.1%}")
        st.metric("期望值 (RM100)", f"RM{a_ev:.2f}")
        if a_ev > 0:
            st.success("✅ 正期望值")
        else:
            st.error("❌ 负期望值")

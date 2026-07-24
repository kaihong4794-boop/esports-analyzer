# ══════════════════════════════════════════════════════════════════════════════
# 新增功能：把当前比赛和历史最相似的那一场并排对比
#
# 1. 加这个新函数（放在 show_similar_table 函数下面就行）
# 2. tab1(电竞) 和 tab2(足球) 里，show_similar_table(...) 那行下面加一行调用
# ══════════════════════════════════════════════════════════════════════════════


def show_top_match_comparison(current, similar, dist_label="综合相似度"):
    """
    并排对比：当前这场 vs 历史最相似的那一场（similar 已经按距离排过序，[0]就是最相似）
    current: dict，h_wp / a_wp / h_ev / a_ev
    """
    if not similar:
        return

    top = similar[0]
    st.divider()
    st.subheader("🔍 与最相似历史比赛对比")
    st.caption(
        f"{top.get('主队','')} vs {top.get('客队','')}（{top.get('日期','')}）"
        f"· 综合相似度距离 {top.get(dist_label, '—')}（数值越小越像）"
    )

    col_now, col_hist = st.columns(2)
    with col_now:
        st.markdown("**🎯 本场（当前）**")
        st.metric("主WP", f"{current['h_wp']:.1f}%")
        st.metric("客WP", f"{current['a_wp']:.1f}%")
        st.metric("主EV", f"{current['h_ev']:.2f}")
        st.metric("客EV", f"{current['a_ev']:.2f}")
    with col_hist:
        st.markdown(f"**📜 历史：{top.get('主队','')} vs {top.get('客队','')}**")
        st.metric("主WP", f"{top['主WP']:.1f}%", delta=f"{top['主WP']-current['h_wp']:+.1f}")
        st.metric("客WP", f"{top['客WP']:.1f}%", delta=f"{top['客WP']-current['a_wp']:+.1f}")
        st.metric("主EV", f"{top['主EV']:.2f}", delta=f"{top['主EV']-current['h_ev']:+.2f}")
        st.metric("客EV", f"{top['客EV']:.2f}", delta=f"{top['客EV']-current['a_ev']:+.2f}")

    st.info(f"📌 那场实际结果：{top.get('比赛结果', '—')}")


# ══════════════════════════════════════════════════════════════════════════════
# tab1（电竞）里，show_similar_table(...) 那行下面加：
# ══════════════════════════════════════════════════════════════════════════════

show_top_match_comparison(
    current={"h_wp": h_wp_pct, "a_wp": a_wp_pct, "h_ev": r["h_ev"], "a_ev": r["a_ev"]},
    similar=similar,
)


# ══════════════════════════════════════════════════════════════════════════════
# tab2（足球）里，show_similar_table(...) 那行下面也加同样一段：
# ══════════════════════════════════════════════════════════════════════════════

show_top_match_comparison(
    current={"h_wp": h_wp_pct, "a_wp": a_wp_pct, "h_ev": r["h_ev"], "a_ev": r["a_ev"]},
    similar=similar,
)

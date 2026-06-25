# ══════════════════════════════════════════════════════════════════════════════
# 让球盘 Sheet2 工具函数
# ══════════════════════════════════════════════════════════════════════════════
HANDICAP_HEADERS = [
    "日期", "赛事",
    "电竞版_方向", "电竞版_主WP", "电竞版_客WP", "电竞版_历史参考",
    "足球版_方向", "足球版_主WP", "足球版_客WP", "足球版_历史参考1", "足球版_历史参考2",
    "实际结果", "赢/输"
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
    except Exception as e:
        return pd.DataFrame(columns=HANDICAP_HEADERS)

# ── 让球盘辅助函数 ─────────────────────────────────────────────────────────────
def _ref_direction(score_str):
    """从比分字符串判断方向：F/C/D"""
    score_str = str(score_str).strip()
    if not re.match(r'^\d+-\d+$', score_str):
        return None
    h, a = map(int, score_str.split('-'))
    if h > a:   return "F"
    elif a > h: return "C"
    else:       return "D"

def _ref_goals(score_str):
    """从比分字符串算总进球数"""
    score_str = str(score_str).strip()
    if not re.match(r'^\d+-\d+$', score_str):
        return None
    h, a = map(int, score_str.split('-'))
    return h + a

def analyze_handicap_signals(e_dir, f_dir, e_ref, f_ref1, f_ref2):
    """
    分析让球盘信号，返回信号列表
    每个信号: {"level": "gold"/"warn"/"skip", "msg": str, "rate": str}
    """
    signals = []

    ref1_dir = _ref_direction(f_ref1)
    ref2_dir = _ref_direction(f_ref2)
    ref1_goals = _ref_goals(f_ref1)
    ref2_goals = _ref_goals(f_ref2)

    avg_goals = None
    if ref1_goals is not None and ref2_goals is not None:
        avg_goals = (ref1_goals + ref2_goals) / 2

    # ── 1. 三重确认 ───────────────────────────────────────────────────────────
    # 电竞版 = 足球版 = 两个历史参考方向一致（非平局）
    refs_agree = (ref1_dir == ref2_dir and ref1_dir not in (None, "D"))
    triple = (e_dir == f_dir and refs_agree and ref1_dir == f_dir)
    if triple:
        if f_dir == "C":
            signals.append({
                "level": "skip",
                "msg": f"⚠️ 三重确认C方向 → 历史胜率0%，强烈建议跳过或反押F",
                "rate": "0%"
            })
        else:
            signals.append({
                "level": "gold",
                "msg": f"🏆 三重确认（电竞版=足球版=历史参考均为{f_dir}）→ 历史胜率86%",
                "rate": "86%"
            })

    # ── 2. C方向警告 ──────────────────────────────────────────────────────────
    if f_dir == "C" and not triple:
        signals.append({
            "level": "warn",
            "msg": "🔄 足球版方向为C → 历史胜率仅33%，建议反押F（反押胜率67%）",
            "rate": "反押67%"
        })

    # ── 3. F方向 + 大球（历史参考平均>3球）→ 黄金组合 ────────────────────────
    if f_dir == "F" and avg_goals is not None and avg_goals > 3:
        signals.append({
            "level": "gold",
            "msg": f"⚽ F方向 + 历史参考大球（均{avg_goals:.1f}球 > 3）→ 历史胜率81%",
            "rate": "81%"
        })

    # ── 4. F方向 + 小球（≤2.5）→ 建议跳过 ────────────────────────────────────
    if f_dir == "F" and avg_goals is not None and avg_goals <= 2.5:
        signals.append({
            "level": "skip",
            "msg": f"💤 F方向 + 历史参考小球（均{avg_goals:.1f}球 ≤ 2.5）→ 历史胜率仅42%，建议跳过",
            "rate": "42%"
        })

    # ── 5. 历史参考平局 → 跳过 ────────────────────────────────────────────────
    if ref1_dir == "D" or ref2_dir == "D":
        signals.append({
            "level": "skip",
            "msg": "➖ 历史参考含平局比分 → 历史胜率44%，建议跳过",
            "rate": "44%"
        })

    # ── 6. 两个历史参考都一致（非平局）→ 加分 ────────────────────────────────
    if refs_agree and ref1_dir == f_dir and not triple:
        signals.append({
            "level": "good",
            "msg": f"✅ 两个历史参考方向一致（均为{ref1_dir}）→ 历史胜率75%",
            "rate": "75%"
        })

    # ── 7. 无信号 ─────────────────────────────────────────────────────────────
    if not signals:
        signals.append({
            "level": "neutral",
            "msg": "⚪ 无特殊信号，整体胜率约58%",
            "rate": "58%"
        })

    return signals


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6: 让球盘分析
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("🎯 让球盘分析记录")
    st.caption("记录F/C让球盘数据，两个版本对比，自动统计胜率")

    st.subheader("➕ 新增记录")

    col1, col2 = st.columns(2)
    with col1:
        hc_sport = st.selectbox("赛事", ["足球", "电竞"], key="hc_sport")
        hc_date = st.date_input("日期", value=date.today(), key="hc_date")

    st.divider()

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
        hc_f_ref1 = st.text_input("足球版历史参考比分1（较近）", placeholder="如 2-1", key="hc_f_ref1")
        hc_f_ref2 = st.text_input("足球版历史参考比分2（较早）", placeholder="如 1-0", key="hc_f_ref2")
        f_dir = "F" if "F" in hc_f_main else "C"
        st.caption(f"→ {f_dir}方向  主{hc_f_h}% vs 客{hc_f_a}%")

    # ── 实时信号分析 ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔍 信号分析")

    signals = analyze_handicap_signals(e_dir, f_dir, hc_e_ref, hc_f_ref1, hc_f_ref2)

    for sig in signals:
        if sig["level"] == "gold":
            st.success(sig["msg"])
        elif sig["level"] == "good":
            st.info(sig["msg"])
        elif sig["level"] == "warn":
            st.warning(sig["msg"])
        elif sig["level"] == "skip":
            st.error(sig["msg"])
        else:
            st.info(sig["msg"])

    # 两版本一致提示
    if e_dir == f_dir:
        st.info(f"✅ 两版本方向一致（均为{f_dir}）")
    else:
        st.warning(f"⚠️ 两版本方向不一致（电竞{e_dir} vs 足球{f_dir}）→ 信号冲突，谨慎")

    if st.button("💾 保存记录", key="hc_save", type="primary"):
        record = {
            "日期": str(hc_date), "赛事": hc_sport,
            "电竞版_方向": e_dir,
            "电竞版_主WP": f"{hc_e_h}%", "电竞版_客WP": f"{hc_e_a}%",
            "电竞版_历史参考": hc_e_ref,
            "足球版_方向": f_dir,
            "足球版_主WP": f"{hc_f_h}%", "足球版_客WP": f"{hc_f_a}%",
            "足球版_历史参考1": hc_f_ref1,
            "足球版_历史参考2": hc_f_ref2,
            "实际结果": "", "赢/输": ""
        }
        save_to_sheet2(record)
        st.success("✅ 已保存！比赛结束后回来填实际结果。")

    # ── 填写实际结果 ──────────────────────────────────────────────────────────
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
                ref1 = row.get("足球版_历史参考1", "")
                ref2 = row.get("足球版_历史参考2", "")
                label = f"{row['日期']} | {row['赛事']} | 电竞{row['电竞版_方向']} | 足球{row['足球版_方向']} | 史分{ref1}/{ref2}"
                with st.expander(label):
                    res_input = st.text_input("实际结果（如 2-1）", key=f"hc_res_{idx}")
                    if st.button("保存", key=f"hc_save_res_{idx}"):
                        if re.match(r"^\d+-\d+$", res_input.strip()):
                            s1, s2 = map(int, res_input.split("-"))
                            direction = row["足球版_方向"]  # 以足球版为准
                            if s1 == s2:
                                win_loss = "C"   # 平局算C赢
                            elif s1 > s2:
                                win_loss = "F"
                            else:
                                win_loss = "C"
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

    # ── 胜率统计 ──────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 胜率统计")

    hc_df = load_from_sheet2()
    completed = hc_df[hc_df["赢/输"].astype(str).isin(["F", "C"])]

    if completed.empty:
        st.info("还没有完成的记录，继续加油记录！")
    else:
        # 以足球版方向为准判断赢输
        completed = completed.copy()
        completed["_win"] = completed.apply(
            lambda r: r["赢/输"] == r["足球版_方向"], axis=1
        )
        n = len(completed)
        wins = completed["_win"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总场次", len(hc_df))
        c2.metric("✓ 赢", int(wins))
        c3.metric("✗ 输", n - int(wins))
        c4.metric("胜率", f"{wins/n:.1%}" if n > 0 else "—")

        st.divider()

        # ── F vs C 胜率 ───────────────────────────────────────────────────────
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
                    reverse_rate = 1 - cw/len(c_rows)
                    st.caption(f"💡 C反押F胜率：{reverse_rate:.1%}")

        st.divider()

        # ── 三重确认统计 ──────────────────────────────────────────────────────
        triple_rows = []
        for _, row in completed.iterrows():
            ref1_d = _ref_direction(str(row.get("足球版_历史参考1", "")))
            ref2_d = _ref_direction(str(row.get("足球版_历史参考2", "")))
            e_d = str(row.get("电竞版_方向", ""))
            f_d = str(row.get("足球版_方向", ""))
            if e_d == f_d and ref1_d == f_d and ref2_d == f_d and f_d != "D":
                triple_rows.append(row)
        if triple_rows:
            triple_df = pd.DataFrame(triple_rows)
            triple_df["_win"] = triple_df.apply(
                lambda r: r["赢/输"] == r["足球版_方向"], axis=1
            )
            tw = triple_df["_win"].sum()
            st.metric("🏆 三重确认胜率", f"{tw/len(triple_df):.1%}", f"{int(tw)}/{len(triple_df)}场")

        # ── F+大球统计 ────────────────────────────────────────────────────────
        fb_rows = []
        for _, row in completed.iterrows():
            if str(row.get("足球版_方向", "")) != "F":
                continue
            g1 = _ref_goals(str(row.get("足球版_历史参考1", "")))
            g2 = _ref_goals(str(row.get("足球版_历史参考2", "")))
            if g1 is not None and g2 is not None and (g1 + g2) / 2 > 3:
                fb_rows.append(row)
        if fb_rows:
            fb_df = pd.DataFrame(fb_rows)
            fb_df["_win"] = fb_df.apply(
                lambda r: r["赢/输"] == r["足球版_方向"], axis=1
            )
            fbw = fb_df["_win"].sum()
            st.metric("⚽ F+大球(>3)胜率", f"{fbw/len(fb_df):.1%}", f"{int(fbw)}/{len(fb_df)}场")

        st.divider()
        st.subheader("📄 完整记录")
        st.dataframe(hc_df, use_container_width=True, hide_index=True)
        csv2 = hc_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ 下载让球盘记录", csv2, "handicap_records.csv", "text/csv")

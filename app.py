# ══════════════════════════════════════════════════════════════════════════════
# 改动说明:
# 1. find_similar_matches() 整个函数替换成下面这版
#    —— 从"按WP距离找相似"改成"按(主WP,客WP,主EV,客EV)4维归一化距离找相似"
# 2. tab1(电竞) 和 tab2(足球) 里调用 find_similar_matches 的地方要跟着改调用方式
#    —— 从传 match_val/match_col/h_wr_val/a_wr_val 改成传一个 current 字典
# ══════════════════════════════════════════════════════════════════════════════

import statistics  # 加在文件顶部 import 区，跟其他 import 放一起


def _std(vals):
    """标准差，样本<2或方差为0时退化为1，避免除零导致距离爆炸"""
    if len(vals) < 2:
        return 1.0
    s = statistics.pstdev(vals)
    return s if s > 1e-9 else 1.0


def find_similar_matches(df, sport, current, dist_label="综合相似度",
                          top_n=15, event_level=None, restrict_level=False):
    """
    current: dict，包含当前这场比赛的四个值 —— h_wp / a_wp / h_ev / a_ev

    用(主WP, 客WP, 主EV, 客EV)四个维度的归一化欧式距离找最相似的历史比赛。
    归一化：每个维度先除以该维度在候选池里的标准差，再算距离——
    这样EV(可能到±200+)不会因为数值本身比WP(0-100)大，就把WP的影响盖过去，
    四个维度才是公平地一起参与排序。

    restrict_level=True 时，只在同一"赛事级别"里找参考比赛。
    """
    if df.empty:
        return [], 0

    candidates = df[df["运动"] == sport].copy()
    if restrict_level and event_level:
        candidates = candidates[candidates["赛事级别"] == event_level]
    if candidates.empty:
        return [], 0

    parsed_rows = []
    for _, row in candidates.iterrows():
        result = str(row.get("比赛结果", "")).strip()
        if not result or result in ("nan", "None", "—", "CANCEL"):
            continue
        c_h_wp = _parse_pct(row.get("主WP"))
        c_a_wp = _parse_pct(row.get("客WP"))
        c_h_ev = _parse_ev(row.get("主EV"))
        c_a_ev = _parse_ev(row.get("客EV"))
        # 四个维度缺任何一个都跳过，不然距离算不出来
        if None in (c_h_wp, c_a_wp, c_h_ev, c_a_ev):
            continue
        parsed_rows.append({
            "row": row, "h_wp": c_h_wp, "a_wp": c_a_wp,
            "h_ev": c_h_ev, "a_ev": c_a_ev, "result": result,
        })

    if not parsed_rows:
        return [], 0

    std_h_wp = _std([p["h_wp"] for p in parsed_rows])
    std_a_wp = _std([p["a_wp"] for p in parsed_rows])
    std_h_ev = _std([p["h_ev"] for p in parsed_rows])
    std_a_ev = _std([p["a_ev"] for p in parsed_rows])

    rows = []
    for p in parsed_rows:
        d = (
            ((p["h_wp"] - current["h_wp"]) / std_h_wp) ** 2 +
            ((p["a_wp"] - current["a_wp"]) / std_a_wp) ** 2 +
            ((p["h_ev"] - current["h_ev"]) / std_h_ev) ** 2 +
            ((p["a_ev"] - current["a_ev"]) / std_a_ev) ** 2
        ) ** 0.5

        rows.append({
            dist_label: round(d, 3),
            "日期": p["row"].get("日期", ""),
            "主队": p["row"].get("主队", ""),
            "客队": p["row"].get("客队", ""),
            "主WP": p["h_wp"], "客WP": p["a_wp"],
            "主EV": p["h_ev"], "客EV": p["a_ev"],
            "比赛结果": p["result"],
        })

    rows.sort(key=lambda x: x[dist_label])
    total_found = len(rows)
    return rows[:top_n], total_found


# ══════════════════════════════════════════════════════════════════════════════
# tab1（电竞）里原来的调用：
#
#   similar, total_found = find_similar_matches(
#       history_df, "电竞", match_val=a_wp_pct, match_col="客WP", dist_label="距离(WP差)",
#       top_n=15, h_wr_val=h_wp_pct, event_level=r["event_level"], restrict_level=restrict,
#   )
#
# 改成：
# ══════════════════════════════════════════════════════════════════════════════

similar, total_found = find_similar_matches(
    history_df, "电竞",
    current={"h_wp": h_wp_pct, "a_wp": a_wp_pct, "h_ev": r["h_ev"], "a_ev": r["a_ev"]},
    dist_label="综合相似度", top_n=15,
    event_level=r["event_level"], restrict_level=restrict,
)


# ══════════════════════════════════════════════════════════════════════════════
# tab2（足球）里原来的调用：
#
#   similar, total_found = find_similar_matches(
#       history_df, "足球", match_val=a_wp_pct, match_col="客WP", dist_label="距离(WP差)",
#       top_n=15, h_wr_val=h_wp_pct, event_level=r["event_level"], restrict_level=restrict,
#   )
#
# 改成：
# ══════════════════════════════════════════════════════════════════════════════

similar, total_found = find_similar_matches(
    history_df, "足球",
    current={"h_wp": h_wp_pct, "a_wp": a_wp_pct, "h_ev": r["h_ev"], "a_ev": r["a_ev"]},
    dist_label="综合相似度", top_n=15,
    event_level=r["event_level"], restrict_level=restrict,
)

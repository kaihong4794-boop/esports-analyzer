# ============================================================
# analyze.py — 甜蜜点分析脚本
# 使用方法：python3 analyze.py your_data.pdf
# ============================================================

import sys
import re
import pdfplumber

# ─── 解析PDF ─────────────────────────────────────────────────
def load_data(pdf_path):
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith('2026'):
                    all_rows.append(line)
    return all_rows

def parse_row(line):
    parts = line.split()
    if len(parts) < 6: return None
    sport = parts[1]
    signed_pct = re.findall(r'[+-]\d+\.\d+%', line)
    unsigned_pcts = [float(x) for x in re.findall(r'(?<![+-])(\d+\.\d+)%', line)]
    line_no_pct = re.sub(r'[+-]?\d+\.\d+%', 'PCT', line)
    ev_nums = [float(x) for x in re.findall(r'([+-]?\d+\.\d+)', line_no_pct) if abs(float(x)) <= 700]
    has_adv = len(signed_pct) > 0
    result_match = re.search(r'\b(\d+)-(\d+)\b', line[-30:])
    if has_adv:
        home_wp = unsigned_pcts[0] if len(unsigned_pcts) >= 1 else None
        away_wp = unsigned_pcts[2] if len(unsigned_pcts) >= 3 else None
        home_ev = ev_nums[0] if len(ev_nums) >= 1 else None
        away_ev = ev_nums[2] if len(ev_nums) >= 3 else None
    else:
        home_wp = unsigned_pcts[0] if len(unsigned_pcts) >= 1 else None
        away_wp = unsigned_pcts[1] if len(unsigned_pcts) >= 2 else None
        home_ev = ev_nums[0] if len(ev_nums) >= 1 else None
        away_ev = ev_nums[1] if len(ev_nums) >= 2 else None
    return {
        'sport': sport,
        'home': parts[2], 'away': parts[3],
        'home_wp': home_wp, 'away_wp': away_wp,
        'home_ev': home_ev, 'away_ev': away_ev,
        'result': result_match.group() if result_match else '',
        'home_win': int(result_match.group(1)) > int(result_match.group(2)) if result_match else None,
        'away_win': int(result_match.group(2)) > int(result_match.group(1)) if result_match else None,
        'draw': result_match.group(1) == result_match.group(2) if result_match else None,
        'date': parts[0], 'line': line
    }

# ─── 甜蜜点条件（完全对应 app.py）────────────────────────────
def check_football_spots(h_wp, a_wp, h_ev, a_ev):
    spots = []
    if h_wp >= 50 and -40 <= h_ev <= -20:   spots.append("F1精准主")
    elif h_wp >= 40 and -40 <= h_ev <= -20:  spots.append("F1主")
    elif h_wp >= 30 and -40 <= h_ev <= -20:  spots.append("F2主→押平局")
    if a_wp >= 50 and -40 <= a_ev <= -20:    spots.append("F1精准客")
    elif a_wp >= 40 and -40 <= a_ev <= -20:  spots.append("F1客")
    elif a_wp >= 30 and -40 <= a_ev <= -20:  spots.append("F2客→押平局")
    if h_wp + a_wp >= 110:                   spots.append(f"F3({h_wp+a_wp:.0f}%)")
    if a_ev > 60:                            spots.append(f"W1↩主({a_ev:.0f})")
    if h_ev > 100:                           spots.append(f"W1↩客({h_ev:.0f})")
    if h_ev <= -99.9 and 10 <= a_wp <= 29:   spots.append(f"W2↩客({a_wp:.0f}%)")
    if a_ev <= -99.9 and 10 <= h_wp <= 29:   spots.append(f"W2↩主({h_wp:.0f}%)")
    return spots

def check_esports_spots(h_wp, a_wp, h_ev, a_ev):
    spots = []
    diff_h = h_wp - a_wp
    diff_a = a_wp - h_wp
    if h_wp >= 60 and -50 <= h_ev <= 0:      spots.append("E1主")
    if a_wp >= 60 and -50 <= a_ev <= 0:      spots.append("E1客")
    if h_wp >= 55 and -50 <= h_ev <= -10 and not (h_wp >= 60 and -50 <= h_ev <= 0):
        spots.append("E2主")
    if a_wp >= 55 and -50 <= a_ev <= -10 and not (a_wp >= 60 and -50 <= a_ev <= 0):
        spots.append("E2客")
    if h_wp >= 50 and diff_h >= 10:          spots.append(f"E3主(+{diff_h:.0f}%)")
    if a_wp >= 50 and diff_a >= 10:          spots.append(f"E3客(+{diff_a:.0f}%)")
    low_wp  = min(h_wp, a_wp)
    high_wp = max(h_wp, a_wp)
    gap = high_wp - low_wp
    if 30 <= low_wp <= 49 and gap <= 20:
        if h_wp == low_wp and h_ev < 0:      spots.append("E4主")
        elif a_wp == low_wp and a_ev < 0:    spots.append("E4客")
    if h_ev > 40:                            spots.append(f"W1↩客({h_ev:.0f})")
    if a_ev > 30:                            spots.append(f"W1↩主({a_ev:.0f})")
    if h_ev <= -99.9 and 10 <= a_wp <= 29:   spots.append(f"W2↩客({a_wp:.0f}%)")
    if a_ev <= -99.9 and 10 <= h_wp <= 29:   spots.append(f"W2↩主({h_wp:.0f}%)")
    return spots

# ─── 统计函数 ──────────────────────────────────────────────────
def stat(data, cond, win_field, min_n=5):
    m = [r for r in data if cond(r) and r.get(win_field) is not None]
    if len(m) < min_n: return None
    w = sum(1 for r in m if r[win_field])
    d = sum(1 for r in m if r.get('draw')) if win_field != 'draw' else w
    return len(m), w, w / len(m) * 100

def stat3(data, cond):
    """返回主赢/平局/客赢三方向"""
    m = [r for r in data if cond(r) and r.get('home_win') is not None]
    if not m: return None
    hw = sum(1 for r in m if r['home_win'])
    d  = sum(1 for r in m if r['draw'])
    aw = sum(1 for r in m if r['away_win'])
    return len(m), hw, d, aw

def star(rate):
    if rate >= 85: return "⭐⭐⭐"
    if rate >= 75: return "⭐⭐"
    if rate >= 65: return "⭐"
    return ""

# ─── 主分析 ───────────────────────────────────────────────────
def run_analysis(pdf_path):
    print(f"\n{'='*65}")
    print(f"  甜蜜点分析报告")
    print(f"  数据来源: {pdf_path}")
    print(f"{'='*65}\n")

    rows_raw = load_data(pdf_path)
    rows = [r for r in [parse_row(l) for l in rows_raw] if r]

    fb = [r for r in rows if r['sport'] == '足球'
          and all(r.get(k) is not None for k in ['home_wp','away_wp','home_ev','away_ev'])
          and r['home_win'] is not None]
    es = [r for r in rows if r['sport'] == '电竞'
          and all(r.get(k) is not None for k in ['home_wp','away_wp','home_ev','away_ev'])
          and r['home_win'] is not None]

    print(f"📊 数据概况")
    print(f"   总场次: {len(rows)}  |  足球: {len(fb)}场  |  电竞: {len(es)}场")
    print(f"   时段: {rows[0]['date']} 至 {rows[-1]['date']}\n")

    # ── 足球甜蜜点 ──────────────────────────────────────────────
    print(f"{'='*65}")
    print(f"⚽ 足球甜蜜点")
    print(f"{'='*65}")
    print(f"\n{'代号':<18} {'方向':<10} {'场数':>5} {'主赢%':>7} {'平局%':>7} {'客赢%':>7} {'建议押':<10} {'评级'}")
    print("-"*72)

    fb_spots = [
        ("F1精准主",  lambda r: r['home_wp']>=50 and -40<=r['home_ev']<=-20),
        ("F1标准主",  lambda r: 40<=r['home_wp']<50 and -40<=r['home_ev']<=-20),
        ("F1精准客",  lambda r: r['away_wp']>=50 and -40<=r['away_ev']<=-20),
        ("F1标准客",  lambda r: 40<=r['away_wp']<50 and -40<=r['away_ev']<=-20),
        ("F2主",      lambda r: 30<=r['home_wp']<=39 and -40<=r['home_ev']<=-20),
        ("F3总WP≥110%", lambda r: r['home_wp']+r['away_wp']>=110),
        ("W1↩主(客EV>60)", lambda r: r['away_ev']>60),
        ("W1↩客(主EV>100)", lambda r: r['home_ev']>100),
        ("W2↩客(主EV=-100)", lambda r: r['home_ev']<=-99.9 and 10<=r['away_wp']<=29),
    ]

    for label, cond in fb_spots:
        res = stat3(fb, cond)
        if not res: continue
        n, hw, d, aw = res
        if n < 5: continue
        best_rate = max(hw, d, aw) / n * 100
        if hw >= d and hw >= aw:   best = f"押主队 {hw/n*100:.0f}%"
        elif d >= hw and d >= aw:  best = f"押平局 {d/n*100:.0f}%"
        else:                      best = f"押客队 {aw/n*100:.0f}%"
        print(f"{label:<18} {'足球':<10} {n:>5}  {hw/n*100:>6.1f}%  {d/n*100:>6.1f}%  {aw/n*100:>6.1f}%  {best:<12} {star(best_rate)}")

    # ── 电竞甜蜜点 ──────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"🎮 电竞甜蜜点（无主客场之分）")
    print(f"{'='*65}")
    print(f"\n{'代号':<20} {'场数':>5} {'强队赢%':>8} {'弱队赢%':>8} {'建议押':<12} {'评级'}")
    print("-"*60)

    es_spots = [
        ("E1(WP≥60%+EV-50~0)",
         lambda r: r['home_wp']>=60 and -50<=r['home_ev']<=0,
         lambda r: r['away_wp']>=60 and -50<=r['away_ev']<=0),
        ("E2(WP≥55%+EV-50~-10)",
         lambda r: r['home_wp']>=55 and -50<=r['home_ev']<=-10 and not(r['home_wp']>=60 and -50<=r['home_ev']<=0),
         lambda r: r['away_wp']>=55 and -50<=r['away_ev']<=-10 and not(r['away_wp']>=60 and -50<=r['away_ev']<=0)),
        ("E3(WP≥50%+差距≥10%)",
         lambda r: r['home_wp']>=50 and (r['home_wp']-r['away_wp'])>=10,
         lambda r: r['away_wp']>=50 and (r['away_wp']-r['home_wp'])>=10),
        ("E4(低WP爆冷30~49%差距≤20%)",
         lambda r: 30<=r['home_wp']<=49 and (max(r['home_wp'],r['away_wp'])-min(r['home_wp'],r['away_wp']))<=20 and r['home_wp']==min(r['home_wp'],r['away_wp']) and r['home_ev']<0,
         lambda r: 30<=r['away_wp']<=49 and (max(r['home_wp'],r['away_wp'])-min(r['home_wp'],r['away_wp']))<=20 and r['away_wp']==min(r['home_wp'],r['away_wp']) and r['away_ev']<0),
        ("W1↩(主EV>40反买客)",
         lambda r: r['home_ev']>40,
         None),
        ("W1↩(客EV>30反买主)",
         None,
         lambda r: r['away_ev']>30),
    ]

    for label, cond_h, cond_a in es_spots:
        strong_wins = strong_total = weak_wins = weak_total = 0
        for r in es:
            if r['home_win'] is None: continue
            if cond_h and cond_h(r):
                strong_total += 1
                if r['home_win']: strong_wins += 1
            if cond_a and cond_a(r):
                strong_total += 1
                if r['away_win']: strong_wins += 1
        if strong_total < 5: continue
        strong_rate = strong_wins / strong_total * 100
        weak_rate = 100 - strong_rate
        print(f"{label:<20} {strong_total:>5}  {strong_rate:>7.1f}%  {weak_rate:>7.1f}%  {'押强队' if strong_rate>=60 else '押弱队':<12} {star(strong_rate)}")

    # ── 逆向思维发现 ─────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"🔄 逆向思维发现（足球）")
    print(f"{'='*65}")
    print(f"\n{'条件':<35} {'场数':>5} {'主赢%':>7} {'平局%':>7} {'客赢%':>7} {'最优'}")
    print("-"*68)

    reverse = [
        ("F2主 → 考虑押平局",         lambda r: 30<=r['home_wp']<=39 and -40<=r['home_ev']<=-20),
        ("主WP>客WP但主EV<客EV",      lambda r: r['home_wp']>r['away_wp'] and r['home_ev']<r['away_ev']),
        ("两队WP都在30~50%",           lambda r: 30<=r['home_wp']<=50 and 30<=r['away_wp']<=50),
        ("W2↩主（客EV=-100+主WP低）",  lambda r: r['away_ev']<=-99.9 and 10<=r['home_wp']<=29),
    ]

    for label, cond in reverse:
        res = stat3(fb, cond)
        if not res: continue
        n, hw, d, aw = res
        if n < 5: continue
        best_rate = max(hw, d, aw) / n * 100
        if hw >= d and hw >= aw:   best = f"押主 {hw/n*100:.0f}%"
        elif d >= hw and d >= aw:  best = f"押平 {d/n*100:.0f}% ⚠️"
        else:                      best = f"押客 {aw/n*100:.0f}%"
        print(f"{label:<35} {n:>5}  {hw/n*100:>6.1f}%  {d/n*100:>6.1f}%  {aw/n*100:>6.1f}%  {best}")

    # ── 赔率盈亏平衡 ─────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"💰 赔率盈亏平衡（你的范围 1.30 ~ 2.50）")
    print(f"{'='*65}\n")
    print(f"{'赔率':>6}  {'需要最低胜率':>12}  {'F1精准91%':>10}  {'E系列80%':>10}  {'W1↩67%':>10}")
    print("-"*58)
    for odds in [1.30, 1.50, 1.70, 1.90, 2.00, 2.20, 2.50]:
        min_rate = 1 / odds * 100
        f1  = "✅赚" if 91 > min_rate else "❌亏"
        e   = "✅赚" if 80 > min_rate else "❌亏"
        w1  = "✅赚" if 67 > min_rate else "❌亏"
        print(f"{odds:>6.2f}  {min_rate:>11.1f}%  {f1:>10}  {e:>10}  {w1:>10}")

    # ── 总结建议 ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"📋 总结建议")
    print(f"{'='*65}")
    print("""
  ✅ 最可靠：E系列（E1/E2/E3）80-85%，任何赔率都赚
  ✅ 最精准：F1精准（WP≥50%）91%，但场次少
  ⚠️  注意：F2 应该押平局（53%），不是押主队赢
  ⚠️  注意：W1↩ 足球赔率需 ≥1.55 才有正期望
  ❌ 避免：1.30赔率只适合 E系列 和 F1精准
  ❌ 避免：没有甜蜜点触发就不下注
    """)

# ─── 入口 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python3 analyze.py your_data.pdf")
        sys.exit(1)
    run_analysis(sys.argv[1])

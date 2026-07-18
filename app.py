"""
一次性迁移脚本
把 sheet1 里已经用新算法写入、但错位对不上旧表头的记录
（特征：A列是8位hex比赛ID，比如 19d67044）
搬到新分页「比赛记录_v2」，并从 sheet1 删除这些行。

运行前请先手动备份一下 Google Sheet（File > Make a copy），
脚本会真的删除 sheet1 里的行，删完不可撤销（除非你有备份）。

用法：
    python migrate_new_records.py            # 先 dry-run，只打印要迁移的行，不做任何修改
    python migrate_new_records.py --apply     # 确认无误后正式执行迁移+删除
"""

import sys
import re
import json
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1LWzu7jwRan5-WSGhWUxnmwCLJ0iyxhVH07bLojGD-3s"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

HEADERS = [
    "比赛ID", "日期", "运动", "赛事级别", "主队", "客队",
    "主WP", "平WP", "客WP",
    "主EV", "平EV", "客EV",
    "主隐含概率", "平隐含概率", "客隐含概率",
    "历史参考样本数", "样本置信度",
    "甜蜜点触发", "预测方向",
    "比赛结果", "预测命中",
]

# 匹配 new_match_id() 生成的格式：uuid4().hex[:8]，8位小写十六进制
ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def get_client(credentials_path):
    with open(credentials_path, "r", encoding="utf-8") as f:
        credentials_info = json.load(f)
    creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_v2(spreadsheet):
    try:
        return spreadsheet.worksheet("比赛记录_v2")
    except Exception:
        ws = spreadsheet.add_worksheet(title="比赛记录_v2", rows=2000, cols=len(HEADERS) + 2)
        ws.append_row(HEADERS)
        return ws


def find_new_format_rows(sheet1):
    """
    扫描 sheet1 所有行，找出 A列是8位hex ID 的行
    （这些就是新算法误写进旧表的记录）
    返回 [(row_number, raw_values)]，row_number 是 sheet 里的实际行号（从1开始，含表头）
    """
    all_values = sheet1.get_all_values()
    matches = []
    for i, row in enumerate(all_values, start=1):
        if not row:
            continue
        first_cell = row[0].strip()
        if ID_PATTERN.match(first_cell):
            matches.append((i, row))
    return matches


def row_to_record(raw_row):
    """
    把错位存储的原始行（按你截图看到的列顺序）转换回 HEADERS 对应的字典。
    根据截图，错位后的实际存储顺序大致是：
    比赛ID, 日期, 运动, 赛事级别, 主队, 客队,
    主WP, (跳过一列), 客WP,
    主EV, (跳过一列), 客EV,
    ...
    但由于是 append_row 按 HEADERS 顺序整段写入的，
    实际上这一整行本身就是完整的21个值，只是"表头文字"对不上——
    数据本身没错位，只需要按 HEADERS 顺序直接 zip 即可。
    """
    values = list(raw_row) + [""] * (len(HEADERS) - len(raw_row))
    values = values[:len(HEADERS)]
    return dict(zip(HEADERS, values))


def main():
    apply_changes = "--apply" in sys.argv
    credentials_path = "credentials.json"  # 改成你本地服务账号json的路径

    client = get_client(credentials_path)
    spreadsheet = client.open_by_key(SHEET_ID)
    sheet1 = spreadsheet.sheet1
    v2 = get_or_create_v2(spreadsheet)

    found = find_new_format_rows(sheet1)

    if not found:
        print("没有找到需要迁移的行（A列没有8位hex ID的记录）。")
        return

    print(f"找到 {len(found)} 行需要迁移：\n")
    for row_num, raw in found:
        record = row_to_record(raw)
        print(f"  行{row_num}: {record['比赛ID']} | {record['日期']} | "
              f"{record['运动']} | {record['主队']} vs {record['客队']}")

    if not apply_changes:
        print("\n这是 dry-run，没有做任何修改。确认无误后加 --apply 参数正式执行。")
        return

    # 正式迁移：先全部写入 v2，成功后再从 sheet1 删除（倒序删，避免行号错位）
    print("\n开始写入 比赛记录_v2 ...")
    for row_num, raw in found:
        record = row_to_record(raw)
        v2.append_row([record.get(h, "") for h in HEADERS])
    print(f"已写入 {len(found)} 行到 比赛记录_v2。")

    print("开始从 sheet1 删除已迁移的行...")
    for row_num, _ in sorted(found, key=lambda x: x[0], reverse=True):
        sheet1.delete_rows(row_num)
    print(f"已从 sheet1 删除 {len(found)} 行。")

    print("\n迁移完成！")


if __name__ == "__main__":
    main()

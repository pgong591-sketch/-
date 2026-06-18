"""将硬编码的 SHORT_NAME_MAP 写入 company_aliases 表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import get_session
from sqlalchemy import text

# 从 reports.py 提取的 SHORT_NAME_MAP（保持与代码一致）
SHORT_NAME_MAP = {
    "管理中心": "101",
    "非学科管理中心": "1010101",
    "南城华凯": "101010102",
    "深圳卓越": "1010201",
    "东莞国际校区": "101020101",
    "莞城小学": "101010120", "莞城高中": "101010121",
    "莞城初中": "101010128", "莞城个性化": "101010129",
    "拔创中心": "101010136",
    # 尔遇书馆分支
    "尔遇书馆东城天骄": "1020403",
    "尔遇书馆东城星城": "1020405",
    "尔遇书馆东城": "1020403",
    "尔遇书馆莞城鸿福": "1020401",
    "尔遇书馆莞城西城楼": "1020408",
    "尔遇书馆莞城": "1020401",
    "尔遇书馆西平荣郡": "1020402",
    "尔遇书馆西平": "1020402",
    "尔遇书馆南城金域": "1020404",
    "尔遇书馆南城翡丽山": "1020407",
    "尔遇书馆南城": "1020404",
    "尔遇书馆万江龙景": "1020406",
    "尔遇书馆万江": "1020406",
    # 尔遇书馆简称
    "尔遇书馆翡丽山": "1020407",
    "尔遇书馆天骄": "1020403",
    "尔遇书馆星城": "1020405",
    "尔遇书馆鸿福": "1020401",
    "尔遇书馆西城楼": "1020408",
    "尔遇书馆荣郡": "1020402",
    "尔遇书馆金域": "1020404",
    "尔遇书馆龙景": "1020406",
    "尔遇书馆管理中心": "10204",
    "书馆管理中心": "10204",
    # 纯地名简称
    "东城天骄": "1020403",
    "东城星城": "1020405",
    "莞城鸿福": "1020401",
    "西平荣郡": "1020402",
    "南城金域": "1020404",
    "万江龙景": "1020406",
    "南城翡丽山": "1020407",
    "莞城西城楼": "1020408",
    # 合并报表中的名称
    "南城宏图": "101010117",
    "素质管理中心": "1010101",
    "东莞国际": "101020101",
    # 地名简称（避免模糊匹配误匹配）
    "万江": "101010104",
    "西平": "101010106",
    "厚街": "101010110",
    "石碣": "101010111",
    "虎门": "101010112",
    "石井": "101010113",
    "东泰": "101010116",
    "石龙": "101010103",
    "寮步": "101010130",
    "茶山": "101010131",
    "长安": "101010134",
    "高埗": "101010135",
    "虎翼营": "101010123",
    "宏图": "101010117",
    "南城": "101010133",
}

def migrate_aliases() -> tuple[int, int]:
    """Write legacy short-name mappings into company_aliases."""
    session = get_session()

    existing = session.execute(text("SELECT alias FROM company_aliases")).fetchall()
    existing_set = {r[0] for r in existing}

    inserted = 0
    skipped = 0
    for alias, code in SHORT_NAME_MAP.items():
        if alias in existing_set:
            skipped += 1
            continue
        session.execute(
            text("INSERT INTO company_aliases (alias, company_code, source) VALUES (:a, :c, 'config')"),
            {"a": alias, "c": code}
        )
        inserted += 1

    session.commit()
    session.close()
    return inserted, skipped


def main() -> None:
    inserted, skipped = migrate_aliases()
    print(f"新增 {inserted} 条别名，跳过 {skipped} 条已存在的")
    print("完成！")


if __name__ == "__main__":
    main()

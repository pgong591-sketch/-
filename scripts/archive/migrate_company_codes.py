"""迁移旧数据：将 account_balance 中的公司简称映射为正确的公司编码"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import execute_sql, get_session
from sqlalchemy import text

# 完整映射表（简称 → 正式编码）
NAME_TO_CODE = {
    "万江": "101010104", "东泰": "101010116",
    "南城华凯": "101010102", "南城虎翼营": "101010133",
    "厚街": "101010110", "宏图": "101010117",
    "寮步": "101010130", "拔创中心": "101010136",
    "石井": "101010113", "石碣": "101010111",
    "石龙": "101010103", "西平": "101010106",
    "西平三和": "101010132", "长安": "101010134",
    "高埗": "101010135", "虎门": "101010112",
    "茶山学前": "101010131", "虎翼营": "101010123",
    "非学科管理中心": "1010101",
    "管理中心": "10101",
    "莞城小学": "101010120", "莞城小学部": "101010120",
    "莞城初中": "101010128", "莞城初中部": "101010128",
    "莞城高中": "101010121", "莞城高中部": "101010121",
    "莞城个性化": "101010129",
    "尔遇书馆东城": "1020403",
    "尔遇书馆星城": "1020405",
    "尔遇书馆翡丽山": "1020407",
    "尔遇书馆莞城": "1020401",
    "尔遇书馆西城楼": "1020408",
    "尔遇书馆西平": "1020402",
    "尔遇书馆金域": "1020404",
    "尔遇书馆龙景": "1020406",
    "尔遇书馆管理中心": "10204",
    "东莞国际校区": "10102", "深圳卓越": "102",
    "多维学校": "1010801", "莞城青少年宫": "1011801",
    "青少年宫": "10118",
    "幼儿园": "10107", "新阳光幼儿园": "1010702",
    "托育": "1010703", "茶山托育": "1010703",
    "探幽文旅": "10121",
    "松山湖": "101010138",
}

session = get_session()
updated = 0
skipped = []

old_codes = execute_sql("SELECT DISTINCT company_code FROM account_balance")
for _, row in old_codes.iterrows():
    old_code = str(row["company_code"]).strip()
    if old_code.isdigit() or old_code == "ROOT":
        continue

    new_code = NAME_TO_CODE.get(old_code)
    if not new_code:
        for key, val in NAME_TO_CODE.items():
            if key in old_code or old_code in key:
                new_code = val
                break

    if new_code:
        try:
            # 删掉目标编码下已有的同期数据，避免唯一键冲突
            session.execute(text(
                "DELETE FROM account_balance WHERE company_code = :new AND period IN "
                "(SELECT DISTINCT period FROM account_balance WHERE company_code = :old)"
            ), {"new": new_code, "old": old_code})
            session.execute(
                text("UPDATE account_balance SET company_code = :new WHERE company_code = :old"),
                {"new": new_code, "old": old_code}
            )
            print(f"  ✅ {old_code:20s} → {new_code}")
            updated += 1
        except Exception as e:
            print(f"  ⚠️ {old_code:20s} 失败: {e}")
            skipped.append(old_code)
    else:
        print(f"  ❌ {old_code:20s} → 无映射")
        skipped.append(old_code)

session.commit()
session.close()
print(f"\n✅ 更新 {updated} 个")
if skipped:
    print(f"❌ 跳过 {len(skipped)} 个: {skipped}")

ab = execute_sql("SELECT DISTINCT company_code FROM account_balance ORDER BY company_code")
print(f"\n更新后共 {len(ab)} 个公司编码:")
for _, r in ab.iterrows():
    print(f"  {r['company_code']}")


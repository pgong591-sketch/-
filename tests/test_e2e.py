"""
端到端集成测试

验证数据库初始化、数据插入、查询和报表生成的完整流程。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import init_database, execute_sql, get_session
from src.reports import get_account_balance, get_balance_sheet, get_companies
from sqlalchemy import text


def test_full_pipeline():
    """测试完整数据流程"""
    print("=" * 60)
    print("📋 端到端集成测试")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n1️⃣  初始化数据库...")
    init_database()
    print("   ✅ 数据库初始化完成")

    # 2. 插入测试公司
    print("\n2️⃣  插入测试公司...")
    session = get_session()

    companies_data = [
        ("GD", "广东事业部", None, 1, 1),
        ("DG001", "东莞XX学校", "GD", 3, 1),
        ("DG002", "东莞YY学校", "GD", 3, 1),
    ]

    for code, name, parent, level, consolidated in companies_data:
        session.execute(
            text("""INSERT OR IGNORE INTO companies
                    (code, name, parent_code, level, is_consolidated)
                    VALUES (:code, :name, :parent, :level, :consolidated)"""),
            {"code": code, "name": name, "parent": parent,
             "level": level, "consolidated": consolidated}
        )
    session.commit()
    print("   ✅ 测试公司插入完成")

    # 3. 插入科目余额数据
    print("\n3️⃣  插入科目余额测试数据...")

    balance_data = [
        # (company, period, code, name, opening, debit, credit, ending, direction)
        # DG001 试算平衡：借方总额=385000, 贷方总额=385000 ✓
        ("DG001", "202603", "1001", "库存现金", 10000, 5000, 3000, 12000, "借"),
        ("DG001", "202603", "1002", "银行存款", 500000, 200000, 50000, 650000, "借"),
        ("DG001", "202603", "2001", "应付账款", 200000, 30000, 132000, 302000, "贷"),
        ("DG001", "202603", "3001", "实收资本", 500000, 0, 0, 500000, "贷"),
        ("DG001", "202603", "4001", "主营业务收入", 0, 0, 200000, 200000, "贷"),
        ("DG001", "202603", "5001", "主营业务成本", 0, 120000, 0, 120000, "借"),
        ("DG001", "202603", "6001", "管理费用", 0, 30000, 0, 30000, "借"),
    ]

    for row in balance_data:
        session.execute(
            text("""INSERT OR REPLACE INTO account_balance
                    (company_code, period, account_code, account_name,
                     opening_balance, debit_amount, credit_amount, ending_balance, direction)
                    VALUES (:company, :period, :code, :name,
                            :opening, :debit, :credit, :ending, :direction)"""),
            {"company": row[0], "period": row[1], "code": row[2],
             "name": row[3], "opening": row[4], "debit": row[5],
             "credit": row[6], "ending": row[7], "direction": row[8]}
        )
    session.commit()
    print("   ✅ 科目余额测试数据插入完成")
    session.close()

    # 4. 查询验证
    print("\n4️⃣  查询验证...")

    # 4.1 公司列表
    companies = get_companies()
    print(f"\n   公司列表 ({len(companies)} 家):")
    for _, row in companies.iterrows():
        print(f"     {row['code']} - {row['name']}")

    # 4.2 科目余额查询
    balance = get_account_balance(company_code="DG001", period="202603")
    print(f"\n   DG001 202603 科目余额 ({len(balance)} 条):")
    for _, row in balance.iterrows():
        print(f"     {row['account_code']} {row['account_name']}: "
              f"期初={row['opening_balance']:,.2f} → 期末={row['ending_balance']:,.2f}")

    # 4.3 资产负债表
    print("\n5️⃣  测试报表生成...")
    bs = get_balance_sheet(company_code="DG001", period="202603", use_template=True)
    if bs is not None:
        print(f"   资产负债表: {len(bs)} 行")
    else:
        print("   资产负债表: 暂无模板数据（可接受）")

    # 5. 验证借贷平衡
    print("\n6️⃣  验证借贷平衡...")
    df = execute_sql("""
        SELECT
            SUM(debit_amount) as total_debit,
            SUM(credit_amount) as total_credit
        FROM account_balance
        WHERE company_code = 'DG001' AND period = '202603'
    """)
    row = df.iloc[0]
    debit_credit_ok = abs(row["total_debit"] - row["total_credit"]) < 0.01
    print(f"   借方合计: {row['total_debit']:,.2f}")
    print(f"   贷方合计: {row['total_credit']:,.2f}")
    print(f"   {'✅ 借贷平衡' if debit_credit_ok else '❌ 借贷不平衡'}")

    # 汇总
    print(f"\n{'=' * 60}")
    if debit_credit_ok:
        print("✅ 所有端到端测试通过！")
    else:
        print("❌ 测试未完全通过")


if __name__ == "__main__":
    test_full_pipeline()

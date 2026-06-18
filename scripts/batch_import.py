"""
批量导入脚本

扫描指定目录中的所有 Excel 文件，自动识别报表类型并导入数据库。

用法：
    python scripts/batch_import.py --dir data/excel_files [--company ALL]
    python scripts/batch_import.py --file data/excel_files/xxx.xlsx --type "科目余额表"
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_connection import init_database
from src.reports import import_excel_to_db
from src.import_parser import identify_report_type
from src.models import REPORT_TYPES_CN


def import_single_file(file_path: str, report_type: str = None,
                       company: str = None, period: str = None):
    """导入单个文件"""
    print(f"\n{'='*60}")
    print(f"📄 导入文件: {file_path}")
    print(f"{'='*60}")

    result = import_excel_to_db(
        file_path=file_path,
        company_code=company,
        period=period,
        report_type=report_type,
    )

    # 输出结果
    status_icon = "✅" if result.get("success") else "❌"
    print(f"\n{status_icon} 导入结果: {'成功' if result.get('success') else '失败'}")
    print(f"  报表类型: {result.get('report_type', '未知')}")
    print(f"  批次号: {result.get('batch_no', '')}")

    for step in result.get("steps", []):
        step_name = step.get("step", "")
        if step_name == "解析":
            info = step.get("info", {})
            rows = info.get("rows", 0)
            print(f"  📊 解析: {rows} 行")
        elif step_name == "校验":
            errors = step.get("errors", [])
            warnings = step.get("warnings", [])
            valid = step.get("is_valid", False)
            print(f"  🔍 校验: {'通过' if valid else '失败'}")
            for e in errors[:3]:
                print(f"    ⛔ {e}")
            for w in warnings[:3]:
                print(f"    ⚠️  {w}")
        elif step_name == "写入":
            info = step.get("info", {})
            print(f"  💾 写入: {info.get('inserted_rows', 0)} 新增, {info.get('updated_rows', 0)} 更新")

    if result.get("error"):
        print(f"  ❌ 错误: {result['error']}")

    return result.get("success", False)


def import_directory(dir_path: str, company: str = None, period: str = None):
    """批量导入目录中的所有 Excel 文件"""
    dir_path = Path(dir_path)
    if not dir_path.exists():
        print(f"❌ 目录不存在: {dir_path}")
        return

    excel_files = list(dir_path.glob("*.xlsx")) + list(dir_path.glob("*.xls"))
    if not excel_files:
        print(f"⚠️  目录中没有找到 Excel 文件: {dir_path}")
        return

    print(f"\n📂 在 {dir_path} 中找到 {len(excel_files)} 个 Excel 文件")
    print(f"开始批量导入...\n")

    success_count = 0
    fail_count = 0

    for file_path in excel_files:
        try:
            ok = import_single_file(str(file_path), company=company, period=period)
            if ok:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"  ❌ 导入异常: {e}")
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"📊 批量导入完成: 成功 {success_count}, 失败 {fail_count}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="财务数据批量导入工具")
    parser.add_argument("--dir", type=str, help="包含 Excel 文件的目录路径")
    parser.add_argument("--file", type=str, help="单个 Excel 文件路径")
    parser.add_argument("--type", type=str, help="报表类型（自动识别时可不填）",
                        choices=REPORT_TYPES_CN)
    parser.add_argument("--company", type=str, help="公司编码")
    parser.add_argument("--period", type=str, help="期间 YYYYMM")
    parser.add_argument("--init-db", action="store_true", help="导入前初始化数据库")

    args = parser.parse_args()

    # 初始化数据库
    if args.init_db:
        print("🔄 初始化数据库...")
        init_database()

    if args.file:
        import_single_file(args.file, args.type, args.company, args.period)
    elif args.dir:
        import_directory(args.dir, args.company, args.period)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

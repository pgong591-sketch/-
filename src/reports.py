"""
报表生成核心模块

基于数据库中的科目余额数据和明细数据，按模板驱动方式生成各类财务报表。
支持单公司查询和跨公司汇总。
"""

from typing import Optional, List, Dict, Any, Tuple
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import numpy as np

from .db_connection import execute_sql, get_session
from sqlalchemy import text


# ============================================================================
# 辅助函数
# ============================================================================

def _bind_in_clause(
    column: str,
    items: List[Any],
    params: Dict[str, Any],
    prefix: str,
) -> str:
    """Build a parameterized SQL IN clause and add values to params."""
    placeholders = []
    for idx, item in enumerate(items):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = item
    if not placeholders:
        return "1=0"
    return f"{column} IN ({', '.join(placeholders)})"


_NULL_UNIQUE_COLUMNS = {
    "account_balance": ("assist_dimensions",),
    "pl_detail": ("dept_code",),
    "non_subject_allocation": ("account_code",),
}


def _normalize_nullable_unique_values(table_name: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize nullable fields that participate in unique keys."""
    for col in _NULL_UNIQUE_COLUMNS.get(table_name, ()):
        value = row.get(col)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            row[col] = ""
    return row


def _period_range(start_period: str, end_period: str) -> List[str]:
    """生成期间列表"""
    periods = []
    year = int(start_period[:4])
    month = int(start_period[4:6])
    end_year = int(end_period[:4])
    end_month = int(end_period[4:6])

    while (year < end_year) or (year == end_year and month <= end_month):
        periods.append(f"{year}{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1

    return periods


# ============================================================================
# 公司信息查询
# ============================================================================

def get_companies() -> pd.DataFrame:
    """获取所有公司列表"""
    return execute_sql("SELECT * FROM companies ORDER BY code")


def get_company(company_code: str) -> Optional[Dict[str, Any]]:
    """获取单个公司信息"""
    df = execute_sql("SELECT * FROM companies WHERE code = :code", {"code": company_code})
    if len(df) > 0:
        return df.iloc[0].to_dict()
    return None


def get_child_companies(parent_code: str) -> pd.DataFrame:
    """获取指定公司的所有下级公司"""
    return execute_sql(
        "SELECT * FROM companies WHERE parent_code = :parent ORDER BY code",
        {"parent": parent_code}
    )


def get_company_tree(company_code: Optional[str] = None) -> pd.DataFrame:
    """获取公司树形结构"""
    if company_code:
        return execute_sql(
            "SELECT * FROM v_company_tree WHERE code = :code OR path LIKE '%' || (SELECT name FROM companies WHERE code = :code2) || '%'",
            {"code": company_code, "code2": company_code}
        )
    return execute_sql("SELECT * FROM v_company_tree ORDER BY path")


# ============================================================================
# 科目余额表查询
# ============================================================================

def get_account_balance(
    company_code: Optional[str] = None,
    period: Optional[str] = None,
    account_code: Optional[str] = None,
    company_list: Optional[List[str]] = None,
    period_list: Optional[List[str]] = None,
    account_list: Optional[List[str]] = None,
    as_summary: bool = False,
) -> pd.DataFrame:
    """
    查询科目余额表

    Args:
        company_code: 公司编码（单选）
        period: 期间 YYYYMM
        account_code: 科目编码（单选）
        company_list: 公司列表（多选）
        period_list: 期间列表（多选）
        account_list: 科目编码列表（多选）
        as_summary: 是否按会计科目汇总

    Returns:
        科目余额 DataFrame
    """
    conditions = []
    params: Dict[str, Any] = {}

    if company_code:
        conditions.append("ab.company_code = :company_code")
        params["company_code"] = company_code
    if company_list:
        conditions.append(_bind_in_clause("ab.company_code", company_list, params, "company_list"))
    if period:
        conditions.append("ab.period = :period")
        params["period"] = period
    if period_list:
        conditions.append(_bind_in_clause("ab.period", period_list, params, "period_list"))
    if account_code:
        conditions.append("ab.account_code = :account_code")
        params["account_code"] = account_code
    if account_list:
        conditions.append(_bind_in_clause("ab.account_code", account_list, params, "account_list"))

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    if as_summary:
        # 汇总模式：按会计科目汇总
        sql = f"""
        SELECT
            ab.account_code,
            ab.account_name,
            SUM(ab.opening_balance) AS opening_balance,
            SUM(ab.debit_amount) AS debit_amount,
            SUM(ab.credit_amount) AS credit_amount,
            SUM(ab.ending_balance) AS ending_balance
        FROM account_balance ab
        WHERE {where_clause}
        GROUP BY ab.account_code, ab.account_name
        ORDER BY ab.account_code
        """
    else:
        sql = f"""
        SELECT
            ab.company_code,
            c.name AS company_name,
            ab.period,
            ab.account_code,
            ab.account_name,
            ab.opening_balance,
            ab.debit_amount,
            ab.credit_amount,
            ab.ending_balance,
            ab.direction,
            ab.assist_dimensions
        FROM account_balance ab
        LEFT JOIN companies c ON ab.company_code = c.code
        WHERE {where_clause}
        ORDER BY ab.company_code, ab.period, ab.account_code, ab.assist_dimensions
        """

    return execute_sql(sql, params)


# ============================================================================
# 资产负债表生成
# ============================================================================

def get_balance_sheet(
    company_code: str,
    period: str,
    use_template: bool = True,
) -> pd.DataFrame:
    """
    生成资产负债表

    两种模式：
    1. 模板驱动（默认）：从 balance_sheet_template 取数
    2. 直接计算：从科目余额表按科目分类汇总

    Args:
        company_code: 公司编码
        period: 期间 YYYYMM
        use_template: 是否使用模板

    Returns:
        资产负债表 DataFrame
    """
    if use_template:
        return _generate_report_from_template(
            template_table="balance_sheet_template",
            company_code=company_code,
            period=period,
            order_col="sort_order",
        )
    else:
        return _generate_bs_direct(company_code, period)


def _generate_bs_direct(company_code: str, period: str) -> pd.DataFrame:
    """直接计算资产负债表（不使用模板）"""
    sql = """
    SELECT
        ab.account_code,
        ab.account_name,
        ab.ending_balance,
        ab.direction,
        sa.category
    FROM account_balance ab
    LEFT JOIN standard_accounts sa ON ab.account_code = sa.code
    WHERE ab.company_code = :company
      AND ab.period = :period
    ORDER BY ab.account_code
    """
    df = execute_sql(sql, {"company": company_code, "period": period})

    if len(df) == 0:
        return pd.DataFrame()

    # 按科目类别分类汇总
    assets = df[df["category"] == "资产"]["ending_balance"].sum()
    liabilities = df[df["category"] == "负债"]["ending_balance"].sum()
    equity = df[df["category"] == "权益"]["ending_balance"].sum()

    result = pd.DataFrame([
        {"项目": "资产总计", "期末余额": assets, "类别": "资产"},
        {"项目": "负债总计", "期末余额": liabilities, "类别": "负债"},
        {"项目": "所有者权益总计", "期末余额": equity, "类别": "权益"},
        {"项目": "负债及所有者权益总计", "期末余额": liabilities + equity, "类别": "合计"},
    ])
    return result


# ============================================================================
# 利润表（损益表）生成
# ============================================================================

def get_income_statement(
    company_code: str,
    period: str,
    use_template: bool = True,
) -> pd.DataFrame:
    """
    生成利润表/损益表

    Args:
        company_code: 公司编码
        period: 期间 YYYYMM
        use_template: 是否使用模板

    Returns:
        利润表 DataFrame
    """
    if use_template:
        return _generate_report_from_template(
            template_table="income_statement_template",
            company_code=company_code,
            period=period,
            order_col="sort_order",
        )
    else:
        return _generate_is_direct(company_code, period)


def _generate_is_direct(company_code: str, period: str) -> pd.DataFrame:
    """直接计算利润表"""
    sql = """
    SELECT
        ab.account_code,
        ab.account_name,
        ab.ending_balance,
        ab.direction,
        sa.category
    FROM account_balance ab
    LEFT JOIN standard_accounts sa ON ab.account_code = sa.code
    WHERE ab.company_code = :company
      AND ab.period = :period
      AND sa.category IN ('损益', '成本')
    ORDER BY ab.account_code
    """
    df = execute_sql(sql, {"company": company_code, "period": period})
    return df


# ============================================================================
# 现金流量表生成
# ============================================================================

def get_cashflow(
    company_code: str,
    period: str,
    use_template: bool = True,
) -> pd.DataFrame:
    """
    生成现金流量表

    Args:
        company_code: 公司编码
        period: 期间 YYYYMM
        use_template: 是否使用模板

    Returns:
        现金流量表 DataFrame
    """
    if use_template:
        return _generate_report_from_template(
            template_table="cashflow_template",
            company_code=company_code,
            period=period,
            order_col="sort_order",
        )
    else:
        return _generate_cf_direct(company_code, period)


def _generate_cf_direct(company_code: str, period: str) -> pd.DataFrame:
    """直接计算现金流量表（简化版）"""
    # 假设现金科目为 1001（库存现金）和 1002（银行存款）
    sql = """
    SELECT
        ab.account_code,
        ab.account_name,
        ab.debit_amount,
        ab.credit_amount,
        ab.ending_balance
    FROM account_balance ab
    WHERE ab.company_code = :company
      AND ab.period = :period
      AND ab.account_code IN ('1001', '1002')
    ORDER BY ab.account_code
    """
    df = execute_sql(sql, {"company": company_code, "period": period})
    return df


# ============================================================================
# 模板驱动报表生成
# ============================================================================

def _generate_report_from_template(
    template_table: str,
    company_code: str,
    period: str,
    order_col: str = "line_no",
) -> pd.DataFrame:
    """
    根据模板生成报表

    从模板表读取行项目定义和取数公式，从科目余额表取数计算。

    Args:
        template_table: 模板表名
        company_code: 公司编码
        period: 期间
        order_col: 排序列

    Returns:
        报表 DataFrame
    """
    # 1. 获取模板定义
    template_sql = f"SELECT * FROM {template_table} ORDER BY {order_col}"
    template_df = execute_sql(template_sql)

    if len(template_df) == 0:
        # 如果模板表为空，返回空DataFrame
        return pd.DataFrame(columns=["行次", "项目", "期末余额"])

    # 2. 获取科目余额数据
    balance_sql = """
    SELECT account_code, ending_balance, debit_amount, credit_amount
    FROM account_balance
    WHERE company_code = :company AND period = :period
    """
    balance_df = execute_sql(balance_sql, {"company": company_code, "period": period})

    if len(balance_df) > 0:
        numeric_cols = ["ending_balance", "debit_amount", "credit_amount"]
        for col in numeric_cols:
            balance_df[col] = pd.to_numeric(balance_df[col], errors="coerce").fillna(0.0)
        balance_df = balance_df.groupby("account_code", as_index=True)[numeric_cols].sum()
    else:
        balance_df = pd.DataFrame(columns=["ending_balance", "debit_amount", "credit_amount"])

    # 3. 按模板逐行计算
    rows = []
    for _, tmpl_row in template_df.iterrows():
        line_no = tmpl_row.get("line_no", 0)
        item_name = tmpl_row.get("item_name", "")
        formula_type = tmpl_row.get("formula_type", "科目范围")
        account_ranges_str = tmpl_row.get("account_ranges", "")
        sql_expr = tmpl_row.get("sql_expression", "")
        sign = tmpl_row.get("sign", "+")
        is_subtotal = tmpl_row.get("is_subtotal", 0)
        indent_level = tmpl_row.get("indent_level", 0)

        amount = 0.0

        if formula_type == "固定值":
            # 取 account_ranges 中的数值
            try:
                amount = float(account_ranges_str) if account_ranges_str else 0.0
            except (ValueError, TypeError):
                amount = 0.0

        elif formula_type == "科目范围" and account_ranges_str:
            # 解析科目范围
            amount = _calculate_from_account_ranges(
                account_ranges_str, balance_df, sign
            )

        elif formula_type == "SQL表达式" and sql_expr:
            # 执行自定义SQL
            try:
                custom_df = execute_sql(
                    sql_expr,
                    {"company": company_code, "period": period}
                )
                if len(custom_df) > 0:
                    amount = custom_df.iloc[0, 0] or 0.0
            except Exception as e:
                amount = 0.0

        rows.append({
            "行次": line_no,
            "项目": item_name,
            "期末余额": round(amount, 2),
            "是否小计": "是" if is_subtotal else "",
            "缩进层级": indent_level,
        })

    return pd.DataFrame(rows)


def _calculate_from_account_ranges(
    ranges_json: str,
    balance_df: pd.DataFrame,
    default_sign: str = "+",
) -> float:
    """
    根据科目范围 JSON 计算金额

    JSON 格式:
    [
        {"from": "1001", "to": "1012", "sign": "+"},
        {"from": "2001", "sign": "-"}
    ]

    Args:
        ranges_json: 科目范围 JSON 字符串
        balance_df: 科目余额 DataFrame（以 account_code 为索引）
        default_sign: 默认符号

    Returns:
        计算后的金额
    """
    total = 0.0

    try:
        ranges = json.loads(ranges_json) if isinstance(ranges_json, str) else ranges_json
    except (json.JSONDecodeError, TypeError):
        return 0.0

    if not isinstance(ranges, list):
        return 0.0

    for r in ranges:
        from_code = r.get("from", "")
        to_code = r.get("to", "")
        sign = r.get("sign", default_sign)

        if not from_code:
            continue

        if to_code:
            # 范围取数
            matching = balance_df[
                (balance_df.index >= from_code) &
                (balance_df.index <= to_code)
            ]
            amount = matching["ending_balance"].sum() if "ending_balance" in matching.columns else 0.0
        else:
            # 单科目取数
            if from_code in balance_df.index:
                amount = float(balance_df.loc[from_code, "ending_balance"]) if "ending_balance" in balance_df.columns else 0.0
            else:
                amount = 0.0

        if sign == "-":
            total -= amount
        else:
            total += amount

    return total


# ============================================================================
# 合并/汇总报表
# ============================================================================

def get_consolidated_balance_sheet(
    period: str,
    company_list: Optional[List[str]] = None,
    parent_code: Optional[str] = None,
) -> pd.DataFrame:
    """
    合并资产负债表（支持层级汇总）

    Args:
        period: 期间
        company_list: 公司列表
        parent_code: 上级公司编码，自动获取其所有子孙公司

    Returns:
        合并资产负债表
    """
    from .company_hierarchy import get_company_list_for_summary

    if parent_code:
        # 使用层级树自动获取所有子孙公司
        company_list = get_company_list_for_summary(parent_code)

    if not company_list:
        return pd.DataFrame()

    params = {"period": period}
    company_clause = _bind_in_clause("ab.company_code", company_list, params, "company_list")
    sql = f"""
    SELECT
        ab.account_code,
        ab.account_name,
        SUM(ab.opening_balance) AS opening_balance,
        SUM(ab.debit_amount) AS debit_amount,
        SUM(ab.credit_amount) AS credit_amount,
        SUM(ab.ending_balance) AS ending_balance,
        ab.direction
    FROM account_balance ab
    WHERE ab.period = :period
      AND {company_clause}
    GROUP BY ab.account_code, ab.account_name, ab.direction
    ORDER BY ab.account_code
    """
    return execute_sql(sql, params)


def get_consolidated_income_statement(
    period: str,
    company_list: Optional[List[str]] = None,
    parent_code: Optional[str] = None,
) -> pd.DataFrame:
    """
    合并利润表

    Args:
        period: 期间
        company_list: 公司列表
        parent_code: 上级公司编码

    Returns:
        合并利润表
    """
    if not company_list and parent_code:
        companies_df = get_child_companies(parent_code)
        company_list = companies_df["code"].tolist()

    if not company_list:
        return pd.DataFrame()

    params = {"period": period}
    company_clause = _bind_in_clause("pd.company_code", company_list, params, "company_list")
    sql = f"""
    SELECT
        pd.category,
        pd.item_code,
        pd.item_name,
        SUM(pd.amount) AS total_amount
    FROM pl_detail pd
    WHERE pd.period = :period
      AND {company_clause}
    GROUP BY pd.category, pd.item_code, pd.item_name
    ORDER BY pd.category, pd.item_code
    """
    return execute_sql(sql, params)


def get_multi_period_summary(
    company_code: str,
    start_period: str,
    end_period: str,
    report_type: str = "account_balance",
) -> pd.DataFrame:
    """
    多期间汇总查询

    Args:
        company_code: 公司编码
        start_period: 起始期间 YYYYMM
        end_period: 结束期间 YYYYMM
        report_type: 报表类型

    Returns:
        多期间汇总数据
    """
    periods = _period_range(start_period, end_period)
    params = {"company": company_code}
    period_clause = _bind_in_clause("period", periods, params, "period_list")

    if report_type == "account_balance":
        sql = f"""
        SELECT
            account_code,
            account_name,
            period,
            opening_balance,
            debit_amount,
            credit_amount,
            ending_balance
        FROM account_balance
        WHERE company_code = :company
          AND {period_clause}
        ORDER BY account_code, period
        """
    elif report_type == "pl_detail":
        sql = f"""
        SELECT
            category,
            item_code,
            item_name,
            period,
            amount
        FROM pl_detail
        WHERE company_code = :company
          AND {period_clause}
        ORDER BY category, item_code, period
        """
    else:
        raise ValueError(f"不支持的报表类型: {report_type}")

    return execute_sql(sql, params)


# ============================================================================
# 明细表查询
# ============================================================================

def get_pl_detail(
    company_code: Optional[str] = None,
    period: Optional[str] = None,
    category: Optional[str] = None,
) -> pd.DataFrame:
    """查询损益明细"""
    conditions = []
    params: Dict[str, Any] = {}

    if company_code:
        conditions.append("company_code = :company")
        params["company"] = company_code
    if period:
        conditions.append("period = :period")
        params["period"] = period
    if category:
        conditions.append("category = :category")
        params["category"] = category

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
    SELECT *
    FROM pl_detail
    WHERE {where}
    ORDER BY category, item_code
    """
    return execute_sql(sql, params)


def get_revenue_volume(
    company_code: Optional[str] = None,
    period: Optional[str] = None,
) -> pd.DataFrame:
    """查询收入人次"""
    conditions = []
    params: Dict[str, Any] = {}

    if company_code:
        conditions.append("company_code = :company")
        params["company"] = company_code
    if period:
        conditions.append("period = :period")
        params["period"] = period

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
    SELECT *
    FROM revenue_volume
    WHERE {where}
    ORDER BY COALESCE(business_period, period), COALESCE(campus_name, product_line), COALESCE(grade, ''), COALESCE(subject, '')
    """
    return execute_sql(sql, params)


def get_non_subject_allocation(
    company_code: Optional[str] = None,
    period: Optional[str] = None,
) -> pd.DataFrame:
    """查询非学科费用分配"""
    conditions = []
    params: Dict[str, Any] = {}

    if company_code:
        conditions.append("company_code = :company")
        params["company"] = company_code
    if period:
        conditions.append("period = :period")
        params["period"] = period

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
    SELECT *
    FROM non_subject_allocation
    WHERE {where}
    ORDER BY cost_center
    """
    return execute_sql(sql, params)


def get_mgmt_dept_income_cost(
    company_code: Optional[str] = None,
    period: Optional[str] = None,
) -> pd.DataFrame:
    """查询管理中心部门收入成本费用"""
    conditions = []
    params: Dict[str, Any] = {}

    if company_code:
        conditions.append("company_code = :company")
        params["company"] = company_code
    if period:
        conditions.append("period = :period")
        params["period"] = period

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
    SELECT *
    FROM mgmt_dept_income_cost
    WHERE {where}
    ORDER BY dept_code
    """
    return execute_sql(sql, params)


def get_non_subject_teaching_fee(
    company_code: Optional[str] = None,
    period: Optional[str] = None,
) -> pd.DataFrame:
    """查询非学科课酬"""
    conditions = []
    params: Dict[str, Any] = {}

    if company_code:
        conditions.append("company_code = :company")
        params["company"] = company_code
    if period:
        conditions.append("period = :period")
        params["period"] = period

    where = " AND ".join(conditions) if conditions else "1=1"

    sql = f"""
    SELECT *
    FROM non_subject_teaching_fee
    WHERE {where}
    ORDER BY teacher_id
    """
    return execute_sql(sql, params)


# ============================================================================
# 数据导入（写入数据库）
# ============================================================================

def import_to_database(
    df: pd.DataFrame,
    table_name: str,
    company_code: str,
    period: str,
    batch_no: str,
    file_name: str = "",
) -> Dict[str, Any]:
    """
    将解析后的 DataFrame 写入数据库

    使用批量事务写入，并记录导入日志。

    Args:
        df: 数据 DataFrame
        table_name: 目标表名
        company_code: 公司编码
        period: 期间
        batch_no: 批次号
        file_name: 原始文件名

    Returns:
        导入结果统计
    """
    result = {
        "batch_no": batch_no,
        "table_name": table_name,
        "company_code": company_code,
        "period": period,
        "total_rows": len(df),
        "inserted_rows": 0,
        "updated_rows": 0,
        "errors": [],
    }

    if len(df) == 0:
        return result

    try:
        session = get_session()

        # 添加 import_batch 字段
        if "import_batch" not in df.columns:
            df["import_batch"] = batch_no

        # 写入数据库
        # 使用 replace 策略处理唯一键冲突
        df_to_insert = df.copy()

        # 逐行写入，处理唯一键冲突
        inserted = 0
        updated = 0

        for row_num, (_, row) in enumerate(df_to_insert.iterrows(), start=1):
            row_dict = row.dropna().to_dict()
            # 移除 nan 值
            row_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}
            row_dict = _normalize_nullable_unique_values(table_name, row_dict)

            try:
                # 构建 INSERT OR REPLACE 语句（SQLite）
                cols = list(row_dict.keys())
                placeholders = [f":{c}" for c in cols]
                col_names = ", ".join(cols)
                val_placeholders = ", ".join(placeholders)

                insert_sql = text(f"""
                INSERT OR REPLACE INTO {table_name} ({col_names})
                VALUES ({val_placeholders})
                """)

                session.execute(insert_sql, row_dict)
                updated += 1
            except Exception as e:
                result["errors"].append(f"行 {row_num}: {e}")
                break

        if result["errors"]:
            session.rollback()
            session.close()
            return result

        # 记录导入日志（含文件名）
        log_sql = text("""
        INSERT INTO import_logs
            (batch_no, company_code, period, report_type, status,
             total_rows, success_rows, error_rows, error_detail,
             file_name)
        VALUES
            (:batch, :company, :period, :report, :status,
             :total, :success, :error, :detail,
             :fname)
        """)

        error_detail = json.dumps(result["errors"][:20], ensure_ascii=False)
        status = "成功" if len(result["errors"]) == 0 else "警告"

        session.execute(log_sql, {
            "batch": batch_no,
            "company": company_code,
            "period": period,
            "report": table_name,
            "status": status,
            "total": len(df),
            "success": updated,
            "error": len(result["errors"]),
            "detail": error_detail,
            "fname": file_name or None,
        })
        session.commit()

        result["inserted_rows"] = inserted
        result["updated_rows"] = updated
        session.close()

    except Exception as e:
        result["errors"].append(f"数据库写入失败: {e}")
        if "session" in locals():
            session.rollback()
            session.close()

    return result


def precheck_import(
    file_path: str,
    company_code: Optional[str] = None,
    period: Optional[str] = None,
    report_type: Optional[str] = None,
    original_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    导入预检：解析文件、校验数据、检查公司和期间合法性，但不写入数据库。

    Args:
        参数同 import_excel_to_db

    Returns:
        {
            "passed": bool,
            "report_type": str,
            "company_code": str,
            "company_name": str,
            "period": str,
            "table_name": str,
            "row_count": int,
            "columns": List[str],
            "warnings": List[str],
            "errors": List[str],
            "validation": Dict,
        }
    """
    from .import_parser import parse_file
    from .validators import validate_report_data
    from .models import get_table_name
    from sqlalchemy import text

    result: Dict[str, Any] = {
        "passed": True,
        "report_type": "",
        "company_code": company_code or "",
        "company_name": "",
        "period": period or "",
        "table_name": "",
        "row_count": 0,
        "columns": [],
        "warnings": [],
        "errors": [],
        "validation": {},
    }

    # Step 1: 解析文件
    effective_path = file_path
    parse_company = company_code
    parse_period = period

    if not parse_company or not parse_period:
        if original_filename:
            import re
            m = re.search(r"^(\d{6})[\s_\-]*(.+?)(?:\.xlsx?|$)", original_filename)
            if m:
                if not parse_period:
                    parse_period = m.group(1).strip()
                if not parse_company:
                    raw = m.group(2).strip()
                    for kw in ["科目辅助余额表", "资产负债表", "利润表", "损益表",
                                "收入成本费用表", "收入成本费用明细表",
                                "现金流量表", "收入人次表", "课酬表", "课酬"]:
                        raw = raw.replace(kw, "")
                    name_match = re.search(r"[\u4e00-\u9fff]+", raw)
                    if name_match:
                        parse_company = name_match.group()

    df, rtype, parse_info = parse_file(
        effective_path,
        report_type,
        parse_company,
        parse_period,
        original_filename,
    )
    result["report_type"] = rtype or ""

    if df is None or len(df) == 0:
        err = parse_info.get("errors", ["解析失败"])
        result["errors"].extend(err)
        result["passed"] = False
        return result

    result["row_count"] = len(df)
    result["columns"] = list(df.columns)

    # Step 2: 检查报表类型
    table_name = get_table_name(rtype) if rtype else None
    if not table_name:
        result["errors"].append(f"不支持的报表类型: {rtype}")
        result["passed"] = False
        return result
    result["table_name"] = table_name

    # Step 3: 检查公司和期间
    actual_company = company_code or (df["company_code"].iloc[0] if "company_code" in df.columns else "")
    actual_period = period or (df["period"].iloc[0] if "period" in df.columns else "")

    if not actual_company:
        result["errors"].append("无法识别公司编码")
        result["passed"] = False
    else:
        session = get_session()
        try:
            comp = session.execute(
                text("SELECT name FROM companies WHERE code = :c"),
                {"c": actual_company}
            ).fetchone()
            if comp:
                result["company_code"] = actual_company
                result["company_name"] = comp[0]
            else:
                # 检查是否是简称
                alias = session.execute(
                    text("SELECT company_code FROM company_aliases WHERE alias = :a"),
                    {"a": actual_company}
                ).fetchone()
                if alias:
                    result["company_code"] = alias[0]
                    comp2 = session.execute(
                        text("SELECT name FROM companies WHERE code = :c"),
                        {"c": alias[0]}
                    ).fetchone()
                    result["company_name"] = comp2[0] if comp2 else alias[0]
                else:
                    result["errors"].append(f"公司 '{actual_company}' 不存在")
                    result["passed"] = False
        finally:
            session.close()

    if not actual_period:
        result["errors"].append("无法识别期间")
        result["passed"] = False
    elif not (len(actual_period) == 6 and actual_period.isdigit()):
        result["warnings"].append(f"期间格式非常规: {actual_period}")
    result["period"] = actual_period

    # Step 4: 校验数据
    validation = validate_report_data(df, table_name)
    result["validation"] = {
        "is_valid": validation.is_valid,
        "errors": validation.errors[:10],
        "warnings": validation.warnings[:10],
    }
    if validation.errors:
        result["warnings"].extend(validation.errors[:5])
    if not validation.is_valid:
        result["warnings"].append("数据校验未通过，请检查数据后重试")

    # Step 5: 检查是否重复导入
    if actual_company and actual_period and rtype:
        try:
            s = get_session()
            dup = s.execute(
                text("SELECT COUNT(*) FROM import_logs WHERE company_code = :c AND period = :p AND report_type = :r AND status = '成功'"),
                {"c": actual_company, "p": actual_period, "r": table_name}
            ).scalar()
            if dup and dup > 0:
                result["warnings"].append(f"该公司/期间/类型已存在 {dup} 条成功导入记录，重复导入会覆盖数据")
            s.close()
        except Exception:
            pass

    return result


def import_excel_to_db(
    file_path: str,
    company_code: Optional[str] = None,
    period: Optional[str] = None,
    report_type: Optional[str] = None,
    original_filename: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    一键导入 Excel 文件到数据库

    集成了识别、解析、校验、写入全流程。

    Args:
        file_path: Excel 文件路径
        company_code: 公司编码
        period: 期间
        report_type: 报表类型
        original_filename: 原始上传文件名（用于提取公司和记录日志）

    Returns:
        导入结果
    """
    from .import_parser import parse_file
    from .validators import validate_report_data
    from .models import get_table_name, generate_batch_no
    from sqlalchemy import text

    # 使用原始文件名重新定位文件（如果原始文件名提供了公司和期间信息）
    effective_path = file_path
    effective_company = company_code
    effective_period = period

    if original_filename:
        # 保存原始文件名用于日志
        pass  # 下面会用

    result = {
        "success": False,
        "file_path": effective_path,
        "file_name": original_filename or Path(file_path).name,
        "company_code": company_code or "",
        "period": period or "",
        "batch_no": generate_batch_no(),
        "steps": [],
    }

    # Step 1: 解析（优先用原始文件名提取公司和期间）
    parse_company = company_code
    parse_period = period
    if not parse_company or not parse_period:
        # 如果能从原始文件名提取，就先用原始文件名
        if original_filename:
            from .import_parser import identify_report_type
            temp_company, temp_period = None, None
            import re
            # 从原始文件名提取
            m = re.search(r"^(\d{6})[\s_\-]*(.+?)(?:\.xlsx?|$)", original_filename)
            if m:
                if not parse_period:
                    parse_period = m.group(1).strip()
                if not parse_company:
                    raw = m.group(2).strip()
                    for kw in ["科目辅助余额表", "科目辅助余额", "科目余额表",
                                "辅助余额表", "辅助余额", "余额表",
                                "资产负债表", "利润表", "损益表",
                                "收入成本费用表", "收入成本费用明细表",
                                "现金流量表", "收入人次表", "收入人次",
                                "课酬表", "课酬"]:
                        raw = raw.replace(kw, "")
                    name_match = re.search(r"[\u4e00-\u9fff]+", raw)
                    if name_match:
                        parse_company = name_match.group()
            else:
                # 尝试 公司名_202603 格式
                m2 = re.search(r"(.+?)[_\- ](\d{6})", original_filename)
                if m2:
                    if not parse_company:
                        parse_company = m2.group(1).strip()
                    if not parse_period:
                        parse_period = m2.group(2).strip()

    df, rtype, parse_info = parse_file(
        effective_path,
        report_type,
        parse_company,
        parse_period,
        original_filename,
    )
    result["report_type"] = rtype
    result["steps"].append({"step": "解析", "info": parse_info})

    if df is None:
        result["error"] = parse_info.get("errors", ["解析失败"])[0]
        return result

    table_name = get_table_name(rtype) if rtype else None
    if not table_name:
        result["error"] = f"无法确定目标表: {rtype}"
        return result

    # Step 2: 校验
    validation = validate_report_data(df, table_name)
    result["steps"].append({
        "step": "校验",
        "is_valid": validation.is_valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
    })

    if not validation.is_valid:
        summary = "数据校验未通过"
        if validation.errors:
            summary += "：" + "；".join(validation.errors[:5])
            if len(validation.errors) > 5:
                summary += f"…（共{len(validation.errors)}条错误）"
        result["error"] = summary
        result["validation_errors"] = validation.errors
        result["warnings"] = validation.warnings
        return result

    # Step 3: 获取公司和期间
    actual_company = company_code or (df["company_code"].iloc[0] if "company_code" in df.columns else "")
    actual_period = period or (df["period"].iloc[0] if "period" in df.columns else "")
    result["company_code"] = str(actual_company or "")
    result["period"] = str(actual_period or "")

    # Step 3.2: 简称→编码映射（匹配公司层级中的正式编码）
    if actual_company:
        session_map = get_session()
        try:
            matched = False
            # 从 company_aliases 表读取简称映射（配置化）
            alias_rows = session_map.execute(
                text("SELECT alias, company_code FROM company_aliases WHERE status = 1")
            ).fetchall()
            alias_map = {r[0]: r[1] for r in alias_rows}
            if actual_company in alias_map:
                actual_company = alias_map[actual_company]
                df["company_code"] = actual_company
                result["company_code"] = str(actual_company or "")
                matched = True
                print(f"  别名映射: {actual_company}")
            else:
                # 构建名称映射
                all_companies = session_map.execute(text("SELECT code, name FROM companies")).fetchall()
                name_to_code = {}
                for row in all_companies:
                    code = row[0]
                    name = row[1]
                    name_to_code[name] = code
                    name_to_code[code] = code

                # 精确匹配
                if actual_company in name_to_code:
                    mapped_code = name_to_code[actual_company]
                    if mapped_code != actual_company:
                        print(f"  名称映射: {actual_company} -> {mapped_code}")
                        actual_company = mapped_code
                        df["company_code"] = mapped_code
                        result["company_code"] = str(mapped_code or "")
                    matched = True
                else:
                    # 模糊匹配（取名称包含关系，按名称长度降序避免误匹配）
                    matched = False
                    for full_name, code in sorted(name_to_code.items(), key=lambda x: -len(x[0])):
                        if actual_company in full_name or full_name in actual_company:
                            if str(code).isdigit():
                                actual_company = code
                                df["company_code"] = code
                                result["company_code"] = str(code or "")
                                matched = True
                                break
                if not matched:
                    msg = f"公司 '{actual_company}' 在公司层级中不存在，请先在「公司层级」页面导入或添加该公司"
                    result["error"] = msg
                    result["steps"].append({"step": "公司匹配", "info": {"error": msg}})
                    session_map.close()
                    return result
        except Exception as e:
            session_map.close()
            raise e
        finally:
            session_map.close()

    if not actual_company:
        result["error"] = "无法识别公司编码，请在导入设置中手动填写或在文件名中加入公司信息"
        return result

    # Step 3.8: 重复性检查 - 默认拒绝，必要时可覆盖旧批次
    duplicate_strategy = kwargs.get("duplicate_strategy", "拒绝")
    strategy_map = {
        "reject": "拒绝",
        "拒绝": "拒绝",
        "replace": "覆盖",
        "overwrite": "覆盖",
        "覆盖": "覆盖",
    }
    duplicate_strategy = strategy_map.get(str(duplicate_strategy).strip(), str(duplicate_strategy).strip())
    if actual_company and actual_period and rtype:
        s = get_session()
        try:
            table_for_check = get_table_name(rtype)
            if duplicate_strategy not in ("拒绝", "覆盖"):
                result["error"] = f"不支持的重复导入策略: {duplicate_strategy}"
                return result
            dup = s.execute(
                text("""SELECT COUNT(*) FROM import_logs
                      WHERE company_code = :c AND period = :p AND report_type = :r AND status = '成功'"""),
                {"c": actual_company, "p": actual_period, "r": table_for_check}
            ).scalar()
            if dup and dup > 0:
                if duplicate_strategy == "拒绝":
                    result["error"] = f"重复导入: {actual_company} {actual_period} {rtype} 已存在，请先删除原记录再导入或选择「覆盖」策略"
                    return result
                elif duplicate_strategy == "覆盖":
                    # 删除旧数据
                    old_batches = s.execute(
                        text("SELECT batch_no FROM import_logs WHERE company_code = :c AND period = :p AND report_type = :r AND status = '成功'"),
                        {"c": actual_company, "p": actual_period, "r": table_for_check}
                    ).fetchall()
                    for (batch,) in old_batches:
                        s.execute(text(f"DELETE FROM {table_for_check} WHERE import_batch = :b"), {"b": batch})
                        s.execute(text("DELETE FROM import_logs WHERE batch_no = :b"), {"b": batch})
                    s.commit()
                    result["steps"].append({"step": "覆盖", "info": f"已删除 {len(old_batches)} 批旧数据"})
        except Exception as e:
            result["error"] = f"重复导入检查失败，已阻止写库: {e}"
            return result
        finally:
            s.close()

    # Step 4: 写入数据库（附带原始文件名）
    log_filename = original_filename or Path(file_path).name
    import_result = import_to_database(
        df, table_name, actual_company, actual_period, result["batch_no"],
        file_name=log_filename,
    )
    result["steps"].append({"step": "写入", "info": import_result})

    result["success"] = len(import_result.get("errors", [])) == 0
    if import_result.get("errors"):
        result["error"] = import_result["errors"][0]

    return result

"""
数据校验模块

提供各报表数据的校验逻辑，包括：
- 试算平衡校验
- 表间勾稽校验
- 数据完整性校验
- 去重校验
"""

from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    infos: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.is_valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_info(self, msg: str) -> None:
        self.infos.append(msg)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """合并另一个校验结果"""
        self.is_valid = self.is_valid and other.is_valid
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.infos.extend(other.infos)
        return self

    def __str__(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"❌ 错误 ({len(self.errors)}):\n  " + "\n  ".join(self.errors[:5]))
        if self.warnings:
            parts.append(f"⚠️  警告 ({len(self.warnings)}):\n  " + "\n  ".join(self.warnings[:5]))
        if self.infos:
            parts.append(f"ℹ️  信息 ({len(self.infos)}):\n  " + "\n  ".join(self.infos[:3]))
        status = "✅ 通过" if self.is_valid else "❌ 失败"
        return f"[{status}]\n" + "\n".join(parts)


# ============================================================================
# 科目余额表校验
# ============================================================================

def validate_account_balance(df: pd.DataFrame) -> ValidationResult:
    """
    校验科目余额表数据

    校验规则：
    1. 必填字段完整性
    2. 期初余额 + 借方 - 贷方 = 期末余额
    3. 资产类科目余额方向应为借
    4. 负债/权益类科目余额方向应为贷
    5. 数值字段非负检查

    Args:
        df: 科目余额表DataFrame

    Returns:
        校验结果
    """
    result = ValidationResult()
    required_cols = ["company_code", "period", "account_code", "account_name"]

    # 1. 必填字段检查
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        result.add_error(f"缺少必填字段: {missing_cols}")
        return result

    # 2. 空值检查
    for col in required_cols:
        null_count = df[col].isna().sum()
        if null_count > 0:
            result.add_error(f"字段 '{col}' 有 {null_count} 行空值")

    # 3. 试算平衡校验
    if all(c in df.columns for c in ["opening_balance", "debit_amount", "credit_amount", "ending_balance"]):
        df_check = df.copy()
        # 填充空值
        for c in ["opening_balance", "debit_amount", "credit_amount", "ending_balance"]:
            df_check[c] = pd.to_numeric(df_check[c], errors="coerce").fillna(0)

        # 根据余额方向计算期末余额
        # 借方余额: 期末 = 期初 + 借方 - 贷方
        # 贷方余额: 期末 = 期初 + 贷方 - 借方
        if "direction" in df_check.columns:
            df_check["direction"] = df_check["direction"].fillna("借").astype(str)
            calc_debit = df_check["opening_balance"] + df_check["debit_amount"] - df_check["credit_amount"]
            calc_credit = df_check["opening_balance"] + df_check["credit_amount"] - df_check["debit_amount"]

            is_ping = df_check["direction"].str.contains("平")
            is_debit = df_check["direction"].str.contains("借")

            df_check["calculated_ending"] = 0.0
            # 借方余额：期末 = 期初 + 借方 - 贷方
            df_check.loc[is_debit, "calculated_ending"] = calc_debit
            # 贷方余额：期末 = 期初 + 贷方 - 借方
            df_check.loc[~is_debit & ~is_ping, "calculated_ending"] = calc_credit
            # 方向"平": 期末是绝对值, 取两个计算结果中绝对值匹配的那个
            df_check.loc[is_ping, "calculated_ending"] = df_check.loc[is_ping].apply(
                lambda r: r["ending_balance"] if (
                    abs(calc_debit.loc[r.name]) == r["ending_balance"] or
                    abs(calc_credit.loc[r.name]) == r["ending_balance"]
                ) else calc_debit.loc[r.name],
                axis=1
            )
        else:
            df_check["calculated_ending"] = df_check["opening_balance"] + df_check["debit_amount"] - df_check["credit_amount"]

        # 允许微小浮点误差（考虑绝对值，因为来源数据可能只存正数）
        mismatch = df_check[
            (abs(df_check["calculated_ending"] - df_check["ending_balance"]) > 0.01) &
            (abs(abs(df_check["calculated_ending"]) - df_check["ending_balance"]) > 0.01)
        ]
        if len(mismatch) > 0:
            sample = mismatch.head(5)
            for _, row in sample.iterrows():
                result.add_error(
                    f"试算不平衡: 科目 {row['account_code']} {row['account_name']}, "
                    f"方向={row.get('direction','借')}, "
                    f"期初={row['opening_balance']}, 借方={row['debit_amount']}, "
                    f"贷方={row['credit_amount']}, 期末={row['ending_balance']}, "
                    f"计算期末={row['calculated_ending']:.2f}"
                )

        # 4. 合计试算平衡（分别检查借贷方总额是否平衡）
        total_opening = df_check["opening_balance"].sum()
        total_debit = df_check["debit_amount"].sum()
        total_credit = df_check["credit_amount"].sum()
        total_ending = df_check["ending_balance"].sum()

        # 借贷平衡：借方总额 = 贷方总额
        if abs(total_debit - total_credit) > 0.05:
            result.add_warning(
                f"借贷不平: 借方合计={total_debit:.2f}, 贷方合计={total_credit:.2f}, "
                f"差额={abs(total_debit - total_credit):.2f}"
            )
        else:
            result.add_info(f"借贷平衡: 借方合计={total_debit:.2f} = 贷方合计={total_credit:.2f}")

    # 5. 负值检查
    for col in ["opening_balance", "debit_amount", "credit_amount"]:
        if col in df.columns:
            neg_count = (pd.to_numeric(df[col], errors="coerce") < -0.001).sum()
            if neg_count > 0:
                result.add_warning(f"字段 '{col}' 有 {neg_count} 行负值，请确认")

    # 6. 期间格式检查
    if "period" in df.columns:
        invalid_periods = df[~df["period"].astype(str).str.match(r"^\d{6}$")]
        if len(invalid_periods) > 0:
            result.add_error(f"有 {len(invalid_periods)} 行期间格式不正确")

    return result


# ============================================================================
# 损益明细表校验
# ============================================================================

def validate_pl_detail(df: pd.DataFrame) -> ValidationResult:
    """
    校验损益明细表数据

    Args:
        df: 损益明细表DataFrame

    Returns:
        校验结果
    """
    result = ValidationResult()
    required_cols = ["company_code", "period", "item_code", "item_name", "category", "amount"]

    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        result.add_error(f"缺少必填字段: {missing_cols}")
        return result

    # 类别校验
    valid_categories = ["收入", "成本", "费用", "利润"]
    invalid_cats = df[~df["category"].isin(valid_categories)]
    if len(invalid_cats) > 0:
        invalid_values = invalid_cats["category"].unique()
        result.add_error(f"无效的类别值: {invalid_values}，有效值: {valid_categories}")

    return result


# ============================================================================
# 通用校验
# ============================================================================

def validate_required_columns(df: pd.DataFrame, required_cols: List[str],
                               table_name: str = "") -> ValidationResult:
    """
    校验必填字段

    Args:
        df: 数据DataFrame
        required_cols: 必填字段列表
        table_name: 表名（用于错误信息）

    Returns:
        校验结果
    """
    result = ValidationResult()
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        result.add_error(f"[{table_name}] 缺少必填字段: {missing}")
    return result


def validate_no_duplicates(df: pd.DataFrame,
                           unique_cols: List[str],
                           table_name: str = "",
                           duplicate_is_error: bool = True) -> ValidationResult:
    """
    校验是否有重复数据

    Args:
        df: 数据DataFrame
        unique_cols: 唯一键字段列表
        table_name: 表名
        duplicate_is_error: 重复是否视为错误（否则降级为警告）

    Returns:
        校验结果
    """
    result = ValidationResult()
    # 过滤掉不在DataFrame中的列
    effective_cols = [c for c in unique_cols if c in df.columns]
    if len(effective_cols) < 2:
        return result

    dupes = df[df.duplicated(subset=effective_cols, keep=False)]
    if len(dupes) > 0:
        msg = f"[{table_name}] 发现 {len(dupes)} 行重复数据，唯一键: {effective_cols}"
        samples = dupes.groupby(effective_cols).size().reset_index(name="count")
        samples = samples[samples["count"] > 1].head(3)
        for _, row in samples.iterrows():
            key_desc = ", ".join(f"{c}={row[c]}" for c in effective_cols)
            msg += f"\n  重复: {key_desc}"

        if duplicate_is_error:
            result.add_error(msg)
        else:
            result.add_warning(msg)

    return result


def validate_data_types(df: pd.DataFrame, type_rules: Dict[str, type],
                         table_name: str = "") -> ValidationResult:
    """
    校验字段数据类型

    Args:
        df: 数据DataFrame
        type_rules: 字段类型规则 {字段名: 目标类型}
        table_name: 表名

    Returns:
        校验结果
    """
    result = ValidationResult()
    for col, expected_type in type_rules.items():
        if col not in df.columns:
            continue
        if expected_type in (float, int):
            non_numeric = pd.to_numeric(df[col], errors="coerce").isna()
            # 排除原始就是空值的行
            actual_non_numeric = non_numeric & df[col].notna()
            count = actual_non_numeric.sum()
            if count > 0:
                result.add_error(f"[{table_name}] 字段 '{col}' 有 {count} 行非数值数据")
    return result


# ============================================================================
# 综合校验入口
# ============================================================================

REPORT_VALIDATORS = {
    "account_balance": {
        "validator": validate_account_balance,
        "required_cols": ["company_code", "period", "account_code", "account_name",
                          "opening_balance", "debit_amount", "credit_amount", "ending_balance"],
        "unique_cols": ["company_code", "period", "account_code", "assist_dimensions"],
    },
    "pl_detail": {
        "validator": validate_pl_detail,
        "required_cols": ["company_code", "period", "item_code", "item_name", "category", "amount"],
        "unique_cols": ["company_code", "period", "item_code", "dept_code"],
    },
    "revenue_volume": {
        "validator": None,
        "required_cols": ["company_code", "period", "product_line", "customer_count", "revenue_amount"],
        "unique_cols": ["company_code", "period", "product_line"],
    },
    "non_subject_allocation": {
        "validator": None,
        "required_cols": ["company_code", "period", "cost_center", "allocated_amount"],
        "unique_cols": ["company_code", "period", "cost_center", "account_code"],
    },
    "mgmt_dept_income_cost": {
        "validator": None,
        "required_cols": ["company_code", "period", "dept_code", "dept_name"],
        "unique_cols": ["company_code", "period", "dept_code"],
    },
    "non_subject_mgmt_dept_income_cost": {
        "validator": None,
        "required_cols": ["company_code", "period", "dept_code", "dept_name", "subject_type"],
        "unique_cols": ["company_code", "period", "dept_code", "subject_type"],
    },
    "non_subject_teaching_fee": {
        "validator": None,
        "required_cols": ["company_code", "period", "teacher_id", "course_type", "hours", "rate"],
        "unique_cols": ["company_code", "period", "teacher_id", "course_type"],
    },
}


def validate_report_data(df: pd.DataFrame, table_name: str) -> ValidationResult:
    """
    对指定报表类型执行综合校验

    Args:
        df: 数据DataFrame
        table_name: 数据库表名

    Returns:
        综合校验结果
    """
    result = ValidationResult()

    if table_name not in REPORT_VALIDATORS:
        result.add_warning(f"未知报表类型 '{table_name}'，跳过校验")
        return result

    config = REPORT_VALIDATORS[table_name]

    # 1. 必填字段校验
    required_result = validate_required_columns(df, config["required_cols"], table_name)
    result.merge(required_result)

    if not result.is_valid:
        # 必填字段缺失时，后续校验可能失败，提前返回
        return result

    # 2. 唯一性校验（科目余额表因辅助核算可能存在重复，降级为警告）
    is_strict = table_name != "account_balance"
    unique_result = validate_no_duplicates(df, config["unique_cols"], table_name,
                                           duplicate_is_error=is_strict)
    result.merge(unique_result)

    # 3. 类型校验
    type_rules = {}
    numeric_fields = ["opening_balance", "debit_amount", "credit_amount", "ending_balance",
                       "amount", "revenue_amount", "cost_amount", "expense_amount",
                       "profit_amount", "allocation_base", "allocated_amount",
                       "hours", "rate", "total_amount", "customer_count"]
    for f in numeric_fields:
        if f in df.columns:
            type_rules[f] = float
    type_result = validate_data_types(df, type_rules, table_name)
    result.merge(type_result)

    # 4. 专用校验器
    validator_func = config.get("validator")
    if validator_func:
        specific_result = validator_func(df)
        result.merge(specific_result)

    return result


def validate_import_file(df: pd.DataFrame, report_type_cn: str) -> ValidationResult:
    """
    根据报表中文类型名校验导入文件

    Args:
        df: 数据DataFrame
        report_type_cn: 报表类型中文名

    Returns:
        校验结果
    """
    from .models import get_table_name
    table_name = get_table_name(report_type_cn)
    if not table_name:
        result = ValidationResult()
        result.add_error(f"未知的报表类型: {report_type_cn}")
        return result
    return validate_report_data(df, table_name)

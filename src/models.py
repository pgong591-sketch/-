"""
数据模型定义模块

包含所有表结构的数据类定义，以及常用的数据操作函数。
支持 SQLAlchemy ORM 风格和普通字典风格两种使用方式。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


# ============================================================================
# 数据类定义（用于内存中传递数据）
# ============================================================================

@dataclass
class Company:
    """公司基础信息"""
    code: str
    name: str
    short_name: Optional[str] = None
    parent_code: Optional[str] = None
    level: int = 0
    is_consolidated: int = 0
    status: int = 1


@dataclass
class AccountBalance:
    """科目余额"""
    company_code: str
    period: str
    account_code: str
    account_name: str
    opening_balance: float = 0.0
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    ending_balance: float = 0.0
    direction: str = "借"
    assist_dimensions: Optional[str] = None
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class PlDetail:
    """损益明细"""
    company_code: str
    period: str
    item_code: str
    item_name: str
    category: str  # 收入/成本/费用/利润
    amount: float = 0.0
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None
    remark: Optional[str] = None
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class RevenueVolume:
    """收入人次"""
    company_code: str
    period: str
    product_line: str
    data_period: Optional[str] = None
    business_period: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    calendar_quarter: Optional[str] = None
    source_quarter_label: Optional[str] = None
    campus_name: Optional[str] = None
    grade: Optional[str] = None
    subject: Optional[str] = None
    customer_count: int = 0
    revenue_amount: float = 0.0
    unit_price: float = 0.0
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class NonSubjectAllocation:
    """非学科费用分配"""
    company_code: str
    period: str
    cost_center: str
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    allocation_base: float = 0.0
    allocated_amount: float = 0.0
    ratio: float = 0.0
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class MgmtDeptIncomeCost:
    """管理中心部门收入成本费用"""
    company_code: str
    period: str
    dept_code: str
    dept_name: str
    income_amount: float = 0.0
    cost_amount: float = 0.0
    expense_amount: float = 0.0
    profit_amount: float = 0.0
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class NonSubjectMgmtDeptIncomeCost:
    """非学科管理中心部门收入成本费用"""
    company_code: str
    period: str
    dept_code: str
    dept_name: str
    subject_type: str
    income_amount: float = 0.0
    cost_amount: float = 0.0
    expense_amount: float = 0.0
    profit_amount: float = 0.0
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class NonSubjectTeachingFee:
    """非学科课酬"""
    company_code: str
    period: str
    teacher_id: str
    teacher_name: Optional[str] = None
    course_type: str = ""
    hours: float = 0.0
    rate: float = 0.0
    total_amount: float = 0.0
    is_locked: int = 0
    import_batch: Optional[str] = None


@dataclass
class AccountMapping:
    """科目映射"""
    company_code: str
    local_code: str
    standard_code: str
    local_name: Optional[str] = None
    standard_name: Optional[str] = None
    mapping_type: str = "精确映射"
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None


# ============================================================================
# 表名常量映射
# ============================================================================

TABLE_NAMES = {
    "companies": "companies",
    "account_balance": "account_balance",
    "pl_detail": "pl_detail",
    "revenue_volume": "revenue_volume",
    "non_subject_allocation": "non_subject_allocation",
    "mgmt_dept_income_cost": "mgmt_dept_income_cost",
    "non_subject_mgmt_dept_income_cost": "non_subject_mgmt_dept_income_cost",
    "non_subject_teaching_fee": "non_subject_teaching_fee",
    "account_mapping": "account_mapping",
    "standard_accounts": "standard_accounts",
    "balance_sheet_template": "balance_sheet_template",
    "income_statement_template": "income_statement_template",
    "cashflow_template": "cashflow_template",
    "budget_targets": "budget_targets",
    "budget_actual_overrides": "budget_actual_overrides",
    "import_logs": "import_logs",
}

# 报表类型与表名映射（集中定义在 report_types.py）
from .report_types import REPORT_TYPE_TABLE_MAP, ALL_REPORT_TYPES

REPORT_TYPES_CN = ALL_REPORT_TYPES

def get_table_name(report_type: str) -> Optional[str]:
    """根据报表类型中文名获取数据库表名"""
    from .report_types import get_table_name as _gtn
    return _gtn(report_type)


def dataclass_to_dict(obj) -> Dict[str, Any]:
    """
    将数据类实例转换为字典，排除 None 值

    Args:
        obj: 数据类实例

    Returns:
        字典
    """
    return {k: v for k, v in asdict(obj).items() if v is not None}


def dict_to_dataclass(data: Dict[str, Any], model_class) -> Any:
    """
    将字典转换为数据类实例

    Args:
        data: 字典数据
        model_class: 目标数据类

    Returns:
        数据类实例
    """
    valid_fields = {f.name for f in model_class.__dataclass_fields__.values()}
    filtered_data = {k: v for k, v in data.items() if k in valid_fields}
    return model_class(**filtered_data)


def generate_batch_no() -> str:
    """
    生成导入批次号

    Returns:
        批次号字符串
    """
    from datetime import datetime
    import random
    now = datetime.now()
    return f"IMP{now.strftime('%Y%m%d%H%M%S')}{random.randint(100, 999)}"


def validate_period(period: str) -> bool:
    """
    验证期间格式是否正确 (YYYYMM)

    Args:
        period: 期间字符串

    Returns:
        是否有效
    """
    if not period or len(period) != 6:
        return False
    try:
        year = int(period[:4])
        month = int(period[4:6])
        return 2000 <= year <= 2100 and 1 <= month <= 12
    except ValueError:
        return False

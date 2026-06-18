"""
报表类型常量模块

集中管理所有报表类型的定义、解析器映射、表名映射、文件名识别规则和表头关键字。
各模块统一从此处导入，避免分散定义。
"""

from typing import Dict, List, Tuple, Optional

# ============================================================================
# 1. 报表类型中文名常量
# ============================================================================

RT_ACCOUNT_BALANCE = "科目余额表"
RT_BALANCE_SHEET = "资产负债表"
RT_INCOME_STATEMENT = "损益表"
RT_PL_DETAIL = "损益明细表"
RT_INCOME_COST_EXPENSE = "收入成本费用表"
RT_REVENUE_VOLUME = "收入人次表"
RT_NON_SUBJECT_ALLOCATION = "非学科费用分配表"
RT_MGMT_DEPT_INCOME_COST = "管理中心部门收入成本费用表"
RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST = "非学科管理中心部门收入成本费用表"
RT_NON_SUBJECT_TEACHING_FEE = "非学科课酬"

# 所有报表类型列表
ALL_REPORT_TYPES = [
    RT_ACCOUNT_BALANCE,
    RT_BALANCE_SHEET,
    RT_INCOME_STATEMENT,
    RT_PL_DETAIL,
    RT_INCOME_COST_EXPENSE,
    RT_REVENUE_VOLUME,
    RT_NON_SUBJECT_ALLOCATION,
    RT_MGMT_DEPT_INCOME_COST,
    RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST,
    RT_NON_SUBJECT_TEACHING_FEE,
]

# ============================================================================
# 2. 报表类型 → 数据库表名映射
# ============================================================================

REPORT_TYPE_TABLE_MAP: Dict[str, str] = {
    RT_ACCOUNT_BALANCE: "account_balance",
    RT_BALANCE_SHEET: "balance_sheet",
    RT_INCOME_STATEMENT: "income_statement",
    RT_PL_DETAIL: "pl_detail",
    RT_INCOME_COST_EXPENSE: "pl_detail",
    RT_REVENUE_VOLUME: "revenue_volume",
    RT_NON_SUBJECT_ALLOCATION: "non_subject_allocation",
    RT_MGMT_DEPT_INCOME_COST: "mgmt_dept_income_cost",
    RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST: "non_subject_mgmt_dept_income_cost",
    RT_NON_SUBJECT_TEACHING_FEE: "non_subject_teaching_fee",
}

def get_table_name(report_type: str) -> Optional[str]:
    """根据报表类型中文名获取数据库表名"""
    return REPORT_TYPE_TABLE_MAP.get(report_type)

# ============================================================================
# 3. 文件名识别规则
# ============================================================================

FILE_NAME_PATTERNS: List[Tuple[str, str]] = [
    (r"科目.*余额", RT_ACCOUNT_BALANCE),
    (r"资产负债表", RT_BALANCE_SHEET),
    (r"利润表|损益表", RT_INCOME_STATEMENT),
    (r"现金流量表", "现金流量表"),
    (r"收入人次", RT_REVENUE_VOLUME),
    (r"非学科费用分配", RT_NON_SUBJECT_ALLOCATION),
    (r"管理中心.*收入|管理中心.*成本|管理中心.*费用", RT_MGMT_DEPT_INCOME_COST),
    (r"非学科管理中心", RT_NON_SUBJECT_MGMT_DEPT_INCOME_COST),
    (r"收入成本费用表|收入成本费用明细", RT_INCOME_COST_EXPENSE),
    (r"非学科课酬|课酬", RT_NON_SUBJECT_TEACHING_FEE),
]

# ============================================================================
# 4. 表头关键字识别规则
# ============================================================================

HEADER_KEYWORDS: Dict[str, List[str]] = {
    RT_ACCOUNT_BALANCE: ["科目编码", "科目名称", "期初余额", "本期发生", "期末余额"],
    RT_BALANCE_SHEET: ["资产", "负债", "所有者权益", "流动资产", "流动负债"],
    RT_INCOME_STATEMENT: ["营业收入", "营业成本", "利润总额", "净利润", "损益表"],
    "利润表": ["营业收入", "营业成本", "利润总额", "净利润"],
    "现金流量表": ["经营活动", "投资活动", "筹资活动", "现金流"],
    RT_PL_DETAIL: ["收入", "成本", "费用", "合计", "项目", "本月"],
    RT_REVENUE_VOLUME: ["人次", "人数", "产品", "收入"],
    RT_MGMT_DEPT_INCOME_COST: ["部门", "中心", "收入", "成本", "费用"],
}

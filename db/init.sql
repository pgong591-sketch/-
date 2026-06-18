-- ============================================================================
-- 财务数据仓库 - 数据库初始化脚本 (SQLite)
-- 说明：本脚本创建完整的财务数据仓库表结构
-- 目标数据库：SQLite 3
-- ============================================================================

-- 开启外键约束
PRAGMA foreign_keys = ON;

-- ============================================================================
-- 1. 公司基础信息表（支持树形层级）
-- ============================================================================
CREATE TABLE IF NOT EXISTS companies (
    code            TEXT PRIMARY KEY,          -- 公司编码（唯一标识）
    name            TEXT NOT NULL,             -- 公司全称
    short_name      TEXT,                      -- 公司简称
    parent_code     TEXT,                      -- 上级公司编码（顶级为NULL）
    level           INTEGER DEFAULT 0,         -- 层级深度（0=集团,1=一级子,2=二级子...）
    tree_path       TEXT,                      -- 物化路径 '/ROOT/A/B/C' 便于子树查询
    is_leaf         INTEGER DEFAULT 1,         -- 是否末级公司 1=是 0=否
    is_consolidated INTEGER DEFAULT 1,         -- 是否纳入合并范围 0=否 1=是
    status          INTEGER DEFAULT 1,         -- 状态 0=停用 1=启用
    currency        TEXT DEFAULT 'CNY',        -- 本位币
    industry        TEXT,                      -- 行业
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_code) REFERENCES companies(code)
);

-- ============================================================================
-- 1.1 公司别名映射表（源文件简称/别名 -> 正式公司编码）
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alias           TEXT NOT NULL UNIQUE,
    company_code    TEXT NOT NULL,
    source          TEXT DEFAULT 'manual',
    status          INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_code) REFERENCES companies(code)
);

-- ============================================================================
-- 1.2 公司维度属性表（用于看板切片、资金预警和后续合并抵消）
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_company (
    company_id      TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    business_group  TEXT,
    business_type   TEXT,
    region          TEXT,
    is_operational  INTEGER DEFAULT 1,
    update_time     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(code)
);

-- ============================================================================
-- 1.3 股权关系表（支持分层持股）
-- ============================================================================
CREATE TABLE IF NOT EXISTS ownership (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_code     TEXT NOT NULL,             -- 母公司编码
    sub_code        TEXT NOT NULL,             -- 子公司编码
    ownership_pct   REAL NOT NULL DEFAULT 100, -- 直接持股比例(%)
    effective_date  TEXT NOT NULL,             -- 生效日期 YYYYMMDD
    expiration_date TEXT,                      -- 失效日期，NULL=至今
    is_control      INTEGER DEFAULT 1,         -- 是否形成控制 0=否 1=是
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_code) REFERENCES companies(code),
    FOREIGN KEY (sub_code) REFERENCES companies(code),
    UNIQUE(parent_code, sub_code, effective_date)
);

-- ============================================================================
-- 2. 科目余额表（核心事实表）
-- ============================================================================
CREATE TABLE IF NOT EXISTS account_balance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,             -- 公司编码
    period          TEXT NOT NULL,             -- 期间 YYYYMM
    account_code    TEXT NOT NULL,             -- 科目编码
    account_name    TEXT NOT NULL,             -- 科目名称
    opening_balance REAL DEFAULT 0,            -- 期初余额
    debit_amount    REAL DEFAULT 0,            -- 本期借方发生额
    credit_amount   REAL DEFAULT 0,            -- 本期贷方发生额
    ending_balance  REAL DEFAULT 0,            -- 期末余额
    direction       TEXT DEFAULT '借',         -- 余额方向 借/贷
    assist_dimensions TEXT,                    -- 辅助维度（JSON格式，如 {"部门":"教学部","项目":"A项目"}）
    is_internal     INTEGER DEFAULT 0,         -- 是否内部交易科目 0=否 1=是
    counterparty    TEXT,                      -- 内部交易对方公司代码
    is_locked       INTEGER DEFAULT 0,         -- 锁定标志 0=未锁定 1=已锁定
    import_batch    TEXT,                      -- 导入批次号
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, account_code, assist_dimensions)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_account_balance_unique_coalesced
ON account_balance (company_code, period, account_code, COALESCE(assist_dimensions, ''));

-- ============================================================================
-- 3. 损益明细表（收入成本费用明细表）
-- ============================================================================
-- ============================================================================
-- 2.2 资产负债表导入快照表
-- ============================================================================
CREATE TABLE IF NOT EXISTS balance_sheet (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    side            TEXT NOT NULL,
    item_name       TEXT NOT NULL,
    line_number     TEXT,
    ending_balance  REAL DEFAULT 0,
    opening_balance REAL DEFAULT 0,
    is_subtotal     INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 2.3 损益表导入快照表
-- ============================================================================
CREATE TABLE IF NOT EXISTS income_statement (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code     TEXT NOT NULL,
    period           TEXT NOT NULL,
    item_name        TEXT NOT NULL,
    period1_value    REAL DEFAULT 0,
    period2_value    REAL DEFAULT 0,
    period3_value    REAL DEFAULT 0,
    period4_value    REAL DEFAULT 0,
    sort_order       INTEGER DEFAULT 0,
    import_batch     TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    original_name    TEXT,
    cumulative_value REAL DEFAULT 0
);

-- ============================================================================
-- 2.4 通用财务报表数据表（预留）
-- ============================================================================
CREATE TABLE IF NOT EXISTS financial_report_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    report_type     TEXT NOT NULL,
    line_no         INTEGER,
    item_name       TEXT,
    amount1         REAL DEFAULT 0,
    amount2         REAL DEFAULT 0,
    direction       TEXT,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pl_detail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    item_code       TEXT NOT NULL,             -- 项目编码
    item_name       TEXT NOT NULL,             -- 项目名称
    category        TEXT NOT NULL,             -- 类别：收入/成本/费用/利润
    amount          REAL DEFAULT 0,            -- 金额
    dept_code       TEXT,                      -- 部门编码（可选）
    dept_name       TEXT,                      -- 部门名称（可选）
    remark          TEXT,                      -- 备注
    is_locked       INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, item_code, dept_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pl_detail_unique_coalesced
ON pl_detail (company_code, period, item_code, COALESCE(dept_code, ''));

-- ============================================================================
-- 4. 收入人次表
-- ============================================================================
CREATE TABLE IF NOT EXISTS revenue_volume (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    product_line    TEXT NOT NULL,             -- 产品线
    data_period     TEXT,                      -- 文件批次期间 YYYYMM
    business_period TEXT,                      -- 明细业务期间 YYYYMM
    year            INTEGER,                   -- 业务年份
    month           INTEGER,                   -- 业务月份
    calendar_quarter TEXT,                     -- 自然季度标签
    source_quarter_label TEXT,                 -- 源季度/班期标签
    campus_name     TEXT,                      -- 校区名称
    grade           TEXT,                      -- 年级
    subject         TEXT,                      -- 科目
    customer_count  INTEGER DEFAULT 0,         -- 客户人次
    revenue_amount  REAL DEFAULT 0,            -- 收入金额
    unit_price      REAL DEFAULT 0,            -- 单价（计算字段）
    source_file     TEXT,                      -- 来源文件名
    source_sheet    TEXT,                      -- 来源sheet
    is_locked       INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, product_line)
);

-- ============================================================================
-- 5. 非学科费用分配表
-- ============================================================================
CREATE TABLE IF NOT EXISTS non_subject_allocation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    cost_center     TEXT NOT NULL,             -- 成本中心
    account_code    TEXT,                      -- 科目编码
    account_name    TEXT,                      -- 科目名称
    allocation_base REAL DEFAULT 0,            -- 分配基数
    allocated_amount REAL DEFAULT 0,           -- 分配金额
    ratio           REAL DEFAULT 0,            -- 分配比例
    is_locked       INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, cost_center, account_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_non_subject_allocation_unique_coalesced
ON non_subject_allocation (company_code, period, cost_center, COALESCE(account_code, ''));

-- ============================================================================
-- 6. 管理中心部门收入成本费用表
-- ============================================================================
CREATE TABLE IF NOT EXISTS mgmt_dept_income_cost (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    dept_code       TEXT NOT NULL,             -- 部门编码
    dept_name       TEXT NOT NULL,             -- 部门名称
    income_amount   REAL DEFAULT 0,            -- 收入金额
    cost_amount     REAL DEFAULT 0,            -- 成本金额
    expense_amount  REAL DEFAULT 0,            -- 费用金额
    profit_amount   REAL DEFAULT 0,            -- 利润金额（计算字段）
    is_locked       INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, dept_code)
);

-- ============================================================================
-- 7. 非学科管理中心部门收入成本费用表
-- ============================================================================
CREATE TABLE IF NOT EXISTS non_subject_mgmt_dept_income_cost (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    dept_code       TEXT NOT NULL,
    dept_name       TEXT NOT NULL,
    subject_type    TEXT NOT NULL,             -- 学科类型
    income_amount   REAL DEFAULT 0,
    cost_amount     REAL DEFAULT 0,
    expense_amount  REAL DEFAULT 0,
    profit_amount   REAL DEFAULT 0,
    is_locked       INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, dept_code, subject_type)
);

-- ============================================================================
-- 8. 非学科课酬表
-- ============================================================================
CREATE TABLE IF NOT EXISTS non_subject_teaching_fee (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    period          TEXT NOT NULL,
    teacher_id      TEXT NOT NULL,             -- 教师编码
    teacher_name    TEXT,                      -- 教师姓名
    course_type     TEXT NOT NULL,             -- 课程类型
    hours           REAL DEFAULT 0,            -- 课时数
    rate            REAL DEFAULT 0,            -- 课酬单价
    total_amount    REAL DEFAULT 0,            -- 课酬总额
    is_locked       INTEGER DEFAULT 0,
    import_batch    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, period, teacher_id, course_type)
);

-- ============================================================================
-- 9. 科目映射表（各公司科目体系→标准科目）
-- ============================================================================
CREATE TABLE IF NOT EXISTS account_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,             -- 公司编码（ALL=全局映射）
    local_code      TEXT NOT NULL,             -- 公司本地科目编码
    local_name      TEXT,                      -- 公司本地科目名称
    standard_code   TEXT NOT NULL,             -- 标准科目编码
    standard_name   TEXT,                      -- 标准科目名称
    mapping_type    TEXT DEFAULT '精确映射',    -- 映射类型：精确映射/范围映射
    effective_from  TEXT,                      -- 生效起始期间 YYYYMM
    effective_to    TEXT,                      -- 生效结束期间 YYYYMM
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_code, local_code)
);

-- ============================================================================
-- 10. 标准科目表
-- ============================================================================
CREATE TABLE IF NOT EXISTS standard_accounts (
    code            TEXT PRIMARY KEY,          -- 标准科目编码
    name            TEXT NOT NULL,             -- 标准科目名称
    category        TEXT NOT NULL,             -- 科目类别：资产/负债/权益/成本/损益
    balance_direction TEXT DEFAULT '借',       -- 余额方向 借/贷
    level           INTEGER DEFAULT 1,         -- 科目层级
    parent_code     TEXT,                      -- 上级科目编码
    is_leaf         INTEGER DEFAULT 1,         -- 是否末级科目
    status          INTEGER DEFAULT 1,
    sort_order      INTEGER DEFAULT 0,
    FOREIGN KEY (parent_code) REFERENCES standard_accounts(code)
);

-- ============================================================================
-- 11. 资产负债表模板
-- ============================================================================
CREATE TABLE IF NOT EXISTS balance_sheet_template (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    line_no         INTEGER NOT NULL,          -- 行次
    item_name       TEXT NOT NULL,             -- 项目名称
    bs_category     TEXT NOT NULL,             -- 类别：资产/负债/权益
    is_subtotal     INTEGER DEFAULT 0,         -- 是否小计行
    subtotal_group  TEXT,                      -- 小计分组标识
    formula_type    TEXT DEFAULT '科目范围',    -- 公式类型：科目范围/SQL表达式/固定值
    account_ranges  TEXT,                      -- 科目范围 JSON：[{"from":"1001","to":"1012","sign":"+"}]
    sql_expression  TEXT,                      -- SQL表达式（当formula_type=SQL表达式时）
    indent_level    INTEGER DEFAULT 0,         -- 缩进层级
    is_bold         INTEGER DEFAULT 0,         -- 是否加粗
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 12. 损益表模板
-- ============================================================================
CREATE TABLE IF NOT EXISTS income_statement_template (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    line_no         INTEGER NOT NULL,
    item_name       TEXT NOT NULL,
    is_subtotal     INTEGER DEFAULT 0,
    subtotal_group  TEXT,
    formula_type    TEXT DEFAULT '科目范围',
    account_ranges  TEXT,
    sql_expression  TEXT,
    sign            TEXT DEFAULT '+',          -- 取数符号 +/-
    indent_level    INTEGER DEFAULT 0,
    is_bold         INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 13. 现金流量表模板
-- ============================================================================
CREATE TABLE IF NOT EXISTS cashflow_template (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    line_no         INTEGER NOT NULL,
    item_name       TEXT NOT NULL,
    cf_category     TEXT NOT NULL,             -- 类别：经营活动/投资活动/筹资活动
    is_subtotal     INTEGER DEFAULT 0,
    subtotal_group  TEXT,
    formula_type    TEXT DEFAULT '科目范围',
    account_ranges  TEXT,
    sql_expression  TEXT,
    sign            TEXT DEFAULT '+',
    indent_level    INTEGER DEFAULT 0,
    is_bold         INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 13.1 年度预算目标表
-- ============================================================================
CREATE TABLE IF NOT EXISTS budget_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_year     TEXT NOT NULL,             -- 预算年度 YYYY
    module          TEXT,                      -- 模块/板块
    project         TEXT NOT NULL,             -- 校区/项目名称
    company_code    TEXT,                      -- 匹配到的公司编码，未匹配时为空
    target_type     TEXT NOT NULL,             -- income/profit
    annual_target   REAL DEFAULT 0,            -- 年度目标
    source_sheet    TEXT,                      -- 来源 sheet
    source_row      INTEGER,                   -- 来源行号
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(budget_year, project, target_type)
);

-- ============================================================================
-- 13.2 年度预算实际补录表
-- ============================================================================
CREATE TABLE IF NOT EXISTS budget_actual_overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_year     TEXT NOT NULL,             -- 预算年度 YYYY
    period          TEXT NOT NULL,             -- 期间 YYYYMM
    module          TEXT,
    project         TEXT NOT NULL,
    company_code    TEXT,
    metric_type     TEXT NOT NULL,             -- income/profit
    amount          REAL DEFAULT 0,
    source_sheet    TEXT,
    source_row      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(budget_year, period, project, metric_type)
);

-- ============================================================================
-- 14. 导入日志表
-- ============================================================================
CREATE TABLE IF NOT EXISTS import_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no        TEXT NOT NULL,             -- 批次号
    company_code    TEXT NOT NULL,             -- 公司编码
    period          TEXT NOT NULL,             -- 期间
    report_type     TEXT NOT NULL,             -- 报表类型
    file_name       TEXT,                      -- 原始文件名
    file_path       TEXT,                      -- 文件路径
    status          TEXT DEFAULT '处理中',      -- 状态：处理中/成功/警告/失败
    total_rows      INTEGER DEFAULT 0,         -- 总行数
    success_rows    INTEGER DEFAULT 0,         -- 成功行数
    error_rows      INTEGER DEFAULT 0,         -- 错误行数
    error_detail    TEXT,                      -- 错误详情（JSON）
    operator        TEXT,                      -- 操作人
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 14.1 月度财务数据收集闭环
-- ============================================================================
CREATE TABLE IF NOT EXISTS monthly_collection_requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL,
    company_code    TEXT NOT NULL,
    report_type     TEXT NOT NULL,
    required        INTEGER DEFAULT 1,
    due_date        TEXT,
    remark          TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period, company_code, report_type)
);

CREATE TABLE IF NOT EXISTS monthly_collection_status (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    period                TEXT NOT NULL,
    company_code          TEXT NOT NULL,
    report_type           TEXT NOT NULL,
    status                TEXT DEFAULT '缺失',
    latest_batch_no       TEXT,
    latest_file_name      TEXT,
    latest_import_time    TEXT,
    total_success_batches INTEGER DEFAULT 0,
    total_error_batches   INTEGER DEFAULT 0,
    issue_detail          TEXT,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period, company_code, report_type)
);

-- ============================================================================
-- 15. 汇率表（多币种支持）
-- ============================================================================
CREATE TABLE IF NOT EXISTS exchange_rates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_currency   TEXT NOT NULL,             -- 源币种
    to_currency     TEXT NOT NULL,             -- 目标币种
    rate            REAL NOT NULL,             -- 汇率
    rate_date       TEXT NOT NULL,             -- 汇率日期
    rate_type       TEXT DEFAULT '即期汇率',    -- 汇率类型
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_currency, to_currency, rate_date, rate_type)
);

-- ============================================================================
-- 16. 利润表系统化底表（数据来源追溯）
-- ============================================================================
CREATE TABLE IF NOT EXISTS finance_import_batch (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no     TEXT NOT NULL UNIQUE,
    period_id    TEXT,
    file_name    TEXT,
    file_type    TEXT,
    sheet_name   TEXT,
    imported_by  TEXT,
    imported_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status       TEXT DEFAULT '已导入',
    remark       TEXT
);

CREATE TABLE IF NOT EXISTS fact_profit_loss (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id          TEXT NOT NULL,
    organization_id    TEXT NOT NULL,
    subject_id         TEXT NOT NULL,
    amount             REAL DEFAULT 0,
    data_scope         TEXT DEFAULT 'month',
    source_type        TEXT DEFAULT 'excel_import',
    import_batch_id    INTEGER,
    source_file_name   TEXT,
    source_sheet_name  TEXT,
    source_row_no      INTEGER,
    source_column_name TEXT,
    source_cell_ref    TEXT,
    original_value     REAL DEFAULT 0,
    adjusted_value     REAL DEFAULT 0,
    final_value        REAL DEFAULT 0,
    remark             TEXT,
    status             TEXT DEFAULT '已审核',
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (import_batch_id) REFERENCES finance_import_batch(id)
);

CREATE TABLE IF NOT EXISTS finance_remark_template (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    template_code  TEXT UNIQUE,
    template_text  TEXT NOT NULL,
    subject_id     TEXT,
    status         INTEGER DEFAULT 1,
    sort_order     INTEGER DEFAULT 0,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_anomaly_rule (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code     TEXT UNIQUE,
    rule_name     TEXT NOT NULL,
    metric_name   TEXT,
    operator      TEXT,
    threshold     REAL,
    severity      TEXT DEFAULT '关注',
    status        INTEGER DEFAULT 1,
    remark        TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 索引创建
-- ============================================================================

-- 科目余额表索引
CREATE INDEX IF NOT EXISTS idx_account_balance_company_period
    ON account_balance(company_code, period);
CREATE INDEX IF NOT EXISTS idx_account_balance_account
    ON account_balance(account_code);
CREATE INDEX IF NOT EXISTS idx_account_balance_company_period_account
    ON account_balance(company_code, period, account_code);

-- 损益明细表索引
-- 资产负债表导入快照索引
CREATE INDEX IF NOT EXISTS idx_balance_sheet_company_period
    ON balance_sheet(company_code, period);
CREATE INDEX IF NOT EXISTS idx_balance_sheet_company_period_item
    ON balance_sheet(company_code, period, item_name, side);

-- 损益表导入快照索引
CREATE INDEX IF NOT EXISTS idx_income_statement_company_period
    ON income_statement(company_code, period);
CREATE INDEX IF NOT EXISTS idx_income_statement_company_period_item
    ON income_statement(company_code, period, item_name);

-- 通用财务报表数据索引
CREATE INDEX IF NOT EXISTS idx_financial_report_data_company_period
    ON financial_report_data(company_code, period);
CREATE INDEX IF NOT EXISTS idx_financial_report_data_type
    ON financial_report_data(report_type);

CREATE INDEX IF NOT EXISTS idx_pl_detail_company_period
    ON pl_detail(company_code, period);
CREATE INDEX IF NOT EXISTS idx_pl_detail_category
    ON pl_detail(category);

-- 收入人次表索引
CREATE INDEX IF NOT EXISTS idx_revenue_volume_company_period
    ON revenue_volume(company_code, period);

-- 非学科费用分配表索引
CREATE INDEX IF NOT EXISTS idx_allocation_company_period
    ON non_subject_allocation(company_code, period);

-- 管理中心部门表索引
CREATE INDEX IF NOT EXISTS idx_mgmt_dept_company_period
    ON mgmt_dept_income_cost(company_code, period);

-- 非学科管理中心表索引
CREATE INDEX IF NOT EXISTS idx_non_subject_mgmt_company_period
    ON non_subject_mgmt_dept_income_cost(company_code, period);

-- 非学科课酬表索引
CREATE INDEX IF NOT EXISTS idx_teaching_fee_company_period
    ON non_subject_teaching_fee(company_code, period);

-- 科目映射表索引
CREATE INDEX IF NOT EXISTS idx_company_aliases_alias
    ON company_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_company_aliases_company
    ON company_aliases(company_code);

CREATE INDEX IF NOT EXISTS idx_account_mapping_company
    ON account_mapping(company_code);
CREATE INDEX IF NOT EXISTS idx_account_mapping_standard
    ON account_mapping(standard_code);

-- 导入日志索引
CREATE INDEX IF NOT EXISTS idx_import_logs_batch
    ON import_logs(batch_no);
CREATE INDEX IF NOT EXISTS idx_import_logs_company_period
    ON import_logs(company_code, period);

-- 月度收集闭环索引
CREATE INDEX IF NOT EXISTS idx_monthly_collection_requirements_period
    ON monthly_collection_requirements(period);
CREATE INDEX IF NOT EXISTS idx_monthly_collection_status_period
    ON monthly_collection_status(period);
CREATE INDEX IF NOT EXISTS idx_monthly_collection_status_status
    ON monthly_collection_status(status);

-- 利润表系统化底表索引
CREATE INDEX IF NOT EXISTS idx_finance_import_batch_no
    ON finance_import_batch(batch_no);
CREATE INDEX IF NOT EXISTS idx_fact_profit_loss_period_org_subject
    ON fact_profit_loss(period_id, organization_id, subject_id);
CREATE INDEX IF NOT EXISTS idx_fact_profit_loss_source
    ON fact_profit_loss(source_type, import_batch_id);
CREATE INDEX IF NOT EXISTS idx_finance_remark_template_subject
    ON finance_remark_template(subject_id);
CREATE INDEX IF NOT EXISTS idx_finance_anomaly_rule_status
    ON finance_anomaly_rule(status);

-- 预算目标和补录索引
CREATE INDEX IF NOT EXISTS idx_budget_targets_year_type
    ON budget_targets(budget_year, target_type);
CREATE INDEX IF NOT EXISTS idx_budget_targets_company
    ON budget_targets(company_code);
CREATE INDEX IF NOT EXISTS idx_budget_actual_period_type
    ON budget_actual_overrides(period, metric_type);
CREATE INDEX IF NOT EXISTS idx_budget_actual_company
    ON budget_actual_overrides(company_code);

-- ============================================================================
-- 视图：便于查询的常用视图
-- ============================================================================

-- 视图1：公司层级结构视图
CREATE VIEW IF NOT EXISTS v_company_tree AS
    WITH RECURSIVE company_tree AS (
        SELECT code, name, parent_code, level, name AS path
        FROM companies WHERE parent_code IS NULL OR parent_code = ''
        UNION ALL
        SELECT c.code, c.name, c.parent_code, c.level,
               ct.path || ' > ' || c.name AS path
        FROM companies c
        JOIN company_tree ct ON c.parent_code = ct.code
    )
    SELECT * FROM company_tree;

-- 视图2：带科目映射的科目余额视图
CREATE VIEW IF NOT EXISTS v_account_balance_mapped AS
    SELECT
        ab.company_code,
        ab.period,
        COALESCE(am.standard_code, ab.account_code) AS standard_code,
        COALESCE(am.standard_name, ab.account_name) AS standard_name,
        sa.category AS account_category,
        ab.opening_balance,
        ab.debit_amount,
        ab.credit_amount,
        ab.ending_balance,
        ab.direction
    FROM account_balance ab
    LEFT JOIN account_mapping am ON ab.company_code = am.company_code
                                 AND ab.account_code = am.local_code
    LEFT JOIN standard_accounts sa ON COALESCE(am.standard_code, ab.account_code) = sa.code;

-- ============================================================================
-- 初始化完成标志
-- ============================================================================
SELECT '财务数据仓库表结构创建完成！' AS message;

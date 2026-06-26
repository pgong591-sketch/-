# 财务数据仓库与报表生成系统

> 轻量级集团财务数据仓库，支持多公司 Excel 数据导入、公司层级管理、单体/汇总/合并报表生成及标准 Excel 导出。

---

## 项目结构

```
finance_dw/
├── data/                    # 数据文件（数据库、上传文件、输出）
│   └── output/              # 报表导出目录
├── db/
│   └── init.sql             # 建表脚本（完整表结构）
├── config/                  # 配置文件
│   ├── README.md            # 配置说明
│   ├── companies.xlsx       # 公司清单（模板）
│   ├── account_standard.xlsx # 标准科目表（模板）
│   └── report_templates.xlsx # 报表模板定义（模板）
├── scripts/
│   └── batch_import.py      # 批量导入脚本
├── src/
│   ├── __init__.py
│   ├── db_connection.py     # 数据库连接管理
│   ├── models.py            # 数据模型定义
│   ├── import_parser.py     # 报表解析器集合
│   ├── validators.py        # 数据校验逻辑
│   ├── reports.py           # 报表生成核心
│   └── excel_exporter.py    # Excel 格式化导出
├── tests/                   # 测试目录
├── app.py                   # Streamlit Web 界面
├── requirements.txt         # 依赖清单
└── README.md
```

---

## 快速开始

### 1. 安装依赖

```bash
cd finance_dw
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python -c "from src.db_connection import init_database; init_database()"
```

或者在启动 Streamlit 时自动初始化。

### 3. 导入数据

**方式一：Web 界面上传**

```bash
streamlit run app.py --server.port 8502
```

在浏览器中打开，进入「数据导入」页面上传 Excel 文件。

**方式二：命令行批量导入**

```bash
# 导入单个文件
python scripts/batch_import.py --file "data/xxx.xlsx" --company DG001 --period 202603

# 批量导入目录
python scripts/batch_import.py --dir "data/excel_files" --init-db

# 指定报表类型
python scripts/batch_import.py --file "data/xxx.xlsx" --type "科目余额表"
```

### 4. 查询报表

启动 Streamlit Web 界面后，可通过导航菜单访问各报表页面。

---

## 数据库设计

### 核心表

| 表名 | 说明 |
|------|------|
| `companies` | 公司基础信息 |
| `account_balance` | 科目余额表（核心事实表） |
| `pl_detail` | 损益明细表 |
| `revenue_volume` | 收入人次表 |
| `non_subject_allocation` | 非学科费用分配表 |
| `mgmt_dept_income_cost` | 管理中心部门收入成本费用表 |
| `non_subject_mgmt_dept_income_cost` | 非学科管理中心部门收入成本费用表 |
| `non_subject_teaching_fee` | 非学科课酬表 |

### 辅助表

| 表名 | 说明 |
|------|------|
| `balance_sheet_template` | 资产负债表模板 |
| `income_statement_template` | 损益表模板 |
| `cashflow_template` | 现金流量表模板 |
| `account_mapping` | 科目映射表 |
| `standard_accounts` | 标准科目表 |
| `import_logs` | 导入日志 |
| `exchange_rates` | 汇率表（多币种支持） |

---

## 支持导入的报表类型

1. **科目余额表** — 核心事实表，资产负债/损益/现金流均可从中派生
2. **损益明细表** — 收入成本费用明细
3. **收入人次表** — 各产品线的人次和收入
4. **非学科费用分配表** — 费用分配明细
5. **管理中心部门收入成本费用表** — 部门维度收支
6. **非学科管理中心部门收入成本费用表** — 非学科部门维度收支
7. **非学科课酬** — 教师课酬明细

---

## 功能特性

- ✅ **自动识别报表类型**：根据文件名和表头关键字自动判断
- ✅ **数据校验**：试算平衡、表间勾稽、数据完整性检查
- ✅ **模板驱动报表**：资产负债表、利润表、现金流量表可通过模板灵活定义
- ✅ **跨公司汇总**：支持按公司层级进行合并查询
- ✅ **多期对比**：任意时间范围的期间对比分析
- ✅ **格式化导出**：自动设置样式、列宽、数字格式的 Excel 输出
- ✅ **导入溯源**：每次导入记录批次号，可追溯数据来源

---

## 配置说明

详细配置说明请参阅 [config/README.md](config/README.md)。

### 公司清单 (config/companies.xlsx)

定义各公司编码、名称、层级关系和合并范围。

### 标准科目表 (config/account_standard.xlsx)

定义标准科目编码、名称、类别和层级。

### 报表模板 (config/report_templates.xlsx)

定义报表的行项目、取数公式。支持三类公式：
- **科目范围**：按科目编码范围取数
- **SQL表达式**：自定义 SQL 取数
- **固定值**：直接填入固定数值

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 数据库 | SQLite（当前支持）；PostgreSQL 迁移待开发 |
| 数据处理 | Pandas、NumPy |
| Excel 读写 | OpenPyXL |
| Web 界面 | Streamlit（可选） |
| ORM | SQLAlchemy |

---

## 开发计划

- [x] 环境搭建与数据库初始化
- [x] 数据导入功能（解析器 + 校验）
- [x] 报表生成核心（模板驱动）
- [x] Excel 导出与 Streamlit 界面
- [ ] 内部交易抵消逻辑
- [ ] 权限管理
- [ ] 自动生成标准科目映射
- [ ] PostgreSQL 迁移支持

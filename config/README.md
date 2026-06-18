# 配置文件说明

## companies.xlsx
公司清单模板，包含 code/name/short_name/parent_code/level/is_consolidated 字段。

## account_standard.xlsx
标准科目表模板，包含 code/name/category/balance_direction/level/parent_code/sort_order 字段。

## report_templates.xlsx
报表模板定义，包含 balance_sheet（资产负债表）、income_statement（利润表）、cashflow（现金流量表）三个 sheet。

每个sheet包含：
| 字段 | 说明 |
|------|------|
| line_no | 行次 |
| item_name | 项目名称 |
| formula_type | 公式类型（科目范围/SQL表达式/固定值） |
| account_ranges | 科目范围（JSON格式） |
| sign | 取数符号（+/-） |
| is_subtotal | 是否小计行 |
| indent_level | 缩进层级 |

### 科目范围 JSON 格式示例
```json
[
    {"from": "1001", "to": "1012", "sign": "+"},
    {"from": "2001", "sign": "-"},
    {"from": "3001", "to": "3005", "sign": "+"}
]
```

- `from`: 起始科目编码
- `to`: 结束科目编码（可选，不指定则为单科目）
- `sign`: "+" 表示加，"-" 表示减

## 4. account_mapping.xlsx（可选）
科目映射表。如果各公司科目体系不统一，需要建立映射：
| 字段 | 说明 |
|------|------|
| company_code | 公司编码（ALL=全局映射） |
| local_code | 本地科目编码 |
| local_name | 本地科目名称 |
| standard_code | 标准科目编码 |
| standard_name | 标准科目名称 |

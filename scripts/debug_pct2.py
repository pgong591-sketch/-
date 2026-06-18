"""模拟透视和百分比转换"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd

# 模拟透视结果
pivot = pd.DataFrame({
    "项目": ["一、营业收入", "减：营业成本", "毛利", "净利率", "二、营业利润"],
    "莞城小学部": [1467682.58, 784699.67, 0.47, 0.26, 381073.44],
    "莞城初中部": [2622609.25, 972479.77, 0.63, 0.46, 1194895.27],
})

print("=== 原始数据 ===")
print(pivot)

# 模拟转换
pct_items = pivot["项目"].str.contains("毛利|净利率", na=False)
print(f"\n=== 百分比行索引 ===")
print(pct_items)

for col in pivot.columns:
    if col != "项目":
        pivot[col] = pd.to_numeric(pivot[col], errors="coerce").fillna(0)
        mask = pct_items
        pct_vals = pivot.loc[mask, col].apply(
            lambda x: f"{x*100:.0f}%" if abs(x*100 - round(x*100)) < 0.001 else f"{x*100:.1f}%"
        )
        other_vals = pivot.loc[~mask, col].apply(lambda x: f"{x:,.2f}")
        pivot[col] = pivot[col].astype(object)
        pivot.loc[mask, col] = pct_vals
        pivot.loc[~mask, col] = other_vals

print(f"\n=== 转换后 ===")
print(pivot)
print(f"\n数据类型:")
print(pivot.dtypes)

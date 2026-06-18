"""检查科目名称列的分隔符"""
import pandas as pd

df = pd.read_excel('data/202603莞城小学科目辅助余额表.xlsx', header=3)
sample = str(df.iloc[4, 1])
print("原始repr:", repr(sample))

# 检查各种分隔符
for ch in ['\\', '/', '_', '-', '|']:
    if ch in sample:
        print(f"包含分隔符 '{ch}'，拆分结果: {sample.split(ch)}")

# 用反斜杠拆分 (Python中需要转义)
if '\\' in sample:
    parts = sample.split('\\')
    print(f"反斜杠拆分: {parts}")
    print(f"编码部分: {parts[0]}")
    print(f"名称部分: {parts[1]}")
else:
    print("不包含反斜杠")

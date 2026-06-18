"""对比schema差异"""
import re

with open("db/init.sql", encoding="utf-8") as f:
    init_text = f.read()
with open("db/real_schema.sql", encoding="utf-8", errors="replace") as f:
    real_text = f.read()

def parse_tables(sql_text):
    tables = {}
    blocks = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;", sql_text, re.I | re.DOTALL)
    for tname, col_block in blocks:
        cols = {}
        for line in col_block.split("\n"):
            line = line.strip().strip(",").strip()
            if not line or line.startswith("--") or line.startswith("PRIMARY") or line.startswith("FOREIGN") or line.startswith("UNIQUE") or line.startswith("CHECK") or line.startswith("INDEX") or line.startswith("CONSTRAINT"):
                continue
            m = re.match(r'"*(\w+)"*\s+(\w+)', line)
            if m:
                cols[m.group(1)] = line.strip()
        tables[tname] = cols
    return tables

real = parse_tables(real_text)
init = parse_tables(init_text)

print("仅在真实库:", set(real) - set(init))
print("仅在init.sql:", set(init) - set(real))
print()
for t in sorted(set(real) & set(init)):
    rc, ic = set(real[t]), set(init[t])
    if rc - ic:
        print(f"  [{t}] 真实库多: {rc - ic}")
    if ic - rc:
        print(f"  [{t}] init.sql多: {ic - rc}")

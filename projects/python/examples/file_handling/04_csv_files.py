import csv
from pathlib import Path

path = Path("data/articles.csv")

with path.open("r", encoding="utf-8", newline="") as file:
    rows = list(csv.DictReader(file))

print(rows[0]["title"])  # 路径基础
print(len(rows))  # 3

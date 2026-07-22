import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


config = read_json(Path("data/config.json"))
print(config["language"])  # zh-CN

records = [{"title": "向量检索", "status": "learning"}]
path = Path("../../.agent-tmp/python-file-handling/records.json")
path.parent.mkdir(parents=True, exist_ok=True)

with path.open("w", encoding="utf-8") as file:
    json.dump(records, file, ensure_ascii=False, indent=2)

path = Path("data/documents.jsonl")

with path.open("r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        if line.strip():
            record = json.loads(line)
            print(line_number, record)

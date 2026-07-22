from pathlib import Path

path = Path("data/knowledge/guide.md")
content = path.read_text(encoding="utf-8")
print(content)

output_path = Path("../../.agent-tmp/python-file-handling/cleaned.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("清洗后的内容\n", encoding="utf-8")

path = Path("data/large-corpus.txt")

with path.open("r", encoding="utf-8") as file:
    for line in file:
        normalized = line.strip()
        if normalized:
            print(normalized)

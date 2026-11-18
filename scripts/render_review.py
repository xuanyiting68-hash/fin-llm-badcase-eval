"""把 data/questions.jsonl 渲染成便于人工审阅的 Markdown。
用法: python scripts/render_review.py data/questions.jsonl data/questions_review.md
"""
import json
import sys


def main(src: str, dst: str) -> None:
    with open(src, encoding="utf-8") as f:
        qs = [json.loads(line) for line in f if line.strip()]

    lines = ["# 题库审阅版", "", f"共 {len(qs)} 题。由 `questions.jsonl` 自动生成，修改请改 jsonl。", ""]
    current = None
    for q in qs:
        if q["category"] != current:
            current = q["category"]
            lines += [f"## {current}", ""]
        lines += [
            f"### {q['id']}（{q['difficulty']}｜{q['answer_type']}｜{q.get('persona','')}）",
            "",
            f"**题目**：{q['question']}",
            "",
            f"**标准答案**：{q['reference_answer']}",
            "",
            "**评分要点**：",
            *[f"- {p}" for p in q["key_points"]],
            "",
            *([f"**数值容差**：{q['tolerance']}", ""] if q.get("tolerance") else []),
            *(["**可接受的等价回答**："] + [f"- {a}" for a in q["accepted_alternatives"]] + [""] if q.get("accepted_alternatives") else []),
            f"**考点陷阱**：{q['trap']}",
            "",
            f"**出处**：{q['source']}",
            "",
            "**审核**：☐ 通过　☐ 需修改：",
            "",
            "---",
            "",
        ]
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

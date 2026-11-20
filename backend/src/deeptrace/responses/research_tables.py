"""Render the report's experimental comparison from grounded field records."""

import re


def _cell(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("[", "［").replace("]", "］")


def _first_table(lines):
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence or "|" not in line or index + 1 >= len(lines):
            continue
        if not re.search(r"模型|研究|论文|\b(?:models?|stud(?:y|ies)|papers?)\b", line, re.IGNORECASE):
            continue
        separator = lines[index + 1].strip().strip("|")
        columns = separator.split("|")
        if len(columns) < 2 or not all(re.fullmatch(r"\s*:?-{3,}:?\s*", c) for c in columns):
            continue
        end = index + 2
        while end < len(lines) and "|" in lines[end] and lines[end].strip():
            end += 1
        return index, end
    return None


def render_research_table(content, records, *, max_chars):
    """Replace one prose-generated table; never rewrite values or cut a row.

    The caller supplies only current visible, provenance-checked records.
    This enforces table fidelity, not the semantic correctness of the prose.
    """
    rows, studies, seen = [], set(), set()
    for record in records:
        study = record.get("research_result")
        if not study:
            continue
        for experiment in record["experiments"]:
            refs = list(dict.fromkeys(ref for cell in experiment.values() for ref in cell["refs"]
                if re.fullmatch(r"\[[1-9][0-9]*\]", ref)))
            if not refs:
                continue
            values = [experiment.get(name, {}).get("value", "本次未核实")
                      for name in ("model", "dataset", "metric", "result", "budget", "conditions")]
            key = (study["title"], *values)
            if key in seen:
                continue
            seen.add(key)
            studies.add(study["title"].casefold())
            rows.append("| " + " | ".join([_cell(study["title"]) + " " + "".join(refs),
                *[_cell(value) for value in values]]) + " |")
    if len(studies) < 2:
        return content, 0
    table = "\n".join([
        "| 研究 | 模型 | 数据集 | 指标 | 原文结果 | 计算预算 | 适用条件/实验口径 |",
        "|---|---|---|---|---|---|---|", *rows,
        "\n‘本次未核实’表示当前证据记录未覆盖，不能据此认定原论文未披露。",
    ])
    lines = content.splitlines()
    span = _first_table(lines)
    if span:
        first, last = span
        rendered = "\n".join([*lines[:first], table, *lines[last:]])
    else:
        rendered = "### 原文实验记录\n\n" + table + "\n\n" + content
    return (rendered, len(rows)) if len(rendered) <= max_chars else (content, 0)

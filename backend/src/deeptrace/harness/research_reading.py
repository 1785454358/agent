"""Bounded bilingual field queries for original scientific documents."""

import re


def scientific_reading_query(query: str) -> str:
    # Preserve the original requirement. Supplement only requested dimensions;
    # these are retrieval terms, never expected papers, answers or numbers.
    terms = []
    for pattern, english in (
        (r"模型|基座|架构", "model architecture experimental setup"),
        (r"评测|基准|数据集", "benchmark dataset evaluation"),
        (r"预算|算力|计算|开销|采样|成本", "compute budget tokens FLOPs samples"),
        (r"结果|指标|成绩", "results accuracy evaluation table"),
        (r"条件|限制|边界|协议", "conditions limitations evaluation protocol"),
    ):
        if re.search(pattern, query):
            terms.append(english)
    suffix = " " + " ".join(terms) if terms else ""
    return query[:1000-len(suffix)] + suffix

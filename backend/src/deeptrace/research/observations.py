"""Resolve field-level readings without granting semantic entailment."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, StringConstraints, ValidationError, model_validator

from deeptrace.domain.evidence import EvidenceSupport
from deeptrace.domain.research_record import ExperimentRecord, ObservedValue


class ObservationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)] = Field(
        description="逐字复制对应原文单元格或短句，不翻译、不改写、不将多个片段拼成新句子。")
    refs: list[Annotated[str, Field(pattern=r"^[npg][1-9][0-9]{0,2}$")]] = Field(min_length=1, max_length=3)


class ExperimentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ObservationDraft | None = Field(default=None, description="一个模型的原文名称，保留版本和后缀，不自行追加括号说明。")
    dataset: ObservationDraft | None = Field(default=None, description="单一评测集的原文名称；不同数据集或设置分开记录，不能列清单。")
    budget: ObservationDraft | None = Field(default=None, description="原文资源数量及单位；最大长度不是实际用量，准确率和pass@1不是预算。")
    metric: ObservationDraft | None = Field(default=None, description="与本条结果对应的单一指标原文名称。")
    result: ObservationDraft | None = Field(default=None, description="本模型、本数据集、本配置的单个原文结果值或单元格；不把多个成绩拼成说明句。")
    conditions: ObservationDraft | None = Field(default=None, description="保留本结果限制或实验协议的原文短句，不能概括改写。")
    _invalid_fields: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="wrap")
    @classmethod
    def isolate_optional_cells(cls, data, handler):
        if not isinstance(data, dict):
            return handler(data)
        values, invalid = dict(data), []
        for name in cls.model_fields:
            if values.get(name) is not None:
                try:
                    values[name] = ObservationDraft.model_validate(values[name])
                except ValidationError:
                    values[name] = None
                    invalid.append(name)
        result = handler(values)
        result._invalid_fields = invalid
        return result


def value_in_quotes(value: str, supports: list[EvidenceSupport]) -> bool:
    normalized = lambda text: " ".join(text.casefold().split())
    # The model must extract a literal value, not paraphrase a number or name.
    pattern = r"(?<![\w-])" + re.escape(normalized(value)) + r"(?![\w-])"
    return re.search(pattern, normalized(" ".join(s.quote for s in supports))) is not None


def resolve_experiments(drafts, references, supports):
    """Append new valid supports, return field-isolated records and diagnostics.

    Reference values are host-resolved short quotes. Never join experiments
    across documents or versions, even when the model says they are comparable.
    """
    original_sources = {(s.evidence_id, s.version, s.content_hash) for s in supports}
    records, issues = [], []
    for number, draft in enumerate(drafts):
        issues.extend(f"invalid_experiment_field:{number}:{name}" for name in draft._invalid_fields)
        fields, record_source = {}, None
        for name in ExperimentDraft.model_fields:
            cell = getattr(draft, name)
            if cell is None:
                continue
            groups = [references.get(ref, []) for ref in cell.refs]
            quotes = list(dict.fromkeys(s.model_dump_json() for group in groups for s in group))
            quotes = [EvidenceSupport.model_validate_json(s) for s in quotes]
            sources = {(s.evidence_id, s.version, s.content_hash) for s in quotes}
            if (not all(groups) or len(sources) != 1 or not sources <= original_sources
                    or (record_source is not None and sources != {record_source})
                    or not value_in_quotes(cell.value, quotes)
                    or (name == "budget" and re.fullmatch(
                        r"(?:pass@\d+|cons@\d+|accuracy|success rate|准确率|正确率)"
                        r"(?:\s*[,;/]\s*(?:pass@\d+|cons@\d+|accuracy))*", cell.value, re.IGNORECASE))):
                issues.append(f"invalid_experiment_field:{number}:{name}")
                continue
            additions = [s for s in quotes if s not in supports]
            if len(supports) + len(additions) > 128 or len(quotes) > 12:
                issues.append(f"experiment_support_capacity:{number}:{name}")
                continue
            supports.extend(additions)
            record_source = next(iter(sources))
            fields[name] = ObservedValue(value=cell.value, support_indices=[supports.index(s) for s in quotes])
        if fields:
            records.append(ExperimentRecord(**fields))
    return records, issues


def field_supports(finding, cell):
    if cell is None or any(i >= len(finding.supports) for i in cell.support_indices):
        return []
    quotes = [finding.supports[i] for i in dict.fromkeys(cell.support_indices)]
    if len({(s.evidence_id, s.version, s.content_hash) for s in quotes}) != 1:
        return []
    return quotes if value_in_quotes(cell.value, quotes) else []


def observation_supports(finding):
    """Required qualifiers precede generic claim paragraphs in bounded views."""
    result = []
    for experiment in finding.experiments:
        for name in ("conditions", "budget", "model", "dataset", "metric", "result"):
            for support in field_supports(finding, getattr(experiment, name)):
                if support not in result:
                    result.append(support)
    return result


def visible_research_records(findings, references):
    """Expose only field values backed by current, actually visible passages."""
    result = []
    for finding in findings:
        experiments = []
        for experiment in finding.experiments:
            fields, source = {}, None
            for name in ExperimentRecord.model_fields:
                cell = getattr(experiment, name)
                quotes = field_supports(finding, cell)
                if not quotes:
                    continue
                identity = (quotes[0].evidence_id, quotes[0].version, quotes[0].content_hash)
                if source is not None and source != identity:
                    continue
                labels = []
                for support in quotes:
                    label = next((ref for ref, passages in references.items() if any(
                        (p.evidence_id, p.version, p.content_hash) == identity
                        and p.start <= support.start < support.end <= p.end
                        and p.text[support.start-p.start:support.end-p.start] == support.quote
                        for p in passages)), None)
                    if label is None:
                        break
                    if label not in labels:
                        labels.append(label)
                else:
                    source = identity
                    fields[name] = {"value": cell.value, "refs": labels}
            if fields:
                experiments.append(fields)
        if experiments:
            result.append({"finding_id": finding.id,
                "research_result": finding.research_result.model_dump(mode="json")
                if finding.research_result else None, "experiments": experiments,
                "missing_field_meaning": "not_verified_in_visible_passages"})
        if len(result) >= 12:
            break
    return result

"""Typed budget lines; the host computes shares, totals and the displayed table."""

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, le=10**12, max_digits=18, decimal_places=4, allow_inf_nan=False)]
Quantity = Annotated[Decimal, Field(ge=0, le=10**6, max_digits=12, decimal_places=4, allow_inf_nan=False)]
Divisor = Annotated[Decimal, Field(gt=0, le=10**6, max_digits=12, decimal_places=4, allow_inf_nan=False)]


class BudgetItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    low: Money | None
    high: Money | None
    quantity: Quantity = Decimal(1)
    divisor: Divisor = Decimal(1)
    kind: Literal["verified", "reference", "estimate", "unpriced"]
    scope: Literal["selected", "optional"] = "selected"
    note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def valid_price(self):
        if self.scope == "optional" and not self.note.strip():
            raise ValueError("optional_expense_requires_exclusion_reason")
        if self.kind == "unpriced":
            if self.low is not None or self.high is not None:
                raise ValueError("unpriced_is_not_zero")
        elif self.low is None or self.high is None or self.low > self.high:
            raise ValueError("invalid_price_range")
        return self

    def amount(self):
        if self.low is None:
            return None
        return tuple((v * self.quantity / self.divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                     for v in (self.low, self.high))


class BudgetTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=32)
    items: list[BudgetItem] = Field(min_length=1, max_length=16)


def _cell(text):
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _number(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _range(values):
    return _number(values[0]) if values[0] == values[1] else "—".join(_number(v) for v in values)


def render_budget_content(content: str, budgets: list[BudgetTable]) -> tuple[str, list[str]]:
    references = re.findall(r"\{\{budget_(\d+)\}\}", content)
    if sorted(references) != [str(i) for i in range(1, len(budgets) + 1)]:
        raise ValueError("invalid_budget_placeholders")
    if any(not 1 <= int(i) <= len(budgets) for i in re.findall(r"\{\{total_(\d+)\}\}", content)):
        raise ValueError("invalid_budget_total_reference")
    if budgets:
        # There is no safe way to bind a free-written alternate total to a
        # scope. Remove the duplicate checksum; the typed tables remain exact.
        number = r"\d+(?:,\d{3})*(?:\.\d+)?"
        # Bind only an explicit currency assertion immediately after a label.
        # Crossing arbitrary prose consumes scope headings and counts such as
        # “两人合计，人均2000元口径” or “余量，可增加1–2顿正餐”.
        content = re.sub(
            r"(合计|小计|总额|余量)[ \t]*(?:(?:约为|大约|预计|为|约|共|[:：=])[ \t]*)?"
            + r"(?:\*\*)?" + number
            + r"(?:[ \t]*[—–-][ \t]*" + number + r")?[ \t]*元(?:\*\*)?",
            lambda match: match[1] + "以对应预算表为准", content,
        )
    if re.search(r"^\|\s*(?:\*\*)?(?:已知|已列金额|已核实)?(?:合计|小计|总计|total|subtotal)", content, re.M | re.I):
        raise ValueError("unstructured_budget_total")
    unresolved = []
    labels = {"verified": "已核实", "reference": "参考报价", "estimate": "估算", "unpriced": "待核实"}
    for index, budget in enumerate(budgets, 1):
        rows = [f"**{_cell(budget.scope)}**", "", f"| 项目 | 金额（{_cell(budget.unit)}） | 性质 | 说明 |",
                "|---|---:|---|---|"]
        totals, unknown = [Decimal(0), Decimal(0)], []
        for item in budget.items:
            amount = item.amount()
            if item.scope == "optional":
                pass
            elif amount is None:
                unknown.append(item.label)
            else:
                totals = [a + b for a, b in zip(totals, amount)]
            rows.append(f"| {_cell(item.label)} | {_range(amount) if amount else '待核实'} | "
                        f"{labels[item.kind]}{'（可选，不计入合计）' if item.scope == 'optional' else ''} | {_cell(item.note)} |")
        label = "已列金额小计（不含待核实项）" if unknown else "合计"
        rows.append(f"| **{label}** | **{_range(totals)}** | — | 按上表已列金额加总 |")
        if unknown:
            reason = f"{budget.scope}未计价：" + "、".join(unknown)
            unresolved.append(reason[:300])
            rows.extend(["", "未计价项目仍需核实，不能据此承诺整体预算。"])
        content = content.replace("{{budget_" + str(index) + "}}", "\n".join(rows))
        content = content.replace("{{total_" + str(index) + "}}", _range(totals))
    if unresolved:
        content = "> 预算尚未完整计价：" + "；".join(unresolved) + "。不能据此承诺整体预算。\n\n" + content
    return content, unresolved

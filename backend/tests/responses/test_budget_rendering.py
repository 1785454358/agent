"""Typed budget lines produce totals; a model does not write its own checksum."""

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError
from langchain_core.messages import AIMessage

from responses.test_solution_consistency import solution_case


def budget_data():
    return {"scope": "2人同行，每人费用", "unit": "元/人", "items": [
        {"label": "住宿", "low": 350, "high": 500, "quantity": 2, "divisor": 2, "kind": "estimate"},
        {"label": "景山", "low": 2, "high": 2, "kind": "verified", "note": "来源 [1]"},
        {"label": "慕田峪", "low": 60, "high": 60, "kind": "reference"},
        {"label": "长城交通", "low": 32, "high": 80, "kind": "reference"},
        {"label": "地铁", "low": 30, "high": 40, "kind": "estimate"},
        {"label": "餐饮", "low": 100, "high": 150, "quantity": 3, "kind": "estimate"},
        {"label": "机动", "low": 300, "high": 500, "kind": "estimate"},
        {"label": "故宫", "low": None, "high": None, "kind": "unpriced"},
        {"label": "天坛", "low": None, "high": None, "kind": "unpriced"},
    ]}


def test_totals_and_shares_are_computed_and_unknown_costs_are_never_zero():
    from deeptrace.responses.budgets import BudgetTable, render_budget_content

    table = BudgetTable.model_validate(budget_data())
    content, unresolved = render_budget_content("行程 [1]。\n\n{{budget_1}}", [table])
    assert "1074—1632" in content
    assert "300—450" in content
    assert "{{budget_1}}" not in content
    assert "待核实" in content and "故宫" in content and "天坛" in content
    assert "不能据此承诺整体预算" in content
    assert unresolved


@pytest.mark.parametrize("defect", ["negative", "backwards", "formula", "zero_divisor", "missing_price"])
def test_unsafe_or_inconsistent_budget_line_is_rejected(defect):
    from deeptrace.responses.budgets import BudgetTable

    data = budget_data()
    row = data["items"][0]
    if defect == "negative": row["low"] = -1
    elif defect == "backwards": row["high"] = 100
    elif defect == "formula": row["low"] = "10+20"
    elif defect == "zero_divisor": row["divisor"] = 0
    else: row["low"] = None
    with pytest.raises(ValidationError):
        BudgetTable.model_validate(data)


def test_budget_placeholder_is_required_and_cannot_be_duplicated_or_invented():
    from deeptrace.responses.budgets import BudgetTable, render_budget_content

    table = BudgetTable.model_validate(budget_data())
    for content in ["No budget", "{{budget_1}} {{budget_1}}", "{{budget_2}}"]:
        with pytest.raises(ValueError):
            render_budget_content(content, [table])


def test_prose_totals_reference_the_same_host_computed_values():
    from deeptrace.responses.budgets import BudgetTable, render_budget_content

    table = BudgetTable.model_validate(budget_data())
    content, _ = render_budget_content("已知小计{{total_1}}，未含待核实项。\n{{budget_1}}", [table])
    assert "{{total_1}}" not in content
    assert content.count("1074—1632") == 2
    # Keep valid structured work; discard a free-written duplicate checksum
    # instead of spending the last provider allowance repairing presentation.
    content, _ = render_budget_content("已知小计1014—1592元。\n{{budget_1}}", [table])
    assert "1014—1592" not in content
    assert "1074—1632" in content
    with pytest.raises(ValueError):
        render_budget_content("{{total_2}}\n{{budget_1}}", [table])


def test_budget_scope_and_meal_counts_are_not_rewritten_as_duplicate_totals():
    from deeptrace.responses.budgets import BudgetTable, render_budget_content

    table = BudgetTable.model_validate(budget_data())
    heading = "分项预算（两人合计，人均2000元口径）"
    remainder = "余量，可用于：升级住宿档位、增加1–2顿正餐。"
    content, _ = render_budget_content(
        heading + "\n" + remainder + "\n{{budget_1}}", [table],
    )
    assert heading in content
    assert remainder in content


@pytest.mark.parametrize("statement", ["合计约1,632元", "小计：1074—1632元", "余量为300元"])
def test_explicit_free_written_currency_totals_remain_subject_to_validation(statement):
    from deeptrace.responses.budgets import BudgetTable, render_budget_content

    table = BudgetTable.model_validate(budget_data())
    content, _ = render_budget_content(statement + "。\n{{budget_1}}", [table])
    assert statement not in content
    assert "以对应预算表为准" in content


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_table", [False, True])
async def test_review_renders_host_total_and_unknown_cost_forces_partial_information(legacy_table):
    from deeptrace.responses.fact_review import review_answer

    payload, fixture = await solution_case()

    class Reviewer:
        calls = 0

        async def invoke(self, **kwargs):
            self.calls += 1
            if legacy_table and self.calls == 1:
                return AIMessage(content=json.dumps({"content": "[1]\n|项目|金额|\n|---|---|\n|住宿|10|\n|合计|100|",
                    "issues": [], "unanswered_points": [], "consistency_checks": [
                        {"check_id": key, "status": "passed", "reason": "Same scope"} for key in ["c1", "c2"]]}))
            return AIMessage(content=json.dumps({"content": "建议路线 [1]。\n\n{{budget_1}}",
                "budgets": [budget_data()], "issues": [], "unanswered_points": [],
                "consistency_checks": [{"check_id": key, "status": "passed", "reason": "Same scope"}
                                       for key in ["c1", "c2"]]}))

    model = Reviewer()
    result = await review_answer(replace(fixture.context, model_gateway=model), question="Plan a trip",
        constraints=[], content="Wrong model subtotal [1]。", sources=["[1] reference"], input_budget=20000,
        max_content_chars=8000, delivery_plan=payload.research_outcome.delivery_plan)
    assert "1074—1632" in result.content
    assert result.unanswered_points
    assert model.calls == (2 if legacy_table else 1)

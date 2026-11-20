from deeptrace.observability.messages import public_event_details


def test_model_measurement_json_fields_survive_public_event_projection():
    details = public_event_details({'prompt_segment_estimates_json':'{"evidence":123}',
        'request_parameters_json':'{"model":"fixture","temperature":0}',
        'api_key':'secret'})
    assert details == {'prompt_segment_estimates_json':'{"evidence":123}',
        'request_parameters_json':'{"model":"fixture","temperature":0}'}


def test_public_details_keep_flow_and_error_fields_without_arbitrary_payloads():
    payload = {
        "tool": "fetch_page", "call_id": "call-1", "ok": False,
        "message": "浏览器抓取超时", "error_code": "browser_failed",
        "round": 2, "tasks_json": '["查阅论文"]', "api_key": "secret",
        "request": {"authorization": "secret"}, "diagnostics": {"anything": 1},
    }
    details = public_event_details(payload)
    assert details == {k: payload[k] for k in ["tool", "call_id", "ok", "message", "error_code", "round", "tasks_json"]}


def test_preflight_observation_preserves_result_without_preview_or_secrets():
    details = public_event_details({
        "tool": "read_evidence", "tool_call_id": "read-1",
        "result": {"ok": False, "error_code": "evidence_not_authorized", "message": "读取未获授权", "preview": "secret"},
    })
    assert details == {"tool": "read_evidence", "call_id": "read-1", "ok": False,
                       "error_code": "evidence_not_authorized", "message": "读取未获授权"}


def test_observation_uses_gateway_identity_when_both_ids_are_present():
    details = public_event_details({"call_id": "scoped-call", "tool_call_id": "model-call"})
    assert details["call_id"] == "scoped-call"


def test_replayed_tool_has_a_readable_message():
    from deeptrace.observability.messages import humanize_event_message

    assert humanize_event_message("tool.replayed", {"tool": "search_web", "ok": True}) == "网页搜索复用已有结果"

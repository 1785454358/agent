"""Provider compatibility options, separate from runtime assembly."""

from langchain_openai import ChatOpenAI


def build_model_gateway(settings, gateway_type):
    thinking = settings.model_thinking
    if thinking == "auto":
        thinking = (
            "disabled"
            if settings.openai_model.lower().startswith(
                ("doubao-seed-2.0-lite", "doubao-seed-2-0-lite")
            )
            else "provider_default"
        )
    extra_body = (
        None if thinking == "provider_default" else {"thinking": {"type": thinking}}
    )
    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0,
        max_retries=0,
        max_tokens=settings.openai_max_tokens,
        extra_body=extra_body,
    )
    model_gateway = gateway_type(
        model,
        timeout_seconds=settings.planner_timeout_seconds,
        retry_attempts=1,
        role_overrides={
            role: {"response_format": {"type": "json_object"}}
            for role in (
                "planner",
                "scope_reviewer",
                "replanner",
                "supervisor",
                "follow_up",
                "evaluator",
                "responder",
            )
        }
        if settings.openai_model.lower().startswith(
            (
                "doubao-seed-2.0-lite",
                "doubao-seed-2-0-lite",
                "deepseek-v4.1-flash",
                "deepseek-v4-1-flash",
            )
        )
        else None,
        role_timeout_seconds={
            "router": min(20.0, settings.planner_timeout_seconds),
            "evaluator": settings.evaluator_timeout_seconds,
            "responder": settings.writer_timeout_seconds,
        },
    )

    return model_gateway

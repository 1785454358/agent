import pytest


@pytest.mark.asyncio
async def test_document_example_uses_real_file_gateway_and_measured_calls(tmp_path):
    from deeptrace.examples.local_documents import run_document_demo

    (tmp_path / "guide.md").write_text(
        "One loop, explicit tools, bounded execution.", encoding="utf-8"
    )
    result = await run_document_demo(tmp_path, "guide.md")
    assert result["stop_reason"] == "completed"
    assert "One loop, explicit tools, bounded execution." in result["outcome"]
    assert result["usage"]["provider_attempts"] == 2
    assert result["usage"]["input_tokens"] is None
    assert [message.type for message in result["messages"]] == ["ai", "tool", "ai"]


@pytest.mark.asyncio
async def test_document_example_returns_controlled_failure_on_directory_escape(
    tmp_path,
):
    from deeptrace.examples.local_documents import run_document_demo

    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "private.md").write_text("Secret outside root", encoding="utf-8")
    result = await run_document_demo(root, "../private.md")
    assert result["stop_reason"] == "tool_error"
    assert "Secret outside root" not in result["outcome"]

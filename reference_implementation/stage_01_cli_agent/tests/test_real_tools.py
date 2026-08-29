from deeptrace.config import Settings


def test_real_service_settings_are_available() -> None:
    settings = Settings.from_env()

    assert settings.openai_api_key
    assert settings.openai_base_url.startswith(("http://", "https://"))
    assert settings.openai_model
    assert settings.tavily_api_key
    assert 1 <= settings.max_steps <= 20
    assert 1_000 <= settings.max_page_chars <= 100_000

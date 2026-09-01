from deeptrace.tools.search import rank_search_results


def test_ranking_prefers_primary_and_diverse_sources() -> None:
    results = [
        {
            "title": "Best agents in 2026",
            "url": "https://seo.example/list",
            "snippet": "2026",
        },
        {
            "title": "2024 agent release",
            "url": "https://openai.com/research/release",
            "snippet": "2024 release",
        },
        {
            "title": "2024 agent paper",
            "url": "https://arxiv.org/abs/2401.00001",
            "snippet": "2024",
        },
    ]

    ranked = rank_search_results(results, "2024 agent progress", {2024})

    assert [item["url"] for item in ranked[:2]] == [
        "https://openai.com/research/release",
        "https://arxiv.org/abs/2401.00001",
    ]
    assert all(item["registered_domain"] for item in ranked)

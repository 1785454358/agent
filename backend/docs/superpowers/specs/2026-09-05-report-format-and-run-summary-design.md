# Report Formatting and Run Summary Design

## Goal

Make the Basic research report read like a numbered paper while keeping the
current flat pipeline and deterministic fallback. The final report must not
show URLs in its body or use Markdown heading markers. The final research
event must summarize wall-clock duration and Provider token usage.

## Scope

This change affects the Writer prompt, deterministic report post-processing,
fallback output, the final `run.completed` event, tests, and user-facing
documentation. It does not add `ResearchNote`, Claim, Evidence, Verifier, or
any other persistent or structured research object. It must not add another
model call.

## Report headings

The Writer is instructed to emit a plain report title followed by numbered
section headings:

```text
1 Top-level section
1.1 Subsection
1.1.1 Third-level section
```

The final report must contain no Markdown ATX heading markers (`#`). A
deterministic normalizer removes accidental heading markers from model and
fallback output. Numbered headings already produced by the model remain
unchanged.

## Citations and references

The Writer prompt receives a stable source-index map and cites sources with
internal source markers. Post-processing also recognizes known source URLs
when the model emits a Markdown link or bare URL despite the prompt.

The renderer scans the report body from start to finish. The first distinct
source encountered becomes `[1]`, the next becomes `[2]`, and repeated uses
keep their original number. URLs and Markdown link targets are removed from
the body. Link labels are retained when useful, followed by the numbered
citation.

Only sources cited in the body are included in the final reference list. The
list appears at the end without a Markdown heading marker:

```text
参考文献

[1] https://example.com/first
[2] https://example.com/second
```

English reports use `References`. The public `sources` metadata continues to
contain the complete de-duplicated collection source list, including sources
not cited by the Writer.

The same renderer is applied to deterministic fallback reports so copied
`Source:` lines cannot expose body URLs.

## Completion event

`run.completed` remains the last pipeline event. Its message includes:

```text
研究任务完成；总耗时 86.4 秒；总消耗 Token 12,345
```

Elapsed time is measured from the run's existing UTC `started_at` value until
the Writer has finished. Token usage is the sum of all Provider usage reported
by Planner and Writer calls, including retries. Search, scraping, and local BGE
work do not report Provider tokens and therefore do not add to this value.

The event details include `elapsed_seconds`, `total_tokens`, `input_tokens`,
and `output_tokens`. Providers that omit usage metadata naturally contribute
zero, matching the existing accounting behavior.

## Verification

Tests cover first-appearance citation ordering, repeated citations, Markdown
links, bare URLs, unknown URLs, no body URLs, no heading markers, fallback
formatting, localized reference headings, cumulative Planner/Writer usage,
elapsed time, and final event ordering. The complete test suite must pass
before the server is restarted for browser verification.

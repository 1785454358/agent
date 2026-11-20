"""Narrow guards for reproduced retry-code errors; never execute model code."""

import re


def retry_constraint_issue(question: str, content: str) -> str | None:
    code = "\n".join(re.findall(r"```[^\n]*\n(.*?)```", content, re.S))
    restricted_post = "post" in question.casefold() and re.search(
        r"(?:未|没有|无).{0,16}(?:去重|幂等)|without.{0,20}(?:dedup|idempotenc)", question, re.I
    )
    if restricted_post:
        if re.search(
            r"\band\s+not\s+accept_?duplicate_?risk\b|\bor\s+(?:accept_?duplicate_?risk|business_?accepts_?(?:duplicate_?)?risk)\b", code, re.I
        ):
            return "unsafe_post_retry_override"
        # A renamed Boolean must not conceal the same unsafe policy in prose.
        # Negative explanations remain valid, e.g. “不能以业务接受重复为依据”.
        for sentence in re.split(r"[。！？\n]", content):
            if (re.search(r"业务.{0,20}(?:接受|容忍).{0,16}(?:重复|风险)", sentence)
                    and not re.search(r"不得|不能|不应|不允许|禁止|不是|不构成", sentence)):
                return "unsafe_post_retry_override"
    if re.search(r"retry|重试", question, re.I) and re.search(r"总时限|总预算|total.{0,12}(?:budget|deadline)", question, re.I):
        for arguments in re.findall(r"\bsend\s*\(([^()\n]*)\)", code):
            if not re.search(r"timeout|deadline|remaining|超时|剩余", arguments, re.I):
                return "unbounded_http_send"
    return None

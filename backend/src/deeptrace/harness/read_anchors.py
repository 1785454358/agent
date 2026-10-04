"""Validate only actual successful read previews at the host tool boundary."""

import json

from pydantic import ValidationError

from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor


def capture_read_anchors(
    preview: str, evidence_id: str
) -> tuple[list[ReadEvidenceAnchor], list[str]]:
    try:
        payload = json.loads(preview)
        if payload["evidence_id"] != evidence_id or payload["historical"] is not False:
            raise ValueError("read_source_mismatch")
        if type(payload["version"]) is not int or payload["version"] < 1:
            raise ValueError("invalid_read_version")
        body_length = payload["selection"]["body_length"]
        if type(body_length) is not int or body_length < 0:
            raise ValueError("invalid_body_length")
        if not isinstance(payload["passages"], list):
            raise TypeError("invalid_passages")
        anchors = []
        for passage in payload["passages"]:
            anchor = ReadEvidenceAnchor.model_validate(
                {
                    k: passage.get(k, payload.get(k))
                    for k in ("evidence_id", "version", "content_hash", "start", "end")
                }
            )
            if (
                anchor.evidence_id != evidence_id
                or anchor.version != payload["version"]
                or anchor.content_hash != payload["content_hash"]
                or anchor.end > body_length
                or not isinstance(passage["text"], str)
                or len(passage["text"]) != anchor.end - anchor.start
            ):
                raise ValueError("invalid_read_passage")
            anchors.append(anchor)
        return anchors, []
    except (ValueError, TypeError, KeyError, ValidationError):
        return [], ["invalid_read_anchor_preview"]

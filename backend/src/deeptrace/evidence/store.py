"""只在当前进程存活的轻量 Evidence Store。"""

from collections.abc import Iterable, Mapping

from deeptrace.models import Claim, Evidence, Source


class EvidenceStore:
    """提供不可变式 upsert 与 Claim 血缘反查。"""

    def __init__(
        self,
        *,
        sources: Mapping[str, Source] | None = None,
        evidence: Mapping[str, Evidence] | None = None,
        claims: Mapping[str, Claim] | None = None,
    ) -> None:
        self.sources = dict(sources or {})
        self.evidence = dict(evidence or {})
        self.claims = dict(claims or {})

    def upsert_sources(self, items: Iterable[Source]) -> "EvidenceStore":
        updated = {**self.sources, **{item.source_id: item for item in items}}
        return EvidenceStore(
            sources=updated, evidence=self.evidence, claims=self.claims
        )

    def upsert_evidence(self, items: Iterable[Evidence]) -> "EvidenceStore":
        updated = {
            **self.evidence,
            **{item.evidence_id: item for item in items},
        }
        return EvidenceStore(
            sources=self.sources, evidence=updated, claims=self.claims
        )

    def upsert_claims(self, items: Iterable[Claim]) -> "EvidenceStore":
        updated = {**self.claims, **{item.claim_id: item for item in items}}
        return EvidenceStore(
            sources=self.sources, evidence=self.evidence, claims=updated
        )

    def evidence_for_claim(self, claim_id: str) -> list[Evidence]:
        claim = self.claims.get(claim_id)
        if claim is None:
            return []
        return [
            self.evidence[item_id]
            for item_id in claim.evidence_ids
            if item_id in self.evidence
        ]

    def sources_for_claim(self, claim_id: str) -> list[Source]:
        result: list[Source] = []
        seen: set[str] = set()
        for item in self.evidence_for_claim(claim_id):
            if item.source_id in seen or item.source_id not in self.sources:
                continue
            seen.add(item.source_id)
            result.append(self.sources[item.source_id])
        return result


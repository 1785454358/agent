"""Evidence 入库、稳定 ID 与运行时查询公共接口。"""

from deeptrace.evidence.ids import (
    claim_id,
    evidence_id,
    source_id,
    stable_id,
)
from deeptrace.evidence.ingest import (
    EvidenceIngestResult,
    ingest_notes,
    locate_quote,
)
from deeptrace.evidence.store import EvidenceStore

__all__ = [
    "EvidenceIngestResult",
    "EvidenceStore",
    "claim_id",
    "evidence_id",
    "ingest_notes",
    "locate_quote",
    "source_id",
    "stable_id",
]

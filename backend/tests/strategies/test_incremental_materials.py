import json

import pytest
from deeptrace.domain import EvidenceSupport, Finding, ResearchRequirement
from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
from deeptrace.strategies.evaluation_materials import assemble_reference_evaluation_view
from strategies.fixtures import build_gateway_fixture
from strategies.test_reference_materials import seed


@pytest.mark.asyncio
async def test_incremental_view_keeps_whole_proof_and_new_conflicting_text():
    fixture = build_gateway_fixture()
    body = 'Cancellation is cooperative; cleanup must run.\n\n' + 'Unseen middle. ' * 400 + '\n\n' + ('Previously checked cancellation discussion. ' * 8 + '\n\n') * 10
    old = await seed(fixture, 1, body)
    new = await seed(fixture, 2, 'A newer rule contradicts the earlier cancellation guarantee.')
    proof = 'Cancellation is cooperative; cleanup must run.'
    support = EvidenceSupport(evidence_id=old.id, version=old.version,content_hash=old.content_hash,
        start=0,end=len(proof),quote=proof)
    finding = Finding(id='f1',claim=proof,evidence_ids=[old.id],confidence=0.9,supports=[support])
    kwargs = dict(question='Cancellation',requirements=[ResearchRequirement(id='r1',description='Cancellation')],
        evidence_ids=[old.id,new.id],findings=[finding],read_anchors=[
            ReadEvidenceAnchor(evidence_id=old.id,version=old.version,content_hash=old.content_hash,start=0,end=len(proof)),
            ReadEvidenceAnchor(evidence_id=old.id,version=old.version,content_hash=old.content_hash,
                start=body.index('Previously'),end=len(body)),
        ])
    initial = await assemble_reference_evaluation_view(fixture.context, **kwargs)
    previous = [{'evidence_id':p.evidence_id,'version':p.version,'content_hash':p.content_hash,
                 'start':p.start,'end':p.end} for p in initial.passages if p.evidence_id == old.id]
    result = await assemble_reference_evaluation_view(fixture.context, **kwargs, previous_read_ranges=previous)
    material = json.loads(result.prompt.split('EVIDENCE_VIEW_JSON:',1)[1])
    texts = '\n'.join(p['text'] for p in material['passages'])
    assert proof in texts
    assert 'newer rule contradicts' in texts
    assert len(result.prompt) < len(initial.prompt)

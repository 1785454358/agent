"""Optimistic snapshots: a stale run owner cannot overwrite newer consumption."""

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from deeptrace.persistence.orm import ModelBudgetRow


class SqlAlchemyModelBudgetStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def load(self, run_id):
        async with self._sessions() as session:
            row = await session.get(ModelBudgetRow, run_id)
            return (row.revision, row.payload) if row is not None else None

    async def save(self, run_id, payload, expected_revision):
        revision = (expected_revision or 0) + 1
        try:
            async with self._sessions() as session, session.begin():
                if expected_revision is None:
                    session.add(
                        ModelBudgetRow(
                            run_id=run_id, revision=revision, payload=payload
                        )
                    )
                    await session.flush()
                else:
                    result = await session.execute(
                        update(ModelBudgetRow)
                        .where(
                            ModelBudgetRow.run_id == run_id,
                            ModelBudgetRow.revision == expected_revision,
                        )
                        .values(revision=revision, payload=payload)
                    )
                    if result.rowcount != 1:
                        raise RuntimeError("budget_revision_conflict")
        except IntegrityError as exc:
            raise RuntimeError("budget_revision_conflict") from exc
        return revision

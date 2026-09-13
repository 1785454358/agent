# Budget and Tool Ledger Recovery Design

## Goal

Make distributed crash recovery preserve exact tool budget consumption and make SQL execution followers recover without runtime errors or duplicate ownership.

## Design

Budget seeding is asynchronous and guarded by a single initialization lock. The durable ledger returns usage grouped by `(mode, caller_id)`; the runtime expands that data into real `BudgetScopeKey` values for run, mode, and agent scopes before the first reservation proceeds. Seed failure remains fail-open, but all concurrent callers observe the same completed initialization attempt.

Each tool execution row stores cumulative committed `BudgetUnits`. The gateway passes zero units for replayed cache hits and rejected/unstarted calls, and passes the committed reservation units for every actual provider attempt, including transient failures. A later generation increments the same row, so recovery reads exact durable counters instead of inferring usage from terminal status.

`wait()` remains a follower-only operation returning `ToolResult`. A recoverable or abandoned owner causes `ExecutionAbandonedError`; the caller may retry through `claim()`. SQL ownership transitions happen inside transactions, and first-insert uniqueness conflicts are resolved by re-reading the row instead of leaking `IntegrityError`.

## Error Handling

- Invalid or foreign claims remain rejected.
- Stale owners cannot complete a newer generation.
- A recoverable result durably records its budget before ownership is released.
- Budget reconstruction failure is logged once and does not deadlock reservations.

## Verification

- A non-empty seed updates run, mode, and agent counters.
- Concurrent first reservations wait for one seed operation.
- SQL followers are awakened with a retry signal after transient failure.
- Reclaimed generations accumulate exact committed units.
- Cached and budget-exhausted executions add zero units.
- Migration upgrades existing databases with zero-valued usage columns.


import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from deeptrace.multi_agent.runtime import MultiAgentRuntime, QuotaManager


def test_first_batch_reserves_follow_up_capacity():
    async def scenario():
        quota = QuotaManager(total=30, per_researcher=10, reserve_ratio=0.2)
        leases = await quota.allocate_initial(["r1", "r2", "r3"])
        assert [leases[key].limit for key in ("r1", "r2", "r3")] == [8, 8, 8]
        assert quota.reserved == 6
        assert [await leases["r1"].acquire_network() for _ in range(9)] == [
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            False,
        ]
        assert await leases["r2"].acquire_network()

    asyncio.run(scenario())


def test_unused_first_batch_capacity_is_returned_for_follow_up():
    async def scenario():
        quota = QuotaManager(total=10, per_researcher=4, reserve_ratio=0.2)
        leases = await quota.allocate_initial(["r1", "r2"])
        assert await leases["r1"].acquire_network()
        await leases["r1"].release()
        await leases["r2"].release()
        follow_up = await quota.allocate_follow_up(["r3"])
        assert follow_up["r3"].limit == 4
        assert quota.consumed == 1

    asyncio.run(scenario())


def test_parallel_acquire_never_exceeds_global_or_local_limit():
    async def scenario():
        quota = QuotaManager(total=3, per_researcher=3, reserve_ratio=0)
        lease = (await quota.allocate_initial(["r1"]))["r1"]
        results = await asyncio.gather(*(lease.acquire_network() for _ in range(10)))
        assert sum(results) == 3
        assert quota.consumed == 3

    asyncio.run(scenario())


def test_runtime_counts_supervisor_usage_and_emits_event():
    class Model:
        async def ainvoke(self, messages):
            return AIMessage(
                content="ok",
                usage_metadata={
                    "input_tokens": 2,
                    "output_tokens": 3,
                    "total_tokens": 5,
                },
            )

    async def scenario():
        runtime = MultiAgentRuntime(
            SimpleNamespace(multi_agent_call_timeout_seconds=1)
        )
        await runtime.invoke(Model(), [], "supervisor")
        runtime.emit("supervisor.started", "开始")
        assert runtime.steps == 1
        assert runtime.role_usage.supervisor.total_tokens == 5
        assert runtime.events[0].event_type == "supervisor.started"

    asyncio.run(scenario())


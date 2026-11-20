**结论：** 在 Python 3.11 中，`asyncio.gather()` 默认 `return_exceptions=False` 时，第一个异常会立即传播给等待 `gather()` 的任务，但 `aws` 中其他 awaitable **不会被取消**，会继续运行 [1]。因此修复不能只靠“捕获异常”，而要让失败触发对同组任务的取消：若可接受 3.11+ 且希望结构化并发，选 `TaskGroup`；若需兼容 3.10 及更早或保留 `gather` 调用形态，选手动取消。选择依据正是上述诊断：`gather` 的异常传播与取消是分离的，必须显式补上取消动作。

## 一、原因分析

`gather` 文档明确写道：若 `return_exceptions` 为 `False`（默认），第一个抛出的异常会立即传播到等待 `gather()` 的任务，`aws` 序列中的其他 awaitable **won’t be cancelled**，并将继续运行 [1]。

还需注意三个边界：

- 若 `gather()` 本身被取消，所有尚未完成的提交 awaitable 也会被取消 [1]。
- 若 `aws` 中某个 Task/Future 被取消，它被当作抛出 `CancelledError`，但 `gather()` 调用本身**不会**因此被取消，以避免一个子任务取消导致其他子任务被取消 [1]。
- 文档特别提示：`return_exceptions=False` 时，`gather()` 因传播异常而标记完成后，再调用 `gather.cancel()` 不会取消其他 awaitable [1]。所以“先 await 抛异常、再 cancel gather”不是有效修复。

## 二、方案选择

| 维度 | `TaskGroup` | 手动取消 `gather` |
|---|---|---|
| 首个非取消异常后的行为 | 组内剩余任务被取消，且不能再添加新任务 [1] | 默认不取消其他任务，需自行实现 [1] |
| 异常汇总 | 全部结束后以 `ExceptionGroup`/`BaseExceptionGroup` 抛出 [1] | 默认只传播第一个异常 [1] |
| 版本 | 3.11 新增 [1] | 可用于更早版本（本次资料仅覆盖 3.11 文档） |
| 适用 | 新代码、可要求 3.11+、希望结构化并发 | 需兼容旧版本，或已有 `gather` 结构不宜大改 |

**建议：** 新项目且运行环境确定 ≥3.11 时优先 `TaskGroup`，因为它把“一个失败→取消其余→等待全部结束→汇总异常”内建为语义 [1]。需要兼容 3.10 及更早时，用 `gather` 加显式取消；这是基于版本可用性的取舍，旧版本行为未在本次资料中核实。

## 三、修复步骤

### 方案 A：TaskGroup（3.11+）

```python
import asyncio

async def main():
    async with asyncio.TaskGroup() as tg:
        t1 = tg.create_task(work(1))
        t2 = tg.create_task(work(2))
        t3 = tg.create_task(work(3))
    # 退出 async with 时等待全部任务；
    # 若有非 CancelledError 失败，这里抛 ExceptionGroup
    return [t1.result(), t2.result(), t3.result()]

try:
    asyncio.run(main())
except* ExceptionGroup as eg:
    for exc in eg.exceptions:
        print("failed:", repr(exc))
```

要点：

1. 用 `async with asyncio.TaskGroup()` 包住任务创建；组内任务在上下文退出时全部被等待 [1]。
2. 第一个非 `CancelledError` 失败会取消组内剩余任务，且此后不能再添加任务 [1]。
3. 若 `async with` 主体仍在执行，直接包含该语句的任务也会被取消；由此产生的 `CancelledError` 会中断 `await`，但不会冒出 `async with` [1]。
4. 全部结束后，非取消异常合并为 `ExceptionGroup`/`BaseExceptionGroup` 抛出 [1]。`KeyboardInterrupt`、`SystemExit` 是特例：仍取消并等待其余任务，但重新抛出原异常而非异常组 [1]。

### 方案 B：手动取消 gather

```python
import asyncio

async def run_all(coros):
    tasks = [asyncio.create_task(c) for c in coros]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            if not t.done():
                t.cancel()
        # 等待取消真正落地，并收集清理阶段的异常
        results = await asyncio.gather(*tasks, return_exceptions=True)
        raise
```

要点：

1. 先把协程包装成 `Task` 并保留引用；`create_task()` 会把协程自动调度运行 [1]。
2. 在 `except BaseException` 中取消所有未完成任务。用 `BaseException` 是为了同时覆盖普通异常与取消路径；`CancelledError` 直接继承 `BaseException` [1]。
3. 取消后必须再等待任务结束，否则清理逻辑可能尚未执行完。`Task.cancel()` 只是请求取消，会在下一个事件循环周期向协程抛 `CancelledError`，协程可用 `try/finally` 清理 [1]。
4. 第二次 `gather(..., return_exceptions=True)` 用于等待并吞掉取消产生的 `CancelledError`，避免掩盖原始异常；随后 `raise` 重抛原始异常。
5. 不要依赖“捕获异常后再 `gather.cancel()`”：此时 `gather()` 已因异常标记完成，不会再取消其他 awaitable [1]。

## 四、逐项验证

### 1. 异常传播

- `TaskGroup`：构造一个任务立即 `raise ValueError`，其余任务 `await asyncio.sleep(10)`。预期：其余任务被取消，`async with` 退出处抛 `ExceptionGroup`，其中含 `ValueError` [1]。
- 手动取消：同样构造，预期 `await gather()` 立即抛 `ValueError`；进入 `except` 后其余任务被 `cancel()`，第二次 `gather` 返回含 `CancelledError` 的结果列表，原始 `ValueError` 被重抛。
- 对照验证原始缺陷：不取消时，`gather` 抛异常后其余任务仍会打印完成日志，符合文档“won’t be cancelled” [1]。

### 2. 取消后清理

- 在每个工作任务中写 `try/finally`，`finally` 里记录“cleanup done”。文档建议协程用 `try/finally` 可靠执行清理 [1]。
- 预期：两种方案下，被取消任务的 `finally` 都在 `main` 返回前执行完毕。
- 若协程捕获 `CancelledError`，清理完成后应继续传播；文档指出结构化并发组件内部依赖取消，吞掉 `CancelledError` 可能导致行为异常，确需抑制时还要调用 `uncancel()` [1]。
- 验证 `Task.cancel()` 不保证一定取消：协程可抑制取消请求，但文档明确这不常见且被积极劝阻 [1]。

### 3. 兼容性

- `TaskGroup` 为 3.11 新增 [1]；在 3.10 及更早不可用。本次资料只覆盖 3.11 文档，未核实更早版本的具体行为。
- `gather` 在 3.10 移除了 `loop` 参数，3.10 起无位置参数或不全是 Future-like 且无运行中事件循环时会发弃用警告 [1]；手动方案应避免传 `loop`。
- 3.11 中 `wait_for()` 改抛 `TimeoutError` 而非 `asyncio.TimeoutError` [1]；若修复代码同时涉及超时处理，需按 3.11 语义断言。
- 3.11 中 `Task.cancel(msg)` 的 `msg` 会从被取消任务传播给等待者 [1]；若依赖取消消息做诊断，可在 3.11 上验证。

**未核实项：** 本次资料未给出 `TaskGroup` 在 3.12+ 的行为变化，也未提供旧版本 `gather` 的逐版本差异；上述兼容性结论仅限 3.11 文档可见内容。
**结论先行：三者不是同一层面的替代品，且本轮资料不足以支撑“谁更快”的判断。** Python asyncio 是事件循环上的协作式并发，取消靠向 Task 注入 `CancelledError`；Java 虚拟线程是 JVM 调度的用户态线程，取消沿用 `Thread.interrupt()` 中断协议；Go goroutine 本轮只有 Go 1.26 发布说明，未覆盖其并发模型与取消机制，因此 Go 方向只能给出“资料不足”，不能凭记忆补写。选型上：I/O 密集且已在 asyncio 生态内选 asyncio；已有阻塞式 Java 代码、想低成本提升线程数选虚拟线程；Go 方向待补官方文档后再定。三者都不能被预先假定更快 [1][2][3]。

## 一、Python asyncio（Python 3.15.2 文档）

**并发模型。** 可等待对象有三类：coroutine、Task、Future；Task 用于“并发地”调度 coroutine [1]。并发单位是 Task，由事件循环驱动，属协作式：只有在 `await` 点才可能切换。文档摘录未展开事件循环与线程的关系，故“单线程”本轮不作为原文事实引用。

**取消机制。** Task 可被安全取消；取消时会在该 Task 的下一个机会抛出 `asyncio.CancelledError` [1]。推荐用 `try/finally` 做清理；若显式捕获 `CancelledError`，清理完成后一般应继续传播。它直接继承 `BaseException`，多数代码无需感知 [1]。`TaskGroup`（3.11 新增）与 `asyncio.timeout()` 内部就是用取消实现的，若协程吞掉 `CancelledError` 可能行为异常；确实要抑制时必须同时调用 `uncancel()` 才能完全清除取消状态 [1]。

**超时。** `asyncio.timeout(delay)` 是异步上下文管理器，超时后取消当前任务并把 `CancelledError` 转成 `TimeoutError`，因此 `TimeoutError` 只能在上下文管理器**外面**捕获；`delay=None` 表示不设限，之后可用 `reschedule()` 改期；超时上下文可安全嵌套（3.11 新增）[1]。`wait_for` 在 3.11 起改抛 `TimeoutError`，3.12 起改为基于 `asyncio.timeout()` 实现 [1]。

**适用限制（据上述原文可推）。** 取消是“下一个机会”生效，不是抢占式中断；清理逻辑必须写成 `finally`，否则资源释放不可靠；吞取消会破坏结构化并发组件 [1]。CPU 密集任务是否适合，本轮摘录未涉及，不作断言。

## 二、Java 虚拟线程（JDK 21 `Thread` 文档）

**并发模型。** 虚拟线程是通常由 Java 运行时而非操作系统调度的用户态线程，资源需求少，单个 JVM 可支持数百万个；适合大部分时间处于阻塞、常等 I/O 完成的任务，**不面向长时间 CPU 密集运算** [2]。它们跑在一小组平台线程（carrier threads）上，锁与 I/O 等操作可能使 carrier 从一个虚拟线程改派给另一个；虚拟线程内代码感知不到 carrier，`currentThread()` 总返回虚拟线程自身 [2]。虚拟线程是守护线程，不阻止 JVM 关闭流程开始；优先级固定不可改，默认无名字（`getName` 返回空串）[2]。

**取消机制。** 文档给的是 `Thread.interrupt()` 语义：若线程阻塞在 `Object.wait`、`join`、`sleep` 上，中断状态被清除并收到 `InterruptedException`；阻塞在 `InterruptibleChannel` 的 I/O 上则通道关闭、状态置位并收到 `ClosedByInterruptException`；阻塞在 `Selector` 上则状态置位并立即返回；其余情况仅置中断状态 [2]。对已不存活线程的中断“不必有影响”，但 JDK 参考实现仍会记录该请求并可由 `interrupted()`/`isInterrupted()` 读出 [2]。`join` 可等待线程终止，超时 0 表示一直等 [2]。

**适用限制。** 官方明确不适合长时 CPU 密集任务 [2]；中断是协作信号，不是强制终止，被中断代码需自行处理异常或轮询状态；虚拟线程无名字、优先级固定，依赖线程名或优先级的既有逻辑需调整 [2]。

## 三、Go goroutine（Go 1.26 发布说明）

本轮唯一 Go 资料是 Go 1.26 发布说明（2026 年 2 月发布，维持 Go 1 兼容承诺）[3]。其中与 goroutine 相关的可见内容只有“实验性 goroutine 泄漏 profile”，并给出一个真实泄漏示例，目标是 Go 1.27 默认启用 [3]。**该资料没有描述 goroutine 的调度模型、`context` 取消传播、`select`/channel 语义或适用限制**，因此本方向无法给出有依据的模型与取消结论。可确认的只有：Go 1.26 提供了实验性的 goroutine 泄漏检测手段，说明泄漏是可观测的工程问题 [3]。

## 四、选型对比

| 维度 | Python asyncio 3.15.2 | Java 虚拟线程 JDK 21 | Go goroutine 1.26 |
|---|---|---|---|
| 并发单位 | Task 调度 coroutine [1] | 运行时调度的用户态线程 [2] | 资料未覆盖 [3] |
| 调度方式 | 事件循环 + await 协作切换 [1] | JVM 调度到少量 carrier 线程 [2] | 资料未覆盖 [3] |
| 取消 | 注入 `CancelledError`，下一机会生效 [1] | `interrupt()` 置位/抛异常/关通道 [2] | 资料未覆盖 [3] |
| 超时 | `asyncio.timeout()` 转 `TimeoutError` [1] | 无内建统一超时，靠 `join(millis)` 等 [2] | 资料未覆盖 [3] |
| 明确不适合 | 资料未涉及 | 长时 CPU 密集 [2] | 资料未覆盖 [3] |
| 可观测性 | 资料未涉及 | 资料未涉及 | 实验性泄漏 profile [3] |

**取舍建议（依据上表，属建议非原文事实）：** 若系统已是 asyncio 生态、I/O 等待为主，选 asyncio，并把清理写进 `finally`、不吞 `CancelledError`，超时统一用 `asyncio.timeout()` [1]。若已有大量阻塞式 Java 代码、想以低改造成本提升并发线程数，选虚拟线程，但把 CPU 密集段移出虚拟线程，并检查依赖线程名/优先级的逻辑 [2]。Go 方向在补齐官方并发与取消文档前，不给选型结论；仅可提示 Go 1.26 起可用泄漏 profile 做排查 [3]。

**未核实项：** 三者性能对比（原文均未给基准，不能假定谁更快）；Go 的调度与取消细节；asyncio 与线程/多进程的关系；虚拟线程在具体框架中的行为。这些需补充对应官方文档或实测后再下结论。
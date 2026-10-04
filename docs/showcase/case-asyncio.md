# 真实研究案例：Python asyncio 官方文档对比

这是一次使用真实模型、搜索与网页抓取完成的技术文档研究。运行日期：2026-10-04，策略：Plan-and-Execute。

## 用户问题

> 请仅依据 Python 3.11 官方文档，对比 asyncio.TaskGroup 与 asyncio.gather 在一个子任务抛出普通异常（不是 CancelledError）时的行为：其他子任务是否取消、异常如何传回调用方；再说明捕获 CancelledError 后应如何处理，为什么不应吞掉它。用中文简洁回答并给出文档出处。

## 研究过程

1. 将问题拆为异常传播与取消行为、捕获取消后的处理、结构化并发机制三个研究方向。
2. 通过搜索与抓取取得 Python 官方资料。
3. 按研究问题阅读原文，保留支持结论的证据位置。
4. 评估材料后，将已读证据交给 Writer，生成中文回答并附出处。

## 原始回答

以下保留本次运行的回答文本：

asyncio.TaskGroup在一个子任务抛出非CancelledError普通异常时，剩余未完成的其他子任务会被取消[1]。asyncio.gather默认参数return_exceptions=False时，一个子任务抛出该异常，其他未完成子任务不会被取消[1]。

asyncio.TaskGroup会在所有子任务完成后，将异常聚合到ExceptionGroup或BaseExceptionGroup中引发，传回给调用方[1]。asyncio.gather默认return_exceptions=False时，首个异常会立即直接传给等待gather的调用方；若return_exceptions为True，异常会和正常结果一起聚合到结果列表传回[1]。

捕获CancelledError后，应在完成清理逻辑后重新传播（抛出）该异常；如果确实需要抑制取消请求，需要调用Task.uncancel()移除取消状态[1]。

不应吞掉CancelledError，因为TaskGroup、asyncio.timeout()这类结构化并发组件内部依赖取消机制实现功能，吞掉该异常会导致这些组件无法正常工作，且未移除的取消状态会影响后续流程[1]。

文档出处：协程与任务 — Python 3.11.17 说明文档 [1]

[1]: https://docs.python.org/zh-tw/3.11/library/asyncio-task.html

来源：[Python 3.11 官方文档：协程与任务](https://docs.python.org/zh-tw/3.11/library/asyncio-task.html)。

## 运行记录

| 项目 | 结果 |
| --- | --- |
| 状态 | completed |
| 研究耗时 | 116.29 秒 |
| 研究 token | 62,191（输入 54,734 / 输出 7,457） |
| Factual Correctness F1 | 1.00 |
| Faithfulness | 0.90 |
| 搜索 / 抓取 / 阅读 | 1 / 1 / 3 次 Gateway 请求 |
| 模型 | doubao-seed-2.0-lite，temperature=0 |

这是单道已知诊断题的一次运行，指标描述本案例；研究用量与评分调用分别计量。数据文件保留该运行的完整三项原始指标与条件。

[下载案例数据](data/asyncio-20261004.json) · [查看证据评估实现](../../backend/src/deeptrace/strategies/evidence_evaluation.py) · [查看回答证据装配](../../backend/src/deeptrace/responses/evidence.py)

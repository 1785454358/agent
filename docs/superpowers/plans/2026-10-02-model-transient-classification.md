# Model Transient Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复新版 LangChain 连接/超时包装异常不进入现有有界重试的问题。

**Architecture:** 保留 ChatModelGateway 的暂态名称白名单，只添加两个已核验的包装类型名称。用真实异常类型和离线 Provider 双桩验证网关外部行为；计量集成测试保留真实 MeteredChatModel / RequestCounter。

**Tech Stack:** Python、pytest-asyncio、LangChain、httpx；不新增依赖。

**Spec:** ../specs/2026-10-02-model-transient-classification-design.md（用户已确认书面规格）。

## Global Constraints

- 最多 2 次尝试，不是额外重试 2 次。
- SDK 重试设置、网关次数/超时/退避、预算、权限和计量不变。
- 401/400、取消、预算哨兵不因新增规则重试。
- 真实实验运行时不改生产/评分代码，不把旧数据重标为修复后结果。
- 当前没有可用的 subagent-driven-development / executing-plans 技能或子代理工具，按已授权实施在当前会话逐项执行并内联复核。
- 工作区已有大量不相关修改，Git 提交只包含本规格、计划、新测试和网关最小修改，不使用 git add .。

---

### Task 1: 分类兼容与调用边界回归

**Files:**

- Modify: backend/src/deeptrace/harness/model_gateway.py（仅 `_transient`）。
- Create: backend/tests/harness/test_model_transport_compatibility.py。
- Update: 本计划、真实开发校准报告。

**Interfaces:**

- Consumes: `ChatModelGateway.invoke(role=..., messages=...)`、`task_messages`、真实 LangChain 异常构造器。
- Produces: 既有 `AIMessage` 成功返回或 `ModelCallError.category`；不新增生产接口。

- [x] **Step 1: 等预算探针完成，固定真实实验结果。** 两条探针 CLI 已结束，均 partial；主评分继续收尾，额外探针评分使用登记的 48 次上限。并行准备的新测试未被实验加载；生产代码和 HEAD 在两个研究批次结束前保持不变。探针 184 个源文件哈希逐份匹配主批留存快照，差异 0。
- [x] **Step 2: 提交单文件规格。** staging 检查为空后仅提交规格，提交 `3e62c16`。未混入工作区其他内容。
- [x] **Step 3: 写离线失败测试。** 移除连接/超时包装类型分类应使恢复与暂态类别测试失败；错误重试认证/预算异常、漏计尝试应使边界测试失败。Provider 双桩只替代外部网络，不替代网关、分类器或计量。使用 `httpx.Request('POST', 'https://provider.invalid/v1/chat/completions')` 构造真实异常：

```python
@pytest.mark.parametrize('error_type', [OpenAIConnectionError, OpenAITimeoutError])
async def test_wrapper_connection_or_timeout_recovers(error_type):
    provider = Provider(error_type(request=REQUEST), AIMessage(content='recovered'))
    response = await ChatModelGateway(provider, retry_base_seconds=0).invoke(
        role='researcher', messages=MESSAGES,
    )
    assert response.content == 'recovered'
    assert provider.calls == 2
```

持续失败测试放入三个异常作为序列，断言只消耗两个，最终类别 TRANSIENT 且对外消息不含 private-key。401/400 用 `OpenAIAuthenticationError` / `OpenAIInvalidRequestError` 和对应 httpx.Response，第二个序列项为不应执行的成功回答，断言一次调用、FATAL。取消与 RequestLimitReached 同样断言仅一次。

计量测试对连接/超时各执行：`MeteredChatModel(provider, meter, RequestCounter(2), RequestCounter(2))`，第一次暂态、第二次带 input=7 / output=3 的成功返回；断言 provider_attempts=2、missing_usage_attempts=1、observed_input_tokens=7、input_tokens=null。额度 1 的独立测试断言第二次不进入 Provider、最终 FATAL、provider_attempts=1；首次异常不得退款。

- [x] **Step 4: 确认 RED。** 在 backend 执行 `.venv/Scripts/python.exe -X utf8 -m pytest tests/harness/test_model_transport_compatibility.py -q --tb=short`；实际 10 failed / 4 passed，4.92 秒。包装异常恢复/类别/计量用例失败于现有 FATAL；预算上限用例失败于还未进入预算拒绝分支。401/400、取消和预算哨兵保护通过，导入与真实异常构造正常。
- [x] **Step 5: 最小 GREEN 修改。** 在既有名称集合中仅加入：

```python
'OpenAIConnectionError',
'OpenAITimeoutError',
```

- [x] **Step 6: 验证。** 网关新旧测试及计量 25 passed / 3.71 秒；非真实 API 回归 927 passed、2 deselected / 108.89 秒；隔离评测测试 34 passed / 6.29 秒。网关和新测试 Ruff check、format --check 全通过；未修不相关 lint 债务，未重新运行收费 API。
- [x] **Step 7: 自审与报告。** 按 code-review-and-quality 五轴复核：最小名称集合兼容，测试覆盖新异常恢复/持续失败、401/400/取消/预算不可重试与两级计量上限；没有新依赖、无限重试或 runtime → eval 引用（仅测试使用 eval 计量）。对外错误保持脱敏；沿用既有异常日志，不新增敏感输出。时间与费用开销仍受现有有界重试控制。无本改动的必修阻断项；不宣称完整 E2E 修复，未作独立模型复审/部署验证。
- [x] **Step 8: 定向提交。** 已复核 diff 与空 staging，定向提交网关、新测试、本计划：`git commit -m 'fix: retry LangChain connection wrappers within existing limits'`，不包含真实实验 tmp 数据、凭据或其他工作区修改。提交结果以 Git 命令输出和日志为准。

## 计划自审

单任务覆盖分类、持续失败、不可重试边界、计量与缺失 usage、实验隔离和回归要求。签名沿用现有网关，零生产接口扩展；实现无未定义依赖或待定行为。

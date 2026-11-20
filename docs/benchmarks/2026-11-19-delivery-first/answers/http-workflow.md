**结论：** GET /orders/{id} 在“请求已发出、未收到响应”时可自动重试；POST /orders 在服务端未承诺去重、且客户端无法确认原请求未生效时，遇到①连接断开、②429、③503 均不得自动重发。429 与 503 只是“可能稍后再试”的信号，不是自动重试的许可；只有在该分支允许重试、Retry-After 合法且等待落在 30 秒剩余预算内时才重试，缺失或无效时按自行建议的短退避处理，等待超出剩余预算即停止。任何重试都不保证成功。

## 一、风险诊断

| 情形 | GET /orders/{id} | POST /orders |
|---|---|---|
| ① 已发出后连接断开、未收到响应 | 风险低：GET 是安全方法，重复请求的预期效果与一次相同 [1]（9.2.1、9.2.2） | 风险高：POST 非幂等，原请求可能已被处理，重试可能重复创建订单 [1]（9.2.2、9.3.3） |
| ② 429 | 表示被限流，响应可含 Retry-After 指示等待多久再发新请求 [2]（4） | 同左；且原请求是否已产生副作用未知，重试本身也消耗配额 |
| ③ 503 | 临时过载或计划维护，服务端“MAY”发 Retry-After 建议等待时间 [1]（15.6.4） | 同左；若原请求是否已处理未知，仍受非幂等约束 |

关键区分：429/503 是服务端返回的响应，说明本次请求被拒绝或暂不可处理，但它并不等于“原请求一定未生效”。RFC 9110 对非幂等方法的自动重试限制写在 9.2.2：客户端 SHOULD NOT 自动重试非幂等请求，除非有办法确知该请求语义幂等，或有办法检测原请求未被应用 [1]（9.2.2）。该条并未把限制限定在通信失败场景，因此 POST 收到 429/503 后同样要先过这一关：没有去重承诺、又不能确认未生效，就不能直接重发。业务上“可以接受重复订单风险”不构成幂等依据，也不构成“未生效”的证据。

## 二、何时可自动重试

**RFC 规则（有规范依据）：**
- GET 属安全方法，通信失败后可自动重试 [1]（9.2.2）。
- 非幂等方法（POST）在通信失败后，客户端 SHOULD NOT 自动重试，除非有办法确知语义幂等或检测原请求未被应用 [1]（9.2.2）。
- 客户端 SHOULD NOT 自动重试“已失败的一次自动重试” [1]（9.2.2）——本方案以“最多 3 次尝试（含首次）”落实为总次数上限。
- 503 的 Retry-After 表示服务预计不可用多久 [1]（10.2.3、15.6.4）；429 的 Retry-After 表示再发新请求前应等多久 [2]（4）。

**自行建议（非规范强制）：**
- GET 的①：直接重试，受总时限与次数约束。
- POST 的①：默认不自动重试；仅当服务端明确承诺按请求去重（如幂等键）或客户端能检测原请求未生效时才重试。不得假定存在幂等键保障。
- 429/503：GET 可重试；POST 仅在上述去重/可检测前提下重试，否则向用户报告“结果不确定”，由用户决定是否另行发起新订单。
- 等待优先取 Retry-After，缺失或无效时用短指数退避（如 1s、2s）加少量抖动。
- 等待时间超出剩余预算即停止，不缩短等待硬闯。

## 三、Retry-After 两种格式与异常处理

RFC 9110 定义：`Retry-After = HTTP-date / delay-seconds`；delay-seconds 为非负十进制整数秒 [1]（10.2.3）。

- **整数秒**：如 `Retry-After: 120` 表示收到响应后再等 120 秒 [1]（10.2.3）。
- **HTTP-date**：如 `Retry-After: Fri, 31 Dec 1999 23:59:59 GMT`，表示等到该绝对时刻 [1]（10.2.3）。计算等待量 = 该时刻 − 当前时刻；已过期则视为 0。
- **缺失**：RFC 未规定客户端必须等待多久；429 中 Retry-After 是 MAY [2]（4），503 中也是 MAY [1]（15.6.4）。自行建议用短退避。
- **无效**（非整数、负号、无法解析的日期、格式不符）：规范未规定处理方式；自行建议按缺失处理，不得把无效值当作 0 立即重试。
- 两种格式都只约束“最早可再试时间”，不保证到点后成功。

## 四、伪代码（总时限 30s，最多 3 次尝试含首次）

```text
CONST TOTAL_BUDGET = 30s
CONST MAX_ATTEMPTS = 3          # 含首次
CONST BACKOFF = [1s, 2s]        # 自行建议，用于缺失/无效 Retry-After

function shouldRetry(method, outcome, serverDedupPromise, originalAppliedKnownFalse):
    if outcome.kind == CONNECTION_DROPPED:
        if method == GET: return true
        if method == POST: return serverDedupPromise or originalAppliedKnownFalse
    if outcome.status == 429 or outcome.status == 503:
        if method == GET: return true
        if method == POST: return serverDedupPromise or originalAppliedKnownFalse
    return false

function parseRetryAfter(resp, now):
    v = resp.header("Retry-After")
    if v is absent: return MISSING
    if v matches /^[0-9]+$/: return seconds(v)
    t = parseHttpDate(v)
    if t is valid: return max(0, t - now)
    return INVALID

function execute(method, url, serverDedupPromise, originalAppliedKnownFalse):
    start = now()
    attempt = 0
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        remaining = TOTAL_BUDGET - (now() - start)
        if remaining <= 0: return STOP_BUDGET
        outcome = sendOnce(method, url, timeout=remaining)   # 单次发送绑定剩余预算
        if outcome is success: return outcome
        if attempt == MAX_ATTEMPTS: return STOP_ATTEMPTS      # 最后一次失败不再等待
        if not shouldRetry(method, outcome, serverDedupPromise, originalAppliedKnownFalse):
            return STOP_NOT_RETRYABLE
        wait = parseRetryAfter(outcome, now())
        if wait is MISSING or wait is INVALID:
            wait = BACKOFF[min(attempt-1, len(BACKOFF)-1)]  # 自行建议
        remaining = TOTAL_BUDGET - (now() - start)
        if wait >= remaining: return STOP_BUDGET   # 等待超出剩余预算即停止
        sleep(wait)
    return STOP_ATTEMPTS
```

说明：`sendOnce` 的超时取剩余预算，避免单次请求耗尽总时限；`serverDedupPromise` 只能由服务端明确承诺置真，`originalAppliedKnownFalse` 只能由可核验的检测手段置真，二者客户端均不得自行假定。最后一次尝试失败后直接返回，不再计算等待。

## 五、未核实与边界

- 本次仅加载 RFC 9110、RFC 6585 摘录，未核实具体服务端是否提供去重或幂等键；伪代码中的 `serverDedupPromise` 需按实际服务能力配置。
- RFC 未规定 Retry-After 缺失/无效时的客户端等待值，退避参数属自行建议。
- 重试不保证成功；POST 在无去重承诺时，自动重试可能造成重复订单，应改为向用户报告不确定状态。
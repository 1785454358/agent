**结论：** GET /orders/{id} 在“请求已发出、连接断开、未收到响应”时可自动重试，因为 GET 是安全方法，而 RFC 9110 §9.2.2 把安全方法列为幂等方法，并说明通信失败、客户端尚未读到响应时可自动重复幂等请求 [1]。POST /orders 在同样情形下，若服务端未承诺去重、客户端也无法检测原请求未被应用，按 RFC 9110 §9.2.2 的 SHOULD NOT 不应自动重试 [1]。429 与 503 都是服务器已返回响应的情形：429 表示限流，可带 Retry-After（RFC 6585 §4）[2]；503 表示临时过载或计划维护，可带 Retry-After（RFC 9110 §15.6.4、§10.2.3）[1]。二者只表示“稍后再试”，并不使 POST 变为幂等，也不证明原 POST 未被处理；因此 POST 收到 429/503 后仍受同一幂等约束，不能直接重发。以下区分 RFC 规则与自行建议。

## 一、风险诊断

| 情形 | GET /orders/{id} | POST /orders |
|---|---|---|
| ① 请求已发出、连接断开、未收到响应 | 风险低：GET 是安全方法，重复执行不改变服务器预期效果；RFC 9110 §9.2.2 允许在通信失败、未读到响应时自动重复幂等请求 [1] | 风险高：POST 非幂等，原请求可能已被处理（订单可能已创建），重试可能重复下单；RFC 9110 §9.2.2 规定客户端对非幂等方法的自动重试 SHOULD NOT，除非能确认语义幂等或能检测原请求未被应用 [1] |
| ② 429 | 可重试，但须遵守限流；429 表示给定时间内请求过多，响应可带 Retry-After 指示发新请求前等待多久（RFC 6585 §4）[2] | 受幂等约束：429 只说明被限流，不证明原 POST 未被处理；未获去重承诺且不能确认未生效时不应自动重试 [1][2] |
| ③ 503 | 可重试；503 表示临时过载或计划维护，预计延迟后缓解，服务器可发 Retry-After 建议等待时间（RFC 9110 §15.6.4）[1] | 受幂等约束：503 不证明原 POST 未被处理；未获去重承诺且不能确认未生效时不应自动重试 [1] |

补充：RFC 9110 §9.2.2 提到有些客户端会冒险猜测，例如在底层连接于收到任何响应部分之前关闭时自动重试 POST，尤其在使用空闲持久连接时；但这是“更冒险的做法”，不是规范要求 [1]。本设计不采用该猜测策略。

## 二、何时可自动重试

**RFC 规则（有原文支持）：**

- 幂等方法的请求可在通信失败、客户端尚未读到服务器响应时自动重复；GET 属安全方法，安全方法是幂等的（RFC 9110 §9.2.2）[1]。
- 非幂等方法（POST）的自动重试：客户端 SHOULD NOT 自动重试，除非有办法知道该请求语义实际上是幂等的，或有办法检测原请求从未被应用（RFC 9110 §9.2.2）[1]。
- 客户端 SHOULD NOT 自动重试“已经失败过的自动重试”（RFC 9110 §9.2.2）[1]。
- 429 响应可含 Retry-After，指示发新请求前等待多久（RFC 6585 §4）[2]；503 响应可含 Retry-After，建议重试前等待时间（RFC 9110 §15.6.4、§10.2.3）[1]。
- Retry-After 值可以是 HTTP-date，也可以是收到响应后延迟的秒数；delay-seconds 是非负十进制整数，单位为秒（RFC 9110 §10.2.3）[1]。

**自行建议（非 RFC 原文）：**

- GET：三种情形均可自动重试，但 ②③ 必须先按 Retry-After 等待；等待超出剩余预算则停止。
- POST：默认三种情形都不自动重试，直接向调用方返回“结果未知/需人工或业务层核对”。仅当业务层明确提供“服务端已承诺去重”或“可查询订单是否已创建”的能力时，才允许自动重试；这属于 RFC 所说的“有办法知道语义幂等或有办法检测原请求未被应用” [1]。业务方口头接受重复风险，不构成幂等承诺，也不构成“原请求未生效”的证据，不能据此开启自动重试。
- 不承诺重试必成功：重试只是再发一次请求，仍可能失败、超时或被限流。

## 三、Retry-After 两种格式与缺失/无效处理

**格式（RFC 9110 §10.2.3）：**

- `Retry-After = HTTP-date / delay-seconds`；delay-seconds 为非负十进制整数，表示收到响应后延迟的秒数 [1]。
- 整数秒示例：`Retry-After: 120` 表示延迟 2 分钟 [1]。
- HTTP-date 示例：`Retry-After: Fri, 31 Dec 1999 23:59:59 GMT` [1]。HTTP-date 是绝对时间点，客户端应计算“该时间点减当前时间”作为等待时长；若该时间点已过，等待时长为 0。
- 429 的 Retry-After 是“发新请求前等待多久” [2]；503 的 Retry-After 是“服务预计不可用多久” [1]。

**缺失或无效时（自行建议，RFC 未规定客户端必须如何取值）：**

- 缺失：采用客户端自定的退避等待（如指数退避加抖动），并受 30 秒总时限约束。
- 无效（无法解析为合法 delay-seconds 或 HTTP-date）：按缺失处理，不把无效值当作 0 立即重试，避免加剧限流。
- 解析出等待时长后，若“当前已用时间 + 等待时长”超出剩余预算，则停止重试；等待本身也计入 30 秒总时限。

## 四、伪代码（总时限 30 秒，最多 3 次尝试含首次）

```text
CONST TOTAL_BUDGET = 30s
CONST MAX_ATTEMPTS = 3          # 含首次
CONST DEFAULT_BACKOFF = [1s, 2s] # 自行建议：缺失/无效 Retry-After 时使用

function request_with_retry(method, url, body, allow_retry):
    start = now()
    attempt = 0
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        remaining = TOTAL_BUDGET - (now() - start)
        if remaining <= 0: return STOP_BUDGET_EXCEEDED

        # send 绑定剩余预算：本次请求最多用掉剩余时间
        result = send_once(method, url, body, timeout=remaining)

        # 情形①：请求已发出、连接断开、未收到响应
        if result is CONNECTION_CLOSED_WITHOUT_RESPONSE:
            if not allow_retry: return UNKNOWN_OUTCOME   # POST 默认走这里
            # GET 允许继续；POST 仅在业务层确认幂等/可检测时 allow_retry=true
            if attempt >= MAX_ATTEMPTS: return STOP_MAX_ATTEMPTS
            wait = backoff_for_attempt(attempt, DEFAULT_BACKOFF)
            if not sleep_within_budget(wait, start): return STOP_BUDGET_EXCEEDED
            continue

        # 情形②：429
        if result.status == 429:
            if not allow_retry: return RATE_LIMITED_NO_RETRY
            if attempt >= MAX_ATTEMPTS: return STOP_MAX_ATTEMPTS
            wait = parse_retry_after(result.headers) or backoff_for_attempt(attempt, DEFAULT_BACKOFF)
            if not sleep_within_budget(wait, start): return STOP_BUDGET_EXCEEDED
            continue

        # 情形③：503
        if result.status == 503:
            if not allow_retry: return UNAVAILABLE_NO_RETRY
            if attempt >= MAX_ATTEMPTS: return STOP_MAX_ATTEMPTS
            wait = parse_retry_after(result.headers) or backoff_for_attempt(attempt, DEFAULT_BACKOFF)
            if not sleep_within_budget(wait, start): return STOP_BUDGET_EXCEEDED
            continue

        return result   # 其他状态码或成功，直接返回

    return STOP_MAX_ATTEMPTS

function parse_retry_after(headers):
    v = headers.get("Retry-After")
    if v is null: return null
    if v matches /^[0-9]+$/: return seconds(v)
    if v parses as HTTP-date: return max(0, date(v) - now())
    return null      # 无效，按缺失处理

function sleep_within_budget(wait, start):
    if (now() - start) + wait >= TOTAL_BUDGET: return false
    sleep(wait)
    return true
```

调用方式（自行建议）：GET 传 `allow_retry=true`；POST 默认传 `allow_retry=false`，仅当业务层提供去重承诺或可检测原请求未应用时传 `true`。最后一次尝试失败后不再进入等待分支，直接返回 `STOP_MAX_ATTEMPTS`。

## 五、RFC 规则与自行建议的边界

- **RFC 规则：** GET 幂等可自动重试；POST 非幂等，未获幂等保证或未检测原请求未应用时 SHOULD NOT 自动重试；不得自动重试已失败的自动重试；429/503 可带 Retry-After；Retry-After 为 HTTP-date 或非负整数秒 [1][2]。
- **自行建议：** 30 秒总预算、3 次尝试上限、缺失/无效 Retry-After 时的默认退避、等待超预算即停止、POST 默认不重试并返回“结果未知”。这些是工程取舍，不是 RFC 强制要求。
- **未核实项：** 本回答未核实具体订单服务是否提供去重键、幂等承诺或订单查询接口；若没有，POST 的自动重试不应开启。RFC 也未规定 Retry-After 缺失或无效时客户端必须等待多久，上述默认退避仅为建议。
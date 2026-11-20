**结论：** GET /orders/{id} 在“请求已发出、未收到响应”时可自动重试，因为 GET 是安全方法，安全方法属于幂等方法，幂等请求在通信失败、未读到响应时可自动重试 [1]（RFC 9110 §9.2.1、§9.2.2）。POST /orders 在同样情形下，若服务端未承诺去重，不得自动重试：POST 非幂等，RFC 9110 §9.2.2 规定客户端 SHOULD NOT 自动重试非幂等请求，除非有手段确认请求语义幂等或原请求未被应用 [1]。429 与 503 只是“可能稍后再试”的信号，不是自动重试授权；对 POST 而言，收到 429/503 也不能证明原请求未生效，未获去重承诺时不得直接重发。Retry-After 是服务器建议的等待时间，缺失或无效时两份 RFC 均未规定默认值，需自行设定保守策略。以下标注“建议”的内容均为自行设计，不是 RFC 强制规则；任何重试都不保证成功。

## 一、风险诊断

| 情形 | GET /orders/{id} | POST /orders |
|---|---|---|
| ① 已发出后连接断开、未收到响应 | 风险低：重复读取不改变服务端状态；GET 安全且幂等 [1]，可自动重试 | 风险高：原请求可能已被处理并创建订单，重试可能重复下单；POST 非幂等 [1]，未获去重承诺时不得假定有幂等键保障 |
| ② 429 | 表示被限流 [2]；可等待后重试，但须尊重 Retry-After（若有）并受总预算约束 | 同左；但 429 不说明上一次 POST 未生效，未获去重承诺时不得直接重发 |
| ③ 503 | 表示临时过载或维护，可能稍后恢复 [1]；可等待后重试 | 同左；503 同样不说明上一次 POST 未生效，未获去重承诺时不得直接重发 |

关键区分：429/503 说明“服务器暂时不让做/做不了”，并不说明“上一次 POST 没生效”。因此对 POST，429/503 下自动重试的安全性取决于能否确认原请求未被应用；仅凭状态码无法确认。业务上“可以接受重复下单风险”不构成幂等依据，也不构成“原请求未生效”的依据，不能据此绕过上述限制。

## 二、何时可自动重试

**RFC 规则：**
- GET 是安全方法 [1]（RFC 9110 §9.2.1）；安全方法属于幂等方法 [1]（§9.2.2）。幂等请求在通信失败、未读到响应时可自动重试 [1]（§9.2.2）。
- 非幂等方法（POST）客户端 SHOULD NOT 自动重试，除非有手段确认请求语义幂等或原请求未被应用 [1]（§9.2.2）。
- 429 响应“MAY include a Retry-After header indicating how long to wait before making a new request” [2]（RFC 6585 §4）；429 响应 MUST NOT 被缓存存储 [2]（§4）。
- 503 响应“MAY send a Retry-After header ... to suggest an appropriate amount of time for the client to wait before retrying” [1]（RFC 9110 §15.6.4）。
- Retry-After 可带于 503，表示服务预计不可用多久；带于 3xx 表示重定向请求前的最小等待 [1]（§10.2.3）。

**自行建议：**
- GET：①可立即自动重试；②③在 Retry-After 允许且预算足够时重试。
- POST：①默认不自动重试，交人工/上层确认；②③仅当服务端明确承诺按幂等键去重，或客户端能查询确认订单未创建时才重试。未获承诺时，即使 429/503 也不自动重试。
- 任何重试都不保证成功；达到尝试上限或预算耗尽即停止并报错。

## 三、Retry-After 两种格式与缺失/无效处理

RFC 9110 §10.2.3 定义：`Retry-After = HTTP-date / delay-seconds`；delay-seconds 为非负十进制整数，单位为秒 [1]。

- **整数秒**：如 `Retry-After: 120`，表示收到响应后再等 120 秒 [1]。
- **HTTP-date**：如 `Retry-After: Fri, 31 Dec 1999 23:59:59 GMT`，表示等到该绝对时刻 [1]。计算等待时长需用本地当前时间与之相减；若该时刻已过，等待为 0。

**缺失或无效时：** RFC 9110 与 RFC 6585 均未规定默认等待值，也未规定无效值如何回退。以下为自行建议：
- 缺失：采用保守的指数退避（如 1s、2s、4s，加随机抖动），且不超过剩余预算。
- 无效（无法解析、负数、非整数秒、非法日期）：视为缺失处理，不盲目采用。
- 服务器给出的等待超过剩余预算：直接停止，不缩短等待强行重试（缩短会违背服务器建议）。

## 四、伪代码（总时限 30 秒，最多 3 次尝试含首次）

```text
CONST TOTAL_BUDGET = 30s
CONST MAX_ATTEMPTS = 3          # 含首次

def request_with_retry(method, url, body, idempotency_confirmed):
    start = now()
    attempt = 0
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        remaining = TOTAL_BUDGET - (now() - start)
        if remaining <= 0: return FAIL_BUDGET

        resp = send(method, url, body, timeout=remaining)   # 发送与等待响应均受剩余预算约束

        # 情形①：未收到响应
        if resp is CONNECTION_CLOSED:
            if method == GET or idempotency_confirmed:
                wait = backoff(attempt)          # 自行建议：1s,2s,4s + 抖动
            else:
                return FAIL_NON_IDEMPOTENT       # POST 未确认去重，不重试

        # 情形②③：429 / 503
        elif resp.status in (429, 503):
            if method != GET and not idempotency_confirmed:
                return FAIL_NON_IDEMPOTENT       # 429/503 不证明原 POST 未生效
            wait = parse_retry_after(resp)       # 见下
            if wait is INVALID or MISSING:
                wait = backoff(attempt)          # 自行建议

        else:
            return resp                          # 成功或其他状态，不重试

        # 最后一次尝试失败后不再等待
        if attempt >= MAX_ATTEMPTS:
            return FAIL_ATTEMPTS_EXHAUSTED

        remaining = TOTAL_BUDGET - (now() - start)
        if wait > remaining: return FAIL_BUDGET  # 等待超出剩余预算即停止
        sleep(wait)

    return FAIL_ATTEMPTS_EXHAUSTED

def parse_retry_after(resp):
    v = resp.header("Retry-After")
    if v is None: return MISSING
    if v is all_digits: return seconds(v)        # 整数秒
    t = parse_http_date(v)
    if t is None: return INVALID
    return max(0, t - now())                     # HTTP-date 转等待秒数
```

说明：`idempotency_confirmed` 表示服务端已明确承诺按幂等键去重，或客户端已确认原请求未被应用；未获此确认时 POST 一律不自动重试。该标志的判定方式超出两份 RFC 的范围，属自行设计。`send` 的超时绑定剩余预算，最后一次失败后直接返回、不再进入等待。

## 五、RFC 规则与自行建议的边界

- **RFC 规则**：GET 安全且幂等、幂等请求可自动重试、非幂等请求 SHOULD NOT 自动重试 [1]（RFC 9110 §9.2.1、§9.2.2）；429/503 可带 Retry-After 且为“建议”而非命令 [1][2]（§10.2.3、§15.6.4；RFC 6585 §4）；Retry-After 两种格式定义 [1]（§10.2.3）。
- **自行建议**：指数退避的具体秒数、缺失/无效时的回退、30 秒与 3 次的上限、POST 的 `idempotency_confirmed` 判定流程。
- **未核实**：两份 RFC 未规定 Retry-After 缺失时的默认值，也未规定客户端必须遵守 Retry-After；本方案中的等待与停止逻辑均为自行设计，不保证重试成功。
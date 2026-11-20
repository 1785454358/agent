**结论（先给取舍）**

- 可见官方材料能确认：WAL 比 rollback journal 多出“checkpoint”这一基本操作，默认在 WAL 超过 1000 页时自动 checkpoint，且可关闭自动 checkpoint；关闭后 WAL 文件可能过度增长 [1]。
- 但本次可见材料**不足以**逐项回答读写并发差异、WAL 下 SQLITE_BUSY 的具体情形、长读事务如何影响 checkpoint、以及“不适合 WAL 的场景”清单。以下表格中这些格子标为“缺口”，不拿常识补全。

**对比表（仅填有证据的格子）**

| 维度 | WAL | rollback journal | 证据状态 |
|---|---|---|---|
| 基本操作 | 读、写、checkpoint 三种 [1] | 读、写两种 [1] | 已覆盖 |
| 提交方式 | 事务追加到 WAL 文件末尾，多个事务可追加到同一 WAL [1] | 原内容先写入回滚日志文件，再直接改数据库文件；删除回滚日志即提交 [1] | 已覆盖 |
| checkpoint | 把 WAL 中追加的事务移回原数据库；默认 WAL 达 1000 页自动执行，阈值可用 `SQLITE_DEFAULT_WAL_AUTOCHECKPOINT` 改，也可关闭自动 checkpoint 改在空闲时或单独线程/进程执行 [1] | 可见材料未描述 rollback journal 的对应“checkpoint”机制 | 部分缺口 |
| 自动 checkpoint 关闭的后果 | 没有任何机制阻止 WAL 文件过度增长 [1] | 不适用（材料未述） | 已覆盖（仅 WAL 侧） |
| 读写并发 | 缺口 | 缺口 | 未覆盖 |
| SQLITE_BUSY | 缺口 | 仅见 rollback 模式：写进程拿不到 RESERVED 锁时写尝试失败并返回 SQLITE_BUSY [2] | 部分缺口 |
| 长读事务对 checkpoint 的影响 | 缺口 | 缺口 | 未覆盖 |
| 不适合 WAL 的场景 | 缺口（仅见只读介质相关片段，但条件列表在摘录中被截断） | — | 未覆盖 |

**逐项回答用户明确询问的点**

1. **WAL 是否意味着不会返回 SQLITE_BUSY？** 可见材料**不能**支持“WAL 不会返回 SQLITE_BUSY”，也**不能**给出 WAL 下返回 SQLITE_BUSY 的具体情形清单。唯一直接证据是 rollback 模式：写进程无法获得 RESERVED 锁时返回 SQLITE_BUSY [2]。因此对 WAL 侧应标为缺口，不能据常识断言“仍会”或“不会”。

2. **长读事务如何影响 checkpoint？** 本次可见原文未说明长读事务阻止 checkpoint 推进或导致 WAL 增长，标为缺口 [1]。可确认的相邻事实只有：关闭自动 checkpoint 后 WAL 可能过度增长 [1]；这与“长读事务”不是同一命题，不能替代回答。

3. **哪些场景不适合 WAL？** 可见材料只出现只读介质片段：旧版本 SQLite 读 WAL 数据库需要写权限，3.22.0 起放宽；只读介质上的 WAL 数据库在满足“一个或多个条件”时可读，但条件列表在摘录中被截断；并建议在把数据库镜像烧录到只读介质前转为 `journal_mode=DELETE` [1]。因此只能确认“只读介质需注意、烧录前建议转 DELETE”，**不能**给出完整的“不适合 WAL”清单。

**缺口与验证建议**

- 缺口范围仅指本次可见材料：r1（读写并发）、r2（WAL 下 SQLITE_BUSY 情形）、r3（长读事务对 checkpoint 的影响）、r4（不适合 WAL 的完整场景）均缺直接原文。
- 建议核查官方 WAL 文档中关于并发、busy 处理、checkpoint 阻塞与限制条件的段落，以及锁文档中 WAL 锁机制的单独章节 [1][2]；在补齐前，上述各项不应写成结论。

**官方来源**

- Write-Ahead Logging：https://www.sqlite.org/wal.html [1]
- File Locking And Concurrency In SQLite Version 3：https://www.sqlite.org/lockingv3.html [2]

**结论**：WAL 的核心优势是“写不阻塞读、读不阻塞写”，但官方强调这只是“大部分”成立，WAL 数据库上的查询仍可能返回 SQLITE_BUSY，应用必须为此做准备 [1]。因此“WAL 意味着不会返回 SQLITE_BUSY”不成立。

**WAL 下仍会 SQLITE_BUSY 的情形**（官方列举）[1]：

- 另一连接以独占锁定模式打开数据库时，所有查询返回 SQLITE_BUSY（如 Chrome、Firefox 运行中打开其数据库）。
- 最后一个连接关闭时，为清理 WAL 和共享内存文件短暂持有独占锁，此时新连接打开并查询可能得到 SQLITE_BUSY。
- 最后一个连接崩溃后，首个新连接执行恢复期间持有独占锁，第三个连接此时查询会得到 SQLITE_BUSY。

**版本与退出**：WAL 下数据库文件格式版本号由 1 增至 2，早于 3.7.0（2010-07-22）的 SQLite 连接会报“文件已加密或不是数据库”类错误；可用 `PRAGMA journal_mode=DELETE;` 显式退出 WAL [1]。

**对比表（仅填有原文支持项）**

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写不阻塞读、读不阻塞写，但仅“大部分”成立 [1] | 本次材料无官方原文，无法确认 |
| SQLITE_BUSY | 仍可能返回，情形见上 [1] | 本次材料无官方原文，无法确认 |
| 长读事务对 checkpoint 的影响 | 本次材料无官方原文，无法确认 | 本次材料无官方原文，无法确认 |
| checkpoint 行为 | 本次材料无官方原文，无法确认 | 本次材料无官方原文，无法确认 |
| 不适合 WAL 的场景 | 仅可确认：需兼容 3.7.0 之前版本时不宜保持 WAL（旧版无法恢复 WAL 库）[1] | 本次材料无官方原文，无法确认 |

**缺口说明**：本次可见材料只有 SQLite 官方 WAL 页面 [1]，它覆盖了读写并发、SQLITE_BUSY 情形、版本兼容与退出 WAL；但 rollback journal 的对应行为、长读事务如何影响 checkpoint、checkpoint 饥饿，以及“哪些场景不适合 WAL”的完整清单，均无合格官方原文支持。上述空白仅表示本次材料不足，不能推出官方文档没有答案。

**可提出的核查建议（非原文事实）**：若要补齐，可查阅 SQLite 官方 `wal.html` 的 checkpoint 章节、`pragma.html` 中 `journal_mode` 与 `wal_checkpoint` 条目，以及 `lockingv3.html`，以核实长读事务与 checkpoint 的交互及 rollback journal 的并发语义。

**来源**：[1] https://www.sqlite.org/wal.html

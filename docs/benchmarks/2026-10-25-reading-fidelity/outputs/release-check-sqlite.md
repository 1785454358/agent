## 结论

- **读写并发**：WAL 下写者不阻塞读者、读者不阻塞写者，但原文强调这“大体上”成立 [1]；rollback journal 下写者持 RESERVED 锁期间其他进程仍可读，但同一时刻只能有一个 RESERVED 锁，即只有一个写者 [2][3]。
- **SQLITE_BUSY**：WAL **不意味着**不会返回 SQLITE_BUSY。排他锁模式、最后连接关闭清理、崩溃后恢复期间均可能返回 [1]；checkpoint 被阻塞时 `wal_checkpoint` 首列为 1，等价 SQLITE_BUSY [4]。
- **长读事务与 checkpoint**：本次可见材料**不足以**说明长读事务如何阻止 checkpoint 推进及对 WAL 文件大小的影响（见“缺口”）。已支持的是：PASSIVE checkpoint 遇并发读者或写者可能无法完成 [1]；RESTART 会阻塞到所有读者用完日志 [4]。
- **不适合 WAL**：网络文件系统/跨主机、需改 page_size、多 ATTACH 库整体原子、`-shm` 无写权限等 [1]。

## 对比表

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写不阻塞读、读不阻塞写，“大体上”成立 [1] | 写者持 RESERVED 时其他进程仍可读；同一时刻仅一个 RESERVED [2][3] |
| 写-写 | 未在可见材料中展开 | 第二个写者取不到 RESERVED 即失败返回 SQLITE_BUSY [3] |
| 读-读 | 未在可见材料中展开 | 多个 SHARED 可共存 [2] |
| SQLITE_BUSY 来源 | 排他锁模式；最后连接关闭清理；崩溃后恢复持排他锁 [1] | 取不到 SHARED 立即返回；取不到 RESERVED 返回 [3] |
| checkpoint | PASSIVE 默认，遇并发读者/写者可能不完成；FULL/RESTART 更努力，仅经 `sqlite3_wal_checkpoint_v2()` 发起 [1]；被阻塞时首列返回 1 [4] | 无 WAL checkpoint 概念；提交时写 journal 并刷盘 [2] |
| 文件处理 | checkpoint 后通常不截断 WAL，而是从头覆盖复用 [1][4] | 提交后删除 journal，或 PERSIST/TRUNCATE 模式处理 [2] |

## 关键说明

**WAL 仍会 SQLITE_BUSY 的三种情形** [1]：
1. 另一连接以 exclusive locking mode 打开数据库——所有查询返回 SQLITE_BUSY（Chrome、Firefox 即如此）。
2. 最后一个连接关闭时短暂持排他锁清理 WAL 与共享内存文件，此时新连接查询可能得到 SQLITE_BUSY。
3. 最后一个连接崩溃后，首个新连接做恢复时持排他锁，第三个连接此时查询会得到 SQLITE_BUSY。

**checkpoint 模式** [1][4]：PASSIVE 为默认，尽量不干扰其他连接，有并发读者或写者时可能跑不完；FULL/RESTART 更努力完成，只能由 `sqlite3_wal_checkpoint_v2()` 发起；RESTART 在 checkpoint 后阻塞（调用 busy-handler）直到所有读者用完日志，期间阻塞并发写者但允许读者；TRUNCATE 在 RESTART 基础上成功后把 WAL 截为 0 字节。`wal_checkpoint` 首列为 1 表示 FULL/RESTART/TRUNCATE 被阻塞，等价于 `sqlite3_wal_checkpoint_v2()` 返回 SQLITE_BUSY [4]。

**不适合 WAL 的场景** [1]：
- 所有进程必须在同一主机；WAL 依赖共享少量内存，无法在网络文件系统上工作。
- 进入 WAL 后不能改 page_size（须在 rollback journal 模式下改）。
- 涉及多个 ATTACH 数据库的更改对每个库原子，但整体不原子。
- 打开 WAL 数据库的进程需对 `-shm` wal-index 共享内存文件有写权限（或对所在目录有写权限）。

## 缺口（本次可见材料不足）

- **长读事务如何阻止 checkpoint 推进、对 WAL 文件大小的影响**：现有原文只说明 PASSIVE checkpoint 遇并发读者/写者可能无法完成 [1]，以及 RESTART 会等所有读者用完日志 [4]；未明确长读事务与 WAL 文件增长、各 checkpoint 模式推进边界的关系。此缺口仅表示本次可见材料不足，不能推出官方文档没有相关说明。
- 建议核查：`sqlite3_wal_checkpoint_v2()` 文档页与 `wal.html` 中关于读者阻塞 checkpoint 的段落，以补齐该维度。

## 官方来源

- [2] Atomic Commit In SQLite：https://sqlite.org/atomiccommit.html
- [3] File Locking And Concurrency In SQLite Version 3：https://www.sqlite.org/lockingv3.html
- [1] Write-Ahead Logging：https://www.sqlite.org/wal.html
- [4] Pragma statements supported by SQLite：https://www.sqlite.org/pragma.html

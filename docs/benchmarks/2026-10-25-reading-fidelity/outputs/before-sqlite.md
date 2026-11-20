## 结论

- **读写并发**：WAL 模式下写入者不阻塞读取者、读取者不阻塞写入者，官方强调这一说法“**mostly**”成立 [1]。同一时刻仍只有一个写入者 [1]。rollback journal 的读写互斥机制在本次可见材料中**无原文支持**，不作断言。
- **SQLITE_BUSY**：WAL **不意味着**不会返回 SQLITE_BUSY。官方明确说明存在若干“obscure cases”，应用须为 SQLITE_BUSY 做好准备 [1]。
- **长读事务与 checkpoint**：本次可见材料**未覆盖**长读事务如何阻止 checkpoint 推进及其对 WAL 文件大小的影响，无法给出有据结论。
- **不适合 WAL 的场景**：本次可见材料**未覆盖**官方列出的不适用场景（如网络文件系统、只读介质等），不作推断。

## 对比表（仅列有据项）

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写入者不阻塞读取者、读取者不阻塞写入者（“mostly”成立）；一次仅一个写入者 [1] | 可见材料未提供 |
| 查询返回 SQLITE_BUSY | 可能：他连接以独占锁打开；最后连接关闭清理 WAL/共享内存文件期间；最后连接崩溃后新连接恢复期间 [1] | 可见材料未提供 |
| checkpoint 与 SQLITE_BUSY | 所有 checkpoint 调用获取数据库文件独占“checkpoint”锁；他进程同时 checkpoint 则取锁失败返回 SQLITE_BUSY，且 busy-handler 不被调用 [2] | 可见材料未提供 |
| FULL/RESTART/TRUNCATE 模式 | 另需独占“writer”锁；取不到时调用 busy-handler 重试，handler 返回 0 则退化为 PASSIVE 式推进并返回 SQLITE_BUSY [2] | 可见材料未提供 |
| 长读事务影响 checkpoint | 可见材料未提供 | 可见材料未提供 |

## 关键条件与取舍

**WAL 仍会 BUSY 的具体触发点**（据 [1]）：

1. 另一连接以独占锁模式打开数据库——此时对该库的所有查询都返回 SQLITE_BUSY（文中举例 Chrome、Firefox 运行期间即如此）。
2. 最后一个连接关闭时，为清理 WAL 与共享内存文件短暂持有独占锁；此间新连接打开并查询可能得到 SQLITE_BUSY。
3. 最后一个连接崩溃后，首个新连接执行恢复并持独占锁；第三个连接此时查询会得到 SQLITE_BUSY。

**checkpoint 的 BUSY 边界**（据 [2]）：

- 并发 checkpoint 冲突返回 SQLITE_BUSY，且**不调用** busy-handler——即配置 busy-handler 也无法等待化解。
- FULL/RESTART/TRUNCATE 等模式等待 writer 锁或读者时，若 busy-handler 返回 0，则按 PASSIVE 方式尽量推进后仍返回 SQLITE_BUSY。
- 最小调用：`sqlite3_wal_checkpoint_v2(db, zDb, eMode, &pnLog, &pnCkpt)`；SQL 侧对应 `PRAGMA wal_checkpoint` [2]。
- 非 WAL 库调用该接口返回 SQLITE_OK，且 `*pnLog`、`*pnCkpt` 置 -1 [2]。

**实际意义**：WAL 提升的是常规读写并行度，而非消除锁冲突；应用仍需处理 SQLITE_BUSY，尤其在高并发 checkpoint、独占打开、关闭清理与崩溃恢复窗口。

## 缺口说明

以下为用户明确询问但本次可见材料不足的项，仅表示**当前材料**未覆盖，不能推出官方文档无答案：

- rollback journal 的读写互斥机制与条件（r1 部分）。
- 长读事务阻止 checkpoint 推进的机理、WAL 文件增长与性能后果（r3）。
- 官方列出的不适合 WAL 的场景，及两种模式 checkpoint 行为对比（r4）。

验证建议（非原文事实）：可直接查阅 [1] 全文的 “Disadvantages” 与 checkpoint 相关章节，以及 [2] 的模式说明，以补齐上述三项。

## 来源

- [2] Checkpoint a database：https://www.sqlite.org/c3ref/wal_checkpoint_v2.html
- [1] Write-Ahead Logging：https://www.sqlite.org/wal.html

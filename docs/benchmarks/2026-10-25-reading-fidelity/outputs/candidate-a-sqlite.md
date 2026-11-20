## 结论

- **读写并发**：WAL 下写者只顺序追加 WAL，读者继续读数据库文件，读写基本互不阻塞；rollback journal 下写者需在数据库文件上取 RESERVED/EXCLUSIVE 锁，读写互斥 [1][2]。
- **SQLITE_BUSY**：WAL **不意味着**不会返回 SQLITE_BUSY。官方称“写者不阻塞读者、读者不阻塞写者”只是 __mostly__ 成立，并列出查询仍可能返回 SQLITE_BUSY 的情形 [2]。rollback journal 下取不到 SHARED 锁或 RESERVED 锁即返回 SQLITE_BUSY [1]。
- **长读事务与 checkpoint**：长读事务会阻止 checkpointer 推进；WAL 无法被回卷重用而持续增长，读性能随 WAL 变大而下降 [2]。
- **不适合 WAL 的场景**：锁原语有缺陷的文件系统（尤其 NFS）上多进程并发访问可能损坏数据库；QNX 上 mmap 共享内存有问题，需用 exclusive locking mode 才能无共享内存使用 WAL；只读介质/无写权限的 WAL 数据库仅在满足特定条件时可读 [3][2]。

## 对比表

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写者顺序写 WAL，读者读数据库文件，读写基本不互斥 [2] | 写者持 RESERVED 后可继续读，但提交需 EXCLUSIVE，读写互斥 [1] |
| SQLITE_BUSY | 仍可能：独占锁模式、最后连接关闭清理、崩溃后恢复持独占锁等 [2] | 取不到 SHARED 锁立即返回；取不到 RESERVED 锁（已有写者）返回 [1] |
| 长读事务 | 阻止 checkpointer 推进，WAL 增长，读变慢 [2] | 读者持 SHARED 锁会阻止写者取得 EXCLUSIVE 提交 [1] |
| checkpoint | 需定期执行以控制 WAL 大小；被阻塞时 `wal_checkpoint` 首列为 1（等价 SQLITE_BUSY）[2][4] | 无 WAL checkpoint 概念；提交时把原页写回数据库文件 [1] |

## 关键说明

**WAL 仍会 BUSY 的条件**（官方列举）[2]：
1. 另一连接以 exclusive locking mode 打开数据库，则所有查询返回 SQLITE_BUSY。
2. 最后一个连接关闭时短暂持独占锁清理 WAL 和共享内存文件，此时新连接查询可能 BUSY。
3. 最后连接崩溃后，首个新连接做恢复时持独占锁，第三个连接此时查询会 BUSY。

**长读事务如何影响 checkpoint**：checkpointer 只能把 WAL 内容转移到数据库文件到“最老读者仍需要的位置”为止，之后无法继续；只有所有读者结束后才能推进。写者在每次写操作时检查 checkpoint 进度，若整个 WAL 已转移且无读者使用 WAL，才把 WAL 回卷到开头重用，从而防止无限增长 [2]。因此长读事务使 WAL 无法回卷、文件持续增大，而每个读者检查 WAL 的时间与 WAL 大小成正比，读性能下降 [2]。

**checkpoint 被阻塞的观测**：`PRAGMA wal_checkpoint` 返回三列，首列为 1 表示 RESTART/FULL/TRUNCATE checkpoint 被阻塞（等价于 `sqlite3_wal_checkpoint_v2()` 返回 SQLITE_BUSY），例如另一线程或进程正在使用数据库 [4]。

**不适合 WAL 的场景**：
- 网络文件系统（尤其 NFS）等锁原语有缺陷的文件系统：若两个以上线程/进程同时访问同一数据库，可能损坏 [3]。
- QNX：mmap 共享内存存在缺陷，大事务多次 mmap 可能损坏数据库；建议不用内存映射 I/O，且用 exclusive locking mode 以无共享内存方式使用 WAL [3]。
- 只读介质或无写权限：SQLite 3.22.0 起，满足以下任一条件仍可读——`-shm` 与 `-wal` 文件已存在且可读；所在目录有写权限等 [2]。
- 旧版本兼容：WAL 数据库只能由 SQLite 3.7.0（2010-07-21）及以上访问 [4]。

## 官方来源

- WAL：https://www.sqlite.org/wal.html [2]
- 文件锁与并发（rollback 模式）：https://www.sqlite.org/lockingv3.html [1]
- 如何损坏数据库文件：https://www.sqlite.org/howtocorrupt.html [3]
- PRAGMA（journal_mode / wal_checkpoint）：https://www.sqlite.org/pragma.html [4]

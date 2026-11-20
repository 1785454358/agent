**结论先行**

WAL 的核心优势是“写者不阻塞读者、读者不阻塞写者”，但官方原文强调这“**mostly**”成立，WAL **不意味着不会返回 SQLITE_BUSY**：排他锁模式、最后连接关闭清理、崩溃后恢复期间都可能让查询得到 SQLITE_BUSY [1]。rollback journal 下写者需 RESERVED 锁、同一时刻仅一个写者，读者持 SHARED 锁可并发读，但写者提交升级排他锁时与读者互斥；取不到锁即返回 SQLITE_BUSY [2]。checkpoint 方面，默认 PASSIVE 在有并发读者或写者时可能无法完成，FULL/RESTART/TRUNCATE 被阻止时等价于 SQLITE_BUSY [1][3]。

**对比表**

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写者不阻塞读者、读者不阻塞写者（“mostly”），读写可并发 [1] | 写者持 RESERVED 时其他进程仍可读；写者最终更新需排他锁，与读者互斥 [2] |
| 写者数量 | 同一时刻一个写者（WAL 写锁语义）[1] | 同一时刻仅一个 RESERVED 锁，即一个写者 [2] |
| SQLITE_BUSY | 仍会返回：他连接以 exclusive locking mode 打开；最后连接关闭清理 WAL/共享内存时短暂排他锁；最后连接崩溃后首个新连接恢复期间持排他锁 [1] | 取不到 SHARED 锁立即 SQLITE_BUSY；取不到 RESERVED 锁写尝试失败返回 SQLITE_BUSY；回滚热日志取锁失败也返回 [2] |
| 长读事务与 checkpoint | 长读事务会阻止 checkpoint 推进（PASSIVE 有并发读者可能无法完成；RESTART 会阻塞等待所有读者读完日志）[1][3] | 无 WAL checkpoint 概念；读者持 SHARED 锁会阻止写者升级排他锁 [2] |
| checkpoint 模式 | PASSIVE 默认、尽量不干扰；FULL/RESTART 更努力，仅 sqlite3_wal_checkpoint_v2() 可发起；TRUNCATE 成功后 WAL 截为零字节 [1][3] | 不适用 |

**WAL 是否意味着不会 SQLITE_BUSY**

不是。官方明确列出查询仍可能返回 SQLITE_BUSY 的三种情形：另一连接以 exclusive locking mode 打开数据库；最后一个连接关闭时短暂获取排他锁清理 WAL 与共享内存文件；最后一个连接崩溃后首个新连接恢复期间持排他锁，此时其他连接查询会得到 SQLITE_BUSY [1]。应用应为此做好准备 [1]。

**长读事务如何影响 checkpoint**

默认 PASSIVE checkpoint“在不干扰其他连接的前提下尽量工作”，若有并发读者或写者可能无法运行到完成 [1]。RESTART 模式在 checkpoint 日志后阻塞（调用 busy-handler）直到所有读者读完日志文件，从而保证下一个写者从头重启日志；RESTART 运行期间阻塞并发写者但允许读者继续 [3]。TRUNCATE 在 RESTART 基础上成功后把 WAL 截为零字节 [3]。wal_checkpoint pragma 第一列通常为 0，若 RESTART/FULL/TRUNCATE 因另一线程或进程正在使用数据库而被阻止完成则为 1，等价于 sqlite3_wal_checkpoint_v2() 返回 SQLITE_BUSY [3]。

**不适合 WAL 的场景与限制**

- 所有使用数据库的进程必须在同一主机；WAL 不能在网络文件系统上工作，因为需要进程共享少量内存 [1]。
- 进入 WAL 模式后无法更改 page_size，必须回到 rollback journal 模式才能改 [1]。
- 打开 WAL 数据库的进程需要对 -shm wal-index 共享内存文件（若存在）或所在目录有写权限 [1]。
- 涉及多个 ATTACH 数据库的事务在每个库内原子，但跨库整体不原子 [1]。

**证据缺口**

本次可见材料未直接给出“长读事务具体如何阻止 checkpoint 推进、对 WAL 文件大小影响”的原文段落；上述关于长读事务与 checkpoint 的说明仅基于 PASSIVE 可能因并发读者无法完成、RESTART 等待所有读者读完日志这两条原文 [1][3]，WAL 文件增长的具体机制无法从现有材料确认。

**官方来源**

- https://www.sqlite.org/wal.html [1]
- https://www.sqlite.org/lockingv3.html [2]
- https://www.sqlite.org/pragma.html [3]
- https://sqlite.org/atomiccommit.html [4]

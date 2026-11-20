**结论**：WAL 模式下读写基本互不阻塞，但并非绝不返回 SQLITE_BUSY；rollback journal 模式下写者持 RESERVED 锁时其他进程仍可读，但读写锁竞争会直接产生 SQLITE_BUSY。长读事务会阻止 checkpoint 完成，持续有活跃读者时 WAL 可无限增长。WAL 依赖共享内存，不适合网络文件系统。[1][2]

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写者不阻塞读者、读者不阻塞写者，官方强调“mostly”成立[1] | 写者持 RESERVED 锁时其他进程仍可读；写前原页写入 journal，主库文件暂不变[2] |
| SQLITE_BUSY | 仍可能：他连接以 exclusive locking mode 打开；最后连接关闭清理 WAL/共享内存；崩溃后新连接恢复持排他锁[1] | 读拿不到 SHARED 锁立即 BUSY；写拿不到 RESERVED 锁（已有写者）则 BUSY[2] |
| 长读事务 | 阻止 checkpoint 完成；若始终有活跃读者，WAL 无限增长[1] | 读者持 SHARED 锁，写者提交前须确保无其他读者，否则等待/受阻[2] |
| checkpoint | PASSIVE 尽量做但可能不完成；RESTART/TRUNCATE 确保完成，但可能阻塞读者；被阻塞时 wal_checkpoint 首列返回 1（等价 SQLITE_BUSY）[1][3] | 无 WAL checkpoint 概念；提交时写主库并删除/截断 journal[4][2] |

**WAL 是否意味着不会返回 SQLITE_BUSY**：不是。官方明确说“读写互不阻塞”只是 mostly 成立，应用应准备处理 BUSY，并列出上述三类情形[1]。此外 RESTART/FULL/TRUNCATE checkpoint 被其他线程或进程阻塞时，wal_checkpoint 首列返回 1，等价于 sqlite3_wal_checkpoint_v2 返回 SQLITE_BUSY[3]。

**长读事务如何影响 checkpoint**：PASSIVE checkpoint 不干扰其他连接，但有并发读者或写者时可能无法完成；checkpoint 会在下次写事务时从上次位置继续，直到某次能完成。若数据库有许多重叠读者且始终至少一个活跃读者，则没有 checkpoint 能完成，WAL 文件无限增长。可用“reader gaps”或在无读者时手动执行 RESTART/TRUNCATE checkpoint 确保完成，代价是读者可能被阻塞[1]。TRUNCATE 成功完成后将 WAL 截断为零字节[3]。

**不适合 WAL 的场景**：网络文件系统，因为 WAL 依赖共享内存，所有读者须在同一机器[1]。另需注意 WAL 是持久设置，关闭重开后仍为 WAL[1][3]；旧于 3.7.0 的 SQLite 无法访问 WAL 数据库[3]。

**官方来源**：
- https://www.sqlite.org/wal.html [1]
- https://sqlite.org/atomiccommit.html [4]
- https://www.sqlite.org/lockingv3.html [2]
- https://www.sqlite.org/pragma.html [3]

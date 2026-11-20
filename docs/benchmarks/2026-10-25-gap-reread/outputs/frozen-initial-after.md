**结论**：WAL 模式下写者不阻塞读者、读者不阻塞写者，读写可并发，但原文强调这只是“mostly”成立 [1]；rollback journal 模式下写者持 RESERVED 锁时其他进程仍可读，但同一时刻只有一个写者 [2]。WAL 并不保证不返回 SQLITE_BUSY，原文列出若干仍会返回该错误的情形 [1]，且 FULL/RESTART/TRUNCATE checkpoint 被阻塞时等价调用也返回 SQLITE_BUSY [3]。长读事务对 checkpoint 的影响：可见材料只说明 PASSIVE checkpoint 在有并发读者或写者时可能无法运行到完成 [1]，RESTART 会阻塞到所有读者用完日志文件、TRUNCATE 成功后才把 WAL 截为零字节 [3]；长读事务具体如何阻止 checkpoint 推进、如何导致 WAL 文件增大，本次可见原文未直接说明，属证据缺口。不适合 WAL 的场景包括：所有使用数据库的进程必须在同一主机、WAL 不能用于网络文件系统 [1]；进入 WAL 后不能改 page_size，须回到 rollback journal 模式才能改 [1]；打开数据库的进程需对 -shm 共享内存文件有写权限，若文件不存在则需对所在目录有写权限 [1]。

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 写者不阻塞读者、读者不阻塞写者，原文强调“mostly”成立 [1] | 写者先取 SHARED 再取 RESERVED；持 RESERVED 时其他进程仍可读，但同一时刻仅一个写者 [2] |
| SQLITE_BUSY | 仍可能返回：另一连接以 exclusive locking mode 打开；最后连接关闭清理 WAL/共享内存时短暂排他锁；最后连接崩溃后新连接恢复期间排他锁 [1] | 取不到 RESERVED 锁的写尝试返回 SQLITE_BUSY；读进程取不到 SHARED 锁立即返回 SQLITE_BUSY [2] |
| 长读事务与 checkpoint | 默认 PASSIVE checkpoint 有并发读者或写者时可能无法完成 [1]；RESTART 阻塞到所有读者用完日志文件，TRUNCATE 成功后才截断 WAL [3]；RESTART/FULL/TRUNCATE 被阻塞时 wal_checkpoint 第一列为 1，等价调用返回 SQLITE_BUSY [3] | 不适用（无 WAL checkpoint 概念） |
| checkpoint 模式 | PASSIVE 默认，尽量不干扰其他连接；FULL、RESTART 更努力完成，只能经 sqlite3_wal_checkpoint_v2() 发起 [1]；TRUNCATE 在 RESTART 基础上成功后把 WAL 截为零字节 [3] | 无 |

**WAL 是否意味着不会返回 SQLITE_BUSY**：不是。原文明确说“读写互不阻塞”只是“mostly”成立，并列出上述三类仍返回 SQLITE_BUSY 的情形，应用应做好准备 [1]。此外，FULL/RESTART/TRUNCATE checkpoint 因另一线程或进程正在使用数据库而被阻止完成时，等价调用会返回 SQLITE_BUSY [3]。

**长读事务如何影响 checkpoint**：可见材料只说明 PASSIVE checkpoint 在有并发读者或写者时“可能无法运行到完成” [1]，以及 RESTART 会阻塞到所有读者用完日志文件、TRUNCATE 成功后才截断 WAL [3]。长读事务具体如何阻止 checkpoint 推进、如何导致 WAL 文件增大，本次可见原文未直接说明，属证据缺口，不能据常识补全；可核查 sqlite3_wal_checkpoint_v2() 文档与 WAL 文档中 checkpoint 章节。

**不适合 WAL 的场景**：所有使用数据库的进程必须在同一主机，WAL 不能用于网络文件系统，因为要求进程共享少量内存 [1]；进入 WAL 后不能改 page_size，须回到 rollback journal 模式才能改 [1]；打开数据库的进程需对 -shm 共享内存文件有写权限，若文件不存在则需对所在目录有写权限 [1]。

**官方来源**：[1] https://www.sqlite.org/wal.html ；[2] https://www.sqlite.org/lockingv3.html ；[3] https://www.sqlite.org/pragma.html

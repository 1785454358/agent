# live-sqlite-wal-20261107 / workflow

依据 SQLite 官方文档，解释 WAL 下长时间读事务为什么可能阻止 checkpoint 推进，以及 WAL 是否意味着不会返回 SQLITE_BUSY。说明多写者限制和多主机网络文件系统的边界。请给出因果解释与官方引用；无法确认的内容应明确说明。

Status: completed; answered flag: True; response reason: None; model calls: 6; seconds: 45.034.

**结论：** WAL 下长时间读事务会通过“读者仍持有旧快照”阻止 FULL/RESTART/TRUNCATE checkpoint 完成；PASSIVE 则不等读者，可能留下未 checkpoint 的帧 [1]。WAL 不保证不返回 SQLITE_BUSY，写者竞争、独占锁、关闭清理、崩溃恢复及 checkpoint 锁竞争都可能返回 [1][2]。WAL 允许多读者与单写者并发，但同一时刻只能有一个写者 [2]；它要求所有进程同主机共享内存，不能用于多主机网络文件系统 [2]。

**1. 长时间读事务为何阻止 checkpoint**

checkpoint 把 WAL 帧写回数据库文件。PASSIVE 模式“尽可能多地 checkpoint，但不等待任何读者或写者结束”，有并发读者或写者时可能未完成 [1]。FULL 模式会阻塞（调用 busy-handler），直到没有写者且所有读者都读取最新数据库快照，然后 checkpoint 日志中所有帧 [1]。因此，长读事务若一直持有旧快照，FULL 等模式无法满足“所有读者读最新快照”的条件，checkpoint 被推迟；若 busy-handler 返回 0，则退化为 PASSIVE 并返回 SQLITE_BUSY [1]。

**2. WAL 是否意味着不会 SQLITE_BUSY**

不是。官方明确说“写者不阻塞读者、读者不阻塞写者”只是“大部分”成立，某些不常见情形下查询仍可能返回 SQLITE_BUSY，应用应做好准备 [2]。列举情形包括：另一连接以 exclusive locking mode 打开数据库；最后一个连接关闭时清理 WAL/共享内存文件期间；崩溃后首个新连接恢复期间持有排他锁 [2]。此外，所有 checkpoint 调用都获取排他 checkpoint 锁，若另一进程同时 checkpoint，则返回 SQLITE_BUSY，且 busy-handler 不会被调用 [1]。

**3. 多写者限制**

WAL 下写者只向 WAL 末尾追加，不干扰读者，故写者与读者可同时运行；但只有一个 WAL 文件，同一时间只能有一个写者 [2]。

**4. 多主机/网络文件系统边界**

WAL 要求所有使用同一数据库的进程在同一台主机上，不能工作在网络文件系统，因为 WAL 要求所有进程共享一小块内存，而不同主机进程无法共享内存 [2]。该共享内存通常通过 mmap() 一个专门的 `-shm` 文件实现，供多个进程作 WAL 索引 [3]。

**无法确认：** 本次材料未给出“长时间读事务”的具体时长阈值，也未给出网络文件系统上具体失败表现或各 VFS 的共享内存替代实现细节；这些不能从现有引用推出。

## Sources

1. Checkpoint a database — https://www.sqlite.org/c3ref/wal_checkpoint_v2.html
2. Write-Ahead Logging — https://www.sqlite.org/wal.html
3. Temporary Files Used By SQLite — https://www.sqlite.org/tempfiles.html

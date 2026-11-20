## 结论

- **读写并发**：WAL 下读不阻塞写、写不阻塞读，读写可并发；但同一时刻仍只有一个写者 [1]。rollback journal 下写者持 RESERVED 锁时其他进程仍可读，但写者把修改写回数据库文件前必须确保无其他进程在读，提交阶段会阻塞读者 [2]。
- **SQLITE_BUSY**：WAL **不意味着不会返回 SQLITE_BUSY**。官方称读写互不阻塞“mostly”成立，少数情况查询仍可能返回 SQLITE_BUSY，应用应做好准备 [1]。
- **长读事务与 checkpoint**：checkpoint 可与读者并发，但必须停在当前任何读者结束标记之后的 WAL 页之前；长读事务会阻止 checkpointer 推进，checkpoint 记住进度并在下次调用时从断点继续 [1]。
- **不适合 WAL 的场景**：所有进程须在同一主机；不能用于网络文件系统（WAL 要求进程共享少量内存）；进入 WAL 后不能改 page_size [1]。

## 对比表

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 读不阻塞写、写不阻塞读，可并发；同一时刻只有一个写者 [1] | 写者持 RESERVED 锁时其他进程可读；写回数据库文件前须确保无其他进程在读，提交阶段阻塞读者 [2] |
| 写写 | 同一时刻只有一个写者 [1] | 同一时刻只有一个进程可持 RESERVED 锁；拿不到则写尝试失败返回 SQLITE_BUSY [2] |
| SQLITE_BUSY 来源 | 另一连接以 exclusive locking mode 打开；最后连接关闭清理 WAL/shm 期间；最后连接崩溃后新连接恢复期间持排他锁 [1]；checkpoint 拿不到排他 checkpoint 锁时返回 SQLITE_BUSY，且 busy-handler 不被调用 [3] | 拿不到 RESERVED 锁；恢复热日志时拿不到 PENDING/EXCLUSIVE 锁 [2] |
| 长读事务影响 | 阻止 checkpoint 推进；checkpoint 记住进度，下次从断点继续 [1] | 无 WAL 意义上的 checkpoint 概念；wal_checkpoint 在非 WAL 模式为无害 no-op，输出列为 -1 [4] |
| checkpoint 机制 | 默认 COMMIT 使 WAL 达 1000 页或最后连接关闭时自动 checkpoint；可用 wal_checkpoint pragma 或 C 接口强制；wal_autocheckpoint 调整阈值或禁用 [1] | 无 checkpoint 概念 [4] |

## WAL 仍会返回 SQLITE_BUSY 的条件

官方明确读写互不阻塞“mostly”成立，但存在少数查询返回 SQLITE_BUSY 的情况 [1]：

1. 另一连接以 exclusive locking mode 打开数据库，则所有查询返回 SQLITE_BUSY [1]。
2. 最后一个连接关闭时短暂持排他锁清理 WAL 和共享内存文件，此时另一连接打开并查询可能得到 SQLITE_BUSY [1]。
3. 最后连接崩溃后，第一个新连接进行恢复时持排他锁，第三个连接此时查询会得到 SQLITE_BUSY [1]。

checkpoint 侧：所有 checkpoint 调用都获取排他 checkpoint 锁；若另一进程正在 checkpoint，锁拿不到即返回 SQLITE_BUSY，即使配置了 busy-handler 也不会被调用 [3]。FULL/RESTART/TRUNCATE 还需获取排他 writer 锁；若不能立即获得且 busy-handler 返回 0，则退化为 PASSIVE 并返回 SQLITE_BUSY [3]。

## 长读事务如何影响 checkpoint

checkpoint 可与读者并发，但必须停在当前任何读者结束标记之后的 WAL 页之前，否则可能覆盖读者正在使用的数据库文件部分；checkpoint 在 wal-index 中记住进度，下次调用从断点继续 [1]。因此长读事务可阻止 checkpointer 推进，但读事务最终结束后 checkpointer 可继续 [1]。

模式差异：PASSIVE 不等待读者或写者结束，可能因并发读者或写者而未完成 [3]；FULL 阻塞直到没有写者且所有读者都读取最新快照，然后 checkpoint 所有帧 [3]。

## 不适合 WAL 的场景

- 所有使用数据库的进程必须在同一主机；WAL 不能用于网络文件系统，因为要求所有进程共享少量内存 [1]。
- 进入 WAL 模式后不能更改 page_size（空库、VACUUM、backup API 恢复均不行），须在 rollback journal 模式下改 [1]。
- 涉及多个 ATTACH 数据库的事务，每个数据库各自原子，但作为整体不跨库原子 [1]。
- 旧版文档曾列“不能打开只读 WAL 数据库”，该条在可见原文中被删除线标记，可能已过时，不宜作为现行限制引用 [1]。

## 官方来源

- WAL 总述、并发、SQLITE_BUSY、checkpoint、限制：https://www.sqlite.org/wal.html [1]
- checkpoint C 接口与模式：https://www.sqlite.org/c3ref/wal_checkpoint_v2.html [3]
- rollback journal 锁与并发：https://www.sqlite.org/lockingv3.html [2]
- wal_checkpoint pragma：https://www.sqlite.org/pragma.html [4]
- WAL 文件格式与关闭时自动 checkpoint：https://www.sqlite.org/walformat.html [5]

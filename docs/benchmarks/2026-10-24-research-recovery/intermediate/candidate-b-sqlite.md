## 结论

- **读写并发**：WAL 下“写不阻塞读、读不阻塞写”基本成立，但官方用“mostly”限定，并非绝对 [1][2]。rollback journal 的写者把改动直接写入数据库文件，读写互斥更直接 [1]。
- **SQLITE_BUSY**：WAL **不意味着**不会返回 SQLITE_BUSY。排他锁模式、最后连接关闭清理、崩溃后恢复期间，查询仍可能得到 SQLITE_BUSY [1][2]。
- **长读事务与 checkpoint**：checkpoint 要“跑完并重置 WAL”，需没有其他使用 WAL 的连接持有读事务；长读事务会造成 checkpoint starvation，WAL 无法重置/截断而持续增长 [2]。
- **checkpoint 机制**：WAL 比 rollback journal 多出第三种基本操作 checkpoint；默认 WAL 超过约 1000 页时自动 checkpoint [1][2]。rollback journal 没有对应 checkpoint，提交靠删除回滚日志完成 [1]。
- **不适合 WAL 的场景**：网络文件系统（需同主机共享内存）、只读介质（官方建议先转 DELETE）、旧版本只读 WAL 限制（3.22.0 前）[2]。

## 对比表

| 维度 | rollback journal | WAL |
|---|---|---|
| 基本操作 | 读、写两种；原内容存回滚日志，改动直接写数据库文件，提交时删除日志 [1] | 读、写、checkpoint 三种；改动追加到 WAL，提交记录写入 WAL [1] |
| 读写并发 | 写者直接改数据库文件，读写互斥更直接 [1] | 写者不阻塞读者、读者不阻塞写者，但官方称“大部分”成立 [1][2] |
| SQLITE_BUSY | 材料未展开 rollback journal 下具体 BUSY 情形 | 仍可能返回：排他锁模式、最后连接关闭清理、崩溃恢复持排他锁 [1][2] |
| 长读事务 | 材料未展开 | 有读事务未结束时 checkpoint 无法完成并重置 WAL，导致 WAL 持续增长 [2] |
| checkpoint | 无此机制；提交即删除回滚日志 [1] | 默认约 1000 页自动 checkpoint；禁用自动 checkpoint 则无机制阻止 WAL 过度增长 [1][2] |
| 适用限制 | 材料未列 | 不能用于网络文件系统；只读介质建议转 DELETE；旧版本只读受限 [2] |

## 关键条件与取舍

**WAL 仍会 BUSY 的三种情形** [1][2]：
1. 另一连接以 exclusive locking mode 打开数据库，所有查询返回 SQLITE_BUSY。
2. 最后一个连接关闭时短暂持排他锁清理 WAL 与共享内存文件，此时新查询可能 BUSY。
3. 最后连接崩溃后，首个新连接恢复期间持排他锁，第三个连接查询会 BUSY。

**长读事务的影响**：checkpoint 只有在没有其他连接使用 WAL 文件（持读事务）时才能跑完并重置 WAL；长扫描或长传输可能使 starvation 持续，WAL 文件无法截断/回收 [2]。

**不适合 WAL 的场景** [2]：
- 网络文件系统：WAL 要求所有进程同主机并共享少量内存，故不能在网络文件系统工作。
- 只读介质：虽 3.22.0 起可只读打开 WAL 数据库（需满足条件），官方仍建议烧录镜像前转 `PRAGMA journal_mode=DELETE`。
- 旧版本（3.22.0 前）只读 WAL 数据库有额外限制。

## 材料缺口

- rollback journal 下 SQLITE_BUSY 的具体触发情形，本次可见材料未展开，无法据此对比。
- rollback journal 的并发细节（如读者与写者锁行为）材料仅给出基本操作描述，未给出完整锁语义。
- 上述缺口仅表示本次可见材料不足，不代表官方文档没有相关内容。

## 官方来源

- https://www.sqlite.org/wal.html [1]
- https://sqlite.org/wal.html [2]

## 结论

- **读写并发**：WAL 下读不阻塞写、写不阻塞读，读写可并发；但同一时刻只能有一个写者，写与写互斥 [1]。rollback journal 的并发行为在可见材料中仅以“WAL 提供更多并发”的对比方式间接体现，本页未展开其具体锁行为 [1]。
- **SQLITE_BUSY**：WAL **不意味着**永不返回 SQLITE_BUSY。官方称“写不阻塞读、读不阻塞写”只是 *mostly* 成立，少数情形下查询仍会返回 SQLITE_BUSY，应用应做好准备 [1]。
- **长读事务与 checkpoint**：本次可见材料**未直接说明**长读事务如何阻止 checkpoint 推进或导致 WAL 增长，此点存在证据缺口，不能据常识补全。已支持的相关事实是：读操作开始时记住 WAL 中最后一个有效提交记录位置（“end mark”），而 WAL 在读期间可能继续增长 [1]；WAL 文件增大会使读性能下降，需定期 checkpoint 保持 WAL 较小 [1]。
- **checkpoint 机制**：WAL 比 rollback journal 多出“checkpoint”这一原语；默认 WAL 达 1000 页自动 checkpoint，也可调阈值、关闭自动并在空闲时或独立线程/进程手动执行 [1]。
- **不适合 WAL 的场景**：所有进程须在同一主机；WAL 不能在网络文件系统上工作，因为依赖共享内存 [1]。

## 对比表

| 维度 | WAL | rollback journal |
|---|---|---|
| 读写并发 | 读不阻塞写、写不阻塞读，可并发；写者唯一 [1] | 原文仅称 WAL“提供更多并发”，未展开其锁行为 [1] |
| 写写并发 | 同一时刻只能有一个写者 [1] | 本页未直接说明 |
| SQLITE_BUSY | 仍可能返回，见下方情形 [1] | 本页未直接展开触发条件 |
| 长读事务影响 checkpoint | 可见材料未直接说明（缺口） | 不适用/未说明 |
| checkpoint | 第三种原语；默认 1000 页自动，可调阈值或手动 [1] | 无 checkpoint 概念（原文以“两种原语：读、写”对比）[1] |
| 文件增长影响 | WAL 增大降低读性能，需定期 checkpoint [1] | 本页未直接说明 |
| 部署限制 | 同主机、非网络文件系统 [1] | 本页未列出同等限制 |

## WAL 下仍返回 SQLITE_BUSY 的情形 [1]

1. 另一连接以 exclusive locking mode 打开数据库，则对该库的所有查询返回 SQLITE_BUSY（如 Chrome、Firefox 运行中读取其数据库）。
2. 最后一个连接关闭时，会短暂持有排他锁清理 WAL 与共享内存文件；此时另一连接打开并查询可能得到 SQLITE_BUSY。
3. 最后一个连接崩溃后，第一个新连接进行恢复期间持有排他锁；第三个连接此时查询会得到 SQLITE_BUSY。

## 长读事务与 checkpoint：证据缺口

本次可见材料只说明：读操作开始时记住 WAL 中最后一个有效提交记录位置（“end mark”），WAL 可能在读期间继续增长 [1]；以及 WAL 增大会拖慢读、需定期 checkpoint [1]。**但未直接说明**长读事务如何阻止 checkpoint 推进。因此“长读事务阻止 checkpoint 推进/导致 WAL 增长”这一因果链无法从当前材料确认，建议查阅 SQLite 官方 WAL 文档中 checkpoint 与读者快照相关章节核实，不应作为已证实结论引用。

## 取舍与适用条件

- 需要读写并发、较少 fsync、顺序 I/O 时，WAL 通常更优 [1]；代价是引入 checkpoint 管理，且 WAL 过大损害读性能 [1]。
- 多主机/网络文件系统共享数据库时不适合 WAL，应改用 rollback journal 等方案 [1]。
- 应用须容忍偶发 SQLITE_BUSY，不能因启用 WAL 就省略忙处理逻辑 [1]。

## 官方来源

- SQLite Write-Ahead Logging：https://www.sqlite.org/wal.html [1]

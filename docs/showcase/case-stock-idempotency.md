# 消息重投与库存幂等

> 订单消息会重复投递。用 Kafka 或 SQS FIFO 时，库存扣减和消息确认应该按什么顺序做？数据库提交前后分别宕机，怎么测试？

**结论：先提交库存扣减事务，再确认消息（Kafka 提交位点 / SQS 删除消息）；并且库存扣减必须用业务幂等键做成可重复执行，不能只靠“先提交后确认”消除重复。** 这个顺序保证的是“至少一次”而非“恰好一次”：提交后、确认前宕机会重投，靠幂等吸收；反过来先确认后提交，确认后、提交前宕机会丢消息。[1][2][3]

## 顺序与依据

- **Kafka**：关闭自动提交，在线程处理完、且对应记录已写入数据库之后再手动提交位点；原文明确说这样会带来“插入后、提交前失败则重复插入”的可能，即 at-least-once。[1] 因此顺序是：消费 → 幂等扣库存并提交事务 → commitSync 位点。
- **SQS FIFO**：处理并提交数据库后调用 DeleteMessage；若在可见性超时内未删除，消息会重新可见并被再次处理。[3] 处理时间可能超过超时时，用 ChangeMessageVisibility 延长；反复失败进死信队列。[2] 注意 FIFO 的 5 分钟发送去重窗口只约束生产端重发，超窗重发会被当新消息，消费端重复仍会发生。[2]

| 顺序 | 宕机点 | 结果 |
|---|---|---|
| 先提交、后确认（推荐） | 提交后确认前 | 重投，幂等吸收 |
| 先确认、后提交 | 确认后提交前 | 消息丢失 |

**幂等实现建议（非原文事实）**：以订单号或消息唯一 ID 建唯一约束，在同一事务内插入去重记录并扣减库存；冲突则视为已处理，直接走确认。PostgreSQL 的 ON CONFLICT 可用于此，唯一冲突时可选择不插入或更新。[4] 事务未提交前其他事务看不到其修改，提交时整体可见。[5]

## 宕机测试

在扣库存事务与消息确认之间插入可控故障点，用注入而非真实杀进程也可，但最终应做一次真实进程终止验证：

1. **提交前宕机**：在事务 commit 调用前终止消费者。预期：数据库无扣减，消息未确认，重投后正常扣减一次。
2. **提交后、确认前宕机**：commit 返回后、commitSync/DeleteMessage 前终止。预期：数据库已扣减，消息重投，幂等逻辑识别重复，库存不再变化，随后确认成功。
3. **确认后宕机**：确认成功后立即终止。预期：不重投，库存保持一次扣减。
4. **SQS 额外场景**：让处理时间超过可见性超时且不延长，验证另一消费者重复处理时幂等仍生效；再验证延长可见性后不重复。[2][3]

每个用例核对三项：库存净变化是否为 1、去重表/唯一键是否只有一条、消息是否最终被确认且无死信堆积。

## 未核实与限制

本轮资料未给出 Kafka 事务性生产/消费（exactly-once）的具体配置，也未给出 SQS FIFO 与数据库之间分布式事务的做法；上述幂等方案属建议，需按实际数据库与框架验证。Kafka 位点提交 API 的具体语义以所用客户端版本为准。[1]

## 引用来源

[1] https://docs.confluent.io/platform/current/clients/javadocs/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html
[2] https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/designing-for-outage-recovery-scenarios.html
[3] https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html
[4] https://www.postgresql.org/docs/17/sql-insert.html
[5] https://www.postgresql.org/docs/17/tutorial-transactions.html
**结论：选 Uptime Kuma 开源自托管主线，部署在现有闲置 Linux 服务器上，用 Docker 运行，20 个 HTTPS 站点按 60 秒间隔检查，SMTP 邮件通知，目标保留 30 天历史。增量月费按已知项目计为 0 元，但 30 天保留的具体配置项与单机容量尚未核实，方案尚未完整确认，不能据此承诺整个方案低于预算。**

## 一、主线与核实情况

Uptime Kuma 是开源自托管监控工具，按间隔检查 HTTP 等站点、记录响应时间、通过 90+ 通知提供方告警，数据存于自有数据库 [1]。官方 Docker 命令为 `louislam/uptime-kuma:2`，映射 `/app/data` 卷、端口 3001，数据目录需支持 POSIX 文件锁以避免 SQLite 损坏，支持主流 Linux 发行版 [2]。

- **HTTPS 监控**：Monitor Type 选 HTTP(s)，填含 `https://` 的完整 URL，可设心跳间隔、重试、超时、接受状态码；默认 2xx 成功、最多跟随 10 次重定向并评估最终状态码 [3]。
- **检查频率**：默认 60 秒，可低至 20 秒；更短间隔发现更快，但增加目标站负载和数据库行数，60 秒对多数站点是合理默认 [3][4]。20 个站点按 60 秒计约每分钟 20 次请求；单机实际容量未量化，属未核实。
- **通知渠道**：SMTP 在 Settings → Notifications → Add New Notification 配置，需主机名、端口（465/587）、加密方式、用户名密码、发件地址；Gmail 需开两步验证并生成 16 位应用专用密码，个人 Gmail 每日约 500 封、Workspace 约 2000 封上限 [5]。保存时有 Default Enabled（自动附加到新监控）与 Apply on all existing monitors（追溯附加到已有监控）[6]。
- **30 天历史**：数据全部存于 `/app/data`（SQLite），必须挂载持久卷，否则重部署丢失 [1]。清理任务按全局保留期删除超过 30 天的旧数据；按监控项自定义保留是未实现特性，已关闭为“不计划” [7]。因此 30 天历史只能依赖全局保留期实现，**具体配置项名称、默认值与可调范围本次材料未给出，标为未核实**；v2 仅存聚合结果，保留更多数据仍影响性能 [7]。

## 二、费用分项（5 人、20 站、按月）

| 项目 | 金额 | 说明 |
|---|---|---|
| 服务器 | 0 元增量 | 已有闲置 Linux 服务器，电费/带宽按沉没成本不计 |
| 软件许可 | 0 元 | 开源自托管，无按监控项费用 [4] |
| 邮件通知 | 0 元 | 用现有邮箱 SMTP；Gmail 个人约 500 封/日、Workspace 约 2000 封/日 [5] |
| 域名/证书 | 0 元（内网访问）或未核实（公网 HTTPS 面板） | 仅内网访问或 SSH 隧道可不配域名；如需公网 HTTPS 面板，域名实价未核实 |
| **已知小计** | **0 元/月** | 余量 300 元，可用于可选域名或备用通知渠道 |

假设：服务器可装 Docker 并能出网访问 20 个目标站；团队已有可用 SMTP 邮箱；服务器电费带宽不计增量。若需公网访问面板，域名年费实价未核实，不能据此承诺整个方案低于预算。

## 三、部署步骤

1. 确认系统与依赖：`docker --version`、`docker compose version`；用 `df -T /opt` 确认 `/opt` 为本地存储，避免 NFS 类文件锁问题 [8][2]。
2. 建目录：`sudo install -d -o "$USER" -g "$USER" /opt/uptime-kuma && cd /opt/uptime-kuma && mkdir -p data backups` [8]。
3. 写 `compose.yaml`，固定镜像版本，端口只绑本机：

```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:2
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "127.0.0.1:3001:3001"
    volumes:
      - ./data:/app/data
```

4. 启动并验证：`docker compose pull && docker compose up -d && docker compose ps && docker compose logs --tail=100 uptime-kuma`；`curl -I http://127.0.0.1:3001` 应返回有效响应 [8]。
5. 浏览器打开 `http://127.0.0.1:3001`（或经 SSH 隧道/反向代理），立即创建管理员账号，未建账号前任何人可抢占实例 [1]。
6. 配置 SMTP 通知：填主机、端口、加密、账号、应用专用密码、收发地址，点 Test 确认收件后 Save；勾选 Default Enabled 使新监控自动附加，勾选 Apply on all existing monitors 追溯附加到已有监控 [6][5]。
7. 逐个添加 20 个 HTTPS 监控：类型 HTTP(s)、完整 URL、间隔 60 秒、重试 1–2 次、超时 15–30 秒、接受状态码 200–299 [3]。
8. 验证：手动停一个测试站确认邮件到达；确认 `/app/data` 有数据库文件、重启容器后历史仍在；在设置中核对全局保留期是否为 30 天（配置项名未核实）。

## 四、一致性与缺口

步骤依赖 Docker、持久卷、SMTP 凭据齐全，顺序可行；已知费用 0 元不超 300 元。**仍存缺口**：30 天保留的具体配置项与默认值、20 站单机容量均未在本次材料中量化，标为未核实；建议部署后在设置页核对全局保留期并观察数据库增长。
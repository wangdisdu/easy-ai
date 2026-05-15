# SRE 运维处置手册 v3.5

本手册整合了告警分级、常见故障处置、监控体系与复盘流程,适用于 SRE 团队日常应急响应与新员工培训。

---

## 1. 故障分级标准

| 等级 | 业务影响 | 响应时限 | 升级路径 |
|---|---|---|---|
| P1 | 核心业务完全不可用 / 数据安全事件 | **15 分钟** | 值班 SRE → 部门总监 → CTO |
| P2 | 核心业务部分不可用 / 性能严重下降 | 30 分钟 | 值班 SRE → 二线负责人 |
| P3 | 非核心业务异常 / 单点警告 | 2 小时 | 值班 SRE |
| P4 | 不影响生产 / 例行优化 | 24 小时 | 值班 SRE 工单跟进 |

P1 事件触发后 **30 分钟** 内必须建立故障作战群,值班 SRE 担任协调指挥(IC)。

---

## 2. Pod 频繁重启排查

排查顺序:

1. 查看 Pod 事件:`kubectl describe pod <name>`,确认退出原因
2. **OOMKilled**:检查容器 memory limit,对比实际用量;Java 应用要把 limit 设置为堆大小的 **1.5 倍**,留出 DirectByteBuffer / Metaspace 空间
3. **CrashLoopBackOff**:看上一容器日志 `kubectl logs <pod> --previous`
4. 健康检查失败:核对 liveness / readiness 探针的 path、timeout
5. 节点驱逐:`kubectl get events -n <ns>` 看是否有 NodeNotReady

K8s 节点 OOM 的常见根因是 **JVM 堆外内存泄漏**,需调整 `-XX:MaxDirectMemorySize`。

---

## 3. MySQL 主从同步延迟

延迟超过 **30 秒** 视为严重,处置步骤:

1. 检查主库 binlog 同步状态:`SHOW MASTER STATUS;`
2. 检查从库 IO 与 SQL 线程:`SHOW SLAVE STATUS\G`
3. 主库磁盘 IOPS 是否打满(典型阈值 80%)
4. 大事务排查:`SELECT * FROM information_schema.innodb_trx;`
5. 必要时启动备库切换,但应用连接池要主动 refresh,否则会握住旧主写入造成 split-brain

**2026-02 数据库主从切换故障复盘**:主库 IOPS 打满 → binlog 同步延迟 → 自动切换 → 应用连接池未刷新 → 30 分钟双写。

---

## 4. Redis 集群脑裂

脑裂根因通常是 **机房间网络分区** + Sentinel 误判。修复策略:

- `sentinel down-after-milliseconds` 调整为 **30000**(30s),避免短暂抖动触发切换
- 启用 `min-replicas-to-write 1`,防止脑裂期间写入丢失
- 跨机房网络监控告警,丢包率 > 10% 时预警
- Sentinel 副本至少跨 3 个机房部署

---

## 5. JVM Full GC 频繁

常见原因:

1. **堆内存设置过小**:`-Xmx` 不足导致老年代频繁回收
2. **大对象直接进入老年代**:`-XX:PretenureSizeThreshold` 设置过低
3. 连接池泄漏:Hikari / Druid 连接未归还
4. 缓存炸库:本地缓存 LRU 配置过大

诊断工具:

- `jstat -gcutil <pid> 1000` 看 GC 频率
- `jmap -dump:format=b,file=heap.bin <pid>` 抓堆快照
- 用 MAT 或 jhat 分析支配树

---

## 6. 告警处置规范

值班 SRE 接警后必须在 **5 分钟内确认**(ACK),否则告警自动升级到二线。

告警分类:

- **基础设施层**:K8s 节点 NotReady、磁盘 > 85%、CPU 5min 持续 > 80%
- **应用层**:HTTP 5xx 率 > 1%、P99 延迟 > 2s、错误率突增 200%
- **业务层**:订单成功率 < 99%、支付失败率 > 0.5%

**告警噪音治理**:连续 7 天命中 > 50 次但无人响应的告警必须重新评估阈值,或合并到聚合告警。

---

## 7. 容量管理

HPA 自动扩容触发条件:CPU 持续 5 分钟 > 80%,扩容上限为当前副本数的 **3 倍**。

HPA 未生效常见原因:

1. Metrics Server 未安装或异常
2. 资源 requests 未设置
3. minReplicas / maxReplicas 配置错误
4. Custom Metrics Adapter 数据中断

容量规划季度复审:大促前 30 天压测,扩容预案要包含 DB 慢查询应急、连接池上调、限流降级开关位置。

---

## 8. 灾备切换演练

季度演练流程:

1. 提前 7 天发送演练通知,确认所有相关方就绪
2. T-1 小时:确认备机健康状态、主从数据延迟 < 1s
3. T 时刻:通过 DNS / SLB 切换流量到备站
4. 验证核心业务功能(下单、支付、查询)各跑 3 次
5. 持续观察 30 分钟,业务指标稳定后回切
6. 演练完成后 3 个工作日内出具报告

历史问题:回切流量后 **CDN 缓存未清理**,导致部分用户访问到旧静态资源,后续要求回切前先清 CDN。

---

## 9. 值班交接

每日 09:00 / 21:00 交接,内容必含:

1. 当前未关闭告警逐条交接(含进展、责任人、ETA)
2. 正在执行的变更:状态、回滚方案、可联系人
3. 即将到来的发布:窗口、相关团队
4. 已知风险:证书到期、容量预警、依赖方维护
5. 双方在交接记录上签字,保留 30 天

---

## 10. 故障复盘要求

P1 / P2 故障必须在 **5 个工作日** 内完成复盘,产出:

- 时间线:故障发生 → 发现 → 定位 → 修复 → 验证
- 根因分析(Five Whys)
- 应急响应评估:发现时延、决策时延、修复时延
- 改进项:技术债、流程优化、监控盲区
- Action Item 必须有 owner 和 deadline,未关闭项进季度回顾

复盘禁止 blame,重点放在系统性问题。

---

## 附录 A:常用命令速查

```bash
# K8s Pod 排错
kubectl describe pod <name> -n <ns>
kubectl logs <pod> --previous --tail=200
kubectl top pod -n <ns> --sort-by=memory

# 节点排错
kubectl describe node <node>
kubectl get events --sort-by='.lastTimestamp' -n <ns>

# 数据库慢查询
SELECT * FROM information_schema.innodb_trx
  WHERE TIME_TO_SEC(TIMEDIFF(NOW(), trx_started)) > 30;
```

---

## 附录 B:联系人

- 值班 SRE 一线:hotline-l1@example.com / 微信群 "SRE-On-Call"
- 二线协调:hotline-l2@example.com
- DBA:dba-oncall@example.com
- 网络:network-oncall@example.com
- CTO 升级线:cto-escalation@example.com

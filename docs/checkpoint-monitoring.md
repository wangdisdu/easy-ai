# Checkpoint 运行态监控

> P0-1 长会话上线后给运维定期手跑，关注 `lg_checkpoint.*` 表的健康度。
> 都是只读 SELECT，对线上无影响。

## 1. 总览：表大小与行数

```sql
-- 各 checkpoint 表的总行数 + 占用空间
SELECT
  schemaname || '.' || relname AS table_name,
  n_live_tup AS row_count,
  pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
  pg_size_pretty(pg_relation_size(relid)) AS table_size,
  pg_size_pretty(pg_indexes_size(relid)) AS index_size
FROM pg_stat_user_tables
WHERE schemaname = 'lg_checkpoint'
ORDER BY pg_total_relation_size(relid) DESC;
```

**关注阈值**（按经验）：
- `checkpoints` 单表超 1 GB → 该排查长 thread 占用
- `checkpoint_blobs` 单表超 5 GB → state.messages 累积失控

## 2. Top 10 最大 thread

```sql
-- 按 checkpoint 行数排序，找最长尾的会话
SELECT
  thread_id,
  count(*) AS checkpoint_count,
  pg_size_pretty(sum(pg_column_size(checkpoint))) AS state_total_bytes,
  max(pg_column_size(checkpoint)) AS biggest_state_bytes,
  to_timestamp(min((metadata->>'ts')::bigint) / 1000) AS first_ts,
  to_timestamp(max((metadata->>'ts')::bigint) / 1000) AS last_ts
FROM lg_checkpoint.checkpoints
GROUP BY thread_id
ORDER BY sum(pg_column_size(checkpoint)) DESC
LIMIT 10;
```

**告警规则建议**：
- 单 thread 总 state 字节 > 50 MB → 强烈建议手工 reset 或调小 `max_input_tokens` 让摘要更早触发
- 单 checkpoint 行 > 10 MB → 单次写入很重，影响延迟

## 3. Purge 健康度

```sql
-- 总会话数 vs 已 purge 数
SELECT checkpoint_status, count(*)
FROM tb_conversation
WHERE thread_id IS NOT NULL
GROUP BY checkpoint_status
ORDER BY checkpoint_status;
```

```sql
-- 最近 7 天 purge 触发情况
SELECT
  to_timestamp(create_time / 1000)::date AS day,
  count(*) AS purged_count
FROM tb_session_audit
WHERE event_type = 'checkpoint_purged'
  AND create_time > (extract(epoch from now()) - 7 * 86400) * 1000
GROUP BY day
ORDER BY day DESC;
```

```sql
-- 最老的 active checkpoint：验证 purge 真生效（应不超过 ttl_days）
SELECT
  thread_id,
  to_timestamp(min((metadata->>'ts')::bigint) / 1000) AS oldest_state,
  now() - to_timestamp(min((metadata->>'ts')::bigint) / 1000) AS age
FROM lg_checkpoint.checkpoints
WHERE thread_id IN (
  SELECT thread_id FROM tb_conversation
  WHERE checkpoint_status = 'active' AND thread_id IS NOT NULL
)
GROUP BY thread_id
ORDER BY oldest_state ASC
LIMIT 5;
```

## 4. Summarization 触发率

DeepAgents 的 `_summarization_event` 直接序列化在 `checkpoint` 字段里（bytea），SQL 里查不出"哪些 thread 触发过摘要"——靠 audit 看不到，因为压缩是 LangGraph 内部行为，不进 `tb_session_audit`。

最可靠路径是看 backend 日志（`logger.info` 那一系列 `[stream] chat_model_*` 配合 elapsed 异常），或：

```sql
-- 间接信号：state 字节大但 messages 多的 thread，说明压缩可能没触发
SELECT
  thread_id,
  pg_column_size(checkpoint) AS state_bytes,
  to_timestamp((metadata->>'ts')::bigint / 1000) AS ts
FROM lg_checkpoint.checkpoints c1
WHERE checkpoint_id = (
  SELECT checkpoint_id FROM lg_checkpoint.checkpoints c2
  WHERE c2.thread_id = c1.thread_id
  ORDER BY checkpoint_id DESC LIMIT 1
)
ORDER BY pg_column_size(checkpoint) DESC
LIMIT 10;
```

跨阈值（如 5 MB 以上）但没在 backend log 里看到对应摘要 elapsed 的 thread，需要排查模型 `max_input_tokens` 配置或 SummarizationMiddleware 行为。

## 5. 降级会话比例

```sql
-- checkpoint 缺失重建的会话占比（degraded 状态）
SELECT
  checkpoint_status,
  count(*) AS conv_count,
  round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM tb_conversation
WHERE thread_id IS NOT NULL
GROUP BY checkpoint_status;
```

`degraded` 占比突然升高 → checkpoint 损坏 / 误清理 / saver 异常。

```sql
-- 最近 24h 降级事件
SELECT
  to_timestamp(create_time / 1000) AS at,
  conversation_id,
  payload
FROM tb_session_audit
WHERE event_type = 'checkpoint_rebuilt_from_messages'
  AND create_time > (extract(epoch from now()) - 86400) * 1000
ORDER BY create_time DESC;
```

## 6. 异常 thread 排查模板

定位某个具体 thread 出问题时：

```sql
-- 1. 业务侧基本信息
SELECT id, user_id, app_id, status, checkpoint_status, thread_id,
       to_timestamp(create_time / 1000), to_timestamp(update_time / 1000)
FROM tb_conversation WHERE thread_id = '<THREAD>';

-- 2. checkpoint 链
SELECT checkpoint_id, parent_checkpoint_id,
       pg_column_size(checkpoint) AS bytes,
       (metadata->>'source')
FROM lg_checkpoint.checkpoints
WHERE thread_id = '<THREAD>'
ORDER BY checkpoint_id DESC LIMIT 20;

-- 3. 该会话的所有 audit 事件
SELECT event_type, payload, to_timestamp(create_time / 1000) AS at
FROM tb_session_audit
WHERE conversation_id = (SELECT id FROM tb_conversation WHERE thread_id = '<THREAD>')
ORDER BY create_time DESC;
```

## 何时跑

| 频次 | 跑哪几节 |
|---|---|
| 每天 | §1 总览、§3 purge 健康度 |
| 每周 | §2 top 10、§5 降级比例 |
| 异常排查 | §6 模板 |

## 后续可补的指标（暂不做）

- Prometheus exporter 把 §1/§3 指标自动采集
- Grafana 大盘
- 单 thread 字节数告警自动推送

P0-1 阶段先靠手工 SQL 即可。

# 重构版本与原实现对比文档

本文档逐步对比重构版本（`AlgorithmEngine.run`）与原实现（`LLMService.run_task`）的处理流程。

**对比范围**：除数据获取、保存外的实现方法

---

## 1. 线程池架构对比

| 特性 | 原实现 | 重构版本 | 是否一致 |
|------|--------|----------|----------|
| 线程池 | `ThreadPoolExecutor(max_workers=200)` | 复用原实现的 `executor` | ✅ |
| 任务提交 | `executor.submit(run_task_cache)` | `executor.submit(run_task_cache)` | ✅ |
| 数据缓冲 | `chunk_list.append(chunk)` | `chunk_list.append(sse_data)` | ✅ |
| 轮询机制 | `while self.is_running()` + `pop(0)` | `while is_running()` + `pop(0)` | ✅ |
| 超时等待 | `concurrent.futures.wait([future], 0.5)` | `concurrent.futures.wait([future], 0.5)` | ✅ |
| 数据库会话 | `session_maker()` 创建独立会话 | `session_maker()` 创建独立会话 | ✅ |
| 会话清理 | `session_maker.remove()` | `session_maker.remove()` | ✅ |

---

## 2. SSE 事件输出顺序对比

### 2.1 主流程 (in_chat=True)

| 步骤 | 原实现事件 | 重构版本事件 | 是否一致 |
|------|-----------|-------------|----------|
| 1 | `{type: 'id', id: record_id}` | `{type: 'id', id: record_id}` | ✅ |
| 2 | `{type: 'regenerate_record_id', ...}` (可选) | `{type: 'regenerate_record_id', ...}` (可选) | ✅ |
| 3 | `{type: 'question', question: ...}` | `{type: 'question', question: ...}` | ✅ |
| 4 | `{type: 'datasource-result', content: ...}` (可选) | 暂未实现动态选择数据源 | ⚠️ |
| 5 | `{type: 'datasource', id: ..., name: ...}` (可选) | 暂未实现 | ⚠️ |
| 6 | `{content: ..., type: 'sql-result'}` (流式) | `{content: ..., type: 'sql-result'}` (流式) | ✅ |
| 7 | `{type: 'info', msg: 'sql generated'}` | `{type: 'info', msg: 'sql generated'}` | ✅ |
| 8 | `{type: 'brief', brief: ...}` (可选) | `{type: 'brief', brief: ...}` (可选) | ✅ |
| 9 | `{content: format_sql, type: 'sql'}` | `{content: format_sql, type: 'sql'}` | ✅ |
| 10 | `{content: 'execute-success', type: 'sql-data'}` | `{content: 'execute-success', type: 'sql-data'}` | ✅ |
| 11 | `{content: ..., type: 'chart-result'}` (流式) | `{content: ..., type: 'chart-result'}` (流式) | ✅ |
| 12 | `{type: 'info', msg: 'chart generated'}` | `{type: 'info', msg: 'chart generated'}` | ✅ |
| 13 | `{content: chart_json, type: 'chart'}` | `{content: chart_json, type: 'chart'}` | ✅ |
| 14 | `{type: 'finish'}` | `{type: 'finish'}` | ✅ |

---

## 3. 核心处理步骤对比

### 3.1 数据源处理

| 特性 | 原实现 (LLMService) | 重构版本 (AlgorithmEngine) | 是否一致 |
|------|---------------------|---------------------------|----------|
| 数据源来源 | `self.ds` (构造时设置) | `self._get_datasource()` | ✅ |
| 连接测试 | `check_connection(ds=self.ds)` | `check_connection(ds=ds)` | ✅ |
| 动态选择 | `self.select_datasource()` | 暂未完整实现 | ⚠️ |

### 3.2 SQL 生成

| 特性 | 原实现 | 重构版本 | 是否一致 |
|------|--------|----------|----------|
| LLM 调用 | `self.generate_sql()` | `self._generate_sql()` | ✅ |
| 流式输出 | `yield 'data:' + orjson.dumps({...})` | `yield StreamEvent(type='sql-result', ...)` | ✅ |
| 图表类型提取 | `self.get_chart_type_from_sql_answer()` | `self._get_chart_type_from_sql_answer()` | ✅ |
| 标题提取 | `self.get_brief_from_sql_answer()` | `self._get_brief_from_sql_answer()` | ✅ |
| SQL 格式化 | `sqlparse.format(sql, reindent=True)` | `self._format_sql(sql)` (内部调用 sqlparse) | ✅ |

### 3.3 行权限过滤

| 特性 | 原实现 | 重构版本 | 是否一致 |
|------|--------|----------|----------|
| 用户检查 | `is_normal_user(self.current_user)` | `self._is_normal_user()` | ✅ |
| SQL 过滤 | `self.generate_filter()` | `self._generate_filter()` | ✅ |
| SQL 解析保存 | `self.check_save_sql()` | `self._check_save_sql()` | ✅ |

### 3.4 SQL 执行

| 特性 | 原实现 | 重构版本 | 是否一致 |
|------|--------|----------|----------|
| 执行方法 | `self.execute_sql(sql)` | `self._execute_sql(sql)` | ✅ |
| 大数据处理 | `DataFormat.convert_large_numbers_in_object_array()` | `DataFormat.convert_large_numbers_in_object_array()` | ✅ |
| 结果限制 | 无默认限制 | `limit=1000` (context.enable_query_limit) | ⚠️ 新增 |

### 3.5 图表生成

| 特性 | 原实现 | 重构版本 | 是否一致 |
|------|--------|----------|----------|
| LLM 调用 | `self.generate_chart()` | `self._generate_chart()` | ✅ |
| 流式输出 | `yield 'data:' + orjson.dumps({...})` | `yield StreamEvent(type='chart-result', ...)` | ✅ |
| 图表解析 | `self.check_save_chart()` | `self._parse_chart_config()` | ✅ |

### 3.6 finish_step 控制

| 步骤值 | 原实现行为 | 重构版本行为 | 是否一致 |
|--------|-----------|-------------|----------|
| GENERATE_SQL | 生成 SQL 后停止 | 生成 SQL 后停止 | ✅ |
| QUERY_DATA | 执行 SQL 后停止 | 执行 SQL 后停止 | ✅ |
| GENERATE_CHART | 生成图表后停止 | 生成图表后停止 | ✅ |

---

## 4. 错误处理对比

| 错误类型 | 原实现处理 | 重构版本处理 | 是否一致 |
|----------|-----------|-------------|----------|
| 连接失败 | `SQLBotDBConnectionError` | `SQLBotDBConnectionError` | ✅ |
| SQL 执行失败 | `SQLBotDBError` | `SQLBotDBError` | ✅ |
| 一般错误 | `{message, traceback}` JSON | `{message, traceback}` JSON | ✅ |
| 单消息错误 | `SingleMessageError` | `SingleMessageError` | ✅ |

---

## 5. SSE 数据格式对比

### 5.1 原实现格式
```python
'data:' + orjson.dumps({'content': ..., 'type': '...'}).decode() + '\n\n'
```

### 5.2 重构版本格式
```python
# BusinessDBService.process() yield 字典
sse_data = {'content': ..., 'type': '...'}
# stream_sql_new 转换为 SSE 格式
f"data: {orjson.dumps(event_data).decode()}\n\n"
```

**对比结果**：✅ 最终输出格式一致

---

## 6. 差异点总结

### 6.1 完全一致的部分 ✅

1. **线程池架构**：使用相同的 `executor.submit` + `chunk_list` + `await_result` 模式
2. **SSE 事件顺序**：主要事件的输出顺序完全一致
3. **LLM 调用流程**：SQL 生成、图表生成的 LLM 调用方式一致
4. **错误处理**：错误类型和格式化方式一致
5. **finish_step 控制**：步骤控制逻辑完全一致

### 6.2 存在差异的部分 ⚠️

| 差异点 | 原实现 | 重构版本 | 影响 |
|--------|--------|----------|------|
| 动态数据源选择 | 完整实现 | 暂未实现 | 低（页面场景不涉及） |
| 查询结果限制 | 无默认限制 | 1000 行限制 | 低（可配置） |
| 推荐问题生成 | 集成在主流程 | 独立 API | 无（已按原设计独立） |

### 6.3 架构改进 ✨

| 改进点 | 说明 |
|--------|------|
| 数据层分离 | 业务数据查询前置到 preprocess |
| 结果统一保存 | 通过 postprocess 批量保存 |
| 上下文传递 | 使用 AlgorithmContext 统一传递 |
| 日志追踪 | 添加 SSEDebugLogUtil 便于调试 |

---

## 7. 测试检查清单

- [ ] 新建会话后推荐问题能正常生成
- [ ] 提问后 SSE 事件按顺序到达前端
- [ ] 前端能正确显示 SQL 生成过程
- [ ] 前端能正确显示图表
- [ ] finish 事件后前端退出"思考中"状态
- [ ] 重新生成功能正常
- [ ] 错误场景能正确显示错误信息

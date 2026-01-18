# 数据库层重构计划

> **For Claude:** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 逐任务实施此计划。

**目标：** 将业务数据库访问从算法处理流程中分离，实现业务数据层 (`business_db`) 和算法层 (`algorithm`) 的解耦，修复推荐问题无法返回前端的 bug。

**架构概述：**
- 业务数据层 (`backend/apps/business_db/`): 负责从业务数据库预加载所有必要数据，保存算法执行结果
- 算法层 (`backend/apps/algorithm/`): 接收预加载的上下文，仅访问目标数据库和本地模板文件，不再查询业务数据库
- 保留原始线程池架构，确保 SSE 流式输出兼容性

**技术栈：** Python 3.11, FastAPI, SQLModel, SQLAlchemy, LangChain

---

## 一、Bug 修复：推荐问题无法返回前端

### 问题描述
原始实现可以正常显示推荐问题，重构版本中前端一直卡在"思考中"状态，重启服务或新建会话后才显示结果。

### 根因分析

**问题位置:** `backend/apps/algorithm/engine.py:1283` 的 `run_recommend_questions` 方法

**问题代码:**
```python
def run_recommend_questions(...):
    try:
        # ... 生成事件 ...
    except Exception as e:
        # ...
    finally:
        session_maker.remove()  # ❌ 问题所在：在 generator 未完全消费时就关闭 session
    return self._result
```

**问题分析:**
1. `process_recommend_questions` 调用 `engine.run_recommend_questions()` 创建 generator
2. generator 刚创建就执行 finally 块，调用 `session_maker.remove()` 关闭 session
3. 但此时 API 路由 (`chat.py:279`) 还在尝试消费 generator 读取事件
4. session 已关闭导致后续操作失败，generator 无法继续 yield 事件
5. 前端收不到 `finish` 事件，一直等待

### 修复方案

**文件:** `backend/apps/algorithm/engine.py`

**步骤 1: 移除 finally 块中的 session_maker.remove()**

```python
# 修改前 (line 1274-1283)
except Exception as e:
    traceback.print_exc()
    error_msg = orjson.dumps({
        'message': str(e),
        'type': 'error'
    }).decode()
    yield StreamEvent(type="error", data={"content": error_msg})
    self._result.error = error_msg

finally:
    session_maker.remove()  # 删除此行

return self._result
```

**步骤 2: 确保 session 在 API 层关闭**

`backend/apps/chat/api/chat.py` 的 `ask_recommend_questions` 函数需要在消费完 generator 后关闭 session。

---

## 二、架构符合性检查

### 已实现部分 ✅

| 组件 | 状态 | 说明 |
|------|------|------|
| `business_db/service.py` | ✅ | 实现 `preprocess()` 预加载数据，`postprocess()` 保存结果 |
| `business_db/context.py` | ✅ | 定义 `AlgorithmContext` 数据传输对象 |
| `business_db/result.py` | ✅ | 定义 `AlgorithmResult` 结果对象 |
| `business_db/repository.py` | ✅ | 实现各实体的仓储类 |
| `algorithm/engine.py` | ✅ | 实现 `AlgorithmEngine`，从 context 读取数据 |
| `stream_sql_new` | ✅ | 在 `chat.py` 中使用线程池架构调用 business_db |

### 待修复/完善部分 ⚠️

| 问题 | 位置 | 严重程度 |
|------|------|----------|
| `run_recommend_questions` 中过早调用 `session_maker.remove()` | `algorithm/engine.py:1283` | 🔴 高 |
| `process_recommend_questions` session 管理 | `business_db/service.py` | 🔴 高 |
| 推荐问题事件格式不一致 | `business_db/service.py:974-976` | 🟡 中 |
| 缺少 `finish` 事件 | `business_db/service.py:982` | 🟡 中 |

---

## 三、详细任务清单

### Task 1: 修复 algorithm engine 的 session 管理

**文件:**
- 修改: `backend/apps/algorithm/engine.py:1274-1283`

**Step 1: 移除 finally 块中的 session_maker.remove()**

```python
# 修改 run_recommend_questions 方法，删除 finally 块中的 session_maker.remove()
```

**Step 2: 验证修改**

运行测试确保 generator 可以正常消费所有事件。

---

### Task 2: 修复 business_db service 的 session 管理

**文件:**
- 修改: `backend/apps/business_db/service.py:902-996`

**Step 1: 修改 process_recommend_questions 方法**

在方法末尾添加 `session_maker.remove()` 调用，确保在所有事件被消费后才关闭 session：

```python
def process_recommend_questions(self, ...):
    # ... 现有代码 ...
    try:
        engine = AlgorithmEngine(context, self.session)
        for event in engine.run_recommend_questions(articles_number=articles_number):
            # ... 处理事件 ...

        # 在所有事件被消费后，保存推荐问题
        if result and result.recommended_question_answer:
            self._update_record_field(...)
            self.session.commit()

    finally:
        # 确保 session 在所有操作完成后关闭
        from apps.chat.task.llm import session_maker
        session_maker.remove()

    return result if result else engine.get_result()
```

**Step 2: 验证修复**

启动服务，测试推荐问题功能是否正常工作。

---

### Task 3: 统一事件格式

**文件:**
- 修改: `backend/apps/business_db/service.py:969-991`

**Step 1: 检查事件格式**

确保 `process_recommend_questions` 中所有事件格式与 `process` 方法一致。

**Step 2: 添加 finish 事件**

确保在推荐问题生成完成后 yield `finish` 事件：

```python
# 在循环结束后
yield {'type': 'finish'}
```

---

### Task 4: 验证主流程（问数功能）

**文件:**
- 测试: `backend/apps/chat/api/chat.py`

**Step 1: 测试新建会话流程**

1. 调用 `POST /chat/start` 创建会话
2. 调用 `POST /chat/question` 输入问题
3. 验证 SSE 事件流正常返回

**Step 2: 验证推荐问题生成**

1. 在新建会话后验证推荐问题显示
2. 检查前端是否正确渲染

---

### Task 5: 对比测试（原始 vs 重构）

**目标:** 确保重构版本与原实现功能一致

**测试场景:**
1. ✅ 新建会话
2. ✅ 输入问题生成 SQL
3. ✅ 执行 SQL 获取数据
4. ✅ 生成图表
5. ✅ 推荐问题生成
6. ✅ 重新生成
7. ✅ 错误处理

---

## 四、测试命令

```bash
# 启动后端服务
cd backend
uv run fastapi dev main.py

# 测试推荐问题 API
curl -X POST "http://localhost:8000/api/v1/chat/recommend_questions/{record_id}" \
  -H "Content-Type: text/event-stream"

# 测试问数 API
curl -X POST "http://localhost:8000/api/v1/chat/question" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": 1, "question": "请统计销售额"}'
```

---

## 五、风险点

1. **Session 生命周期**: 重构后 session 管理更复杂，需要确保在正确的时机关闭
2. **事件格式兼容性**: 前端对 SSE 事件格式有严格要求，需要保持一致
3. **异步执行**: 线程池中的异步操作可能导致竞态条件

---

## 六、后续优化（不在第一版本范围内）

1. 移除对 `apps.chat.task.llm` 的依赖，使用独立的 session_maker
2. 添加单元测试覆盖 business_db 和 algorithm 层
3. 优化错误处理和日志记录
4. 支持更多数据源类型

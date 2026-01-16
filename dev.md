# SQLBot 业务数据层重构开发日志

## 概述

本文档记录了 SQLBot 项目业务数据层重构的开发计划和实现方法。

**重构目标**：将业务数据库访问从算法处理流程中解耦，实现"预处理-算法执行-后处理"的三阶段架构。

## 术语定义

- **业务数据库**：存储聊天记录、用户配置、数据源配置等业务数据的 PostgreSQL 数据库
- **目标数据库**：用户配置的用于执行 SQL 查询的数据源（如 MySQL、PostgreSQL 等）
- **本地模板**：存储在 `backend/templates` 目录下的提示词模板文件

## 原始架构分析

### 数据流

```
前端 → 后端 → 算法处理（过程中多次查询业务数据库）→ 保存结果
```

### 问题

1. 业务逻辑与数据库访问紧密耦合
2. 难以测试和调试算法逻辑
3. 无法批量操作数据库
4. 每次算法执行都会产生多次数据库连接

## 新架构设计

### 数据流

```
前端 → 后端 → BusinessDBService.preprocess() [一次性加载所有业务数据]
         → AlgorithmEngine.run() [只访问目标数据库和本地模板]
         → BusinessDBService.postprocess() [批量保存结果]
```

### 核心原则

1. **预处理阶段**：在算法执行前，从业务数据库一次性加载所有必要数据
2. **算法执行阶段**：
   - 不再访问业务数据库
   - 只访问目标数据库（执行 SQL）
   - 只从本地读取提示词模板
3. **后处理阶段**：在算法结束后，批量保存所有结果

## 模块结构

```
backend/apps/
├── business_db/                    # 业务数据层（新增）
│   ├── __init__.py                 # 模块导出
│   ├── context.py                  # AlgorithmContext DTO
│   ├── result.py                   # AlgorithmResult DTO
│   ├── repository.py               # 仓储类（数据访问）
│   └── service.py                  # BusinessDBService
│
├── algorithm/                      # 算法层（新增）
│   ├── __init__.py                 # 模块导出
│   └── engine.py                   # AlgorithmEngine
│
└── chat/
    ├── api/
    │   └── chat.py                 # 修改：支持新旧架构切换
    ├── task/
    │   └── llm.py                  # 保留：兼容模式入口
    └── curd/
        └── chat.py                 # 保留：兼容模式使用
```

## 详细流程

### 1. 用户新建会话

**接口**：`POST /api/v1/chat/start`

**流程**：
1. 前端发送创建会话请求
2. 后端创建 Chat 记录（保持原结构）
3. 返回会话 ID

**代码位置**：`backend/apps/chat/api/chat.py:start_chat`

```python
@router.post("/start", response_model=ChatInfo)
async def start_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat):
    return create_chat(session, current_user, create_chat_obj)
```

### 2. 用户输入问题

**接口**：`POST /api/v1/chat/question`

**流程**：
1. 前端发送问题请求（包含 chat_id 和 question）
2. API 层接收请求，调用 `stream_sql()`
3. `stream_sql()` 根据 `USE_NEW_ALGORITHM` 配置判断
4. 新架构：调用 `stream_sql_new()` → `BusinessDBService.process()`
5. 原架构：调用原有 `stream_sql()` 实现

**代码位置**：`backend/apps/chat/api/chat.py:stream_sql`

### 3. 业务数据层主入口

**类**：`BusinessDBService`

**方法**：`process()`

**这是业务数据层的主入口方法，负责协调整个处理流程：**

```
┌─────────────────────────────────────────────────────────────────┐
│  BusinessDBService.process()                                    │
│  ========================                                       │
│  1. 判断 USE_NEW_ALGORITHM 配置                                  │
│     - 若禁用：返回 None，由原架构处理                             │
│     - 若启用：继续执行                                           │
│                                                                 │
│  2. 调用 preprocess() - 预处理                                   │
│     - 加载所有业务数据                                           │
│                                                                 │
│  3. 创建聊天记录                                                 │
│                                                                 │
│  4. 调用 AlgorithmEngine.run() - 算法处理                        │
│     - 生成 SQL                                                  │
│     - 执行 SQL（目标数据库）                                     │
│     - 生成图表                                                  │
│                                                                 │
│  5. 调用 postprocess() - 后处理                                  │
│     - 批量保存结果                                              │
└─────────────────────────────────────────────────────────────────┘
```

**代码位置**：`backend/apps/business_db/service.py:BusinessDBService.process`

### 4. 业务数据层构建业务数据

**方法**：`preprocess()`

**功能**：一次性加载所有业务数据

| 数据项 | 来源表 | 说明 |
|--------|--------|------|
| 聊天会话 | `chat` | 获取会话信息 |
| 专业术语 | `terminology` | 格式化后的术语模板 |
| 训练数据 | `data_training` | 格式化后的训练模板 |
| 自定义提示词 | `custom_prompt` | 自定义提示词内容 |
| 聊天历史 | `chat_log` | 历史消息记录 |
| 数据源配置 | `core_datasource` | 目标数据库连接信息 |
| 表结构 | `core_table/core_field` | Schema 信息（支持 embedding） |
| AI 模型配置 | `ai_model_detail` | LLM 配置 |

**代码位置**：`backend/apps/business_db/service.py:BusinessDBService.preprocess`

### 5. 算法处理

**类**：`AlgorithmEngine`

**方法**：`run()`

**流程**：
1. 返回 record_id
2. 获取数据源连接
3. 测试连接
4. 生成 SQL（调用 LLM，从本地模板读取提示词）
5. 执行 SQL（访问目标数据库）
6. 生成图表（调用 LLM，从本地模板读取提示词）
7. 返回结果

**只访问**：
- 目标数据库（执行 SQL）
- 本地模板文件（`backend/templates`）

**不访问**：
- 业务数据库（所有数据已预加载）

**代码位置**：`backend/apps/algorithm/engine.py:AlgorithmEngine.run`

### 6. 结果返回与保存

**流式事件类型**：
| 事件类型 | 说明 |
|----------|------|
| `id` | 记录 ID |
| `question` | 问题内容 |
| `sql-result` | SQL 生成过程（流式） |
| `brief` | 标题 |
| `sql` | 格式化后的 SQL |
| `sql-data` | SQL 执行结果 |
| `chart-result` | 图表生成过程（流式） |
| `chart` | 图表配置 |
| `error` | 错误信息 |
| `finish` | 完成 |

**后处理**：`BusinessDBService.postprocess()`

**保存内容**：
| 表 | 字段 | 说明 |
|----|------|------|
| `chat_record` | sql_answer | SQL 答案 |
| `chat_record` | sql | 格式化 SQL |
| `chat_record` | data | 执行数据 |
| `chat_record` | chart_answer | 图表答案 |
| `chat_record` | chart | 图表配置 |
| `chat_record` | error | 错误信息 |
| `chat_record` | finish | 完成标志 |
| `chat` | brief | 标题 |

**代码位置**：`backend/apps/business_db/service.py:BusinessDBService.postprocess`

## 架构特点

### API 层 vs 业务数据层

**API 层**（`backend/apps/chat/api/chat.py`）：
- 只负责 HTTP 接收和响应
- 薄薄的一层，不包含业务逻辑
- 通过配置开关调用不同的实现

**业务数据层**（`backend/apps/business_db/service.py`）：
- 包含所有业务逻辑
- 协调预处理、算法、后处理流程
- 判断是否启用新架构

### 配置开关

```python
# API 层判断配置
if settings.USE_NEW_ALGORITHM:
    return await stream_sql_new(...)
else:
    return await stream_sql(...)  # 原架构
```

```python
# 业务数据层内部判断
def process(self, ...):
    if not settings.USE_NEW_ALGORITHM:
        yield None  # 告诉 API 层使用原架构
        return
    # ... 继续新架构流程
```

## 关键文件清单

### 新建文件

| 文件路径 | 功能说明 |
|----------|----------|
| `backend/apps/business_db/__init__.py` | 模块导出 |
| `backend/apps/business_db/context.py` | AlgorithmContext DTO |
| `backend/apps/business_db/result.py` | AlgorithmResult DTO |
| `backend/apps/business_db/repository.py` | 仓储类（Chat, ChatRecord, ChatLog, Datasource, Terminology, DataTraining, AiModel） |
| `backend/apps/business_db/service.py` | BusinessDBService（预处理 + 后处理） |
| `backend/apps/algorithm/__init__.py` | 模块导出 |
| `backend/apps/algorithm/engine.py` | AlgorithmEngine |

### 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `backend/common/core/config.py` | 添加 `USE_NEW_ALGORITHM` 配置开关 |
| `backend/apps/chat/api/chat.py` | 添加 `stream_sql_new` 函数，修改 `stream_sql` 支持条件切换 |
| `CLAUDE.md` | 添加新架构文档 |

## 配置开关

### 环境变量

```bash
USE_NEW_ALGORITHM=true  # 启用新架构
USE_NEW_ALGORITHM=false # 使用原架构（默认）
```

### 代码配置

```python
# backend/common/core/config.py
class Settings:
    USE_NEW_ALGORITHM: bool = False  # 默认使用原架构
```

## 验证方法

### 1. 功能测试

```bash
# 设置环境变量
export USE_NEW_ALGORITHM=true

# 启动服务
uv run fastapi dev main.py

# 测试流程：
# 1. 创建会话 POST /api/v1/chat/start
# 2. 发送问题 POST /api/v1/chat/question
# 3. 验证返回结果
```

### 2. 对比测试

分别使用 `USE_NEW_ALGORITHM=true` 和 `USE_NEW_ALGORITHM=false`，对比输出结果是否一致。

### 3. 兼容性测试

验证 `USE_NEW_ALGORITHM=false` 时原有功能正常。

## 开发计划

### Phase 1: 创建业务数据层 ✅

- [x] 创建 `business_db/__init__.py`
- [x] 创建 `business_db/context.py` - AlgorithmContext DTO
- [x] 创建 `business_db/result.py` - AlgorithmResult DTO
- [x] 创建 `business_db/repository.py` - 仓储类
- [x] 创建 `business_db/service.py` - BusinessDBService

### Phase 2: 创建算法层 ✅

- [x] 创建 `algorithm/__init__.py`
- [x] 创建 `algorithm/engine.py` - AlgorithmEngine
- [x] 实现 SQL 生成
- [x] 实现 SQL 执行（目标数据库）
- [x] 实现图表生成

### Phase 3: 集成到 API ✅

- [x] 添加 `USE_NEW_ALGORITHM` 配置
- [x] 添加 `stream_sql_new` 函数
- [x] 修改 `stream_sql` 支持条件切换
- [x] 修复 API 层异常处理
- [x] 补充缺少的 info 事件

### Phase 4: 后续优化

- [x] 补充行权限过滤逻辑
- [x] 补充数据源选择逻辑
- [x] 添加单元测试
- [x] 添加集成测试

## 注意事项

1. **向后兼容**：通过 `USE_NEW_ALGORITHM` 配置开关保持向后兼容
2. **流程一致**：重构后算法处理流程与原架构完全一致
3. **输入输出一致**：API 接口的输入输出保持不变
4. **本地模板**：保留从 `backend/templates` 读取提示词模板的功能
5. **目标数据库**：保留对目标数据库的访问和执行功能

## 常见问题

### Q1: 如何启用新架构？

设置环境变量 `USE_NEW_ALGORITHM=true` 然后重启服务。

### Q2: 新架构会破坏原有功能吗？

不会。新架构通过配置开关控制，默认使用原架构。

### Q3: 算法执行过程中可以访问业务数据库吗？

不可以。新架构要求所有业务数据在预处理阶段加载，算法执行过程中不再访问业务数据库。

### Q4: 如何添加新的业务数据查询？

在 `BusinessDBService.preprocess()` 中添加查询逻辑，将结果存入 `AlgorithmContext`。

### Q5: 流式事件格式是否与原架构一致？

是的。新架构保持与原架构完全一致的 SSE 事件格式。

## 参考资料

- 原始实现：`backend/apps/chat/task/llm.py:run_task`
- API 接口：`backend/apps/chat/api/chat.py`
- 配置：`backend/common/core/config.py`
- 模板：`backend/templates/`

---

**更新日期**：2026-01-16
**版本**：1.0

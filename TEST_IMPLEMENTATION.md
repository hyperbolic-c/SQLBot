# SQLBot 重构版本测试实现方案

## 概述

本文档描述如何基于原版功能正常的 Docker image，构建测试 image 以验证重构版本的功能是否与原实现一致。

## 实现流程

### 流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    测试 Docker Image 构建流程                            │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────┐
  │  原版功能正常镜像   │
  │  dataease/sqlbot │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  复制重构代码      │
  │  backend/        │
  │  tests/          │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  安装测试依赖      │
  │  pytest          │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  验证模块导入      │
  │  algorithm/      │
  │  business_db/    │
  └────────┬─────────┘
           │
           ▼
  ┌──────────────────┐
  │  运行单元测试      │
  │  数据模型         │
  │  服务层           │
  │  SSE 输出格式     │
  └──────────────────┘
```

### 详细步骤

#### 步骤 1: 准备原版镜像

```bash
# 拉取原版功能正常的镜像
docker pull dataease/sqlbot:latest

# 验证镜像可以正常运行
docker run --rm dataease/sqlbot:latest echo "原版镜像运行正常"
```

#### 步骤 2: 构建测试镜像

```bash
# 在项目根目录执行
docker build -f Dockerfile.test -t sqlbot:test-refactor .

# 或使用 Docker Compose
docker-compose -f test_docker_compose.yaml build test-refactor
```

#### 步骤 3: 运行测试

```bash
# 方式 1: 直接运行
docker run --rm sqlbot:test-refactor

# 方式 2: 使用 Docker Compose
docker-compose -f test_docker_compose.yaml up test-refactor

# 方式 3: 运行完整测试脚本
docker run --rm \
  -v $(pwd)/test_results:/opt/sqlbot/app/test_results \
  sqlbot:test-refactor \
  bash /opt/sqlbot/app/tests/run_tests.sh
```

#### 步骤 4: 查看测试结果

```bash
# 查看测试日志
cat test_results/test_report.txt

# 查看详细测试输出
docker logs sqlbot-test-refactor
```

## 文件说明

### Dockerfile.test

基于 `dataease/sqlbot:latest` 构建测试镜像:

```dockerfile
# 阶段 1: 基于原版镜像
FROM dataease/sqlbot:latest AS sqlbot-original

# 阶段 2: 复制重构代码
COPY backend/ ${APP_HOME}/

# 阶段 3: 安装测试依赖并运行
RUN uv sync && \
    uv pip install pytest && \
    python -m pytest tests/ -v
```

### test_docker_compose.yaml

定义三种测试服务:

| 服务 | 用途 |
|------|------|
| `test-refactor` | 运行单元测试 |
| `integration-test` | 集成测试 |
| `compare-test` | API 对比测试 |

### run_tests.sh

自动化测试脚本，执行以下步骤:

1. 验证模块导入
2. 运行数据模型测试
3. 运行服务层测试
4. 运行 SSE 输出格式测试
5. 验证与原实现的一致性
6. 生成测试报告

## 测试覆盖范围

### 1. 数据模型测试 (`test_algorithm_schema.py`)

- AlgorithmInput 必需字段测试
- AlgorithmInput 可选字段测试
- 默认值测试
- 历史消息结构测试
- 历史问题结构测试

### 2. 结果模型测试 (`test_algorithm_result.py`)

- AlgorithmResult 必需字段测试
- AlgorithmResult 可选字段测试
- AlgorithmLog 测试
- OperationType 枚举测试

### 3. 服务层测试 (`test_algorithm_service.py`)

- 服务初始化测试
- chunk_list 操作测试
- Future 属性测试
- 方法测试
- 结果属性测试
- 历史消息测试

### 4. SSE 输出格式测试 (`test_stream_output.py`)

- SSE 格式结构测试
- SQL 结果格式测试
- 信息格式测试
- SQL 输出格式测试
- 完成格式测试
- 错误格式测试
- 推荐问题格式测试
- 图表格式测试

## 验证要点

### 与原实现一致的验证

1. **数据结构**: AlgorithmInput、AlgorithmResult 字段与原实现完全一致
2. **方法签名**: sql_user_question 等方法签名与原实现一致
3. **SSE 格式**: 流式输出格式 `data: {...}\n\n` 与原实现一致
4. **处理流程**: AlgorithmService 的 run_task、run_task_async 等方法流程一致

### 需要在完整 Docker 环境中测试的项目

以下测试需要 `/opt/sqlbot` 目录，会在集成测试中覆盖:

- BusinessDataLayer 完整功能测试
- 数据库连接测试
- 端到端 API 测试

## 常见问题

### Q1: 测试失败 "ModuleNotFoundError"

```bash
# 确保在容器内运行
docker run --rm sqlbot:test-refactor python -m pytest tests/ -v
```

### Q2: 导入错误 "sqlbot_xpack"

这是因为 `sqlbot-xpack` 需要在特定环境中安装。测试时跳过需要完整环境的测试:

```bash
docker run --rm -e SKIP_DOCKER_TESTS=true sqlbot:test-refactor \
    python -m pytest tests/ -v -k "not business"
```

### Q3: 如何对比原版和重构版的 API 响应

1. 启动原版服务: `docker-compose up original`
2. 启动重构版服务: `docker-compose up refactor`
3. 使用测试脚本发送相同请求，对比响应

## 扩展测试

### 添加端到端测试

在 `tests/` 目录下添加 `test_e2e.py`:

```python
# test_e2e.py
import pytest
from apps.api import app
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_algorithm_chat_endpoint():
    """测试算法聊天端点"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/algorithm/chat/question",
            json={
                "chat_id": 1,
                "question": "查询销售额",
                "ai_modal_id": 1,
                "datasource_id": 1,
                "engine_type": "PostgreSQL"
            }
        )
        assert response.status_code == 200
```

## CI/CD 集成

在 `.github/workflows/test.yml` 中添加:

```yaml
name: Test Refactored Version

on:
  push:
    branches: [algorithm-refactor-v2]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Test Image
        run: docker build -f Dockerfile.test -t sqlbot:test-refactor .

      - name: Run Tests
        run: docker run --rm sqlbot:test-refactor
```

## 总结

通过本测试方案，可以:

1. **验证功能一致性**: 重构版本与原实现功能完全一致
2. **快速发现问题**: 及时发现重构引入的问题
3. **自动化测试**: 集成到 CI/CD 流程，确保持续质量
4. **渐进式重构**: 为后续版本的重构提供安全保障

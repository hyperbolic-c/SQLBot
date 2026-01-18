# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SQLBot is a ChatBI (Conversational Business Intelligence) system based on LLM (Large Language Model) and RAG (Retrieval-Augmented Generation). It enables natural language to SQL queries against various data sources.

## Development Commands

### Backend (Python/FastAPI)
```bash
cd backend

# Install dependencies (requires Python 3.11)
uv sync

# Run development server
uv run fastapi dev main.py

# Run tests
uv run pytest

# Type checking
uv run mypy .

# Linting
uv run ruff check .
uv run ruff format .

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

### Frontend (Vue 3 + TypeScript)
```bash
cd frontend

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Linting
npm run lint
```

## Architecture

### Backend Structure (`backend/apps/`)
- **db/** - Database connection management, multi-database engine support (MySQL, PostgreSQL, SQL Server, Oracle, etc.)
- **chat/** - Chat functionality, conversation handling
- **core/** - Core business logic for SQL generation and execution
- **datasource/** - Data source connection management
- **system/** - User, workspace, permission, and AI model management
- **template/** - SQL template management
- **terminology/** - Business terminology configuration
- **ai_model/** - LLM integration (OpenAI, LangChain, LangGraph)

### Frontend Structure (`frontend/src/`)
- **views/** - Page components organized by feature (chat, dashboard, ds, system, work)
- **api/** - API client modules
- **stores/** - Pinia state management
- **components/** - Reusable Vue components
- **utils/** - Utility functions

### Common Shared Code (`backend/common/`)
- **core/** - Configuration, security, pagination, caching
- **audit/** - Request auditing
- **utils/** - Shared utilities

### Database Layer
- Uses **SQLModel** (SQLAlchemy + Pydantic) for ORM
- **PostgreSQL** as primary database with **pgvector** for vector embeddings
- **Alembic** for migrations (stored in `backend/alembic/`)
- Embeddings powered by **sentence-transformers** for RAG

## Key Configuration

Environment variables (see `backend/common/core/config.py`):
- `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `SECRET_KEY` - JWT signing key
- `LOG_LEVEL` - Logging level
- `SQL_DEBUG` - Enable SQL debugging
- `EMBEDDING_ENABLED` - Enable RAG embeddings

## Database Models

Core models in `backend/apps/datasource/models/`:
- `Datasource` - Database connection configurations
- `TableSchema`, `ColumnSchema` - Schema metadata
- `ChatConversation`, `ChatMessage` - Chat history

## API Organization

API routes are organized in `backend/apps/api.py`. Each module registers its own routers:
- `/api/v1/chat` - Chat endpoints
- `/api/v1/datasource` - Data source management
- `/api/v1/system` - System management

## dev plan
1. 定义存储聊天记录、用户配置等信息的数据库为业务数据库，用户执行智能问数的数据库为目标数据库。
2. 目前的项目架构中，后端和主要算法处理流程均为python实现，在主要算法处理流程中，算法根据在处理的过程中，多次访问业务数据库查询到所需的信息。主要算法处理流程相应函数为@backend/apps/chat/api/chat.py 中的question_answer、@backend/apps/chat/task/llm.py 中的run_task。必须与原实现中的线程池等方法保持一致。
3. 将项目重构为：1、将业务数据库的访问、查询、保存功能重构为单独的业务数据层，不再耦合在算法处理部分中，业务数据层在主要算法处理流程开始时，就将处理流程中所需要的全部信息一次性传递给算法端，不再在流程中查询。2、定义一个结果返回数据模型，用于在算法过程中存储结果，在任务完成后，
  返回给业务数据层处理，再返回给前端，以实现算法与数据保存的分离。对于流程中间的输出、结果的保存，不再在流程中的步骤保存，而是在处理流程结束后，一次性返回整个流程所需要保存的内容给业务数据层进行保存，因此在算法流程中不能保留业务数据库的session，需要保存的信息通过变量传递到最后再一起保存。3、保留算法部分对目标数据库的访问和执行功能。
4. 第一个版本：先实现业务数据层的重构，保留其他的后端功能不变，保留从本地文件夹@backend/templates 读取提示词模版的功能。业务数据层的实现放在@backend/apps/business_db 文件夹下，重构的算法实现放在@backend/apps/algorithm 文件夹下。
5. 确保重构后问数算法主要处理流程与原架构保持完全一致，不允许改动流程、输入、输出，仅将“从业务数据库中查询信息”修改为“从数据模型中读取”。
6. 确保用户"新建会话"这一步保持原结构的功能，完成"新建会话"后，进入用户"输入问题"步骤，该步骤的数据流由原来的"前端——后端——算法处理（过程中查询业务数据库）"修改为"前端——后端——业务数据层（构建好算法处理流程中所需要的所有数据）——算法处理（不再查询业务数据库。保留对目标数据库的查询、执行，保留从本地读取提示词模板文件内容）"。用户交互响应、算法处理的流程与原实现完全一致，仅将对业务数据库的访问和保存从处理流程中抽离出来，仅在开头和结尾和业务数据层交互一次，取得数据和保存数据。新建会话后的"推荐问题生成"也属于算法部分。
7. 在重构版本中，去除聊天assitant的内容，不考虑其处理情况，聊天来源仅仅考虑"页面"的情况。
8. [bug] 原本推荐问题调用原始实现的时候，能够正常生成并显示到前端；将其修改到重构版本后，无法显示到前端了。在重构版本的当前会话中，算法处理的结果无法返回前端，前端一直卡在“思考中”的状态，当新建另一个会话或重启服务后，该会话才会显示结果。
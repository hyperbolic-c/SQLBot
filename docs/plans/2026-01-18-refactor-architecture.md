# SQLBot 架构重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 将项目从"前端+后端"架构重构为"前端+后端+算法"三层架构，实现业务数据层与算法层的分离。

**架构设计:**
- 业务数据层 (`business_db/`): 负责从业务数据库查询和保存所有数据，在算法开始前一次性传递所有需要的信息
- 算法层 (`algorithm/`): 专注于问数算法处理，不再直接访问业务数据库，仅保留对目标数据库的访问和模板文件读取
- 后端层 (`api/`): 协调业务数据层和算法层，处理前端请求

**技术栈:**
- Python 3.11 + FastAPI
- SQLModel (SQLAlchemy + Pydantic)
- LangChain/LangGraph
- sentence-transformers (RAG embeddings)

---

## 版本一：基础重构

### 目标: 实现业务数据层和算法层的基础架构，修复推荐问题无法返回前端的 bug

**设计决策确认:**
1. **表结构获取时机**: 在 `BusinessDataLayer.prepare_algorithm_input` 中一次性获取 db_schema（包括生成推荐问题时的表结构）
2. **错误处理策略**: 错误信息在业务数据层保存，由后端层统一管理再返回前端
3. **日志保存时机**: 算法日志在算法完成后统一保存，在算法部分增加详细的 debug 日志捕获

---

### 任务 1: 创建算法输入数据模型

**文件:**
- Create: `backend/apps/algorithm/schema.py`
- Modify: `backend/apps/chat/models/chat_model.py` (ChatQuestion 复制到 algorithm)

**Step 1: 创建算法输入模型文件**

```python
# backend/apps/algorithm/schema.py
from typing import Optional, List, Any, Dict
from pydantic import BaseModel
from enum import Enum

class AlgorithmInput(BaseModel):
    """算法层输入数据模型 - 包含算法处理所需的全部信息"""
    # 基础信息
    chat_id: int
    question: str
    chat_record_id: Optional[int] = None  # 用于重新生成
    ai_modal_id: int
    ai_modal_name: str

    # 数据源信息
    datasource_id: int
    engine_type: str
    db_schema: str  # 表结构信息

    # 提示词相关
    terminologies: str  # 术语模板
    data_training: str  # 数据训练模板
    custom_prompt: str  # 自定义提示词
    error_msg: str  # 错误信息

    # 历史记录
    last_sql_messages: List[Dict[str, Any]] = []  # SQL 生成历史消息
    last_chart_messages: List[Dict[str, Any]] = []  # 图表生成历史消息
    old_questions: List[str] = []  # 用户历史问题列表（用于推荐问题生成）

    # 配置
    language: str = '简体中文'
    enable_row_limit: bool = True
    change_title: bool = False

    class Config:
        from_attributes = True
```

**Step 2: 运行测试验证文件创建**

Run: `ls -la backend/apps/algorithm/schema.py`
Expected: 文件存在

**Step 3: 验证模型正确性**

Run: `cd backend && uv run python -c "from apps.algorithm.schema import AlgorithmInput; print('Model imported successfully')"`
Expected: 成功导入，无错误

---

### 任务 2: 创建算法输出数据模型

**文件:**
- Create: `backend/apps/algorithm/result.py`

**Step 1: 创建输出模型**

```python
# backend/apps/algorithm/result.py
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from enum import Enum

class OperationType(str, Enum):
    """操作类型枚举"""
    GENERATE_SQL = "generate_sql"
    GENERATE_CHART = "generate_chart"
    EXECUTE_SQL = "execute_sql"
    CHOOSE_DATASOURCE = "choose_datasource"
    GENERATE_RECOMMENDED_QUESTIONS = "generate_recommended_questions"
    ANALYSIS = "analysis"
    PREDICT_DATA = "predict_data"

class AlgorithmLog(BaseModel):
    """算法日志记录"""
    operation: OperationType
    ai_modal_id: int
    ai_modal_name: str
    full_message: List[Dict[str, Any]]  # 完整的消息历史
    reasoning_content: Optional[str] = None
    token_usage: Dict[str, int] = {}

class AlgorithmResult(BaseModel):
    """算法层输出结果模型 - 包含所有需要保存到业务数据库的内容"""

    # 基础信息
    record_id: int  # ChatRecord ID
    success: bool = True
    error_message: Optional[str] = None

    # SQL 生成结果
    generated_sql: Optional[str] = None
    sql_answer: Optional[str] = None
    tables_used: List[str] = []  # 使用的表

    # SQL 执行结果
    sql_execution_result: Optional[Dict[str, Any]] = None  # {"fields": [...], "data": [...]}

    # 图表生成结果
    chart_config: Optional[Dict[str, Any]] = None
    chart_answer: Optional[str] = None

    # 推荐问题
    recommended_questions: Optional[str] = None

    # 分析/预测结果
    analysis_result: Optional[str] = None
    predict_result: Optional[str] = None
    predict_data: Optional[str] = None

    # 聊天标题
    chat_brief: Optional[str] = None
    brief_generated: bool = False

    # 数据源选择
    selected_datasource_id: Optional[int] = None
    selected_engine_type: Optional[str] = None

    # 日志
    logs: List[AlgorithmLog] = []

    class Config:
        from_attributes = True
```

**Step 2: 验证输出模型**

Run: `cd backend && uv run python -c "from apps.algorithm.result import AlgorithmResult, AlgorithmLog; print('Result model imported successfully')"`
Expected: 成功导入，无错误

---

### 任务 3: 创建业务数据层初始化

**文件:**
- Create: `backend/apps/business_db/__init__.py`
- Create: `backend/apps/business_db/business_db.py`

**Step 1: 创建 `__init__.py`**

```python
# backend/apps/business_db/__init__.py
"""业务数据层 - 负责从业务数据库查询和保存数据"""
from .business_db import BusinessDataLayer

__all__ = ["BusinessDataLayer"]
```

**Step 2: 创建业务数据层主文件**

```python
# backend/apps/business_db/business_db.py
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, select

from apps.chat.models.chat_model import Chat, ChatRecord, RenameChat
from apps.chat.curd.chat import (
    get_chat, get_chat_record_by_id, list_generate_sql_logs,
    list_generate_chart_logs, get_chat_brief_generate,
    get_last_execute_sql_error, get_old_questions, save_question
)
from apps.datasource.models.datasource import CoreDatasource
from apps.terminology.curd.terminology import get_terminology_template
from apps.data_training.curd.data_training import get_training_template
from apps.ai_model.model_factory import LLMConfig, LLMFactory, get_default_config
from apps.system.crud.parameter_manage import get_groups
from common.core.deps import CurrentUser
from apps.algorithm.schema import AlgorithmInput
import orjson


class BusinessDataLayer:
    """业务数据层 - 负责所有业务数据库的查询和保存操作"""

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user

    async def prepare_algorithm_input(
        self,
        chat_id: int,
        question: str,
        regenerate_record_id: Optional[int] = None,
        embedding: bool = False
    ) -> Tuple[AlgorithmInput, ChatRecord]:
        """
        准备算法层所需的输入数据

        Returns:
            Tuple[AlgorithmInput, ChatRecord]: 算法输入和创建的记录
        """
        # 获取 Chat 信息
        chat: Chat = self.session.get(Chat, chat_id)
        if not chat:
            raise Exception(f"Chat with id {chat_id} not found")

        # 获取数据源
        ds: CoreDatasource = self.session.get(CoreDatasource, chat.datasource)
        if not ds:
            raise Exception("No available datasource configuration found")

        # 创建记录
        from apps.chat.models.chat_model import ChatQuestion
        chat_question = ChatQuestion(
            chat_id=chat_id,
            question=question,
            ai_modal_id=0,  # 暂时设为0，后面会更新
            engine=ds.type_name if ds.type_name else ds.type
        )
        record = save_question(
            session=self.session,
            current_user=self.current_user,
            question=chat_question
        )

        # 获取 LLM 配置
        config: LLMConfig = await get_default_config()

        # 获取行数限制配置
        enable_row_limit = True
        chat_params = await get_groups(self.session, "chat")
        for c in chat_params:
            if c.pkey == 'chat.limit_rows':
                if c.pval.lower().strip() == 'true':
                    enable_row_limit = True
                else:
                    enable_row_limit = False

        # 获取历史消息
        chat_id_val = chat_id
        generate_sql_logs = list_generate_sql_logs(session=self.session, chart_id=chat_id_val)
        generate_chart_logs = list_generate_chart_logs(session=self.session, chart_id=chat_id_val)

        # 获取用户历史问题（用于推荐问题生成）
        old_questions = list(map(lambda q: q.strip(), get_old_questions(self.session, ds.id)))

        # 处理重新生成的历史消息
        last_sql_messages = []
        if regenerate_record_id:
            _temp_log = next(
                filter(lambda obj: obj.pid == regenerate_record_id, generate_sql_logs), None
            )
            last_sql_messages = _temp_log.messages if _temp_log else []
        else:
            last_sql_messages = generate_sql_logs[-1].messages if generate_sql_logs else []

        last_chart_messages = generate_chart_logs[-1].messages if generate_chart_logs else []

        # 获取错误信息
        last_execute_sql_error = get_last_execute_sql_error(self.session, chat_id)
        error_msg = f'''<error-msg>
{last_execute_sql_error}
</error-msg>''' if last_execute_sql_error else ''

        # 获取标题生成标记
        change_title = not get_chat_brief_generate(session=self.session, chat_id=chat_id)

        # 构建算法输入
        algorithm_input = AlgorithmInput(
            chat_id=chat_id,
            question=question,
            chat_record_id=record.id,
            ai_modal_id=config.model_id,
            ai_modal_name=config.model_name,
            datasource_id=ds.id,
            engine_type=(ds.type_name if ds.type != 'excel' else 'PostgreSQL'),
            db_schema="",  # 暂不获取表结构，在算法层处理
            terminologies="",
            data_training="",
            custom_prompt="",
            error_msg=error_msg,
            last_sql_messages=last_sql_messages,
            last_chart_messages=last_chart_messages,
            language="简体中文",  # TODO: 从用户配置获取
            enable_row_limit=enable_row_limit,
            change_title=change_title,
            regenerate_record_id=regenerate_record_id,
            old_questions=old_questions
        )

        return algorithm_input, record

    def get_table_schema(self, ds_id: int, question: str, embedding: bool = False) -> str:
        """
        获取数据源表结构信息

        Args:
            ds_id: 数据源 ID
            question: 用户问题
            embedding: 是否使用 embedding

        Returns:
            表结构信息字符串
        """
        from apps.datasource.crud.datasource import get_table_schema
        ds: CoreDatasource = self.session.get(CoreDatasource, ds_id)
        if ds:
            return get_table_schema(
                session=self.session,
                current_user=self.current_user,
                ds=ds,
                question=question,
                embedding=embedding
            )
        return ""

    def get_terminology_template(self, question: str, ds_id: Optional[int] = None) -> str:
        """获取术语模板"""
        ds = self.session.get(CoreDatasource, ds_id) if ds_id else None
        ds_id_val = ds.id if ds else None
        return get_terminology_template(
            self.session, question, self.current_user.oid, ds_id_val
        )

    def get_data_training_template(self, question: str, ds_id: Optional[int] = None) -> str:
        """获取数据训练模板"""
        ds = self.session.get(CoreDatasource, ds_id) if ds_id else None
        ds_id_val = ds.id if ds else None
        return get_training_template(
            self.session, question, self.current_user.oid, ds_id_val
        )

    def save_algorithm_result(self, record_id: int, result: 'AlgorithmResult'):
        """
        保存算法结果到业务数据库

        Args:
            record_id: 记录 ID
            result: 算法结果
        """
        from apps.chat.curd.chat import (
            save_sql, save_sql_answer, save_sql_exec_data,
            save_chart, save_chart_answer, save_recommend_question_answer,
            save_analysis_answer, save_predict_answer, save_predict_data,
            finish_record, rename_chat as rename_chat_db, save_error_message
        )

        # 保存 SQL
        if result.generated_sql:
            save_sql(session=self.session, sql=result.generated_sql, record_id=record_id)

        # 保存 SQL 回答
        if result.sql_answer:
            save_sql_answer(session=self.session, record_id=record_id, answer=result.sql_answer)

        # 保存 SQL 执行结果
        if result.sql_execution_result:
            save_sql_exec_data(
                session=self.session,
                record_id=record_id,
                data=orjson.dumps(result.sql_execution_result).decode()
            )

        # 保存图表
        if result.chart_config:
            save_chart(session=self.session, chart=orjson.dumps(result.chart_config).decode(), record_id=record_id)

        # 保存图表回答
        if result.chart_answer:
            save_chart_answer(session=self.session, record_id=record_id, answer=result.chart_answer)

        # 保存推荐问题
        if result.recommended_questions:
            save_recommend_question_answer(
                session=self.session,
                record_id=record_id,
                answer={'content': result.recommended_questions}
            )

        # 保存分析结果
        if result.analysis_result:
            save_analysis_answer(
                session=self.session,
                record_id=record_id,
                answer=orjson.dumps({'content': result.analysis_result}).decode()
            )

        # 保存预测结果
        if result.predict_result:
            save_predict_answer(
                session=self.session,
                record_id=record_id,
                answer=orjson.dumps({'content': result.predict_result}).decode()
            )

        # 保存预测数据
        if result.predict_data:
            save_predict_data(session=self.session, record_id=record_id, data=result.predict_data)

        # 保存错误信息
        if result.error_message:
            save_error_message(session=self.session, record_id=record_id, message=result.error_message)

        # 更新标题
        if result.chat_brief:
            rename_chat_db(
                session=self.session,
                rename_object=RenameChat(
                    id=result.record_id.chat_id if hasattr(result.record_id, 'chat_id') else 0,
                    brief=result.chat_brief,
                    brief_generate=result.brief_generated
                )
            )

        # 标记完成
        finish_record(session=self.session, record_id=record_id)
```

**Step 3: 验证文件创建**

Run: `ls -la backend/apps/business_db/`
Expected: `__init__.py` 和 `business_db.py` 存在

**Step 4: 验证导入**

Run: `cd backend && uv run python -c "from apps.business_db import BusinessDataLayer; print('BusinessDataLayer imported successfully')"`
Expected: 成功导入，无错误

---

### 任务 4: 创建算法层核心服务

**文件:**
- Create: `backend/apps/algorithm/service.py`

**Step 1: 创建算法服务**

```python
# backend/apps/algorithm/service.py
import traceback
from typing import Optional, List, Any, Dict, Iterator, Union
from concurrent.futures import ThreadPoolExecutor

import orjson
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

from apps.algorithm.schema import AlgorithmInput
from apps.algorithm.result import AlgorithmResult, AlgorithmLog, OperationType
from apps.db.db import exec_sql
from apps.template.template import get_base_template, get_sql_template
from common.utils.utils import SQLBotLogUtil, extract_nested_json
from common.utils.data_format import DataFormat
from apps.ai_model.model_factory import LLMFactory
from common.error import SingleMessageError
import sqlparse

executor = ThreadPoolExecutor(max_workers=200)


def _debug_log(operation: str, message: str, data: Any = None):
    """Debug 日志记录函数"""
    SQLBotLogUtil.debug(f"[{operation}] {message}")
    if data is not None:
        try:
            import orjson
            SQLBotLogUtil.debug(f"[{operation}] Data: {orjson.dumps(data).decode()[:1000]}")
        except Exception:
            SQLBotLogUtil.debug(f"[{operation}] Data: {str(data)[:1000]}")


class AlgorithmService:
    """算法层服务 - 专注于问数算法处理"""

    def __init__(self, input_data: AlgorithmInput):
        self.input = input_data
        self.result = AlgorithmResult(
            record_id=input_data.chat_record_id or 0,
            success=True
        )
        self.sql_message: List[Union[BaseMessage, dict]] = []
        self.chart_message: List[Union[BaseMessage, dict]] = []
        self.llm = None
        self.ds = None

    def initialize(self, llm_config, datasource):
        """初始化 LLM 和数据源"""
        self.llm = LLMFactory.create_llm(llm_config).llm
        self.ds = datasource

    def run_task(self, in_chat: bool = True, stream: bool = True):
        """
        运行主要任务流程

        Args:
            in_chat: 是否在聊天界面
            stream: 是否流式输出

        Yields:
            流式事件
        """
        try:
            # 初始化消息
            self._init_messages()

            # 返回 ID 和问题
            if in_chat:
                yield {'type': 'id', 'id': self.input.chat_record_id}
                if self.input.regenerate_record_id:
                    yield {'type': 'regenerate_record_id', 'regenerate_record_id': self.input.regenerate_record_id}
                yield {'type': 'question', 'question': self.input.question}

            # 生成 SQL
            sql_result = self._generate_sql()
            full_sql_text = ''
            for chunk in sql_result:
                full_sql_text += chunk.get('content', '')
                if in_chat:
                    yield {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'), 'type': 'sql-result'}

            if in_chat:
                yield {'type': 'info', 'msg': 'sql generated'}

            # 解析 SQL
            sql, tables = self._check_sql(full_sql_text)
            self.result.generated_sql = sql
            self.result.tables_used = tables or []
            self.result.sql_answer = orjson.dumps({'content': full_sql_text}).decode()

            # 格式化 SQL 输出
            format_sql = sqlparse.format(sql, reindent=True)
            if in_chat:
                yield {'content': format_sql, 'type': 'sql'}
            else:
                if stream:
                    yield f'```sql\n{format_sql}\n```\n\n'

            # 执行 SQL
            result = self._execute_sql(sql)
            self.result.sql_execution_result = result

            _data = DataFormat.convert_large_numbers_in_object_array(result.get('data', []))
            result["data"] = _data

            if in_chat:
                yield {'content': 'execute-success', 'type': 'sql-data'}

            # 生成图表
            chart_result = self._generate_chart()
            full_chart_text = ''
            for chunk in chart_result:
                full_chart_text += chunk.get('content', '')
                if in_chat:
                    yield {'content': chunk.get('content'), 'reasoning_content': chunk.get('reasoning_content'), 'type': 'chart-result'}

            if in_chat:
                yield {'type': 'info', 'msg': 'chart generated'}

            # 解析图表配置
            chart = self._check_chart(full_chart_text)
            self.result.chart_config = chart
            self.result.chart_answer = orjson.dumps({'content': full_chart_text}).decode()

            if in_chat:
                yield {'content': orjson.dumps(chart).decode(), 'type': 'chart'}

            # 完成
            if in_chat:
                yield {'type': 'finish'}

        except Exception as e:
            traceback.print_exc()
            self.result.success = False
            error_msg = orjson.dumps({'message': str(e), 'traceback': traceback.format_exc()}).decode()
            self.result.error_message = error_msg
            if in_chat:
                yield {'content': error_msg, 'type': 'error'}
            else:
                yield {'success': False, 'message': str(e)}

    def _init_messages(self):
        """初始化消息"""
        # SQL 消息
        self.sql_message = []
        self.sql_message.append(SystemMessage(
            content=self._build_sql_system_prompt()
        ))

        # 添加历史消息
        count_limit = -6  # 限制消息数量
        last_sql_messages = self.input.last_sql_messages or []
        for msg in last_sql_messages[count_limit:]:
            if msg.get('type') == 'human':
                self.sql_message.append(HumanMessage(content=msg.get('content')))
            elif msg.get('type') == 'ai':
                self.sql_message.append(AIMessage(content=msg.get('content')))

        # 图表消息
        self.chart_message = []
        self.chart_message.append(SystemMessage(content=self._build_chart_system_prompt()))

    def _build_sql_system_prompt(self) -> str:
        """构建 SQL 系统提示词"""
        # 从本地模板文件读取
        base_template = get_base_template()
        sql_template = get_sql_template(self.input.engine_type)

        # 构建提示词
        system_prompt = base_template.get('system', '').format(
            engine=self.input.engine_type,
            schema=self.input.db_schema,
            question=self.input.question,
            terminologies=self.input.terminologies,
            data_training=self.input.data_training,
            custom_prompt=self.input.custom_prompt,
            error_msg=self.input.error_msg,
            limit=self.input.enable_row_limit
        )
        return system_prompt

    def _build_chart_system_prompt(self) -> str:
        """构建图表系统提示词"""
        return self.input.chart_sys_question()

    def _generate_sql(self) -> Iterator[Dict[str, Any]]:
        """生成 SQL"""
        self.sql_message.append(HumanMessage(
            content=self.input.sql_user_question()
        ))

        token_usage = {}
        res = self.llm.stream(self.sql_message)

        full_thinking = ''
        full_content = ''
        for chunk in res:
            content = chunk.content if hasattr(chunk, 'content') else ''
            reasoning = chunk.additional_kwargs.get('reasoning_content', '') if hasattr(chunk, 'additional_kwargs') else ''

            full_content += content
            full_thinking += reasoning

            yield {'content': content, 'reasoning_content': reasoning}

        self.sql_message.append(AIMessage(full_content))

        # 记录日志
        self.result.logs.append(AlgorithmLog(
            operation=OperationType.GENERATE_SQL,
            ai_modal_id=self.input.ai_modal_id,
            ai_modal_name=self.input.ai_modal_name,
            full_message=[{'type': m.type, 'content': m.content} for m in self.sql_message],
            reasoning_content=full_thinking,
            token_usage=token_usage
        ))

    def _check_sql(self, res: str) -> tuple[str, Optional[list]]:
        """检查 SQL"""
        json_str = extract_nested_json(res)
        if json_str is None:
            raise SingleMessageError(f'Cannot parse sql from answer: {res}')

        data = orjson.loads(json_str)
        if data['success']:
            sql = data['sql']
        else:
            raise SingleMessageError(data.get('message', 'SQL generation failed'))

        if sql.strip() == '':
            raise SingleMessageError("SQL query is empty")

        return sql, data.get('tables')

    def _execute_sql(self, sql: str) -> Dict[str, Any]:
        """执行 SQL"""
        SQLBotLogUtil.info(f"Executing SQL on ds_id {self.input.datasource_id}: {sql}")
        try:
            from apps.datasource.models.datasource import CoreDatasource
            ds = CoreDatasource(id=self.input.datasource_id, type=self.input.engine_type)
            return exec_sql(ds=ds, sql=sql, origin_column=False)
        except Exception as e:
            raise SingleMessageError(f"SQL execution failed: {str(e)}")

    def _generate_chart(self) -> Iterator[Dict[str, Any]]:
        """生成图表配置"""
        self.chart_message.append(HumanMessage(
            content=self.input.chart_user_question()
        ))

        token_usage = {}
        res = self.llm.stream(self.chart_message)

        full_thinking = ''
        full_content = ''
        for chunk in res:
            content = chunk.content if hasattr(chunk, 'content') else ''
            reasoning = chunk.additional_kwargs.get('reasoning_content', '') if hasattr(chunk, 'additional_kwargs') else ''

            full_content += content
            full_thinking += reasoning

            yield {'content': content, 'reasoning_content': reasoning}

        self.chart_message.append(AIMessage(full_content))

        # 记录日志
        self.result.logs.append(AlgorithmLog(
            operation=OperationType.GENERATE_CHART,
            ai_modal_id=self.input.ai_modal_id,
            ai_modal_name=self.input.ai_modal_name,
            full_message=[{'type': m.type, 'content': m.content} for m in self.chart_message],
            reasoning_content=full_thinking,
            token_usage=token_usage
        ))

    def _check_chart(self, res: str) -> Dict[str, Any]:
        """检查图表配置"""
        json_str = extract_nested_json(res)
        if json_str is None:
            raise SingleMessageError(f'Cannot parse chart config from answer: {res}')

        data = orjson.loads(json_str)
        if data.get('type') and data.get('type') != 'error':
            chart = data
            if chart.get('columns'):
                for v in chart.get('columns'):
                    v['value'] = v.get('value', '').lower()
            if chart.get('axis'):
                if chart.get('axis').get('x'):
                    chart.get('axis').get('x')['value'] = chart.get('axis').get('x').get('value', '').lower()
                if chart.get('axis').get('y'):
                    chart.get('axis').get('y')['value'] = chart.get('axis').get('y').get('value', '').lower()
                if chart.get('axis').get('series'):
                    chart.get('axis').get('series')['value'] = chart.get('axis').get('series').get('value', '').lower()
            return chart
        else:
            raise SingleMessageError(data.get('reason', 'Chart generation failed'))

    def get_result(self) -> AlgorithmResult:
        """获取结果"""
        return self.result
```

**Step 2: 验证导入**

Run: `cd backend && uv run python -c "from apps.algorithm.service import AlgorithmService; print('AlgorithmService imported successfully')"`
Expected: 成功导入，无错误

---

### 任务 5: 修改 chat.py 集成新架构

**文件:**
- Modify: `backend/apps/chat/api/chat.py`

**Step 1: 备份原文件**

Run: `cp backend/apps/chat/api/chat.py backend/apps/chat/api/chat.py.bak`

**Step 2: 修改 `stream_sql` 函数集成新架构**

```python
# 在 stream_sql 函数中，替换原有的 LLMService 调用
async def stream_sql(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                     current_assistant: Optional[CurrentAssistant] = None, in_chat: bool = True, stream: bool = True,
                     finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, embedding: bool = False):
    try:
        # 仅处理 page 来源
        if current_assistant and current_assistant.type != 4:
            # 回退到原实现
            llm_service = await LLMService.create(session, current_user, request_question, current_assistant,
                                                  embedding=embedding)
            llm_service.init_record(session=session)
            llm_service.run_task_async(in_chat=in_chat, stream=stream, finish_step=finish_step)
        else:
            # 使用新架构
            from apps.business_db import BusinessDataLayer
            from apps.algorithm.service import AlgorithmService

            business_db = BusinessDataLayer(session, current_user)

            # 准备算法输入
            algorithm_input, record = await business_db.prepare_algorithm_input(
                chat_id=request_question.chat_id,
                question=request_question.question,
                regenerate_record_id=request_question.regenerate_record_id,
                embedding=embedding
            )

            # 获取表结构
            db_schema = business_db.get_table_schema(
                algorithm_input.datasource_id,
                algorithm_input.question,
                embedding
            )
            algorithm_input.db_schema = db_schema

            # 获取术语和数据训练模板
            algorithm_input.terminologies = business_db.get_terminology_template(
                algorithm_input.question,
                algorithm_input.datasource_id
            )
            algorithm_input.data_training = business_db.get_data_training_template(
                algorithm_input.question,
                algorithm_input.datasource_id
            )

            # 获取 LLM 配置和数据源
            from apps.ai_model.model_factory import get_default_config
            from apps.datasource.models.datasource import CoreDatasource

            config = await get_default_config()
            ds = session.get(CoreDatasource, algorithm_input.datasource_id)

            # 创建算法服务
            algorithm_service = AlgorithmService(algorithm_input)
            algorithm_service.initialize(config, ds)

            # 异步运行任务
            algorithm_service.future = executor.submit(
                algorithm_service.run_task, in_chat, stream
            )

            # 收集结果
            def collect_result():
                for chunk in algorithm_service.run_task(in_chat=in_chat, stream=stream):
                    yield chunk

                # 保存结果
                result = algorithm_service.get_result()
                result.record_id = record.id
                business_db.save_algorithm_result(record.id, result)

            if stream:
                return StreamingResponse(collect_result(), media_type="text/event-stream")
            else:
                res = collect_result()
                raw_data = {}
                for chunk in res:
                    if chunk:
                        raw_data = chunk
                status_code = 200 if raw_data.get('success', True) else 500
                return JSONResponse(content=raw_data, status_code=status_code)

    except Exception as e:
        traceback.print_exc()

        if stream:
            def _err(_e: Exception):
                yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'
            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(content={'message': str(e)}, status_code=500)

    # 如果回退到原实现
    if stream:
        return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")
    else:
        res = llm_service.await_result()
        raw_data = {}
        for chunk in res:
            if chunk:
                raw_data = chunk
        status_code = 200 if raw_data.get('success', True) else 500
        return JSONResponse(content=raw_data, status_code=status_code)
```

**Step 3: 测试修改**

Run: `cd backend && uv run python -c "from apps.chat.api.chat import stream_sql; print('Modified stream_sql imported successfully')"`
Expected: 成功导入，无错误

---

### 任务 6: 修复推荐问题 bug

**文件:**
- Modify: `backend/apps/chat/api/chat.py` 中的 `ask_recommend_questions` 函数

**Step 1: 修改推荐问题函数**

```python
@router.post("/recommend_questions/{chat_record_id}", summary=f"{PLACEHOLDER_PREFIX}ask_recommend_questions")
async def ask_recommend_questions(session: SessionDep, current_user: CurrentUser, chat_record_id: int,
                                  current_assistant: CurrentAssistant, articles_number: Optional[int] = 4):
    def _return_empty():
        yield 'data:' + orjson.dumps({'content': '[]', 'type': 'recommended_question'}).decode() + '\n\n'

    try:
        # 仅处理 page 来源
        if current_assistant and current_assistant.type != 4:
            # 回退到原实现
            record = get_chat_record_by_id(session, chat_record_id)
            if not record:
                return StreamingResponse(_return_empty(), media_type="text/event-stream")

            request_question = ChatQuestion(chat_id=record.chat_id, question=record.question if record.question else '')
            llm_service = await LLMService.create(session, current_user, request_question, current_assistant, True)
            llm_service.set_record(record)
            llm_service.set_articles_number(articles_number)
            llm_service.run_recommend_questions_task_async()
            return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")

        # 新架构实现
        from apps.business_db import BusinessDataLayer
        from apps.algorithm.service import AlgorithmService
        from apps.algorithm.schema import AlgorithmInput

        record = get_chat_record_by_id(session, chat_record_id)
        if not record:
            return StreamingResponse(_return_empty(), media_type="text/event-stream")

        business_db = BusinessDataLayer(session, current_user)

        # 准备算法输入
        algorithm_input, _ = await business_db.prepare_algorithm_input(
            chat_id=record.chat_id,
            question=record.question or '',
            embedding=True
        )
        algorithm_input.articles_number = articles_number

        # 获取 LLM 配置
        from apps.ai_model.model_factory import get_default_config
        from apps.datasource.models.datasource import CoreDatasource

        config = await get_default_config()
        ds = session.get(CoreDatasource, record.datasource)

        # 创建算法服务
        algorithm_service = AlgorithmService(algorithm_input)
        algorithm_service.initialize(config, ds)
        algorithm_service.set_record(record)
        algorithm_service.set_articles_number(articles_number)

        # 运行推荐问题任务
        def run_recommend():
            try:
                for chunk in algorithm_service.run_recommend_questions_task():
                    yield chunk
            except Exception:
                traceback.print_exc()

        return StreamingResponse(run_recommend(), media_type="text/event-stream")

    except Exception as e:
        traceback.print_exc()

        def _err(_e: Exception):
            yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'

        return StreamingResponse(_err(e), media_type="text/event-stream")
```

**Step 2: 测试修改**

Run: `cd backend && uv run python -c "from apps.chat.api.chat import ask_recommend_questions; print('Modified ask_recommend_questions imported successfully')"`
Expected: 成功导入，无错误

---

### 任务 7: 运行测试验证重构

**Step 1: 运行 pytest**

Run: `cd backend && uv run pytest -xvs`
Expected: 所有测试通过

**Step 2: 运行类型检查**

Run: `cd backend && uv run mypy . --ignore-missing-imports`
Expected: 无类型错误

**Step 3: 运行 linting**

Run: `cd backend && uv run ruff check .`
Expected: 无 lint 错误

---

### 任务 8: 提交代码

```bash
git add backend/apps/algorithm/ backend/apps/business_db/ backend/apps/chat/api/chat.py
git commit -m "refactor: 实现业务数据层和算法层分离 (version 1)"
```

---

## 版本二：完善算法层功能

### 目标: 完善推荐问题生成、分析、预测等功能

---

### 任务 9: 实现推荐问题生成

**文件:**
- Modify: `backend/apps/algorithm/service.py`

**Step 1: 添加推荐问题生成方法**

```python
def run_recommend_questions_task(self):
    """生成推荐问题"""
    try:
        # 获取历史问题
        from apps.chat.curd.chat import get_old_questions
        old_questions = list(map(lambda q: q.strip(), get_old_questions(self.session, self.ds.id)))

        # 构建消息
        guess_msg = []
        guess_msg.append(SystemMessage(content=self.input.guess_sys_question(self.articles_number)))
        guess_msg.append(HumanMessage(content=self.input.guess_user_question(orjson.dumps(old_questions).decode())))

        # 生成
        token_usage = {}
        res = self.llm.stream(guess_msg)

        full_thinking = ''
        full_guess_text = ''
        for chunk in res:
            content = chunk.content if hasattr(chunk, 'content') else ''
            reasoning = chunk.additional_kwargs.get('reasoning_content', '') if hasattr(chunk, 'additional_kwargs') else ''

            full_guess_text += content
            full_thinking += reasoning

            yield {'content': content, 'reasoning_content': reasoning}

        guess_msg.append(AIMessage(full_guess_text))

        # 保存结果
        self.result.recommended_questions = full_guess_text

        # 记录日志
        self.result.logs.append(AlgorithmLog(
            operation=OperationType.GENERATE_RECOMMENDED_QUESTIONS,
            ai_modal_id=self.input.ai_modal_id,
            ai_modal_name=self.input.ai_modal_name,
            full_message=[{'type': m.type, 'content': m.content} for m in guess_msg],
            reasoning_content=full_thinking,
            token_usage=token_usage
        ))

        yield {'recommended_question': full_guess_text}

    except Exception:
        traceback.print_exc()
```

---

### 任务 10: 实现分析和预测功能

**文件:**
- Modify: `backend/apps/algorithm/service.py`

---

## 版本三：优化和测试

### 目标: 完善测试，确保功能稳定

---

### 任务 11: 添加单元测试

**文件:**
- Create: `backend/tests/test_business_db.py`
- Create: `backend/tests/test_algorithm.py`

---

## 注意事项

1. **保留原实现作为回退**: 在新架构完成前，保留 `LLMService` 作为回退方案
2. **仅处理 page 来源**: 根据 dev plan，重构版本不考虑 assistant 来源
3. **保持流式输出**: 确保重构后流式输出行为与原实现一致
4. **错误处理**: 确保错误信息正确返回给前端

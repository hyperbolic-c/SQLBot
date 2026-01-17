"""
Algorithm Engine
Core algorithm processing logic for SQL generation and chart creation.

This module implements the same algorithm flow as the original LLMService.run_task,
but with a key difference:
- All business database queries are pre-loaded in BusinessDBService.preprocess()
- This engine only accesses:
  1. Target databases (for SQL execution)
  2. Local template files (for prompt templates)
  3. No business database queries during execution
"""

import json
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Generator, Union

import orjson
import sqlparse
from langchain.chat_models.base import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

from apps.ai_model.model_factory import LLMConfig, LLMFactory
from apps.chat.models.chat_model import ChatFinishStep, OperationEnum
from apps.db.db import exec_sql, get_version, check_connection
from apps.template.generate_sql.generator import get_sql_template, get_sql_example_template
from apps.template.generate_chart.generator import get_chart_template
from apps.template.generate_analysis.generator import get_analysis_template
from apps.template.generate_predict.generator import get_predict_template
from apps.template.generate_guess_question.generator import get_guess_question_template
from apps.template.select_datasource.generator import get_datasource_template
from apps.template.filter.generator import get_permissions_template
from apps.datasource.crud.permission import get_row_permission_filters
from apps.datasource.models.datasource import CoreDatasource
from common.error import SingleMessageError, SQLBotDBError, SQLBotDBConnectionError, ParseSQLResultError
from common.utils.data_format import DataFormat
from common.utils.utils import SQLBotLogUtil, extract_nested_json

from ..business_db.context import AlgorithmContext
from ..business_db.result import AlgorithmResult, ChatLogCreate, ChatUpdate


@dataclass
class StreamEvent:
    """流式事件"""
    type: str
    data: Dict[str, Any]


class AlgorithmEngine:
    """
    算法引擎

    职责：
    1. 接收 AlgorithmContext（包含所有预加载的业务数据）
    2. 从本地读取提示词模板文件
    3. 访问目标数据库执行 SQL
    4. 生成图表配置
    5. 流式产出中间结果（SSE）
    6. 返回 AlgorithmResult（包含所有待保存数据）

    注意：此引擎不访问业务数据库，所有业务数据已预加载到 context 中
    权限过滤除外，需要查询业务数据库获取用户权限
    """

    def __init__(self, context: AlgorithmContext, session=None):
        self.context = context
        self.session = session  # 用于权限过滤等需要访问业务数据库的场景

        # 目标数据库连接
        self._ds = None
        self._ds_session = None

        # LLM 实例
        self._llm: Optional[BaseChatModel] = None
        self._config: Optional[LLMConfig] = None

        # 消息历史
        self._sql_messages: List[Union[BaseMessage, dict]] = []
        self._chart_messages: List[Union[BaseMessage, dict]] = []

        # 当前日志
        self._current_log: Optional[ChatLogCreate] = None

        # 执行结果
        self._result = AlgorithmResult(
            record_id=0,
            chat_id=context.chat_id or 0,
        )

        # 内部状态
        self._change_title = not context.chat_brief_generate
        self._last_execute_sql_error = ""

    def _is_normal_user(self) -> bool:
        """判断是否是普通用户（非管理员）"""
        # 管理员 id 为 1
        return self.context.user_id != 1

    def _check_save_sql(self, res: str) -> str:
        """
        检查并保存 SQL
        复刻原结构 LLMService.check_save_sql
        """
        sql, *_ = self._check_sql(res=res)
        # 保存 SQL 到结果中，后续 postprocess 会保存
        self._result.sql = sql
        return sql

    def _get_datasource(self):
        """获取目标数据源连接"""
        if self._ds is not None:
            return self._ds

        if self.context.datasource is None:
            return None

        from apps.datasource.utils.utils import aes_decrypt

        try:
            config_str = aes_decrypt(self.context.datasource.configuration)
            from apps.datasource.models.datasource import CoreDatasource, DatasourceConf
            config = DatasourceConf(**json.loads(config_str))
            self._ds = CoreDatasource(
                id=self.context.datasource.id,
                name=self.context.datasource.name,
                type=self.context.datasource.type,
                type_name=self.context.datasource.type,
                configuration=self.context.datasource.configuration,
                oid=self.context.oid,
            )
            return self._ds
        except Exception as e:
            SQLBotLogUtil.error(f"[AlgorithmEngine] 获取数据源失败: {e}")
            return None

    def _select_datasource(self) -> Optional[CoreDatasource]:
        """
        选择数据源（复用原结构 LLMService.select_datasource）

        当没有配置数据源时，从组织的数据源列表中选择：
        1. 如果只有一个可用数据源，自动选择
        2. 如果有多个，调用 LLM 选择
        3. 如果没有可用数据源，抛出异常

        Returns:
            CoreDatasource: 选择的数据源
        """
        if not self.session:
            return None

        from sqlalchemy import select

        # 查询可用的数据源列表
        stmt = select(CoreDatasource.id, CoreDatasource.name, CoreDatasource.description).where(
            CoreDatasource.oid == self.context.oid
        )
        ds_list = []
        for row in self.session.exec(stmt):
            ds_list.append({
                "id": row.id,
                "name": row.name,
                "description": row.description
            })

        if not ds_list:
            raise SingleMessageError('No available datasource configuration found')

        # 如果只有一个数据源，自动选择
        if len(ds_list) == 1:
            ds_id = ds_list[0]['id']
            ds = self.session.get(CoreDatasource, ds_id)
            if ds:
                self._ds = CoreDatasource(**ds.model_dump())
                return self._ds
            return None

        # TODO: 多个数据源时调用 LLM 选择（需要实现完整的选择逻辑）
        # 目前简化处理：选择第一个数据源
        SQLBotLogUtil.warning(f"[AlgorithmEngine] 多个数据源可用，选择第一个: {ds_list[0]['name']}")
        ds_id = ds_list[0]['id']
        ds = self.session.get(CoreDatasource, ds_id)
        if ds:
            self._ds = CoreDatasource(**ds.model_dump())
            return self._ds

        return None

    def _init_llm(self):
        """初始化 LLM"""
        if self._llm is not None:
            return

        if self.context.ai_model is None:
            SQLBotLogUtil.error("[AlgorithmEngine] AI model not configured")
            raise SingleMessageError("AI model not configured")

        SQLBotLogUtil.info(f"[AlgorithmEngine] 初始化 LLM, model={self.context.ai_model.name}")
        SQLBotLogUtil.info(f"[AlgorithmEngine] api_domain={self.context.ai_model.api_domain}")

        # 将 protocol 转换为 model_type 字符串（复刻原 get_default_config 的逻辑）
        model_type = "openai" if self.context.ai_model.protocol == 1 else "vllm"

        self._config = LLMConfig(
            model_id=self.context.ai_model.id,
            model_type=model_type,
            model_name=self.context.ai_model.base_model,
            api_base_url=self.context.ai_model.api_domain,
            api_key=self.context.ai_model.api_key,
        )
        SQLBotLogUtil.info(f"[AlgorithmEngine] LLMConfig api_base_url={self._config.api_base_url}")

        try:
            llm_instance = LLMFactory.create_llm(self._config)
            self._llm = llm_instance.llm
            SQLBotLogUtil.info("[AlgorithmEngine] LLM 初始化成功")
        except Exception as e:
            SQLBotLogUtil.error(f"[AlgorithmEngine] LLM 初始化失败: {e}")
            raise

    def _build_sql_system_prompt(self) -> str:
        """
        构建 SQL 生成系统提示词
        从本地模板文件读取
        """
        # 获取 SQL 模板
        sql_template = get_sql_template()
        SQLBotLogUtil.info(f"[_build_sql_system_prompt] sql_template type: {type(sql_template)}")

        sql_example = get_sql_example_template(self.context.engine)
        SQLBotLogUtil.info(f"[_build_sql_system_prompt] sql_example type: {type(sql_example)}, engine: {self.context.engine}")
        if isinstance(sql_example, str):
            SQLBotLogUtil.info(f"[_build_sql_system_prompt] sql_example content: {sql_example[:200]}")

        # 构建表结构 - 使用原始格式的 db_schema（与原结构一致）
        schema = self.context.db_schema if self.context.db_schema else self._build_schema_text()

        # 构建基础 SQL 规则
        base_sql_rules = ""
        if sql_example and isinstance(sql_example, dict):
            base_sql_rules = sql_example.get('quot_rule', '')
            base_sql_rules += sql_example.get('query_limit', '') if self.context.enable_query_limit else ''
            base_sql_rules += sql_example.get('limit_rule', '')
            other_rule = sql_example.get('other_rule', '')
            if isinstance(other_rule, str):
                base_sql_rules += other_rule
        else:
            SQLBotLogUtil.warning(f"[_build_sql_system_prompt] sql_example is not a dict, using empty rules")

        # 安全获取 sql_example 的值
        if isinstance(sql_example, dict):
            process_check = sql_example.get('process_check', '')
            basic_sql_examples = sql_example.get('basic_example', '')
            example_engine = sql_example.get('example_engine', '')
            example_answer_1 = sql_example.get('example_answer_1_with_limit', '') if self.context.enable_query_limit else sql_example.get('example_answer_1', '')
            example_answer_2 = sql_example.get('example_answer_2_with_limit', '') if self.context.enable_query_limit else sql_example.get('example_answer_2', '')
            example_answer_3 = sql_example.get('example_answer_3_with_limit', '') if self.context.enable_query_limit else sql_example.get('example_answer_3', '')
        else:
            process_check = ''
            basic_sql_examples = ''
            example_engine = ''
            example_answer_1 = ''
            example_answer_2 = ''
            example_answer_3 = ''

        # 构建系统提示词
        system_prompt = sql_template['system'].format(
            engine=self.context.engine,
            schema=schema,
            question=self.context.question,
            lang=self.context.language,
            terminologies=self.context.terminology_template,
            data_training=self.context.data_training_template,
            custom_prompt=self.context.custom_prompt,
            process_check=process_check,
            base_sql_rules=base_sql_rules,
            basic_sql_examples=basic_sql_examples,
            example_engine=example_engine,
            example_answer_1=example_answer_1,
            example_answer_2=example_answer_2,
            example_answer_3=example_answer_3,
        )

        return system_prompt

    def _build_schema_text(self) -> str:
        """构建表结构文本"""
        tables = []
        for t in self.context.table_schema.tables if self.context.table_schema else []:
            table_name = t.get("tableName", "")
            table_comment = t.get("tableComment", "")
            tables.append(f"- {table_name}: {table_comment}")

            # 查找字段
            fields = [f for f in (self.context.table_schema.fields if self.context.table_schema else [])
                     if f.get("tableId") == t.get("id") or f.get("table_id") == t.get("id")]
            for f in fields:
                field_name = f.get("fieldName", "") or f.get("field_name", "")
                field_comment = f.get("fieldComment", "") or f.get("field_comment", "")
                tables.append(f"    - {field_name}: {field_comment}")

        return "\n".join(tables) if tables else self.context.question

    def _build_sql_user_prompt(self) -> str:
        """构建 SQL 生成用户提示词"""
        sql_template = get_sql_template()

        # 处理重新生成
        question = self.context.question
        if self.context.regenerate_record_id:
            question = sql_template.get('regenerate_hint', '') + question

        # 使用原始格式的 db_schema（与原结构一致）
        schema = self.context.db_schema if self.context.db_schema else self._build_schema_text()
        
        user_prompt = sql_template['user'].format(
            engine=self.context.engine,
            schema=schema,
            question=question,
            rule="",
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            error_msg=self.context.error_msg,
            change_title=self._change_title,
        )

        return user_prompt

    def _build_chart_system_prompt(self, sql: str) -> str:
        """构建图表生成系统提示词"""
        chart_template = get_chart_template()
        return chart_template['system'].format(
            sql=sql,
            question=self.context.question,
            lang=self.context.language,
        )

    def _build_chart_user_prompt(self, sql: str, chart_type: str = "") -> str:
        """构建图表生成用户提示词"""
        chart_template = get_chart_template()
        return chart_template['user'].format(
            sql=sql,
            question=self.context.question,
            rule="",
            chart_type=chart_type,
        )

    def _init_sql_messages(self):
        """初始化 SQL 消息历史"""
        # 添加系统提示词
        self._sql_messages = [
            SystemMessage(content=self._build_sql_system_prompt())
        ]

        # 添加历史消息
        for msg in self.context.sql_history_messages[-6:]:
            if msg.get('type') == 'human':
                self._sql_messages.append(HumanMessage(content=msg.get('content', '')))
            elif msg.get('type') == 'ai':
                self._sql_messages.append(AIMessage(content=msg.get('content', '')))

    def _init_chart_messages(self, sql: str):
        """初始化图表消息历史"""
        # 添加系统提示词
        self._chart_messages = [
            SystemMessage(content=self._build_chart_system_prompt(sql))
        ]

        # 添加历史消息
        for msg in self.context.chart_history_messages:
            if msg.get('type') == 'human':
                self._chart_messages.append(HumanMessage(content=msg.get('content', '')))
            elif msg.get('type') == 'ai':
                self._chart_messages.append(AIMessage(content=msg.get('content', '')))

    def _generate_sql(self) -> Generator[StreamEvent, None, str]:
        """生成 SQL"""
        SQLBotLogUtil.info("[AlgorithmEngine] 开始生成 SQL")

        # 初始化 LLM
        self._init_llm()

        # 初始化消息
        self._init_sql_messages()

        # 添加用户消息
        self._sql_messages.append(HumanMessage(
            content=self._build_sql_user_prompt()
        ))

        # 记录日志
        self._current_log = ChatLogCreate(
            type=OperationEnum.GENERATE_SQL.value,
            operate=OperationEnum.GENERATE_SQL.value,
            pid=self._result.record_id,
            ai_modal_id=self.context.ai_model.id if self.context.ai_model else None,
            start_time=datetime.now(),
        )

        full_sql = ""
        token_usage = {}

        try:
            # 调用 LLM 生成 SQL
            for chunk in self._llm.stream(self._sql_messages):
                content = ""
                reasoning = ""
                if hasattr(chunk, 'content'):
                    content = chunk.content
                if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
                    reasoning = chunk.response_metadata.get('reasoning_content', '')

                full_sql += content

                yield StreamEvent(
                    type="sql-result",
                    data={"content": content, "reasoning_content": reasoning}
                )

            # 结束日志
            self._current_log.finish_time = datetime.now()
            self._current_log.messages = [
                {"type": msg.type, "content": msg.content if hasattr(msg, 'content') else str(msg)}
                for msg in self._sql_messages
            ]
            self._current_log.token_usage = token_usage

            # 保存 SQL 答案
            self._result.sql_answer = orjson.dumps({'content': full_sql}).decode()

            return full_sql

        except Exception as e:
            SQLBotLogUtil.error(f"[AlgorithmEngine] 生成 SQL 失败: {e}")
            yield StreamEvent(
                type="error",
                data={"content": f"生成 SQL 失败: {str(e)}", "type": "error"}
            )
            raise

    def _execute_sql(self, sql: str) -> Dict[str, Any]:
        """执行 SQL 查询 (目标数据库)"""
        ds = self._get_datasource()
        if ds is None:
            raise SingleMessageError("No datasource configured")

        SQLBotLogUtil.info(f"[AlgorithmEngine] 执行 SQL: {sql[:100]}...")

        try:
            result = exec_sql(ds=ds, sql=sql, origin_column=False)
            SQLBotLogUtil.info(f"[AlgorithmEngine] SQL执行结果: 类型={type(result).__name__}, 行数={len(result) if result else 0}")
            if result:
                if isinstance(result, list) and len(result) > 0:
                    SQLBotLogUtil.info(f"[AlgorithmEngine] SQL执行数据示例: {result[:2]}")
                elif isinstance(result, dict):
                    SQLBotLogUtil.info(f"[AlgorithmEngine] SQL执行数据示例: {result}")
            return result
        except ParseSQLResultError as e:
            raise e
        except Exception as e:
            err = traceback.format_exc(limit=1, chain=True)
            raise SQLBotDBError(err)

    def _extract_sql_content(self, sql_answer: str) -> str:
        """
        从 sql_answer 中提取内层的 content
        sql_answer 格式为 {"content": "..."}，需要提取内层内容用于解析
        """
        if not sql_answer:
            return sql_answer
        try:
            data = orjson.loads(sql_answer)
            if isinstance(data, dict) and 'content' in data:
                return data['content']
        except Exception:
            pass
        return sql_answer

    def _check_sql(self, res: str) -> tuple[str, Optional[list]]:
        """检查并解析 SQL"""
        json_str = extract_nested_json(res)
        if json_str is None:
            raise SingleMessageError(orjson.dumps({
                'message': 'Cannot parse sql from answer',
                'traceback': f"Cannot parse sql from answer:\n{res}"
            }).decode())

        try:
            data = orjson.loads(json_str)
            if data['success']:
                sql = data['sql']
            else:
                message = data.get('message', 'Unknown error')
                raise SingleMessageError(message)
        except SingleMessageError:
            raise
        except Exception:
            raise SingleMessageError(orjson.dumps({
                'message': 'Cannot parse sql from answer',
                'traceback': f"Cannot parse sql from answer:\n{res}"
            }).decode())

        if sql.strip() == '':
            raise SingleMessageError("SQL query is empty")

        return sql, data.get('tables')

    def _generate_filter(self, sql: str, tables: List[str]) -> Optional[str]:
        """
        生成带权限过滤的 SQL

        复用原结构 LLMService.generate_filter 的实现：
        1. 从业务数据库获取行权限配置
        2. 调用 LLM 生成带权限过滤的 SQL

        Args:
            sql: 原始 SQL
            tables: 涉及的表列表

        Returns:
            带权限过滤的 SQL 答案，或 None（无权限配置）
        """
        if not self.session:
            return None

        # 获取用户上下文（用于权限检查）
        # 创建一个简单的用户对象，get_row_permission_filters 只使用 id, workspace_id, oid
        class SimpleUser:
            def __init__(self, id_, workspace_id, oid):
                self.id = id_
                self.workspace_id = workspace_id
                self.oid = oid

        current_user = SimpleUser(
            id=self.context.user_context.id if self.context.user_context else self.context.user_id,
            workspace_id=self.context.user_context.workspace_id if self.context.user_context else self.context.workspace_id,
            oid=self.context.user_context.oid if self.context.user_context else self.context.oid,
        )

        # 获取行权限过滤配置
        filters = get_row_permission_filters(
            session=self.session,
            current_user=current_user,
            ds=self._get_datasource(),
            tables=tables
        )

        if not filters:
            return None

        # 调用 LLM 生成带权限过滤的 SQL
        return self._build_table_filter(sql=sql, filters=filters)

    def _build_table_filter(self, sql: str, filters: list) -> str:
        """
        构建带权限过滤的 SQL（复用原结构 LLMService.build_table_filter）

        Args:
            sql: 原始 SQL
            filters: 权限过滤配置列表

        Returns:
            带权限过滤的 SQL 答案
        """
        filter_json = json.dumps(filters, ensure_ascii=False)

        # 构建消息
        messages = [
            SystemMessage(content=self._build_filter_sys_prompt()),
            HumanMessage(content=self._build_filter_user_prompt(sql, filter_json))
        ]

        # 记录日志
        self._current_log = ChatLogCreate(
            type=OperationEnum.GENERATE_SQL_WITH_PERMISSIONS.value,
            operate=OperationEnum.GENERATE_SQL_WITH_PERMISSIONS.value,
            pid=self._result.record_id,
            ai_modal_id=self.context.ai_model.id if self.context.ai_model else None,
            start_time=datetime.now(),
        )

        full_filter_text = ""
        token_usage = {}

        for chunk in self._llm.stream(messages):
            content = ""
            reasoning = ""
            if hasattr(chunk, 'content'):
                content = chunk.content
            if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
                reasoning = chunk.response_metadata.get('reasoning_content', '')

            full_filter_text += content

            yield StreamEvent(
                type="filter-result",
                data={"content": content, "reasoning_content": reasoning}
            )

        # 结束日志
        self._current_log.finish_time = datetime.now()
        self._current_log.messages = [
            {"type": msg.type, "content": msg.content if hasattr(msg, 'content') else str(msg)}
            for msg in messages
        ]
        self._result.logs.append(self._current_log)

        SQLBotLogUtil.info(full_filter_text)
        return full_filter_text

    def _build_filter_sys_prompt(self) -> str:
        """构建权限过滤系统提示词"""
        template = get_permissions_template()
        return template['system'].format(
            language=self.context.language,
        )

    def _build_filter_user_prompt(self, sql: str, filter_json: str) -> str:
        """构建权限过滤用户提示词"""
        template = get_permissions_template()
        return template['user'].format(
            original_sql=sql,
            filters=filter_json,
            language=self.context.language,
        )

    def _get_chart_type_from_sql_answer(self, res: str) -> Optional[str]:
        """从 SQL 答案中获取图表类型"""
        json_str = extract_nested_json(res)
        if json_str is None:
            return None

        try:
            data = orjson.loads(json_str)
            if data['success']:
                return data.get('chart-type')
        except Exception:
            pass

        return None

    def _get_brief_from_sql_answer(self, res: str) -> Optional[str]:
        """从 SQL 答案中获取标题"""
        json_str = extract_nested_json(res)
        if json_str is None:
            return None

        try:
            data = orjson.loads(json_str)
            if data['success']:
                return data.get('brief')
        except Exception:
            pass

        return None

    def _generate_chart(self, sql: str, chart_type: str = "") -> Generator[StreamEvent, None, Dict[str, Any]]:
        """生成图表配置"""
        SQLBotLogUtil.info("[AlgorithmEngine] 开始生成图表")

        # 初始化消息
        self._init_chart_messages(sql)

        # 添加用户消息
        self._chart_messages.append(HumanMessage(
            content=self._build_chart_user_prompt(sql, chart_type)
        ))

        # 记录日志
        self._current_log = ChatLogCreate(
            type=OperationEnum.GENERATE_CHART.value,
            operate=OperationEnum.GENERATE_CHART.value,
            pid=self._result.record_id,
            ai_modal_id=self.context.ai_model.id if self.context.ai_model else None,
            start_time=datetime.now(),
        )

        full_chart = ""
        token_usage = {}

        try:
            # 初始化 LLM
            self._init_llm()

            for chunk in self._llm.stream(self._chart_messages):
                content = ""
                reasoning = ""
                if hasattr(chunk, 'content'):
                    content = chunk.content
                if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
                    reasoning = chunk.response_metadata.get('reasoning_content', '')

                full_chart += content

                yield StreamEvent(
                    type="chart-result",
                    data={"content": content, "reasoning_content": reasoning}
                )

            # 解析图表配置
            chart_config = self._parse_chart_config(full_chart)

            # 结束日志
            self._current_log.finish_time = datetime.now()
            self._current_log.messages = [
                {"type": msg.type, "content": msg.content if hasattr(msg, 'content') else str(msg)}
                for msg in self._chart_messages
            ]
            self._current_log.token_usage = token_usage

            # 保存图表答案
            self._result.chart_answer = orjson.dumps({'content': full_chart}).decode()
            SQLBotLogUtil.info(f"[AlgorithmEngine] 图表答案已保存, 长度={len(full_chart)}")

            return chart_config

        except GeneratorExit:
            SQLBotLogUtil.warning(f"[AlgorithmEngine] 图表生成流被提前关闭, 已收集内容: {full_chart[:100] if full_chart else 'empty'}")
            if full_chart:
                self._result.chart_answer = orjson.dumps({'content': full_chart}).decode()
                SQLBotLogUtil.info(f"[AlgorithmEngine] GeneratorExit: 图表答案已保存, 长度={len(full_chart)}")
                # 尝试解析已收集的内容
                chart_config = self._parse_chart_config(full_chart)
                SQLBotLogUtil.info(f"[AlgorithmEngine] GeneratorExit: 图表解析结果: {chart_config}")
                return chart_config
            return {"type": "table", "data": {}}
        except Exception as e:
            SQLBotLogUtil.error(f"[AlgorithmEngine] 生成图表失败: {e}")
            yield StreamEvent(
                type="error",
                data={"content": f"生成图表失败: {str(e)}", "type": "error"}
            )
            raise

    def _parse_chart_config(self, text: str) -> Dict[str, Any]:
        """解析图表配置"""
        try:
            import re
            SQLBotLogUtil.info(f"[AlgorithmEngine] _parse_chart_config 输入长度: {len(text)}")
            SQLBotLogUtil.info(f"[AlgorithmEngine] _parse_chart_config 输入内容: {text[:200]}")

            # 处理 {"content": "..."} 包装格式
            cleaned_text = text
            try:
                outer = orjson.loads(text)
                if isinstance(outer, dict) and 'content' in outer:
                    cleaned_text = outer['content']
                    SQLBotLogUtil.info(f"[AlgorithmEngine] 提取内层content, 长度: {len(cleaned_text)}")
            except Exception:
                pass

            # 清理 markdown 代码块
            # 移除 ```json 和 ``` 标记
            cleaned_text = re.sub(r'```json\s*', '', cleaned_text)
            cleaned_text = re.sub(r'```\s*$', '', cleaned_text)
            cleaned_text = cleaned_text.strip()

            json_match = re.search(r'\{[\s\S]*\}', cleaned_text)
            if json_match:
                json_str = json_match.group()
                SQLBotLogUtil.info(f"[AlgorithmEngine] 找到JSON: {json_str[:100]}...")
                chart_config = json.loads(json_str)
                SQLBotLogUtil.info(f"[AlgorithmEngine] 解析成功: {chart_config}")
                if chart_config.get('type') and chart_config['type'] != 'error':
                    # 处理字段名大小写
                    if chart_config.get('columns'):
                        for v in chart_config.get('columns'):
                            if v.get('value'):
                                v['value'] = v.get('value').lower()
                    if chart_config.get('axis'):
                        if chart_config['axis'].get('x') and chart_config['axis']['x'].get('value'):
                            chart_config['axis']['x']['value'] = chart_config['axis']['x']['value'].lower()
                        if chart_config['axis'].get('y') and chart_config['axis']['y'].get('value'):
                            chart_config['axis']['y']['value'] = chart_config['axis']['y']['value'].lower()
                        if chart_config['axis'].get('series') and chart_config['axis']['series'].get('value'):
                            chart_config['axis']['series']['value'] = chart_config['axis']['series']['value'].lower()
                    return chart_config
            else:
                SQLBotLogUtil.warning(f"[AlgorithmEngine] 未找到JSON配置")
        except json.JSONDecodeError as e:
            SQLBotLogUtil.error(f"[AlgorithmEngine] JSON解析错误: {e}, 位置: {e.pos}, 内容: {text[e.pos-50:e.pos+50] if e.pos < len(text) else text}")
        except Exception as e:
            SQLBotLogUtil.error(f"[AlgorithmEngine] 解析图表配置失败: {e}")

        return {"type": "table", "data": {}}

    def _format_sql(self, sql: str) -> str:
        """格式化 SQL"""
        return sqlparse.format(sql, reindent=True)

    def run(
        self,
        record_id: int,
        finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART,
        in_chat: bool = True,
    ) -> Generator[StreamEvent, None, AlgorithmResult]:
        """
        执行算法处理流程

        这个方法复刻了原 LLMService.run_task 的完整流程：
        1. 初始化
        2. 选择数据源（如果需要）
        3. 生成 SQL
        4. 执行 SQL（目标数据库）
        5. 生成图表
        6. 完成

        Args:
            record_id: 聊天记录 ID
            finish_step: 完成步骤
            in_chat: 是否在聊天中

        Yields:
            StreamEvent: 流式事件

        Returns:
            AlgorithmResult: 执行结果
        """
        self._result.record_id = record_id
        self._result.chat_id = self.context.chat_id or 0

        SQLBotLogUtil.info(f"[AlgorithmEngine] run 方法开始执行, record_id={record_id}")
        try:
            # 1. 返回 record_id
            SQLBotLogUtil.info(f"[AlgorithmEngine] yield id 事件")
            yield StreamEvent(type="id", data={"id": record_id})

            if self.context.regenerate_record_id:
                yield StreamEvent(
                    type="regenerate_record_id",
                    data={"regenerate_record_id": self.context.regenerate_record_id}
                )

            yield StreamEvent(type="question", data={"question": self.context.question})

            # 2. 获取数据源
            ds = self._get_datasource()

            if ds is None:
                # 需要选择数据源 - 复用原结构的选择逻辑
                ds = self._select_datasource()

            if ds is None:
                raise SingleMessageError("No datasource configured")

            # 3. 测试连接
            connected = check_connection(ds=ds, trans=None)
            if not connected:
                raise SQLBotDBConnectionError('Connect DB failed')

            # 4. 生成 SQL
            sql = ""
            if self.context.ai_model:
                SQLBotLogUtil.info("[AlgorithmEngine] 开始调用 LLM 生成 SQL")
                try:
                    for event in self._generate_sql():
                        yield event
                    SQLBotLogUtil.info(f"[AlgorithmEngine] LLM 调用完成, sql_answer={self._result.sql_answer}")
                except Exception as gen_e:
                    SQLBotLogUtil.error(f"[AlgorithmEngine] LLM 调用异常: {gen_e}")
                    SQLBotLogUtil.error(f"[AlgorithmEngine] 异常详情: {traceback.format_exc()}")
                    raise

                # 获取生成的 SQL
                if self._result.sql_answer:
                    try:
                        sql_data = orjson.loads(self._result.sql_answer)
                        sql = sql_data.get('content', '')
                        SQLBotLogUtil.info(f"[AlgorithmEngine] SQL 内容长度: {len(sql)}")
                    except Exception as parse_e:
                        SQLBotLogUtil.error(f"[AlgorithmEngine] 解析 SQL 答案失败: {parse_e}")

            if not sql:
                SQLBotLogUtil.error("[AlgorithmEngine] SQL 生成为空")
                raise SingleMessageError("Failed to generate SQL")

            # info: sql generated
            yield StreamEvent(type="info", data={"msg": "sql generated"})

            # 提取内层 content（sql_answer 格式为 {"content": "..."}）
            sql_answer = self._extract_sql_content(self._result.sql_answer or "")

            # 获取图表类型
            chart_type = self._get_chart_type_from_sql_answer(sql_answer)

            # 行权限过滤（复刻原结构 LLMService.generate_filter）
            # 只对普通用户（非管理员 id=1）进行权限过滤
            if self._is_normal_user() and sql_answer:
                # 从 SQL 答案中获取涉及的表
                try:
                    sql_data = orjson.loads(sql_answer)
                    tables = sql_data.get('tables', []) if isinstance(sql_data, dict) else []
                except Exception:
                    tables = []
                sql_result = self._generate_filter(sql, tables) if tables else None
                if sql_result:
                    SQLBotLogUtil.info(sql_result)
                    sql = self._check_save_sql(res=sql_result)
            # 管理员也需要解析 SQL（用于后续执行）
            elif sql_answer:
                sql = self._check_save_sql(res=sql_answer)

            # 更新标题
            if self._change_title and self.context.question:
                brief = self._get_brief_from_sql_answer(sql_answer)
                llm_brief_generated = bool(brief)
                if llm_brief_generated or self.context.question.strip() != '':
                    save_brief = brief if (brief and brief != '') else self.context.question.strip()[:20]
                    self._result.update_chat = ChatUpdate(
                        brief=save_brief,
                        brief_generate=llm_brief_generated,
                    )
                    yield StreamEvent(type="brief", data={"brief": save_brief})

            # 格式化并返回 SQL
            format_sql = self._format_sql(sql)
            yield StreamEvent(type="sql", data={"content": format_sql})

            # 5. 检查是否需要停止
            if finish_step.value <= ChatFinishStep.GENERATE_SQL.value:
                yield StreamEvent(type="finish", data={})
                self._result.finish = True
                self._result.finish_time = datetime.now()
                return self._result

            # 6. 执行 SQL
            result = self._execute_sql(sql)

            # 处理大数据
            _data = DataFormat.convert_large_numbers_in_object_array(result.get('data', []))
            result["data"] = _data
            limit = 1000
            if _data and len(_data) > limit and self.context.enable_query_limit:
                result["data"] = _data[:limit]
                result["limit"] = limit

            # 保存执行数据
            self._result.data = orjson.dumps(result).decode()
            yield StreamEvent(type="sql-data", data={"content": "execute-success"})

            # 7. 检查是否需要停止
            if finish_step.value <= ChatFinishStep.QUERY_DATA.value:
                yield StreamEvent(type="finish", data={})
                self._result.finish = True
                self._result.finish_time = datetime.now()
                return self._result

            # 8. 生成图表
            yield StreamEvent(type="info", data={"msg": "chart generated"})
            chart = {}
            if self.context.ai_model:
                for event in self._generate_chart(sql, chart_type or ""):
                    yield event

                # 解析图表配置
                SQLBotLogUtil.info(f"[AlgorithmEngine] 图表生成完成, chart_answer长度={len(self._result.chart_answer) if self._result.chart_answer else 0}")
                if self._result.chart_answer:
                    # 提取内层 content（chart_answer 格式为 {"content": "..."}）
                    chart_content = self._extract_sql_content(self._result.chart_answer)
                    chart = self._parse_chart_config(chart_content)
                    SQLBotLogUtil.info(f"[AlgorithmEngine] 图表解析结果: {chart}")

                # 保存图表
                if chart:
                    self._result.chart = orjson.dumps(chart).decode()
                    yield StreamEvent(type="chart", data={"content": orjson.dumps(chart).decode()})
                else:
                    SQLBotLogUtil.warning(f"[AlgorithmEngine] 图表配置为空, chart_answer={self._result.chart_answer[:200] if self._result.chart_answer else 'None'}")

            # 9. 完成
            self._result.finish = True
            self._result.finish_time = datetime.now()

            # 添加日志
            if self._current_log:
                self._result.logs.append(self._current_log)

            yield StreamEvent(type="finish", data={})

        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)

            if isinstance(e, SingleMessageError):
                pass  # Use as-is
            elif isinstance(e, SQLBotDBConnectionError):
                error_msg = orjson.dumps({'message': error_msg, 'type': 'db-connection-err'}).decode()
            elif isinstance(e, SQLBotDBError):
                error_msg = orjson.dumps({
                    'message': 'Execute SQL Failed',
                    'traceback': str(e),
                    'type': 'exec-sql-err'
                }).decode()
            else:
                error_msg = orjson.dumps({
                    'message': error_msg,
                    'traceback': traceback.format_exc(limit=1)
                }).decode()

            yield StreamEvent(type="error", data={"content": error_msg, "type": "error"})
            self._result.error = error_msg
            self._result.finish = True
            self._result.finish_time = datetime.now()

        return self._result

    def get_result(self) -> AlgorithmResult:
        """获取执行结果"""
        return self._result

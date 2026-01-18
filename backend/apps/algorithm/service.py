# backend/apps/algorithm/service.py
import traceback
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import orjson
import sqlparse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from apps.ai_model.model_factory import LLMFactory
from apps.algorithm.result import AlgorithmLog, AlgorithmResult, OperationType
from apps.algorithm.schema import AlgorithmInput
from apps.db.db import exec_sql
from apps.template.template import get_base_template
from common.error import SingleMessageError
from common.utils.data_format import DataFormat
from common.utils.utils import SQLBotLogUtil, extract_nested_json

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
        self.sql_message: list[BaseMessage | dict] = []
        self.chart_message: list[BaseMessage | dict] = []
        self.llm = None
        self.ds = None
        self.chunk_list: list = []  # 用于缓存流式输出
        self.future = None  # 用于异步执行
        self.record = None  # 记录
        self.articles_number = input_data.articles_number or 4  # 推荐问题数量

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

    def _generate_sql(self) -> Iterator[dict[str, Any]]:
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

    def _check_sql(self, res: str) -> tuple[str, list | None]:
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

    def _execute_sql(self, sql: str) -> dict[str, Any]:
        """执行 SQL"""
        SQLBotLogUtil.info(f"Executing SQL on ds_id {self.input.datasource_id}: {sql}")
        try:
            from apps.datasource.models.datasource import CoreDatasource
            ds = CoreDatasource(id=self.input.datasource_id, type=self.input.engine_type)
            return exec_sql(ds=ds, sql=sql, origin_column=False)
        except Exception as e:
            raise SingleMessageError(f"SQL execution failed: {str(e)}")

    def _generate_chart(self) -> Iterator[dict[str, Any]]:
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

    def _check_chart(self, res: str) -> dict[str, Any]:
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

    def set_record(self, record):
        """设置记录"""
        self.result.record_id = record.id
        self.record = record

    def set_articles_number(self, articles_number: int):
        """设置推荐问题数量"""
        self.articles_number = articles_number
        self.input.articles_number = articles_number

    def run_recommend_questions_task_async(self):
        """异步运行推荐问题任务"""
        self.future = executor.submit(self.run_recommend_questions_task_cache)

    def run_recommend_questions_task_cache(self):
        """缓存推荐问题任务结果"""
        for chunk in self.run_recommend_questions_task():
            self.chunk_list.append(chunk)

    def run_recommend_questions_task(self) -> Iterator[dict[str, Any]]:
        """
        生成推荐问题

        遵循原实现的流程：
        1. 获取表结构
        2. 获取用户历史问题
        3. 构建消息
        4. 调用 LLM 生成推荐问题
        5. 保存结果
        """
        from apps.datasource.crud.datasource import get_table_schema

        try:
            # 获取表结构
            if self.input.db_schema == "":
                self.input.db_schema = get_table_schema(
                    session=None,  # 不需要 session，因为已经获取了表结构
                    current_user=None,
                    ds=self.ds,
                    question=self.input.question,
                    embedding=False
                )

            # 获取历史问题
            old_questions = self.input.old_questions or []

            # 构建消息
            guess_msg: list[BaseMessage] = []
            guess_msg.append(SystemMessage(content=self.input.guess_sys_question(self.input.articles_number)))
            guess_msg.append(HumanMessage(content=self.input.guess_user_question(orjson.dumps(old_questions).decode())))

            _debug_log("RECOMMEND_QUESTIONS", "Generating recommend questions", {
                "articles_number": self.input.articles_number,
                "old_questions_count": len(old_questions)
            })

            # 调用 LLM 生成
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

            # 记录日志
            self.result.logs.append(AlgorithmLog(
                operation=OperationType.GENERATE_RECOMMENDED_QUESTIONS,
                ai_modal_id=self.input.ai_modal_id,
                ai_modal_name=self.input.ai_modal_name,
                full_message=[{'type': msg.type, 'content': msg.content} for msg in guess_msg],
                reasoning_content=full_thinking,
                token_usage=token_usage
            ))

            # 保存推荐问题结果
            self.result.recommended_questions = full_guess_text

            yield {'recommended_question': full_guess_text}

            _debug_log("RECOMMEND_QUESTIONS", "Generated recommend questions", {
                "length": len(full_guess_text)
            })

        except Exception:
            traceback.print_exc()
            yield {'content': str(traceback.format_exc()), 'type': 'error'}


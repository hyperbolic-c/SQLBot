"""
Business Database Service
Provides pre-loading and post-processing of business data for algorithm processing.
"""

import json
from datetime import datetime
from typing import Optional, List, Any, Dict, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_

from apps.datasource.utils.utils import aes_decrypt
from common.core.config import settings
from common.utils.utils import SQLBotLogUtil

from .repository import (
    ChatRepository,
    ChatRecordRepository,
    ChatLogRepository,
    DatasourceRepository,
    TerminologyRepository,
    DataTrainingRepository,
    AiModelRepository,
)
from .context import (
    AlgorithmContext,
    TerminologyContext,
    DataTrainingContext,
    ChatHistoryContext,
    DatasourceContext,
    AiModelContext,
    TableSchemaContext,
    UserContext,
)
from .result import AlgorithmResult, ChatLogCreate, ChatUpdate


class BusinessDBService:
    """
    业务数据库服务

    职责：
    1. 预处理：在算法执行前从业务数据库加载所有必要数据
    2. 后处理：在算法执行后批量保存所有结果
    """

    def __init__(self, session: Session):
        self.session = session
        self._last_result = None  # 存储上次执行结果
        self.chat_repo = ChatRepository(session)
        self.record_repo = ChatRecordRepository(session)
        self.log_repo = ChatLogRepository(session)
        self.ds_repo = DatasourceRepository(session)
        self.term_repo = TerminologyRepository(session)
        self.training_repo = DataTrainingRepository(session)
        self.model_repo = AiModelRepository(session)

    def _get_terminology_template(
        self,
        oid: int,
        question: str,
        datasource_id: Optional[int] = None
    ) -> str:
        """
        获取格式化后的专业术语模板
        复刻 apps.terminology.curd.terminology.get_terminology_template
        """
        try:
            from apps.terminology.curd.terminology import (
                select_terminology_by_word,
                to_xml_string,
                get_base_terminology_template
            )
            _results = select_terminology_by_word(self.session, question, oid, datasource_id)
            if _results and len(_results) > 0:
                terminology = to_xml_string(_results)
                template = get_base_terminology_template().format(terminologies=terminology)
                return template
            return ''
        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取专业术语模板失败: {e}")
            return ''

    def _get_training_template(
        self,
        oid: int,
        question: str,
        datasource_id: Optional[int] = None,
        advanced_application_id: Optional[int] = None
    ) -> str:
        """
        获取格式化后的训练数据模板
        复刻 apps.data_training.curd.data_training.get_training_template
        """
        try:
            from apps.data_training.curd.data_training import (
                select_training_by_question,
                to_xml_string as training_to_xml_string,
                get_base_data_training_template
            )
            _results = select_training_by_question(
                self.session, question, oid, datasource_id, advanced_application_id
            )
            if _results and len(_results) > 0:
                data_training = training_to_xml_string(_results)
                template = get_base_data_training_template().format(data_training=data_training)
                return template
            return ''
        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取训练数据模板失败: {e}")
            return ''

    def _get_custom_prompt(
        self,
        oid: int,
        datasource_id: Optional[int] = None
    ) -> str:
        """
        获取自定义提示词
        """
        try:
            from sqlbot_xpack.custom_prompt.curd.custom_prompt import find_custom_prompts
            from sqlbot_xpack.custom_prompt.models.custom_prompt_model import CustomPromptTypeEnum

            from sqlbot_xpack.license.license_manage import SQLBotLicenseUtil
            if not SQLBotLicenseUtil.valid():
                return ""

            prompts = find_custom_prompts(
                self.session,
                CustomPromptTypeEnum.GENERATE_SQL,
                oid,
                datasource_id
            )
            if prompts:
                return "\n".join([p.content for p in prompts if p.content])
            return ""
        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取自定义提示词失败: {e}")
            return ""

    def _get_chat_history_messages(
        self,
        chat_id: int,
        limit: int = 20
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        获取聊天历史消息
        返回: (sql_messages, chart_messages)
        """
        try:
            logs = self.log_repo.get_chat_logs(chat_id, limit)
            sql_messages = []
            chart_messages = []

            for log in logs:
                msg = {
                    'type': 'ai' if log.operate in [OperationEnum.GENERATE_SQL.value, '0'] else 'human',
                    'content': log.messages[-1]['content'] if log.messages else '',
                    'reasoning_content': log.reasoning_content,
                }
                if log.operate in [OperationEnum.GENERATE_SQL.value, '0']:
                    sql_messages.append(msg)
                elif log.operate == OperationEnum.GENERATE_CHART.value:
                    chart_messages.append(msg)

            return sql_messages, chart_messages
        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取聊天历史失败: {e}")
            return [], []

    def _get_table_schema(
        self,
        ds_id: int,
        question: str,
        embedding_enabled: bool = True
    ) -> str:
        """
        获取表结构
        复刻 apps.datasource.crud.datasource.get_table_schema
        """
        try:
            from apps.datasource.crud.datasource import get_table_schema as original_get_table_schema

            # 需要传入 current_user，这里简化处理
            # 在实际使用中需要传入正确的用户
            class FakeUser:
                oid = 1

            ds = self.ds_repo.get_datasource(ds_id)
            if not ds:
                return "[]"

            # 使用仓储的方式获取表结构
            tables_json, fields_json = self.ds_repo.get_table_schema(ds_id, embedding_enabled)

            # 如果启用了 embedding，需要进行向量检索
            if embedding_enabled and settings.TABLE_EMBEDDING_ENABLED:
                try:
                    from apps.datasource.embedding.ds_embedding import get_ds_embedding
                    embedding_results = get_ds_embedding(
                        self.session,
                        FakeUser(),
                        ds,
                        question,
                        settings.TABLE_EMBEDDING_COUNT
                    )
                    if embedding_results:
                        # 使用 embedding 结果构建 schema
                        tables = json.loads(tables_json) if tables_json else []
                        fields = json.loads(fields_json) if fields_json else []

                        # 只保留相关的表和字段
                        relevant_table_ids = set()
                        relevant_field_ids = set()
                        for result in embedding_results:
                            if result.get('table_id'):
                                relevant_table_ids.add(result['table_id'])
                            if result.get('field_id'):
                                relevant_field_ids.add(result['field_id'])

                        # 过滤
                        tables = [t for t in tables if t.get('id') in relevant_table_ids]
                        fields = [f for f in fields if f.get('id') in relevant_field_ids]

                        return json.dumps(tables, ensure_ascii=False), json.dumps(fields, ensure_ascii=False)
                except Exception as embed_e:
                    SQLBotLogUtil.warning(f"[BusinessDBService] embedding 查询失败: {embed_e}")

            return tables_json, fields_json
        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取表结构失败: {e}")
            return "[]", "[]"

    def preprocess(
        self,
        user_id: int,
        workspace_id: int,
        oid: int,
        chat_id: Optional[int],
        question: str,
        datasource_id: Optional[int] = None,
        ai_model_id: Optional[int] = None,
        regenerate_record_id: Optional[int] = None,
        language: str = "zh-CN",
        error_msg: str = "",
    ) -> AlgorithmContext:
        """
        预处理：从业务数据库加载所有必要数据

        这个方法复刻了原 LLMService.__init__ 和 run_task 中的数据查询逻辑，
        将所有业务数据库查询前置到这里，算法执行过程中不再查询业务数据库。

        Returns:
            AlgorithmContext: 包含所有预加载数据的上下文对象
        """
        SQLBotLogUtil.info(f"[BusinessDBService] 开始预处理, chat_id={chat_id}")

        # 1. 获取聊天会话
        chat = None
        if chat_id:
            chat = self.chat_repo.get_chat(chat_id)

        # 2. 获取数据源配置
        datasource_context = None
        engine = ""
        actual_ds_id = datasource_id

        if chat and chat.datasource:
            actual_ds_id = chat.datasource

        if actual_ds_id:
            ds = self.ds_repo.get_datasource(actual_ds_id)
            if ds:
                datasource_context = DatasourceContext(
                    id=ds.id,
                    name=ds.name,
                    type=ds.type,
                    description=ds.description,
                    configuration=ds.configuration,
                    table_relation=ds.table_relation,
                )
                engine = ds.type
                SQLBotLogUtil.info(f"[BusinessDBService] 获取数据源: {ds.name}, type={ds.type}")
            else:
                SQLBotLogUtil.warning(f"[BusinessDBService] 数据源不存在: {actual_ds_id}")

        # 3. 获取表结构 (如果启用了 embedding)
        tables_json = "[]"
        fields_json = "[]"
        if datasource_context and settings.TABLE_EMBEDDING_ENABLED:
            try:
                tables_json, fields_json = self._get_table_schema(
                    datasource_context.id,
                    question,
                    embedding_enabled=True
                )
                SQLBotLogUtil.info(f"[BusinessDBService] 获取表结构完成")
            except Exception as e:
                SQLBotLogUtil.error(f"[BusinessDBService] 获取表结构失败: {e}")

        # 4. 获取格式化后的专业术语
        terminology_template = ""
        if datasource_context:
            terminology_template = self._get_terminology_template(
                oid, question, datasource_context.id
            )
        else:
            terminology_template = self._get_terminology_template(oid, question, None)
        SQLBotLogUtil.info(f"[BusinessDBService] 专业术语模板长度: {len(terminology_template)}")

        # 5. 获取格式化后的训练数据
        data_training_template = ""
        if datasource_context:
            data_training_template = self._get_training_template(
                oid, question, datasource_context.id, None
            )
        SQLBotLogUtil.info(f"[BusinessDBService] 训练数据模板长度: {len(data_training_template)}")

        # 6. 获取自定义提示词
        custom_prompt = ""
        try:
            if datasource_context:
                custom_prompt = self._get_custom_prompt(oid, datasource_context.id)
            else:
                custom_prompt = self._get_custom_prompt(oid, None)
        except Exception as e:
            SQLBotLogUtil.warning(f"[BusinessDBService] 获取自定义提示词失败 (可能未授权): {e}")
        SQLBotLogUtil.info(f"[BusinessDBService] 自定义提示词长度: {len(custom_prompt)}")

        # 7. 获取聊天历史消息
        sql_messages = []
        chart_messages = []
        if chat_id:
            sql_messages, chart_messages = self._get_chat_history_messages(chat_id, limit=20)
        SQLBotLogUtil.info(f"[BusinessDBService] 聊天历史: SQL={len(sql_messages)}, Chart={len(chart_messages)}")

        # 8. 获取 AI 模型配置
        ai_model_context = None
        model_config = {}
        model = None
        if ai_model_id:
            model = self.model_repo.get_ai_model(ai_model_id)
            if model:
                # 解密 API key
                try:
                    api_key = aes_decrypt(model.api_key) if model.api_key else ""
                except Exception:
                    api_key = ""
                ai_model_context = AiModelContext(
                    id=model.id,
                    name=model.name,
                    model_type=model.model_type,
                    base_model=model.base_model,
                    supplier=model.supplier,
                    protocol=model.protocol,
                    api_domain=model.api_domain,
                    api_key=api_key,
                    config=model.config,
                )
                # 解析配置
                if model.config:
                    try:
                        model_config = json.loads(model.config)
                    except Exception:
                        pass
                SQLBotLogUtil.info(f"[BusinessDBService] 获取 AI 模型: {model.name}")

        # 9. 构建上下文 - 包含所有预加载的数据
        # 创建用户上下文
        user_context = UserContext(
            id=user_id,
            workspace_id=workspace_id,
            oid=oid,
        )

        context = AlgorithmContext(
            user_id=user_id,
            workspace_id=workspace_id,
            oid=oid,
            user_context=user_context,
            chat_id=chat_id,
            question=question,
            regenerate_record_id=regenerate_record_id,
            terminologies=[],  # 预加载的数据已转换为模板字符串
            data_training=[],
            chat_history=[],  # 预加载的消息历史
            datasource=datasource_context,
            table_schema=TableSchemaContext(
                tables=json.loads(tables_json) if tables_json != "[]" else [],
                fields=json.loads(fields_json) if fields_json != "[]" else [],
            ) if datasource_context else None,
            engine=engine,
            ai_model=ai_model_context,
            model_config=model_config,
            language=language,
            error_msg=error_msg,

            # 预加载的格式化数据
            terminology_template=terminology_template,
            data_training_template=data_training_template,
            custom_prompt=custom_prompt,
            sql_history_messages=sql_messages,
            chart_history_messages=chart_messages,
            tables_json=tables_json,
            fields_json=fields_json,

            # Chat 配置
            chat_brief_generate=chat.brief_generate if chat else False,
            chat_engine_type=chat.engine_type if chat else "",
        )

        SQLBotLogUtil.info(f"[BusinessDBService] 预处理完成")
        return context

    def create_record(
        self,
        chat_id: int,
        question: str,
        user_id: int,
        datasource_id: Optional[int] = None,
        engine_type: Optional[str] = None,
        ai_model_id: Optional[int] = None,
        regenerate_record_id: Optional[int] = None,
    ) -> int:
        """
        创建新的聊天记录
        复刻 apps.chat.curd.chat.save_question
        """
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update
        from apps.chat.curd.chat import get_chat_record_by_id

        record = ChatRecord(
            chat_id=chat_id,
            question=question,
            create_time=datetime.datetime.now(),
            create_by=user_id,
            datasource=datasource_id,
            engine_type=engine_type,
            ai_modal_id=ai_model_id,
            regenerate_record_id=regenerate_record_id,
        )
        self.session.add(record)
        self.session.flush()
        self.session.refresh(record)
        return record.id

    def save_sql_answer(self, record_id: int, answer: str):
        """保存 SQL 答案"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            sql_answer=answer,
        )
        self.session.execute(stmt)
        self.session.commit()

    def save_sql(self, record_id: int, sql: str):
        """保存 SQL"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            sql=sql,
        )
        self.session.execute(stmt)
        self.session.commit()

    def save_chart_answer(self, record_id: int, answer: str):
        """保存图表答案"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            chart_answer=answer,
        )
        self.session.execute(stmt)
        self.session.commit()

    def save_chart(self, record_id: int, chart: str):
        """保存图表"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            chart=chart,
        )
        self.session.execute(stmt)
        self.session.commit()

    def save_sql_data(self, record_id: int, data: str):
        """保存 SQL 执行数据"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            data=data,
        )
        self.session.execute(stmt)
        self.session.commit()

    def save_error(self, record_id: int, message: str):
        """保存错误信息"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            error=message,
            finish=True,
            finish_time=datetime.datetime.now(),
        )
        self.session.execute(stmt)
        self.session.commit()

    def finish_record(self, record_id: int):
        """完成记录"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(
            finish=True,
            finish_time=datetime.datetime.now(),
        )
        self.session.execute(stmt)
        self.session.commit()

    def update_chat_brief(self, chat_id: int, brief: str, brief_generate: bool = False):
        """更新聊天标题"""
        from apps.chat.models.chat_model import Chat
        from sqlalchemy import update

        stmt = update(Chat).where(Chat.id == chat_id).values(
            brief=brief[:20] if len(brief) > 20 else brief,
            brief_generate=brief_generate,
        )
        self.session.execute(stmt)
        self.session.commit()

    def postprocess(self, result: AlgorithmResult):
        """
        后处理：批量保存算法结果
        """
        SQLBotLogUtil.info(f"[BusinessDBService] 开始后处理, record_id={result.record_id}")

        # 1. 保存 SQL 相关
        if result.sql_answer:
            self.save_sql_answer(result.record_id, result.sql_answer)
        if result.sql:
            self.save_sql(result.record_id, result.sql)

        # 2. 保存图表相关
        if result.chart_answer:
            self.save_chart_answer(result.record_id, result.chart_answer)
        if result.chart:
            self.save_chart(result.record_id, result.chart)

        # 3. 保存执行数据
        if result.data:
            self.save_sql_data(result.record_id, result.data)

        # 4. 保存错误信息
        if result.error:
            self.save_error(result.record_id, result.error)

        # 5. 完成记录
        if result.finish:
            self.finish_record(result.record_id)

        # 6. 更新聊天标题
        if result.update_chat and result.update_chat.brief:
            self.update_chat_brief(
                result.chat_id,
                result.update_chat.brief,
                result.update_chat.brief_generate
            )

        SQLBotLogUtil.info(f"[BusinessDBService] 后处理完成")

    def create_chat(self, user_id: int, question: str, datasource: Optional[int] = None) -> int:
        """创建新的聊天会话"""
        chat = self.chat_repo.create_chat(
            create_by=user_id,
            question=question,
            datasource=datasource,
        )
        return chat.id

    def process(
        self,
        user_id: int,
        workspace_id: int,
        oid: int,
        chat_id: Optional[int],
        question: str,
        datasource_id: Optional[int] = None,
        ai_model_id: Optional[int] = None,
        regenerate_record_id: Optional[int] = None,
        language: str = "zh-CN",
        error_msg: str = "",
        finish_step: Any = None,
        in_chat: bool = True,
        stream: bool = True,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        主入口：处理用户问题

        这是业务数据层的主入口方法，由 API 层调用。
        流程：
        1. preprocess() - 预处理，加载所有业务数据
        2. AlgorithmEngine.run() - 算法处理
        3. postprocess() - 后处理，批量保存结果

        Args:
            user_id: 用户 ID
            workspace_id: 工作空间 ID
            oid: 组织 ID
            chat_id: 聊天会话 ID
            question: 用户问题
            datasource_id: 数据源 ID
            ai_model_id: AI 模型 ID
            regenerate_record_id: 重新生成记录 ID
            language: 语言
            error_msg: 错误信息
            finish_step: 完成步骤
            in_chat: 是否在聊天中
            stream: 是否流式返回

        Yields:
            Dict: 流式事件数据
        """
        from apps.algorithm.engine import AlgorithmEngine, StreamEvent
        from apps.chat.models.chat_model import ChatFinishStep

        SQLBotLogUtil.info(f"[BusinessDBService] 开始处理问题, chat_id={chat_id}")

        # 1. 预处理：加载所有必要数据
        context = self.preprocess(
            user_id=user_id,
            workspace_id=workspace_id,
            oid=oid,
            chat_id=chat_id,
            question=question,
            datasource_id=datasource_id,
            ai_model_id=ai_model_id,
            regenerate_record_id=regenerate_record_id,
            language=language,
            error_msg=error_msg,
        )

        # 2. 获取数据源 ID 和类型
        datasource_id = context.datasource.id if context.datasource else None
        engine_type = context.datasource.type if context.datasource else ""

        # 3. 创建聊天记录
        if regenerate_record_id:
            record_id = self.create_record(
                chat_id=chat_id,
                question=question,
                user_id=user_id,
                datasource_id=datasource_id,
                engine_type=engine_type,
                ai_model_id=ai_model_id,
                regenerate_record_id=regenerate_record_id,
            )
        else:
            record_id = self.create_record(
                chat_id=chat_id,
                question=question,
                user_id=user_id,
                datasource_id=datasource_id,
                engine_type=engine_type,
                ai_model_id=ai_model_id,
            )

        # 4. 创建算法引擎
        engine = AlgorithmEngine(context, session=self.session)

        # 5. 执行算法
        finish_step = finish_step or ChatFinishStep.GENERATE_CHART
        for event in engine.run(
            record_id=record_id,
            finish_step=finish_step,
            in_chat=in_chat,
        ):
            yield {'type': event.type, **event.data}

        # 6. 后处理：保存结果
        result = engine.get_result()
        if result:
            self.postprocess(result)

        SQLBotLogUtil.info(f"[BusinessDBService] 处理完成")

    def get_result(self) -> Optional['AlgorithmResult']:
        """获取上次执行的结果"""
        return self._last_result

    def set_result(self, result: 'AlgorithmResult'):
        """设置执行结果"""
        self._last_result = result

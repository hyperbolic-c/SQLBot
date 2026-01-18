"""
Business Database Service
Provides pre-loading and post-processing of business data for algorithm processing.
"""

import asyncio
import json
from datetime import datetime as dt
from typing import Optional, List, Any, Dict, Tuple, Generator

from sqlalchemy.orm import Session
from sqlalchemy import or_

from apps.chat.models.chat_model import OperationEnum
from common.core.config import settings
from common.utils.crypto import sqlbot_decrypt
from common.utils.utils import SQLBotLogUtil, SSEDebugLogUtil, orjson

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
        # 防止commit后对象过期，确保已提交的数据仍可读取
        self.session.expire_on_commit = False
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

    def _get_old_questions(self, datasource_id: int) -> List[str]:
        """
        获取同一数据源的历史问题（用于生成推荐问题）
        """
        try:
            from apps.chat.models.chat_model import ChatRecord
            from sqlalchemy import select, and_

            if not datasource_id:
                return []

            stmt = select(ChatRecord.question).where(
                and_(
                    ChatRecord.datasource == datasource_id,
                    ChatRecord.question.isnot(None),
                    ChatRecord.error.is_(None)
                )
            ).order_by(ChatRecord.create_time.desc()).limit(20)

            result = self.session.execute(stmt)
            records = [r.question for r in result if r.question]
            return records
        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取历史问题失败: {e}")
            return []

    def _get_table_schema(
        self,
        current_user,
        ds_id: int,
        question: str,
        embedding_enabled: bool = True
    ) -> tuple:
        """
        获取表结构

        复刻 apps.datasource.crud.datasource.get_table_schema
        返回格式与原结构一致，用于算法引擎构建 schema 文本

        Returns:
            tuple: (schema_str, tables_json, fields_json)
                - schema_str: 原始格式的表结构字符串（与原结构一致）
                - tables_json: JSON 格式的表信息列表
                - fields_json: JSON 格式的字段信息列表
        """
        try:
            from apps.datasource.crud.datasource import get_table_obj_by_ds
            from apps.datasource.models.datasource import CoreDatasource

            ds = self.ds_repo.get_datasource(ds_id)
            if not ds:
                return "", "[]", "[]"

            # 获取表对象（包含字段信息）- 复刻原结构
            table_objs = get_table_obj_by_ds(
                session=self.session,
                current_user=current_user,
                ds=ds
            )

            if len(table_objs) == 0:
                return "", "[]", "[]"

            # 构建表结构列表（用于 JSON 格式）
            tables = []
            fields = []

            for obj in table_objs:
                table_id = len(tables) + 1
                table = obj.table
                tables.append({
                    "id": table_id,
                    "tableName": table.table_name,
                    "tableComment": table.custom_comment or table.table_comment or ""
                })

                # 解析字段
                if obj.fields:
                    for field in obj.fields:
                        fields.append({
                            "id": len(fields) + 1,
                            "tableId": table_id,
                            "fieldName": field.field_name,
                            "fieldType": field.field_type or "",
                            "fieldComment": field.custom_comment or field.field_comment or ""
                        })

            tables_json = str(tables).replace("'", '"')
            fields_json = str(fields).replace("'", '"')

            # 构建原始格式的 schema 字符串（与原结构 get_table_schema 一致）
            schema_str = ""
            db_name = table_objs[0].schema if table_objs else ""
            schema_str += f"【DB_ID】 {db_name}\n【Schema】\n"

            for obj in table_objs:
                schema_table = ''
                schema_table += f"# Table: {db_name}.{obj.table.table_name}" if ds.type != "mysql" and ds.type != "es" else f"# Table: {obj.table.table_name}"
                table_comment = ''
                if obj.table.custom_comment:
                    table_comment = obj.table.custom_comment.strip()
                if table_comment == '':
                    schema_table += '\n[\n'
                else:
                    schema_table += f", {table_comment}\n[\n"

                if obj.fields:
                    field_list = []
                    for field in obj.fields:
                        field_comment = ''
                        if field.custom_comment:
                            field_comment = field.custom_comment.strip()
                        if field_comment == '':
                            field_list.append(f"({field.field_name}:{field.field_type})")
                        else:
                            field_list.append(f"({field.field_name}:{field.field_type}, {field_comment})")
                    schema_table += ",\n".join(field_list)
                schema_table += '\n]\n'
                schema_str += schema_table

            SQLBotLogUtil.info(f"[BusinessDBService] 获取表结构完成, 表数量={len(tables)}, 字段数量={len(fields)}")
            return schema_str, tables_json, fields_json

        except Exception as e:
            SQLBotLogUtil.error(f"[BusinessDBService] 获取表结构失败: {e}")
            import traceback
            SQLBotLogUtil.error(f"[BusinessDBService] 异常详情: {traceback.format_exc()}")
            return "", "[]", "[]"

    def preprocess(
        self,
        current_user,
        chat_id: Optional[int],
        question: str,
        datasource_id: Optional[int] = None,
        ai_model_id: Optional[int] = None,
        regenerate_record_id: Optional[int] = None,
        language: str = "zh-CN",
        error_msg: str = "",
        record_id: Optional[int] = None,
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

        # 3. 获取表结构
        tables_json = "[]"
        fields_json = "[]"
        db_schema = ""
        if datasource_context:
            try:
                # embedding_enabled 由 TABLE_EMBEDDING_ENABLED 配置决定
                embedding_enabled = settings.TABLE_EMBEDDING_ENABLED
                db_schema, tables_json, fields_json = self._get_table_schema(
                    current_user,
                    datasource_context.id,
                    question,
                    embedding_enabled=embedding_enabled
                )
            except Exception as e:
                SQLBotLogUtil.error(f"[BusinessDBService] 获取表结构失败: {e}")

        # 4. 获取格式化后的专业术语
        terminology_template = ""
        if current_user is not None:
            user_oid = current_user.oid
            if datasource_context:
                terminology_template = self._get_terminology_template(
                    user_oid, question, datasource_context.id
                )
            else:
                terminology_template = self._get_terminology_template(user_oid, question, None)
        SQLBotLogUtil.info(f"[BusinessDBService] 专业术语模板长度: {len(terminology_template)}")

        # 5. 获取格式化后的训练数据
        data_training_template = ""
        if current_user is not None and datasource_context:
            data_training_template = self._get_training_template(
                current_user.oid, question, datasource_context.id, None
            )
        SQLBotLogUtil.info(f"[BusinessDBService] 训练数据模板长度: {len(data_training_template)}")

        # 6. 获取自定义提示词
        custom_prompt = ""
        try:
            if current_user is not None:
                if datasource_context:
                    custom_prompt = self._get_custom_prompt(current_user.oid, datasource_context.id)
                else:
                    custom_prompt = self._get_custom_prompt(current_user.oid, None)
        except Exception as e:
            SQLBotLogUtil.warning(f"[BusinessDBService] 获取自定义提示词失败 (可能未授权): {e}")
        SQLBotLogUtil.info(f"[BusinessDBService] 自定义提示词长度: {len(custom_prompt)}")

        # 7. 获取聊天历史消息
        sql_messages = []
        chart_messages = []
        if chat_id:
            sql_messages, chart_messages = self._get_chat_history_messages(chat_id, limit=20)
        SQLBotLogUtil.info(f"[BusinessDBService] 聊天历史: SQL={len(sql_messages)}, Chart={len(chart_messages)}")

        # 7.5 获取历史问题（用于生成推荐问题）
        old_questions = []
        if datasource_id:
            old_questions = self._get_old_questions(datasource_id)
        SQLBotLogUtil.info(f"[BusinessDBService] 历史问题数量: {len(old_questions)}")

        # 8. 获取 AI 模型配置
        ai_model_context = None
        model_config = {}
        model = None
        if ai_model_id:
            model = self.model_repo.get_ai_model(ai_model_id)
            if model:
                # 解密 API domain 和 API key（复刻 get_default_config 的逻辑）
                try:
                    api_domain = model.api_domain
                    if not api_domain.startswith("http"):
                        api_domain = asyncio.run(sqlbot_decrypt(api_domain))
                    api_key = asyncio.run(sqlbot_decrypt(model.api_key)) if model.api_key else ""
                except Exception as e:
                    SQLBotLogUtil.error(f"[BusinessDBService] 解密 API 配置失败: {e}")
                    api_domain = model.api_domain
                    api_key = ""
                ai_model_context = AiModelContext(
                    id=model.id,
                    name=model.name,
                    model_type=model.model_type,
                    base_model=model.base_model,
                    supplier=model.supplier,
                    protocol=model.protocol,
                    api_domain=api_domain,
                    api_key=api_key,
                    config=model.config,
                )
                # 解析配置
                if model.config:
                    try:
                        model_config = json.loads(model.config)
                    except Exception:
                        pass
                SQLBotLogUtil.info(f"[BusinessDBService] 获取 AI 模型: {model.name}, api_domain={api_domain}")

        # 9. 构建上下文 - 包含所有预加载的数据
        # 创建用户上下文
        user_context = None
        user_id = None
        workspace_id = None
        oid = None
        if current_user is not None:
            user_id = current_user.id
            workspace_id = current_user.oid
            oid = current_user.oid
            user_context = UserContext(
                id=current_user.id,
                workspace_id=current_user.oid,  # 使用 oid 作为 workspace_id
                oid=current_user.oid,
            )

        context = AlgorithmContext(
            user_id=user_id,
            workspace_id=workspace_id,  # 使用 oid 作为 workspace_id
            oid=oid,
            user_context=user_context,
            chat_id=chat_id,
            chat_record_id=record_id,  # 记录 ID
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
            db_schema=db_schema,

            # Chat 配置
            chat_brief_generate=chat.brief_generate if chat else False,
            chat_engine_type=chat.engine_type if chat else "",

            # 历史问题
            old_questions=old_questions,
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
            create_time=dt.now(),
            create_by=user_id,
            datasource=datasource_id,
            engine_type=engine_type,
            ai_modal_id=ai_model_id,
            regenerate_record_id=regenerate_record_id,
        )
        self.session.add(record)
        self.session.flush()
        self.session.refresh(record)
        # 必须 commit，确保记录对其他连接可见（原实现有 commit）
        self.session.commit()
        return record.id

    def save_sql_answer(self, record_id: int, answer: str):
        """保存 SQL 答案（立即提交）"""
        self._update_record_field(record_id, sql_answer=answer)
        self.session.flush()
        self.session.commit()

    def save_sql(self, record_id: int, sql: str):
        """保存 SQL（立即提交）"""
        self._update_record_field(record_id, sql=sql)
        self.session.flush()
        self.session.commit()

    def save_chart_answer(self, record_id: int, answer: str):
        """保存图表答案（立即提交）"""
        self._update_record_field(record_id, chart_answer=answer)
        self.session.flush()
        self.session.commit()

    def save_chart(self, record_id: int, chart: str):
        """保存图表（立即提交）"""
        self._update_record_field(record_id, chart=chart)
        self.session.flush()
        self.session.commit()

    def save_sql_data(self, record_id: int, data: str):
        """保存 SQL 执行数据（立即提交）"""
        self._update_record_field(record_id, data=data)
        self.session.flush()
        self.session.commit()

    def save_error(self, record_id: int, message: str):
        """保存错误信息（立即提交）"""
        self._update_record_field(
            record_id,
            error=message,
            finish=True,
            finish_time=dt.now()
        )
        self.session.flush()
        self.session.commit()

    def finish_record(self, record_id: int):
        """完成记录（立即提交）"""
        self._update_record_field(
            record_id,
            finish=True,
            finish_time=dt.now()
        )
        self.session.flush()
        self.session.commit()

    def update_chat_brief(self, chat_id: int, brief: str, brief_generate: bool = False):
        """更新聊天标题（立即提交）"""
        self._update_chat_brief(chat_id, brief, brief_generate)
        self.session.flush()
        self.session.commit()

    def postprocess(self, result: AlgorithmResult):
        """
        后处理：保存剩余数据（finish 标志、chat 标题、推荐问题等）
        注意：大部分数据已在事件处理时同步保存
        """
        SQLBotLogUtil.info(f"[BusinessDBService] postprocess 开始, record_id={result.record_id}")

        try:
            # 1. 保存推荐问题
            if result.recommended_question:
                SQLBotLogUtil.info(f"[BusinessDBService] 保存推荐问题")
                self._update_record_field(
                    result.record_id,
                    recommended_question=result.recommended_question
                )
            if result.recommended_question_answer:
                self._update_record_field(
                    result.record_id,
                    recommended_question_answer=result.recommended_question_answer
                )

            # 2. 设置 finish 标志（必须最后设置，确保数据完整）
            if result.finish:
                SQLBotLogUtil.info(f"[BusinessDBService] 设置 finish=true")
                self._update_record_field(
                    result.record_id,
                    finish=True,
                    finish_time=dt.now()
                )

            # 3. 更新聊天标题
            if result.update_chat and result.update_chat.brief:
                SQLBotLogUtil.info(f"[BusinessDBService] 更新聊天标题: {result.update_chat.brief}")
                self._update_chat_brief(
                    result.chat_id,
                    result.update_chat.brief,
                    result.update_chat.brief_generate
                )

            # 提交事务
            SQLBotLogUtil.info(f"[BusinessDBService] postprocess 执行 flush 和 commit")
            self.session.flush()
            self.session.commit()
            SQLBotLogUtil.info(f"[BusinessDBService] postprocess 完成")
        except Exception as e:
            self.session.rollback()
            SQLBotLogUtil.error(f"[BusinessDBService] postprocess 失败: {e}")
            raise

    def _update_record_field(self, record_id: int, **kwargs):
        """内部方法：更新记录字段"""
        from apps.chat.models.chat_model import ChatRecord
        from sqlalchemy import update

        SQLBotLogUtil.info(f"[DEBUG] _update_record_field: record_id={record_id}, kwargs={list(kwargs.keys())}")
        stmt = update(ChatRecord).where(ChatRecord.id == record_id).values(**kwargs)
        result = self.session.execute(stmt)
        SQLBotLogUtil.info(f"[DEBUG] _update_record_field: rows_affected={result.rowcount}")
        self.session.flush()

    def _update_chat_brief(self, chat_id: int, brief: str, brief_generate: bool = False):
        """内部方法：更新聊天标题"""
        from apps.chat.models.chat_model import Chat
        from sqlalchemy import update

        stmt = update(Chat).where(Chat.id == chat_id).values(
            brief=brief[:20] if len(brief) > 20 else brief,
            brief_generate=brief_generate,
        )
        self.session.execute(stmt)

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
        current_user,
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
            current_user: 用户对象 (UserInfoDTO)
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
            current_user=current_user,
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
                user_id=current_user.id,
                datasource_id=datasource_id,
                engine_type=engine_type,
                ai_model_id=ai_model_id,
                regenerate_record_id=regenerate_record_id,
            )
        else:
            record_id = self.create_record(
                chat_id=chat_id,
                question=question,
                user_id=current_user.id,
                datasource_id=datasource_id,
                engine_type=engine_type,
                ai_model_id=ai_model_id,
            )

        # 4. 创建算法引擎
        engine = AlgorithmEngine(context, session=self.session)

        # 5. 执行算法
        finish_step = finish_step or ChatFinishStep.GENERATE_CHART
        SSEDebugLogUtil.info(f"[SSE DEBUG] ========== BusinessDBService.process 开始 ==========")
        SSEDebugLogUtil.info(f"[SSE DEBUG] record_id={record_id}, finish_step={finish_step}, in_chat={in_chat}")
        event_count = 0
        for event in engine.run(
            record_id=record_id,
            finish_step=finish_step,
            in_chat=in_chat,
        ):
            event_count += 1
            SSEDebugLogUtil.info(f"[SSE DEBUG] ========== 收到事件 #{event_count} ==========")
            SSEDebugLogUtil.info(f"[SSE DEBUG] 事件类型: {event.type}")
            SSEDebugLogUtil.info(f"[SSE DEBUG] 事件数据: {event.data}")

            # 同步保存数据到数据库（与原实现保持一致的保存时机）
            result = engine.get_result()

            # info (sql generated) 事件时保存 sql_answer（SQL 生成完成后）
            if event.type == "info" and result and result.sql_answer:
                SQLBotLogUtil.info(f"[BusinessDBService] 保存 sql_answer (info 事件)")
                self._update_record_field(result.record_id, sql_answer=result.sql_answer)
                self.session.flush()
                self.session.commit()

            # sql 事件时保存 sql（SQL 解析完成后）
            if event.type == "sql" and result and result.sql:
                SQLBotLogUtil.info(f"[BusinessDBService] 保存 sql (sql 事件)")
                self._update_record_field(result.record_id, sql=result.sql)
                self.session.flush()
                self.session.commit()

            # sql-data 事件前保存 data（与原实现 save_sql_data 在 yield 前一致）
            if event.type == "sql-data" and result and result.data:
                SQLBotLogUtil.info(f"[BusinessDBService] 保存 data (sql-data 事件), record_id={result.record_id}")
                self._update_record_field(result.record_id, data=result.data)
                self.session.commit()
                SQLBotLogUtil.info(f"[BusinessDBService] data 已提交, record_id={result.record_id}")

            # chart 事件后保存 chart 和 chart_answer（与原实现一致）
            if event.type == "chart" and result:
                if result.chart:
                    SQLBotLogUtil.info(f"[BusinessDBService] 保存 chart")
                    self._update_record_field(result.record_id, chart=result.chart)
                if result.chart_answer:
                    SQLBotLogUtil.info(f"[BusinessDBService] 保存 chart_answer")
                    self._update_record_field(result.record_id, chart_answer=result.chart_answer)
                if result.chart or result.chart_answer:
                    self.session.flush()
                    self.session.commit()

            # 在 yield finish 事件之前，执行完整的 postprocess
            # 保存剩余的数据（update_chat, finish 标志等）
            if event.type == "finish":
                SSEDebugLogUtil.info(f"[SSE DEBUG] 收到 finish 事件，执行 postprocess")
                self.postprocess(result)
                SSEDebugLogUtil.info(f"[SSE DEBUG] postprocess 完成")

            # 生成 SSE 事件，格式与原实现保持一致
            # 原实现格式: {'content': ..., 'type': '...'}，content 在前，type 在后
            sse_data = {'content': event.data.get('content', event.data.get('msg', '')), 'type': event.type}

            # 对于 id 事件，格式为 {'type': 'id', 'id': ...}
            if event.type == 'id':
                sse_data = {'type': event.type, 'id': event.data.get('id')}
            # 对于 regenerate_record_id 事件
            elif event.type == 'regenerate_record_id':
                sse_data = {'type': event.type, 'regenerate_record_id': event.data.get('regenerate_record_id')}
            # 对于 question 事件
            elif event.type == 'question':
                sse_data = {'type': event.type, 'question': event.data.get('question')}
            # 对于 brief 事件
            elif event.type == 'brief':
                sse_data = {'type': event.type, 'brief': event.data.get('brief')}
            # 对于 info 事件
            elif event.type == 'info':
                sse_data = {'type': event.type, 'msg': event.data.get('msg')}
            # 对于 sql 事件
            elif event.type == 'sql':
                sse_data = {'content': event.data.get('content'), 'type': event.type}
            # 对于 sql-data 事件
            elif event.type == 'sql-data':
                sse_data = {'content': event.data.get('content'), 'type': event.type}
            # 对于 chart 事件
            elif event.type == 'chart':
                sse_data = {'content': event.data.get('content'), 'type': event.type}
            # 对于 chart-result 事件
            elif event.type == 'chart-result':
                sse_data = {'content': event.data.get('content'), 'reasoning_content': event.data.get('reasoning_content'), 'type': event.type}
            # 对于 sql-result 事件
            elif event.type == 'sql-result':
                sse_data = {'content': event.data.get('content'), 'reasoning_content': event.data.get('reasoning_content'), 'type': event.type}
            # 对于 filter-result 事件
            elif event.type == 'filter-result':
                sse_data = {'content': event.data.get('content'), 'reasoning_content': event.data.get('reasoning_content'), 'type': event.type}
            # 对于 error 事件
            elif event.type == 'error':
                sse_data = {'content': event.data.get('content'), 'type': event.type}
            # 对于 finish 事件
            elif event.type == 'finish':
                sse_data = {'type': event.type}
            # 对于 datasource 事件
            elif event.type == 'datasource':
                # 原实现格式: {'id': ..., 'datasource_name': ..., 'engine_type': ..., 'type': 'datasource'}
                sse_data = {
                    'id': event.data.get('id'),
                    'datasource_name': event.data.get('name'),
                    'engine_type': event.data.get('type'),
                    'type': event.type
                }

            # 记录 SSE 数据
            sse_json = orjson.dumps(sse_data).decode()
            SSEDebugLogUtil.info(f"[SSE DEBUG] [SSE OUT #{event_count}] {sse_json}")

            yield sse_data
            SSEDebugLogUtil.info(f"[SSE DEBUG] [SSE OUT #{event_count}] 完成")

        SSEDebugLogUtil.info(f"[SSE DEBUG] ========== BusinessDBService.process 完成 (共 {event_count} 个事件) ==========")

        SQLBotLogUtil.info(f"[BusinessDBService] 处理完成")

    def get_result(self) -> Optional['AlgorithmResult']:
        """获取上次执行的结果"""
        return self._last_result

    def set_result(self, result: 'AlgorithmResult'):
        """设置执行结果"""
        self._last_result = result

    def process_recommend_questions(
        self,
        current_user,
        record_id: int,
        articles_number: int = 4,
        in_chat: bool = True,
    ) -> Generator[Dict[str, Any], None, 'AlgorithmResult']:
        """
        处理推荐问题生成（独立流程，不经过主算法流程）

        复刻原 LLMService.generate_recommend_questions_task 流程

        Args:
            current_user: 当前用户（与原实现一致）
            record_id: 聊天记录 ID
            articles_number: 生成推荐问题数量
            in_chat: 是否在聊天中

        Yields:
            Dict: SSE 事件数据

        Returns:
            AlgorithmResult: 执行结果
        """
        from apps.algorithm.engine import AlgorithmEngine
        from apps.ai_model.model_factory import get_default_config
        from apps.chat.models.chat_model import ChatRecord
        import asyncio

        SQLBotLogUtil.info(f"[BusinessDBService] process_recommend_questions 开始, record_id={record_id}")

        # 从 ChatRecord 获取数据源信息
        record = self.session.get(ChatRecord, record_id)
        if not record:
            raise ValueError(f"ChatRecord not found: {record_id}")

        datasource_id = record.datasource
        SQLBotLogUtil.info(f"[BusinessDBService] 从 ChatRecord 获取 datasource_id: {datasource_id}")

        # 预加载业务数据（使用 current_user，与原实现一致）
        context = self.preprocess(
            current_user=current_user,  # 传入当前用户
            chat_id=0,  # 推荐问题不需要 chat_id
            question='',
            record_id=record_id,
            datasource_id=datasource_id,
            ai_model_id=None,
            regenerate_record_id=None,
            language='zh',
        )

        # 获取 AI 模型配置
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        config = loop.run_until_complete(get_default_config())
        context.ai_model_id = config.model_id
        # 将 LLMConfig 转换为 AiModelContext（修复类型不匹配问题）
        context.ai_model = AiModelContext(
            id=config.model_id,
            name=config.model_name,
            model_type=1 if config.model_type == "openai" else 2,
            base_model=config.model_name,
            supplier=0,
            protocol=1 if config.model_type == "openai" else 2,
            api_domain=config.api_base_url or "",
            api_key=config.api_key or "",
            config=None
        )

        # 创建算法引擎
        engine = AlgorithmEngine(context, self.session)

        # 运行推荐问题生成
        result = None
        for event in engine.run_recommend_questions(articles_number=articles_number):
            SQLBotLogUtil.info(f"[BusinessDBService] 收到推荐问题事件: type={event.type}")
            result = engine.get_result()

            # 生成 SSE 事件，格式与原实现保持一致
            if event.type == 'recommended_question':
                sse_data = {'content': event.data.get('content'), 'type': event.type}
                yield sse_data
            elif event.type == 'error':
                sse_data = {'content': event.data.get('content'), 'type': event.type}
                yield sse_data

        # 发送 finish 事件告知前端流已结束
        yield {'type': 'finish'}

        # 保存推荐问题答案（最后统一保存）
        if result and result.recommended_question_answer:
            self._update_record_field(
                record_id,
                recommended_question_answer=result.recommended_question_answer,
                recommended_question=result.recommended_question
            )
            self.session.commit()
            SQLBotLogUtil.info(f"[BusinessDBService] 推荐问题已保存到数据库")

        SQLBotLogUtil.info(f"[BusinessDBService] process_recommend_questions 完成")

        return result if result else engine.get_result()

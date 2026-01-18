# Copyright 2024 SQLBot. All rights reserved.
# 业务数据层 - 负责从业务数据库查询和保存数据

import orjson
from sqlalchemy.orm import Session

from apps.ai_model.model_factory import LLMConfig, get_default_config
from apps.algorithm.result import AlgorithmResult
from apps.algorithm.schema import AlgorithmInput
from apps.chat.curd.chat import (
    get_chat_brief_generate,
    get_last_execute_sql_error,
    get_old_questions,
    list_generate_chart_logs,
    list_generate_sql_logs,
    save_question,
)
from apps.chat.models.chat_model import Chat, ChatRecord, RenameChat
from apps.data_training.curd.data_training import get_training_template
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.parameter_manage import get_groups
from apps.terminology.curd.terminology import get_terminology_template
from common.core.deps import CurrentUser


class BusinessDataLayer:
    """业务数据层 - 负责所有业务数据库的查询和保存操作"""

    def __init__(self, session: Session, current_user: CurrentUser):
        self.session = session
        self.current_user = current_user

    async def prepare_algorithm_input(
        self,
        chat_id: int,
        question: str,
        regenerate_record_id: int | None = None,
        embedding: bool = False
    ) -> tuple[AlgorithmInput, ChatRecord]:
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
        old_questions = [q.strip() for q in get_old_questions(self.session, ds.id)]

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

    def get_terminology_template(self, question: str, ds_id: int | None = None) -> str:
        """获取术语模板"""
        ds = self.session.get(CoreDatasource, ds_id) if ds_id else None
        ds_id_val = ds.id if ds else None
        return get_terminology_template(
            self.session, question, self.current_user.oid, ds_id_val
        )

    def get_data_training_template(self, question: str, ds_id: int | None = None) -> str:
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
            finish_record,
            save_analysis_answer,
            save_chart,
            save_chart_answer,
            save_error_message,
            save_predict_answer,
            save_predict_data,
            save_recommend_question_answer,
            save_sql,
            save_sql_answer,
            save_sql_exec_data,
        )
        from apps.chat.curd.chat import rename_chat as rename_chat_db

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

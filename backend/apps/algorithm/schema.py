# Copyright 2024 SQLBot. All rights reserved.
# 算法层数据模型 - 定义算法输入输出的数据结构

from typing import Any, Optional

from pydantic import BaseModel

from apps.template.generate_chart.generator import get_chart_template
from apps.template.generate_sql.generator import get_sql_template
from apps.template.generate_guess_question.generator import get_guess_question_template


class AlgorithmInput(BaseModel):
    """算法层输入数据模型 - 包含算法处理所需的全部信息"""
    # 基础信息
    chat_id: int
    question: str
    chat_record_id: int | None = None  # 用于重新生成
    ai_modal_id: int
    ai_modal_name: str = ""  # Specific model name

    # 数据源信息
    datasource_id: int
    engine_type: str
    db_schema: str = ""  # 表结构信息

    # 提示词相关字段（与原 AiModelQuestion 保持一致）
    sql: str = ""
    rule: str = ""
    fields: str = ""
    data: str = ""
    lang: str = "简体中文"
    filter: list[str] | str = ""
    sub_query: Optional[list[dict]] = None
    terminologies: str = ""  # 术语模板
    data_training: str = ""  # 数据训练模板
    custom_prompt: str = ""  # 自定义提示词
    error_msg: str = ""  # 错误信息

    # 历史记录
    last_sql_messages: list[dict[str, Any]] = []  # SQL 生成历史消息
    last_chart_messages: list[dict[str, Any]] = []  # 图表生成历史消息
    old_questions: list[str] = []  # 用户历史问题列表（用于推荐问题生成）

    # 配置
    language: str = '简体中文'  # 与 lang 字段保持一致
    enable_row_limit: bool = True
    change_title: bool = False
    regenerate_record_id: int | None = None  # 重新生成关联的记录 ID
    articles_number: int = 4  # 推荐问题数量

    class Config:
        from_attributes = True

    def sql_sys_question(self, db_type: str = "PostgreSQL", enable_query_limit: bool = True) -> str:
        """
        生成 SQL 系统提示词

        与原实现 AiModelQuestion.sql_sys_question 保持一致
        """
        _sql_template = get_sql_example_template(db_type)
        _base_template = get_sql_template()
        _process_check = _sql_template.get('process_check') if _sql_template.get('process_check') else _base_template[
            'process_check']
        _query_limit = _base_template['query_limit'] if enable_query_limit else _base_template['no_query_limit']
        _other_rule = _sql_template['other_rule'].format(multi_table_condition=_base_template['multi_table_condition'])
        _base_sql_rules = _sql_template['quot_rule'] + _query_limit + _sql_template['limit_rule'] + _other_rule
        _sql_examples = _sql_template['basic_example']
        _example_engine = _sql_template['example_engine']
        _example_answer_1 = _sql_template['example_answer_1_with_limit'] if enable_query_limit else _sql_template[
            'example_answer_1']
        _example_answer_2 = _sql_template['example_answer_2_with_limit'] if enable_query_limit else _sql_template[
            'example_answer_2']
        _example_answer_3 = _sql_template['example_answer_3_with_limit'] if enable_query_limit else _sql_template[
            'example_answer_3']
        return _base_template['system'].format(
            engine=self.engine_type,
            schema=self.db_schema,
            question=self.question,
            lang=self.lang,
            terminologies=self.terminologies,
            data_training=self.data_training,
            custom_prompt=self.custom_prompt,
            process_check=_process_check,
            base_sql_rules=_base_sql_rules,
            basic_sql_examples=_sql_examples,
            example_engine=_example_engine,
            example_answer_1=_example_answer_1,
            example_answer_2=_example_answer_2,
            example_answer_3=_example_answer_3
        )

    def sql_user_question(self, current_time: str | None = None, change_title: bool = False) -> str:
        """
        生成 SQL 用户提示词

        与原实现 AiModelQuestion.sql_user_question 保持一致
        """
        _question = self.question
        if self.regenerate_record_id:
            _question = get_sql_template()['regenerate_hint'] + self.question
        return get_sql_template()['user'].format(
            engine=self.engine_type,
            schema=self.db_schema,
            question=_question,
            rule=self.rule,
            current_time=current_time or "",
            error_msg=self.error_msg,
            change_title=change_title
        )

    def chart_sys_question(self) -> str:
        """
        生成图表系统提示词

        与原实现 AiModelQuestion.chart_sys_question 保持一致
        """
        return get_chart_template()['system'].format(
            sql=self.sql,
            question=self.question,
            lang=self.lang
        )

    def chart_user_question(self, chart_type: str | None = None) -> str:
        """
        生成图表用户提示词

        与原实现 AiModelQuestion.chart_user_question 保持一致
        """
        return get_chart_template()['user'].format(
            sql=self.sql,
            question=self.question,
            rule=self.rule,
            chart_type=chart_type or ""
        )

    def guess_sys_question(self, articles_number: int | None = None) -> str:
        """
        生成推荐问题系统提示词

        与原实现 AiModelQuestion.guess_sys_question 保持一致
        """
        _articles_number = articles_number or self.articles_number or 4
        return get_guess_question_template()['system'].format(
            lang=self.lang,
            articles_number=_articles_number
        )

    def guess_user_question(self, old_questions: str | None = None) -> str:
        """
        生成推荐问题用户提示词

        与原实现 AiModelQuestion.guess_user_question 保持一致
        """
        _old_questions = old_questions or "[]"
        return get_guess_question_template()['user'].format(
            question=self.question,
            schema=self.db_schema,
            old_questions=_old_questions
        )


# 延迟导入以避免循环依赖
def get_sql_example_template(db_type: str):
    """获取 SQL 示例模板"""
    from apps.template.generate_sql.generator import get_sql_example_template as _get_template
    return _get_template(db_type)

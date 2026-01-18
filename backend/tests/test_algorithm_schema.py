# Copyright 2024 SQLBot. All rights reserved.
# 测试 AlgorithmInput 数据模型

import pytest
from apps.algorithm.schema import AlgorithmInput


class TestAlgorithmInput:
    """AlgorithmInput 数据模型测试"""

    def test_create_algorithm_input_with_required_fields(self):
        """测试创建 AlgorithmInput 只使用必需字段"""
        input_data = AlgorithmInput(
            chat_id=1,
            question="查询销售额",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL"
        )

        assert input_data.chat_id == 1
        assert input_data.question == "查询销售额"
        assert input_data.ai_modal_id == 1
        assert input_data.datasource_id == 1
        assert input_data.engine_type == "PostgreSQL"
        assert input_data.db_schema == ""
        assert input_data.ai_modal_name == ""

    def test_create_algorithm_input_with_all_fields(self):
        """测试创建 AlgorithmInput 使用所有字段"""
        input_data = AlgorithmInput(
            chat_id=1,
            question="查询销售额",
            chat_record_id=100,
            ai_modal_id=1,
            ai_modal_name="gpt-4",
            datasource_id=1,
            engine_type="PostgreSQL",
            db_schema="public.orders",
            terminologies="销售额 = revenue",
            data_training="使用 PostgreSQL 语法",
            custom_prompt="简洁回答",
            error_msg="语法错误",
            last_sql_messages=[{"type": "human", "content": "之前的查询"}],
            last_chart_messages=[{"type": "ai", "content": "图表配置"}],
            old_questions=["问题1", "问题2"],
            language="简体中文",
            enable_row_limit=True,
            change_title=False,
            regenerate_record_id=99,
            articles_number=5
        )

        assert input_data.chat_id == 1
        assert input_data.chat_record_id == 100
        assert input_data.ai_modal_name == "gpt-4"
        assert input_data.db_schema == "public.orders"
        assert input_data.terminologies == "销售额 = revenue"
        assert input_data.last_sql_messages == [{"type": "human", "content": "之前的查询"}]
        assert input_data.old_questions == ["问题1", "问题2"]
        assert input_data.articles_number == 5

    def test_default_values(self):
        """测试默认值"""
        input_data = AlgorithmInput(
            chat_id=1,
            question="测试问题",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="MySQL"
        )

        assert input_data.chat_record_id is None
        assert input_data.ai_modal_name == ""
        assert input_data.db_schema == ""
        assert input_data.sql == ""
        assert input_data.rule == ""
        assert input_data.lang == "简体中文"
        assert input_data.articles_number == 4
        assert input_data.enable_row_limit is True
        assert input_data.change_title is False
        assert input_data.regenerate_record_id is None
        assert input_data.sub_query is None
        assert input_data.last_sql_messages == []
        assert input_data.last_chart_messages == []
        assert input_data.old_questions == []

    def test_algorithm_input_with_history_messages(self):
        """测试带有历史消息的 AlgorithmInput"""
        last_sql_messages = [
            {"type": "human", "content": "请查询2024年的销售数据"},
            {"type": "ai", "content": "SELECT * FROM sales WHERE year = 2024"}
        ]
        last_chart_messages = [
            {"type": "human", "content": "生成柱状图"},
            {"type": "ai", "content": '{"type": "bar", "columns": []}'}
        ]

        input_data = AlgorithmInput(
            chat_id=1,
            question="按月份统计销售额",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL",
            last_sql_messages=last_sql_messages,
            last_chart_messages=last_chart_messages
        )

        assert len(input_data.last_sql_messages) == 2
        assert input_data.last_sql_messages[0]["type"] == "human"
        assert input_data.last_sql_messages[1]["type"] == "ai"
        assert len(input_data.last_chart_messages) == 2

    def test_algorithm_input_with_old_questions(self):
        """测试带有历史问题的 AlgorithmInput"""
        old_questions = [
            "2023年销售额是多少？",
            "按地区统计销量",
            "最近一个月的订单数量"
        ]

        input_data = AlgorithmInput(
            chat_id=1,
            question="生成下个月的销售预测",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="MySQL",
            old_questions=old_questions
        )

        assert len(input_data.old_questions) == 3
        assert input_data.old_questions[0] == "2023年销售额是多少？"
        assert input_data.question == "生成下个月的销售预测"

    def test_algorithm_input_filter_field(self):
        """测试 filter 字段"""
        input_data = AlgorithmInput(
            chat_id=1,
            question="查询数据",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL",
            filter=["region = 'North'", "status = 'active'"]
        )

        assert isinstance(input_data.filter, list)
        assert len(input_data.filter) == 2

# Copyright 2024 SQLBot. All rights reserved.
# 测试 AlgorithmResult 数据模型

import pytest
from apps.algorithm.result import AlgorithmResult, AlgorithmLog, OperationType


class TestAlgorithmResult:
    """AlgorithmResult 数据模型测试"""

    def test_create_algorithm_result_with_required_fields(self):
        """测试创建 AlgorithmResult 只使用必需字段"""
        result = AlgorithmResult(record_id=1)

        assert result.record_id == 1
        assert result.success is True
        assert result.error_message is None
        assert result.generated_sql is None
        assert result.sql_execution_result is None
        assert result.chart_config is None
        assert result.recommended_questions is None
        assert result.logs == []

    def test_create_algorithm_result_with_all_fields(self):
        """测试创建 AlgorithmResult 使用所有字段"""
        result = AlgorithmResult(
            record_id=1,
            success=True,
            error_message=None,
            generated_sql="SELECT * FROM orders",
            sql_answer='{"content": "SELECT * FROM orders"}',
            tables_used=["orders", "customers"],
            sql_execution_result={
                "fields": [{"name": "id", "type": "int"}],
                "data": [{"id": 1, "name": "test"}]
            },
            chart_config={"type": "bar", "columns": []},
            chart_answer='{"content": "chart config"}',
            recommended_questions='["问题1", "问题2"]',  # JSON string
            analysis_result="分析结果",
            predict_result="预测结果",
            predict_data="预测数据",
            chat_brief="月度销售报告",
            brief_generated=True,
            selected_datasource_id=1,
            selected_engine_type="PostgreSQL"
        )

        assert result.record_id == 1
        assert result.success is True
        assert result.generated_sql == "SELECT * FROM orders"
        assert result.tables_used == ["orders", "customers"]
        assert result.sql_execution_result["fields"][0]["name"] == "id"
        assert result.chart_config["type"] == "bar"
        assert result.recommended_questions == '["问题1", "问题2"]'
        assert result.brief_generated is True

    def test_algorithm_result_with_logs(self):
        """测试带有日志的 AlgorithmResult"""
        log1 = AlgorithmLog(
            operation=OperationType.GENERATE_SQL,
            ai_modal_id=1,
            ai_modal_name="gpt-4",
            full_message=[{"type": "human", "content": "查询数据"}],
            reasoning_content="分析用户意图",
            token_usage={"prompt_tokens": 100, "completion_tokens": 50}
        )
        log2 = AlgorithmLog(
            operation=OperationType.GENERATE_CHART,
            ai_modal_id=1,
            ai_modal_name="gpt-4",
            full_message=[{"type": "human", "content": "生成图表"}],
            reasoning_content=None,
            token_usage={"prompt_tokens": 80, "completion_tokens": 40}
        )

        result = AlgorithmResult(record_id=1, logs=[log1, log2])

        assert len(result.logs) == 2
        assert result.logs[0].operation == OperationType.GENERATE_SQL
        assert result.logs[1].operation == OperationType.GENERATE_CHART
        assert result.logs[0].token_usage["prompt_tokens"] == 100

    def test_algorithm_result_error_state(self):
        """测试错误状态的 AlgorithmResult"""
        result = AlgorithmResult(
            record_id=1,
            success=False,
            error_message="SQL syntax error at line 1"
        )

        assert result.success is False
        assert result.error_message == "SQL syntax error at line 1"

    def test_operation_type_enum(self):
        """测试 OperationType 枚举"""
        assert OperationType.GENERATE_SQL.value == "generate_sql"
        assert OperationType.GENERATE_CHART.value == "generate_chart"
        assert OperationType.EXECUTE_SQL.value == "execute_sql"
        assert OperationType.CHOOSE_DATASOURCE.value == "choose_datasource"
        assert OperationType.GENERATE_RECOMMENDED_QUESTIONS.value == "generate_recommended_questions"
        assert OperationType.ANALYSIS.value == "analysis"
        assert OperationType.PREDICT_DATA.value == "predict_data"


class TestAlgorithmLog:
    """AlgorithmLog 数据模型测试"""

    def test_create_algorithm_log(self):
        """测试创建 AlgorithmLog"""
        log = AlgorithmLog(
            operation=OperationType.GENERATE_SQL,
            ai_modal_id=1,
            ai_modal_name="gpt-4",
            full_message=[
                {"type": "system", "content": "你是一个SQL助手"},
                {"type": "human", "content": "查询销售数据"}
            ],
            reasoning_content="正在分析用户意图...",
            token_usage={
                "prompt_tokens": 150,
                "completion_tokens": 75,
                "total_tokens": 225
            }
        )

        assert log.operation == OperationType.GENERATE_SQL
        assert log.ai_modal_id == 1
        assert log.ai_modal_name == "gpt-4"
        assert len(log.full_message) == 2
        assert log.reasoning_content == "正在分析用户意图..."
        assert log.token_usage["total_tokens"] == 225

    def test_create_algorithm_log_without_optional_fields(self):
        """测试创建没有可选字段的 AlgorithmLog"""
        log = AlgorithmLog(
            operation=OperationType.GENERATE_CHART,
            ai_modal_id=2,
            ai_modal_name="claude-3",
            full_message=[{"type": "human", "content": "生成柱状图"}]
        )

        assert log.reasoning_content is None
        assert log.token_usage == {}

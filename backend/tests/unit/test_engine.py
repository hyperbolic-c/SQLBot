"""
AlgorithmEngine 单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import orjson

from apps.algorithm.engine import AlgorithmEngine, StreamEvent
from apps.business_db.context import AlgorithmContext


class TestStreamEvent:
    """StreamEvent 测试类"""

    def test_stream_event_creation(self):
        """测试创建流式事件"""
        event = StreamEvent(type="sql", data={"content": "SELECT * FROM users"})
        assert event.type == "sql"
        assert event.data["content"] == "SELECT * FROM users"

    def test_stream_event_with_error(self):
        """测试错误事件"""
        event = StreamEvent(
            type="error",
            data={"content": "Database connection failed", "type": "db-connection-err"}
        )
        assert event.type == "error"
        assert "error" in event.data


class TestAlgorithmEngine:
    """AlgorithmEngine 测试类"""

    def test_engine_initialization(self, sample_algorithm_context, mock_session):
        """测试引擎初始化"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)
        assert engine.context == sample_algorithm_context
        assert engine.session == mock_session
        assert engine._ds is None
        assert engine._llm is None

    def test_engine_initialization_without_session(self, sample_algorithm_context):
        """测试引擎初始化（无会话）"""
        engine = AlgorithmEngine(sample_algorithm_context)
        assert engine.session is None

    def test_get_datasource_from_context(self, sample_algorithm_context, mock_session):
        """测试从上下文获取数据源"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)
        ds = engine._get_datasource()
        assert ds is not None
        assert ds.id == 1
        assert ds.name == "test_datasource"

    def test_get_datasource_when_none(self, mock_session):
        """测试数据源为 None 的情况"""
        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="测试",
            datasource=None,
        )
        engine = AlgorithmEngine(context, session=mock_session)
        ds = engine._get_datasource()
        assert ds is None

    def test_format_sql(self, sample_algorithm_context, mock_session):
        """测试 SQL 格式化"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        # 测试基本格式化
        sql = "select * from users"
        formatted = engine._format_sql(sql)
        assert "SELECT" in formatted

    def test_get_chart_type_from_sql_answer(self, sample_algorithm_context, mock_session):
        """测试从 SQL 答案获取图表类型"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        # 有效答案
        valid_answer = orjson.dumps({
            "success": True,
            "sql": "SELECT * FROM users",
            "chart-type": "bar"
        }).decode()
        chart_type = engine._get_chart_type_from_sql_answer(valid_answer)
        assert chart_type == "bar"

        # 无效答案
        invalid_answer = "invalid json"
        chart_type = engine._get_chart_type_from_sql_answer(invalid_answer)
        assert chart_type is None

    def test_get_brief_from_sql_answer(self, sample_algorithm_context, mock_session):
        """测试从 SQL 答案获取标题"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        # 有效答案
        valid_answer = orjson.dumps({
            "success": True,
            "sql": "SELECT * FROM users",
            "brief": "用户列表查询"
        }).decode()
        brief = engine._get_brief_from_sql_answer(valid_answer)
        assert brief == "用户列表查询"

        # 无效答案
        invalid_answer = "invalid json"
        brief = engine._get_brief_from_sql_answer(invalid_answer)
        assert brief is None


class TestAlgorithmEngineSQLGeneration:
    """AlgorithmEngine SQL 生成测试"""

    def test_build_schema_text(self, sample_algorithm_context, mock_session):
        """测试构建表结构文本"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)
        schema_text = engine._build_schema_text()

        assert "users" in schema_text
        assert "orders" in schema_text

    def test_build_schema_text_empty(self, mock_session):
        """测试空表结构"""
        from apps.business_db.context import TableSchemaContext

        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="测试",
            table_schema=TableSchemaContext(tables=[], fields=[]),
        )
        engine = AlgorithmEngine(context, session=mock_session)
        schema_text = engine._build_schema_text()
        # 空表结构时返回问题文本
        assert schema_text == "测试"


class TestAlgorithmEngineCheckSQL:
    """AlgorithmEngine SQL 检查测试"""

    def test_check_sql_valid(self, sample_algorithm_context, mock_session):
        """测试有效 SQL 检查"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        valid_response = orjson.dumps({
            "success": True,
            "sql": "SELECT * FROM users",
            "tables": ["users"]
        }).decode()

        sql, tables = engine._check_sql(valid_response)
        assert sql == "SELECT * FROM users"
        assert tables == ["users"]

    def test_check_sql_empty(self, sample_algorithm_context, mock_session):
        """测试空 SQL 检查"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        empty_sql_response = orjson.dumps({
            "success": True,
            "sql": "   ",
            "tables": []
        }).decode()

        with pytest.raises(Exception):
            engine._check_sql(empty_sql_response)

    def test_check_sql_invalid_json(self, sample_algorithm_context, mock_session):
        """测试无效 JSON 检查"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        with pytest.raises(Exception):
            engine._check_sql("not valid json")


class TestAlgorithmEngineSelectDatasource:
    """AlgorithmEngine 数据源选择测试"""

    def test_select_datasource_no_session(self, sample_algorithm_context):
        """测试无会话时选择数据源"""
        engine = AlgorithmEngine(sample_algorithm_context)
        result = engine._select_datasource()
        assert result is None

    def test_select_datasource_no_datasources(self, sample_algorithm_context, mock_session):
        """测试无可用数据源"""
        # 模拟空查询结果
        mock_session.exec.return_value = []

        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)

        with pytest.raises(Exception) as exc_info:
            engine._select_datasource()

        assert "No available datasource" in str(exc_info.value)


class TestAlgorithmEngineFilter:
    """AlgorithmEngine 权限过滤测试"""

    def test_generate_filter_no_session(self, sample_algorithm_context, mock_session):
        """测试无会话时生成过滤"""
        engine = AlgorithmEngine(sample_algorithm_context)
        result = engine._generate_filter("SELECT * FROM users", ["users"])
        assert result is None

    def test_build_filter_sys_prompt(self, sample_algorithm_context, mock_session):
        """测试构建过滤系统提示词"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)
        prompt = engine._build_filter_sys_prompt()

        assert prompt is not None
        assert isinstance(prompt, str)

    def test_build_filter_user_prompt(self, sample_algorithm_context, mock_session):
        """测试构建过滤用户提示词"""
        engine = AlgorithmEngine(sample_algorithm_context, session=mock_session)
        sql = "SELECT * FROM users"
        filters = [{"table": "users", "filter": "status = 1"}]
        prompt = engine._build_filter_user_prompt(sql, orjson.dumps(filters).decode())

        assert prompt is not None
        assert sql in prompt


class TestAlgorithmEngineResult:
    """AlgorithmResult 测试"""

    def test_result_initialization(self, sample_algorithm_context):
        """测试结果初始化"""
        from apps.business_db.result import AlgorithmResult

        engine = AlgorithmEngine(sample_algorithm_context)
        result = engine._result

        assert result.record_id == 0
        assert result.chat_id == 1
        assert result.finish is False
        assert result.logs == []

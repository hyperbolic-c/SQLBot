"""
AlgorithmResult DTO 单元测试
"""

import pytest
from datetime import datetime
from apps.business_db.result import AlgorithmResult, ChatLogCreate, ChatUpdate


class TestChatLogCreate:
    """ChatLogCreate 测试类"""

    def test_chat_log_create_minimal(self):
        """测试最小化创建日志"""
        log = ChatLogCreate(
            type="sql",
            operate="generate_sql",
            pid=1,
        )
        assert log.type == "sql"
        assert log.operate == "generate_sql"
        assert log.pid == 1
        assert log.id is None
        assert log.messages is None

    def test_chat_log_create_full(self):
        """测试完整创建日志"""
        now = datetime.now()
        log = ChatLogCreate(
            id=1,
            type="sql",
            operate="generate_sql",
            pid=10,
            ai_modal_id=1,
            ai_modal_name="gpt-4",
            start_time=now,
            finish_time=now,
            messages=[{"type": "human", "content": "查询用户"}],
            reasoning_content="thinking...",
            token_usage={"prompt_tokens": 100},
        )
        assert log.id == 1
        assert log.ai_modal_id == 1
        assert log.reasoning_content == "thinking..."
        assert len(log.messages) == 1


class TestChatUpdate:
    """ChatUpdate 测试类"""

    def test_chat_update_creation(self):
        """测试创建聊天更新"""
        update = ChatUpdate(brief="用户查询")
        assert update.brief == "用户查询"
        assert update.brief_generate is False

    def test_chat_update_with_brief_generate(self):
        """测试带标题生成标志的更新"""
        update = ChatUpdate(brief="用户列表", brief_generate=True)
        assert update.brief == "用户列表"
        assert update.brief_generate is True


class TestAlgorithmResult:
    """AlgorithmResult 测试类"""

    def test_result_minimal(self):
        """测试最小化结果"""
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
        )
        assert result.record_id == 1
        assert result.chat_id == 10
        assert result.sql is None
        assert result.sql_answer is None
        assert result.data is None
        assert result.chart is None
        assert result.chart_answer is None
        assert result.error is None
        assert result.finish is False
        assert result.logs == []
        assert result.update_chat is None

    def test_result_with_sql(self):
        """测试带 SQL 的结果"""
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            sql="SELECT * FROM users",
            sql_answer='{"content": "SELECT * FROM users"}',
        )
        assert result.sql == "SELECT * FROM users"
        assert "users" in result.sql_answer

    def test_result_with_chart(self):
        """测试带图表的结果"""
        chart_config = {"type": "bar", "title": "用户分布"}
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            chart_answer='{"content": "chart config"}',
            chart=orjson.dumps(chart_config).decode(),
        )
        assert result.chart is not None
        assert "bar" in result.chart

    def test_result_with_error(self):
        """测试带错误的结果"""
        error_msg = '{"message": "Connection failed", "type": "db-connection-err"}'
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            error=error_msg,
            finish=True,
            finish_time=datetime.now(),
        )
        assert result.error == error_msg
        assert result.finish is True
        assert result.finish_time is not None

    def test_result_with_logs(self):
        """测试带日志的结果"""
        log1 = ChatLogCreate(type="sql", operate="generate_sql", pid=1)
        log2 = ChatLogCreate(type="chart", operate="generate_chart", pid=1)

        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            logs=[log1, log2],
        )
        assert len(result.logs) == 2
        assert result.logs[0].type == "sql"
        assert result.logs[1].type == "chart"

    def test_result_with_chat_update(self):
        """测试带聊天更新的结果"""
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            update_chat=ChatUpdate(brief="用户查询", brief_generate=True),
        )
        assert result.update_chat is not None
        assert result.update_chat.brief == "用户查询"

    def test_result_with_data(self):
        """测试带执行数据的结果"""
        data = [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]
        result = AlgorithmResult(
            record_id=1,
            chat_id=10,
            data=orjson.dumps(data).decode(),
        )
        assert result.data is not None
        parsed_data = orjson.loads(result.data)
        assert len(parsed_data) == 2

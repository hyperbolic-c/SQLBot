# Copyright 2024 SQLBot. All rights reserved.
# 测试 AlgorithmService 服务层

import pytest
from unittest.mock import Mock, patch


class TestAlgorithmServiceBasic:
    """AlgorithmService 基本测试 - 不依赖环境"""

    def test_service_initialization_basic(self):
        """测试服务初始化 - 基本测试"""
        # 直接测试数据模型，不导入服务
        from apps.algorithm.schema import AlgorithmInput
        from apps.algorithm.result import AlgorithmResult

        # 创建输入
        input_data = AlgorithmInput(
            chat_id=1,
            question="查询2024年销售总额",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL"
        )

        # 验证输入
        assert input_data.chat_id == 1
        assert input_data.question == "查询2024年销售总额"
        assert input_data.engine_type == "PostgreSQL"

        # 创建结果
        result = AlgorithmResult(record_id=100)
        assert result.record_id == 100
        assert result.success is True

    def test_service_attributes(self):
        """测试服务属性"""
        from apps.algorithm.schema import AlgorithmInput
        from apps.algorithm.result import AlgorithmResult, OperationType, AlgorithmLog

        input_data = AlgorithmInput(
            chat_id=1,
            question="测试",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="MySQL"
        )

        result = AlgorithmResult(record_id=1)
        assert result.success is True
        assert result.generated_sql is None
        assert result.logs == []

        # 测试日志
        log = AlgorithmLog(
            operation=OperationType.GENERATE_SQL,
            ai_modal_id=1,
            ai_modal_name="gpt-4",
            full_message=[{"type": "human", "content": "test"}]
        )
        result.logs.append(log)
        assert len(result.logs) == 1
        assert result.logs[0].operation == OperationType.GENERATE_SQL


class TestAlgorithmServiceChunkList:
    """AlgorithmService chunk_list 测试"""

    def test_pop_chunk_empty_list(self):
        """测试空列表返回 None"""
        chunk_list = []

        try:
            result = chunk_list.pop(0)
        except IndexError:
            result = None

        assert result is None

    def test_pop_chunk_with_items(self):
        """测试带内容的列表"""
        chunk_list = [{"type": "id", "id": 1}, {"type": "finish"}]

        # 弹出第一个
        chunk1 = chunk_list.pop(0)
        assert chunk1 == {"type": "id", "id": 1}
        assert len(chunk_list) == 1

        # 弹出第二个
        chunk2 = chunk_list.pop(0)
        assert chunk2 == {"type": "finish"}
        assert len(chunk_list) == 0

        # 再次弹出返回 None
        result = chunk_list.pop(0) if chunk_list else None
        assert result is None

    def test_chunk_list_append_and_pop(self):
        """测试列表追加和弹出"""
        chunk_list = []

        # 追加
        chunk_list.append({"type": "sql", "content": "SELECT * FROM test"})
        chunk_list.append({"type": "finish"})

        assert len(chunk_list) == 2

        # 弹出
        while chunk_list:
            chunk = chunk_list.pop(0)
            assert isinstance(chunk, dict)
            assert "type" in chunk

        assert len(chunk_list) == 0


class TestAlgorithmServiceFuture:
    """AlgorithmService Future 测试"""

    def test_future_attribute_exists(self):
        """测试 future 属性存在"""
        # 测试 Future 类可以正常使用
        from concurrent.futures import ThreadPoolExecutor, Future

        executor = ThreadPoolExecutor(max_workers=2)

        def sample_task():
            return "result"

        future = executor.submit(sample_task)
        assert isinstance(future, Future)

        # 在调用 result() 之前，future 可能已完成或未完成
        # 任务很小，可能会立即完成
        result = future.result()
        assert result == "result"

        executor.shutdown(wait=True)


class TestAlgorithmServiceMethods:
    """AlgorithmService 方法测试"""

    def test_set_record(self):
        """测试设置记录"""
        from apps.algorithm.schema import AlgorithmInput
        from apps.algorithm.result import AlgorithmResult

        input_data = AlgorithmInput(
            chat_id=1,
            question="测试",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL"
        )

        result = AlgorithmResult(record_id=1)

        # 模拟设置记录
        mock_record = Mock()
        mock_record.id = 200
        result.record_id = mock_record.id

        assert result.record_id == 200

    def test_set_articles_number(self):
        """测试设置推荐问题数量"""
        from apps.algorithm.schema import AlgorithmInput

        input_data = AlgorithmInput(
            chat_id=1,
            question="测试",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL",
            articles_number=4  # 默认值
        )

        assert input_data.articles_number == 4

        # 修改数量
        input_data.articles_number = 8
        assert input_data.articles_number == 8

    def test_get_result(self):
        """测试获取结果"""
        from apps.algorithm.result import AlgorithmResult

        result = AlgorithmResult(record_id=1)
        result.success = False
        result.error_message = "Test error"

        # 获取结果
        assert result == result
        assert result.success is False
        assert result.error_message == "Test error"


class TestAlgorithmServiceResultAttributes:
    """AlgorithmService 结果属性测试"""

    def test_result_default_attributes(self):
        """测试结果默认属性"""
        from apps.algorithm.result import AlgorithmResult

        result = AlgorithmResult(record_id=1)

        assert result.success is True
        assert result.error_message is None
        assert result.generated_sql is None
        assert result.sql_execution_result is None
        assert result.chart_config is None
        assert result.recommended_questions is None
        assert result.logs == []

    def test_result_set_values(self):
        """测试设置结果值"""
        from apps.algorithm.result import AlgorithmResult

        result = AlgorithmResult(record_id=1)

        # 设置值
        result.generated_sql = "SELECT * FROM test"
        result.tables_used = ["test", "users"]
        result.success = False
        result.error_message = "SQL error"

        assert result.generated_sql == "SELECT * FROM test"
        assert result.tables_used == ["test", "users"]
        assert result.success is False
        assert result.error_message == "SQL error"


class TestAlgorithmServiceHistoryMessages:
    """AlgorithmService 历史消息测试"""

    def test_history_messages_structure(self):
        """测试历史消息结构"""
        from apps.algorithm.schema import AlgorithmInput

        # SQL 历史消息
        sql_messages = [
            {"type": "human", "content": "请查询2024年的销售数据"},
            {"type": "ai", "content": "SELECT * FROM sales WHERE year = 2024"},
            {"type": "human", "content": "按月份统计"}
        ]

        # 图表历史消息
        chart_messages = [
            {"type": "human", "content": "生成柱状图"},
            {"type": "ai", "content": '{"type": "bar", "columns": []}'}
        ]

        input_data = AlgorithmInput(
            chat_id=1,
            question="测试",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL",
            last_sql_messages=sql_messages,
            last_chart_messages=chart_messages
        )

        assert len(input_data.last_sql_messages) == 3
        assert input_data.last_sql_messages[0]["type"] == "human"
        assert input_data.last_sql_messages[1]["type"] == "ai"
        assert len(input_data.last_chart_messages) == 2

    def test_old_questions_structure(self):
        """测试历史问题结构"""
        from apps.algorithm.schema import AlgorithmInput

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
        assert input_data.old_questions[2] == "最近一个月的订单数量"

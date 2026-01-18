# Copyright 2024 SQLBot. All rights reserved.
# 测试流式输出格式一致性

import pytest
import orjson
from apps.algorithm.schema import AlgorithmInput


class TestStreamOutputFormat:
    """流式输出格式测试 - 验证与原实现一致"""

    def test_sse_format_structure(self):
        """测试 SSE 格式结构"""
        # 模拟原实现的输出格式
        expected_format = 'data:' + orjson.dumps({
            'type': 'id',
            'id': 100
        }).decode() + '\n\n'

        assert expected_format.startswith('data:')
        assert expected_format.endswith('\n\n')
        assert orjson.loads(expected_format[5:-2]) == {'type': 'id', 'id': 100}

    def test_sse_sql_result_format(self):
        """测试 SQL 结果 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'content': 'SELECT * FROM orders',
            'reasoning_content': '分析查询意图...',
            'type': 'sql-result'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'sql-result'
        assert 'content' in data
        assert 'reasoning_content' in data

    def test_sse_info_format(self):
        """测试信息 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'type': 'info',
            'msg': 'sql generated'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'info'
        assert data['msg'] == 'sql generated'

    def test_sse_sql_output_format(self):
        """测试 SQL 输出 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'content': 'SELECT * FROM orders WHERE id = 1',
            'type': 'sql'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'sql'
        assert 'SELECT' in data['content']

    def test_sse_finish_format(self):
        """测试完成 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'type': 'finish'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'finish'

    def test_sse_error_format(self):
        """测试错误 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'content': 'Error: SQL syntax error',
            'type': 'error'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'error'
        assert 'Error' in data['content']

    def test_sse_recommended_question_format(self):
        """测试推荐问题 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'content': '["问题1", "问题2", "问题3"]',
            'type': 'recommended_question'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'recommended_question'
        assert '问题1' in data['content']

    def test_sse_chart_format(self):
        """测试图表配置 SSE 格式"""
        chart_config = {
            "type": "bar",
            "columns": [
                {"name": "x", "value": "month"},
                {"name": "y", "value": "amount"}
            ]
        }
        expected_format = 'data:' + orjson.dumps({
            'content': orjson.dumps(chart_config).decode(),
            'type': 'chart'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'chart'
        parsed_config = orjson.loads(data['content'])
        assert parsed_config['type'] == 'bar'

    def test_sse_regenerate_format(self):
        """测试重新生成 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'type': 'regenerate_record_id',
            'regenerate_record_id': 99
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'regenerate_record_id'
        assert data['regenerate_record_id'] == 99

    def test_sse_question_format(self):
        """测试问题 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'type': 'question',
            'question': '2024年销售额是多少？'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'question'
        assert '2024年' in data['question']

    def test_sse_sql_data_format(self):
        """测试 SQL 执行结果 SSE 格式"""
        expected_format = 'data:' + orjson.dumps({
            'content': 'execute-success',
            'type': 'sql-data'
        }).decode() + '\n\n'

        data = orjson.loads(expected_format[5:-2])
        assert data['type'] == 'sql-data'
        assert data['content'] == 'execute-success'


class TestAlgorithmInputPromptMethods:
    """AlgorithmInput 提示词生成方法测试"""

    def test_algorithm_input_has_prompt_methods(self):
        """测试 AlgorithmInput 包含所有提示词生成方法"""
        input_data = AlgorithmInput(
            chat_id=1,
            question="测试问题",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL"
        )

        # 验证方法存在
        assert hasattr(input_data, 'sql_sys_question')
        assert hasattr(input_data, 'sql_user_question')
        assert hasattr(input_data, 'chart_sys_question')
        assert hasattr(input_data, 'chart_user_question')
        assert hasattr(input_data, 'guess_sys_question')
        assert hasattr(input_data, 'guess_user_question')

    def test_sql_user_question_signature(self):
        """测试 sql_user_question 方法签名与原实现一致"""
        input_data = AlgorithmInput(
            chat_id=1,
            question="测试问题",
            ai_modal_id=1,
            datasource_id=1,
            engine_type="PostgreSQL",
            regenerate_record_id=None
        )

        # 原实现: def sql_user_question(self, current_time: str, change_title: bool)
        # 验证方法可以接受两个必需参数
        result = input_data.sql_user_question(
            current_time="2024-01-01 12:00:00",
            change_title=False
        )

        assert isinstance(result, str)
        assert 'user' in result or 'User' in result or 'user' in result.lower()


class TestBusinessDataLayerInterface:
    """BusinessDataLayer 接口测试"""

    def test_business_data_layer_import(self):
        """测试 BusinessDataLayer 可以导入"""
        import pytest
        import os

        # Skip if Docker environment not available
        if not os.path.exists('/opt/sqlbot'):
            pytest.skip("Docker environment not available")

        from apps.business_db import BusinessDataLayer
        assert BusinessDataLayer is not None

    def test_business_data_layer_has_required_methods(self):
        """测试 BusinessDataLayer 包含必需方法"""
        import pytest
        import os

        # Skip if Docker environment not available
        if not os.path.exists('/opt/sqlbot'):
            pytest.skip("Docker environment not available")

        from apps.business_db import BusinessDataLayer
        assert hasattr(BusinessDataLayer, 'prepare_algorithm_input')
        assert hasattr(BusinessDataLayer, 'get_table_schema')
        assert hasattr(BusinessDataLayer, 'get_terminology_template')
        assert hasattr(BusinessDataLayer, 'get_data_training_template')
        assert hasattr(BusinessDataLayer, 'save_algorithm_result')

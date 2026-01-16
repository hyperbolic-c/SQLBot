"""
单元测试配置文件
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from typing import Optional, List, Dict, Any


@pytest.fixture
def mock_session():
    """模拟数据库会话"""
    session = MagicMock()
    return session


@pytest.fixture
def mock_current_user():
    """模拟当前用户"""
    user = MagicMock()
    user.id = 1
    user.workspace_id = 1
    user.oid = 1
    return user


@pytest.fixture
def sample_datasource_context():
    """模拟数据源上下文"""
    from apps.business_db.context import DatasourceContext

    return DatasourceContext(
        id=1,
        name="test_datasource",
        type="PostgreSQL",
        description="Test datasource",
        configuration="encrypted_config",
        table_relation=None,
    )


@pytest.fixture
def sample_ai_model_context():
    """模拟 AI 模型上下文"""
    from apps.business_db.context import AiModelContext

    return AiModelContext(
        id=1,
        name="test_model",
        model_type=1,
        base_model="gpt-4",
        supplier=1,
        protocol=1,
        api_domain="https://api.example.com",
        api_key="encrypted_key",
        config=None,
    )


@pytest.fixture
def sample_table_schema_context():
    """模拟表结构上下文"""
    from apps.business_db.context import TableSchemaContext

    return TableSchemaContext(
        tables=[
            {"id": 1, "tableName": "users", "tableComment": "用户表"},
            {"id": 2, "tableName": "orders", "tableComment": "订单表"},
        ],
        fields=[
            {"id": 1, "tableId": 1, "fieldName": "id", "fieldComment": "ID"},
            {"id": 2, "tableId": 1, "fieldName": "name", "fieldComment": "名称"},
            {"id": 3, "tableId": 2, "fieldName": "order_id", "fieldComment": "订单ID"},
        ],
    )


@pytest.fixture
def sample_user_context():
    """模拟用户上下文"""
    from apps.business_db.context import UserContext

    return UserContext(
        id=1,
        workspace_id=1,
        oid=1,
    )


@pytest.fixture
def sample_algorithm_context(
    sample_datasource_context,
    sample_ai_model_context,
    sample_table_schema_context,
    sample_user_context,
):
    """创建完整的 AlgorithmContext 用于测试"""
    from apps.business_db.context import AlgorithmContext

    return AlgorithmContext(
        user_id=1,
        workspace_id=1,
        oid=1,
        user_context=sample_user_context,
        chat_id=1,
        chat_record_id=10,
        question="查询用户订单",
        regenerate_record_id=None,
        assistant_id=None,
        terminologies=[],
        data_training=[],
        chat_history=[],
        datasource=sample_datasource_context,
        table_schema=sample_table_schema_context,
        engine="PostgreSQL",
        ai_model=sample_ai_model_context,
        model_config={"config_list": []},
        sql_rules=None,
        language="zh-CN",
        enable_query_limit=True,
        error_msg="",
        terminology_template="",
        data_training_template="",
        custom_prompt="",
        sql_history_messages=[],
        chart_history_messages=[],
        tables_json='[{"id": 1, "tableName": "users"}]',
        fields_json='[{"id": 1, "tableId": 1, "fieldName": "id"}]',
        chat_brief_generate=False,
        chat_engine_type="",
    )


@pytest.fixture
def mock_llm():
    """模拟 LLM"""
    llm = MagicMock()
    # 模拟流式响应
    mock_chunk = MagicMock()
    mock_chunk.content = "test content"
    mock_chunk.response_metadata = {}
    llm.stream.return_value = [mock_chunk]
    return llm

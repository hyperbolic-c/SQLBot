"""
AlgorithmContext DTO 单元测试
"""

import pytest
from datetime import datetime
from apps.business_db.context import (
    AlgorithmContext,
    UserContext,
    DatasourceContext,
    AiModelContext,
    TableSchemaContext,
    TerminologyContext,
    DataTrainingContext,
    ChatHistoryContext,
)


class TestUserContext:
    """UserContext 测试类"""

    def test_user_context_creation(self):
        """测试创建用户上下文"""
        user = UserContext(
            id=1,
            workspace_id=2,
            oid=3,
        )
        assert user.id == 1
        assert user.workspace_id == 2
        assert user.oid == 3

    def test_user_context_optional_fields(self):
        """测试用户上下文可选字段"""
        user = UserContext(id=1, workspace_id=1, oid=1)
        assert user.id == 1


class TestDatasourceContext:
    """DatasourceContext 测试类"""

    def test_datasource_context_creation(self):
        """测试创建数据源上下文"""
        ds = DatasourceContext(
            id=1,
            name="test_db",
            type="PostgreSQL",
            description="测试数据库",
            configuration="encrypted_string",
            table_relation=None,
        )
        assert ds.id == 1
        assert ds.name == "test_db"
        assert ds.type == "PostgreSQL"

    def test_datasource_context_with_table_relation(self):
        """测试带表关系的数据源上下文"""
        table_relation = [{"table1": "users", "table2": "orders"}]
        ds = DatasourceContext(
            id=1,
            name="test_db",
            type="MySQL",
            description="",
            configuration="config",
            table_relation=table_relation,
        )
        assert ds.table_relation == table_relation


class TestAiModelContext:
    """AiModelContext 测试类"""

    def test_ai_model_context_creation(self):
        """测试创建 AI 模型上下文"""
        model = AiModelContext(
            id=1,
            name="gpt-4",
            model_type=1,
            base_model="gpt-4",
            supplier=1,
            protocol=1,
            api_domain="https://api.openai.com",
            api_key="sk-xxx",
            config='{"temperature": 0.7}',
        )
        assert model.id == 1
        assert model.name == "gpt-4"
        assert model.model_type == 1

    def test_ai_model_context_optional_config(self):
        """测试 AI 模型上下文可选配置"""
        model = AiModelContext(
            id=1,
            name="test",
            model_type=1,
            base_model="test",
            supplier=1,
            protocol=1,
            api_domain="https://api.example.com",
            api_key="key",
            config=None,
        )
        assert model.config is None


class TestTableSchemaContext:
    """TableSchemaContext 测试类"""

    def test_table_schema_context_creation(self):
        """测试创建表结构上下文"""
        schema = TableSchemaContext(
            tables=[
                {"id": 1, "tableName": "users", "tableComment": "用户表"},
            ],
            fields=[
                {"id": 1, "tableId": 1, "fieldName": "id", "fieldComment": "ID"},
            ],
        )
        assert len(schema.tables) == 1
        assert len(schema.fields) == 1
        assert schema.tables[0]["tableName"] == "users"

    def test_table_schema_context_empty(self):
        """测试空表结构上下文"""
        schema = TableSchemaContext(tables=[], fields=[])
        assert schema.tables == []
        assert schema.fields == []


class TestAlgorithmContext:
    """AlgorithmContext 测试类"""

    def test_algorithm_context_minimal(self):
        """测试最小化的 AlgorithmContext"""
        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="测试问题",
        )
        assert context.user_id == 1
        assert context.workspace_id == 1
        assert context.oid == 1
        assert context.question == "测试问题"
        assert context.chat_id is None
        assert context.datasource is None
        assert context.ai_model is None

    def test_algorithm_context_full(self, sample_algorithm_context):
        """测试完整的 AlgorithmContext"""
        assert sample_algorithm_context.user_id == 1
        assert sample_algorithm_context.chat_id == 1
        assert sample_algorithm_context.question == "查询用户订单"
        assert sample_algorithm_context.datasource is not None
        assert sample_algorithm_context.ai_model is not None
        assert sample_algorithm_context.table_schema is not None

    def test_algorithm_context_with_user_context(self, sample_user_context):
        """测试带用户上下文的 AlgorithmContext"""
        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="测试",
            user_context=sample_user_context,
        )
        assert context.user_context is not None
        assert context.user_context.id == 1

    def test_algorithm_context_with_history_messages(self):
        """测试带历史消息的 AlgorithmContext"""
        messages = [
            {"type": "human", "content": "你好"},
            {"type": "ai", "content": "你好，有什么可以帮助您？"},
        ]
        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="测试",
            sql_history_messages=messages,
        )
        assert len(context.sql_history_messages) == 2
        assert context.sql_history_messages[0]["type"] == "human"

    def test_algorithm_context_default_values(self):
        """测试 AlgorithmContext 默认值"""
        context = AlgorithmContext(
            user_id=1,
            workspace_id=1,
            oid=1,
            question="测试",
        )
        assert context.terminologies == []
        assert context.data_training == []
        assert context.chat_history == []
        assert context.enable_query_limit is True
        assert context.language == "zh-CN"
        assert context.sql_history_messages == []
        assert context.chart_history_messages == []


class TestTerminologyContext:
    """TerminologyContext 测试类"""

    def test_terminology_context_creation(self):
        """测试创建专业术语上下文"""
        term = TerminologyContext(
            id=1,
            word="SQL",
            description="结构化查询语言",
            other_words=["结构化查询"],
            datasource_ids=[1, 2],
        )
        assert term.id == 1
        assert term.word == "SQL"
        assert "SQL" in term.other_words


class TestDataTrainingContext:
    """DataTrainingContext 测试类"""

    def test_data_training_context_creation(self):
        """测试创建数据训练上下文"""
        training = DataTrainingContext(
            id=1,
            question="如何查询订单？",
            description="订单查询示例",
            datasource=1,
        )
        assert training.id == 1
        assert training.question == "如何查询订单？"


class TestChatHistoryContext:
    """ChatHistoryContext 测试类"""

    def test_chat_history_context_creation(self):
        """测试创建聊天历史上下文"""
        history = ChatHistoryContext(
            id=1,
            type="human",
            operate="query",
            messages=[{"role": "user", "content": "hello"}],
            reasoning_content=None,
            start_time=datetime.now(),
            finish_time=datetime.now(),
            token_usage={"prompt_tokens": 10},
        )
        assert history.id == 1
        assert history.type == "human"
        assert len(history.messages) == 1

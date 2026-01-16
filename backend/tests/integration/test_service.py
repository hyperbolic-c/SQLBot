"""
BusinessDBService 集成测试
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from apps.business_db.service import BusinessDBService
from apps.business_db.context import AlgorithmContext, UserContext


class TestBusinessDBService:
    """BusinessDBService 测试类"""

    def test_service_initialization(self, mock_session):
        """测试服务初始化"""
        service = BusinessDBService(mock_session)
        assert service.session == mock_session

    def test_preprocess_minimal(self, mock_session):
        """测试最小化预处理"""
        service = BusinessDBService(mock_session)

        context = service.preprocess(
            user_id=1,
            workspace_id=1,
            oid=1,
            chat_id=None,
            question="测试问题",
        )

        assert context.user_id == 1
        assert context.workspace_id == 1
        assert context.oid == 1
        assert context.question == "测试问题"
        assert context.user_context is not None
        assert context.user_context.id == 1

    def test_preprocess_with_chat_id(self, mock_session):
        """测试带聊天 ID 的预处理"""
        # Mock chat repository
        mock_chat = MagicMock()
        mock_chat.id = 1
        mock_chat.datasource = 1
        mock_chat.brief_generate = False
        mock_chat.engine_type = "PostgreSQL"

        service = BusinessDBService(mock_session)
        service.chat_repo.get_chat = MagicMock(return_value=mock_chat)
        service.ds_repo.get_datasource = MagicMock(return_value=None)

        context = service.preprocess(
            user_id=1,
            workspace_id=1,
            oid=1,
            chat_id=1,
            question="测试问题",
        )

        assert context.chat_id == 1

    def test_preprocess_with_datasource(self, mock_session):
        """测试带数据源的预处理"""
        mock_chat = MagicMock()
        mock_chat.id = 1
        mock_chat.datasource = None
        mock_chat.brief_generate = False
        mock_chat.engine_type = ""

        mock_ds = MagicMock()
        mock_ds.id = 1
        mock_ds.name = "test_db"
        mock_ds.type = "PostgreSQL"
        mock_ds.description = "Test"
        mock_ds.configuration = "encrypted"
        mock_ds.table_relation = None

        service = BusinessDBService(mock_session)
        service.chat_repo.get_chat = MagicMock(return_value=mock_chat)
        service.ds_repo.get_datasource = MagicMock(return_value=mock_ds)

        context = service.preprocess(
            user_id=1,
            workspace_id=1,
            oid=1,
            chat_id=1,
            question="测试问题",
            datasource_id=1,
        )

        assert context.datasource is not None
        assert context.datasource.id == 1
        assert context.datasource.name == "test_db"
        assert context.engine == "PostgreSQL"


class TestBusinessDBCreateRecord:
    """BusinessDBService 记录创建测试"""

    def test_create_record_minimal(self, mock_session):
        """测试最小化创建记录"""
        service = BusinessDBService(mock_session)

        # Mock execute to return the inserted row
        mock_result = MagicMock()
        mock_result.id = 10
        mock_session.execute.return_value = None
        mock_session.flush.return_value = None
        mock_session.refresh.return_value = None
        mock_session.add.return_value = None
        mock_session.commit.return_value = None

        with patch.object(service, 'session', mock_session):
            record_id = service.create_record(
                chat_id=1,
                question="测试问题",
                user_id=1,
            )

            # 验证调用了 execute
            assert mock_session.execute.called


class TestBusinessDBPostprocess:
    """BusinessDBService 后处理测试"""

    def test_postprocess_with_result(self, mock_session):
        """测试带结果的后处理"""
        from apps.business_db.result import AlgorithmResult, ChatUpdate

        service = BusinessDBService(mock_session)

        result = AlgorithmResult(
            record_id=10,
            chat_id=1,
            sql="SELECT * FROM users",
            sql_answer='{"content": "SELECT * FROM users"}',
            finish=True,
        )

        # 执行后处理
        service.postprocess(result)

        # 验证调用了 execute（用于更新记录）
        assert mock_session.execute.called


class TestBusinessDBSaveMethods:
    """BusinessDBService 保存方法测试"""

    def test_save_sql_answer(self, mock_session):
        """测试保存 SQL 答案"""
        service = BusinessDBService(mock_session)
        service.save_sql_answer(1, '{"content": "SELECT * FROM users"}')
        assert mock_session.execute.called

    def test_save_sql(self, mock_session):
        """测试保存格式化 SQL"""
        service = BusinessDBService(mock_session)
        service.save_sql(1, "SELECT * FROM users")
        assert mock_session.execute.called

    def test_save_chart_answer(self, mock_session):
        """测试保存图表答案"""
        service = BusinessDBService(mock_session)
        service.save_chart_answer(1, '{"content": "chart config"}')
        assert mock_session.execute.called

    def test_save_chart(self, mock_session):
        """测试保存图表配置"""
        service = BusinessDBService(mock_session)
        service.save_chart(1, '{"type": "bar"}')
        assert mock_session.execute.called

    def test_save_sql_data(self, mock_session):
        """测试保存 SQL 执行数据"""
        service = BusinessDBService(mock_session)
        service.save_sql_data(1, '[{"id": 1}]')
        assert mock_session.execute.called

    def test_save_error(self, mock_session):
        """测试保存错误信息"""
        service = BusinessDBService(mock_session)
        service.save_error(1, '{"message": "error"}')
        assert mock_session.execute.called

    def test_finish_record(self, mock_session):
        """测试完成记录"""
        service = BusinessDBService(mock_session)
        service.finish_record(1)
        assert mock_session.execute.called

    def test_update_chat_brief(self, mock_session):
        """测试更新聊天标题"""
        service = BusinessDBService(mock_session)
        service.update_chat_brief(1, "用户查询", brief_generate=True)
        assert mock_session.execute.called


class TestBusinessDBProcess:
    """BusinessDBService process 方法测试"""

    def test_process_method_exists(self, mock_session):
        """测试 process 方法存在"""
        service = BusinessDBService(mock_session)
        assert hasattr(service, 'process')
        assert callable(service.process)

    def test_process_yields_events(self, mock_session):
        """测试 process 方法产生事件"""
        service = BusinessDBService(mock_session)

        # Mock all dependencies
        mock_chat = MagicMock()
        mock_chat.id = 1
        mock_chat.datasource = None
        mock_chat.brief_generate = False
        mock_chat.engine_type = ""

        mock_ds = MagicMock()
        mock_ds.id = 1
        mock_ds.name = "test_db"
        mock_ds.type = "PostgreSQL"
        mock_ds.description = "Test"
        mock_ds.configuration = "encrypted"
        mock_ds.table_relation = None

        mock_model = MagicMock()
        mock_model.id = 1
        mock_model.name = "test_model"
        mock_model.model_type = 1
        mock_model.base_model = "gpt-4"
        mock_model.supplier = 1
        mock_model.protocol = 1
        mock_model.api_domain = "https://api.example.com"
        mock_model.api_key = "encrypted_key"
        mock_model.config = None

        service.chat_repo.get_chat = MagicMock(return_value=mock_chat)
        service.ds_repo.get_datasource = MagicMock(return_value=mock_ds)
        service.model_repo.get_model = MagicMock(return_value=mock_model)

        mock_session.execute.return_value = None
        mock_session.flush.return_value = None
        mock_session.refresh.return_value = None
        mock_session.add.return_value = None
        mock_session.commit.return_value = None

        # Process should return a generator
        result = service.process(
            user_id=1,
            workspace_id=1,
            oid=1,
            chat_id=1,
            question="测试问题",
        )

        assert hasattr(result, '__iter__')
        assert hasattr(result, '__next__')

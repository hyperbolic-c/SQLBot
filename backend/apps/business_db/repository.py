"""
Repository Layer
Data access classes for the business database layer.
"""

from datetime import datetime as dt
from typing import Optional, List, Any, Dict

from sqlalchemy import and_, select, desc
from sqlalchemy.orm import Session
from sqlmodel import select

from apps.chat.models.chat_model import Chat, ChatRecord, ChatLog, TypeEnum, OperationEnum
from apps.datasource.models.datasource import CoreDatasource, CoreTable, CoreField
from apps.terminology.models.terminology_model import Terminology
from apps.data_training.models.data_training_model import DataTraining
from apps.system.models.system_model import AiModelDetail
from common.core.deps import CurrentUser


class ChatRepository:
    """聊天记录仓储"""

    def __init__(self, session: Session):
        self.session = session

    def get_chat(self, chat_id: int) -> Optional[Chat]:
        """获取聊天会话"""
        return self.session.get(Chat, chat_id)

    def create_chat(self, create_by: int, question: str, datasource: Optional[int] = None) -> Chat:
        """创建新聊天会话"""
        chat = Chat(
            create_time=dt.now(),
            create_by=create_by,
            brief=question.strip()[:20] if question else "",
            datasource=datasource,
            engine_type="PostgreSQL",
        )
        self.session.add(chat)
        self.session.flush()
        self.session.refresh(chat)
        return chat

    def update_chat(self, chat_id: int, datasource: int, engine_type: str):
        """更新聊天数据源信息"""
        chat = self.session.get(Chat, chat_id)
        if chat:
            chat.datasource = datasource
            chat.engine_type = engine_type
            self.session.add(chat)
            self.session.flush()


class ChatRecordRepository:
    """聊天记录仓储"""

    def __init__(self, session: Session):
        self.session = session

    def create_record(
        self,
        chat_id: int,
        question: str,
        create_by: int,
        datasource: Optional[int] = None,
        engine_type: Optional[str] = None,
        ai_modal_id: Optional[int] = None,
        regenerate_record_id: Optional[int] = None,
    ) -> ChatRecord:
        """创建新的聊天记录"""
        record = ChatRecord(
            chat_id=chat_id,
            question=question,
            create_time=dt.now(),
            create_by=create_by,
            datasource=datasource,
            engine_type=engine_type,
            ai_modal_id=ai_modal_id,
            regenerate_record_id=regenerate_record_id,
        )
        self.session.add(record)
        self.session.flush()
        self.session.refresh(record)
        return record

    def update_record_field(self, record_id: int, **kwargs):
        """更新记录字段"""
        record = self.session.get(ChatRecord, record_id)
        if record:
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            self.session.add(record)
            self.session.flush()

    def finish_record(self, record_id: int):
        """完成记录"""
        self.update_record_field(
            record_id,
            finish=True,
            finish_time=dt.now(),
        )


class ChatLogRepository:
    """聊天日志仓储"""

    def __init__(self, session: Session):
        self.session = session

    def get_chat_logs(self, chat_id: int, limit: int = 20) -> List[ChatLog]:
        """获取聊天历史日志"""
        # Get record IDs for this chat
        record_ids = self.session.exec(
            select(ChatRecord.id).where(ChatRecord.chat_id == chat_id)
        ).all()

        if not record_ids:
            return []

        # Get logs for these records
        return self.session.exec(
            select(ChatLog)
            .where(ChatLog.pid.in_(record_ids))
            .order_by(desc(ChatLog.start_time))
            .limit(limit)
        ).all()

    def create_log(
        self,
        type_: TypeEnum,
        operate: OperationEnum,
        pid: int,
        ai_modal_id: Optional[int] = None,
        base_modal: Optional[str] = None,
    ) -> ChatLog:
        """创建日志"""
        log = ChatLog(
            type=type_,
            operate=operate,
            pid=pid,
            ai_modal_id=ai_modal_id,
            base_modal=base_modal,
            start_time=dt.now(),
        )
        self.session.add(log)
        self.session.flush()
        self.session.refresh(log)
        return log

    def update_log(
        self,
        log_id: int,
        messages: Optional[List[Dict[str, Any]]] = None,
        reasoning_content: Optional[str] = None,
        finish_time: Optional[dt] = None,
        token_usage: Optional[Dict[str, Any]] = None,
    ):
        """更新日志"""
        log = self.session.get(ChatLog, log_id)
        if log:
            if messages is not None:
                log.messages = messages
            if reasoning_content is not None:
                log.reasoning_content = reasoning_content
            if finish_time is not None:
                log.finish_time = finish_time
            if token_usage is not None:
                log.token_usage = token_usage
            self.session.add(log)
            self.session.flush()


class DatasourceRepository:
    """数据源仓储"""

    def __init__(self, session: Session):
        self.session = session

    def get_datasource(self, ds_id: int) -> Optional[CoreDatasource]:
        """获取数据源"""
        return self.session.get(CoreDatasource, ds_id)

    def get_datasources_for_user(self, oid: int) -> List[CoreDatasource]:
        """获取用户可用的数据源列表"""
        return self.session.exec(
            select(CoreDatasource)
            .where(and_(CoreDatasource.oid == oid, CoreDatasource.status == "1"))
            .order_by(CoreDatasource.create_time.desc())
        ).all()

    def get_table_schema(self, ds_id: int, embedding_enabled: bool = True) -> tuple:
        """
        获取数据源的表结构
        Returns: (tables_json, fields_json)
        """
        tables = self.session.exec(
            select(CoreTable)
            .where(and_(CoreTable.ds_id == ds_id, CoreTable.checked == True))
        ).all()

        if not tables:
            return "[]", "[]"

        table_ids = [t.id for t in tables]

        fields = self.session.exec(
            select(CoreField)
            .where(and_(
                CoreField.table_id.in_(table_ids),
                CoreField.checked == True
            ))
        ).all()

        # Convert to JSON-serializable format
        tables_json = [
            {
                "id": t.id,
                "tableName": t.table_name,
                "tableComment": t.table_comment or t.custom_comment or "",
            }
            for t in tables
        ]

        fields_json = [
            {
                "id": f.id,
                "tableId": f.table_id,
                "fieldName": f.field_name,
                "fieldType": f.field_type or "",
                "fieldComment": f.field_comment or f.custom_comment or "",
            }
            for f in fields
        ]

        return (
            str(tables_json).replace("'", '"'),
            str(fields_json).replace("'", '"'),
        )


class TerminologyRepository:
    """专业术语仓储"""

    def __init__(self, session: Session):
        self.session = session

    def get_terminologies_for_user(
        self,
        oid: int,
        datasource_id: Optional[int] = None,
    ) -> List[Terminology]:
        """获取用户可用的专业术语"""
        if datasource_id:
            # Get terms specific to this datasource or global terms
            return self.session.exec(
                select(Terminology)
                .where(and_(
                    Terminology.oid == oid,
                    Terminology.enabled == True,
                    or_(
                        Terminology.specific_ds == False,
                        Terminology.datasource_ids.contains([datasource_id])
                    )
                ))
            ).all()
        else:
            return self.session.exec(
                select(Terminology)
                .where(and_(
                    Terminology.oid == oid,
                    Terminology.enabled == True,
                    Terminology.specific_ds == False
                ))
            ).all()


class DataTrainingRepository:
    """数据训练仓储"""

    def __init__(self, session: Session):
        self.session = session

    def get_data_training_for_user(
        self,
        oid: int,
        datasource_id: Optional[int] = None,
    ) -> List[DataTraining]:
        """获取用户可用的训练数据"""
        if datasource_id:
            return self.session.exec(
                select(DataTraining)
                .where(and_(
                    DataTraining.oid == oid,
                    DataTraining.enabled == True,
                    or_(
                        DataTraining.datasource.is_(None),
                        DataTraining.datasource == datasource_id
                    )
                ))
            ).all()
        else:
            return self.session.exec(
                select(DataTraining)
                .where(and_(
                    DataTraining.oid == oid,
                    DataTraining.enabled == True
                ))
            ).all()


class AiModelRepository:
    """AI模型仓储"""

    def __init__(self, session: Session):
        self.session = session

    def get_ai_model(self, model_id: int) -> Optional[AiModelDetail]:
        """获取AI模型"""
        return self.session.get(AiModelDetail, model_id)

    def get_default_ai_model(self, oid: int) -> Optional[AiModelDetail]:
        """获取默认AI模型"""
        return self.session.exec(
            select(AiModelDetail)
            .where(and_(
                AiModelDetail.oid == oid,
                AiModelDetail.status == 1,
                AiModelDetail.default_model == True
            ))
        ).first()

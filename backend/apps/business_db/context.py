"""
Algorithm Context DTO
Contains all the data pre-loaded from the business database for algorithm processing.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel


@dataclass
class TerminologyContext:
    """专业术语上下文"""
    id: int
    word: str
    description: Optional[str]
    other_words: List[str]
    datasource_ids: List[int]


@dataclass
class DataTrainingContext:
    """数据训练上下文"""
    id: int
    question: str
    description: Optional[str]
    datasource: Optional[int]


@dataclass
class ChatHistoryContext:
    """聊天历史上下文"""
    id: int
    type: str
    operate: str
    messages: Optional[List[Dict[str, Any]]]
    reasoning_content: Optional[str]
    start_time: Optional[datetime]
    finish_time: Optional[datetime]
    token_usage: Optional[Dict[str, Any]]


@dataclass
class UserContext:
    """用户上下文"""
    id: int
    workspace_id: int
    oid: int


@dataclass
class DatasourceContext:
    """数据源上下文"""
    id: int
    name: str
    type: str
    description: Optional[str]
    configuration: str  # Encrypted, need to decrypt
    table_relation: Optional[List[Any]]


@dataclass
class AiModelContext:
    """AI模型上下文"""
    id: int
    name: str
    model_type: int
    base_model: str
    supplier: int
    protocol: int
    api_domain: str
    api_key: str  # Encrypted, need to decrypt
    config: Optional[str]


@dataclass
class TableSchemaContext:
    """表结构上下文"""
    tables: List[Dict[str, Any]]
    fields: List[Dict[str, Any]]


class AlgorithmContext(BaseModel):
    """
    算法执行上下文
    在流程开始时从业务数据库预加载所有必要数据

    这个上下文包含了算法处理所需的全部数据，
    算法执行过程中不再访问业务数据库
    """
    # 用户信息
    user_id: int
    workspace_id: int
    oid: int

    # 用户上下文（用于权限过滤）
    user_context: Optional[UserContext] = None

    # 聊天上下文
    chat_id: Optional[int] = None
    chat_record_id: Optional[int] = None
    question: str
    regenerate_record_id: Optional[int] = None

    # 业务配置 (预加载)
    terminologies: List[TerminologyContext] = []
    data_training: List[DataTrainingContext] = []
    chat_history: List[ChatHistoryContext] = []

    # 数据源配置
    datasource: Optional[DatasourceContext] = None
    table_schema: Optional[TableSchemaContext] = None
    engine: str = ""  # Database type

    # LLM 配置
    ai_model: Optional[AiModelContext] = None
    model_config: Dict[str, Any] = {}

    # 其他配置
    sql_rules: Optional[str] = None
    language: str = "zh-CN"
    enable_query_limit: bool = True

    # 错误信息 (从之前的执行中)
    error_msg: str = ""

    # ===== 以下是预加载的格式化数据 =====

    # 预加载的专业术语模板字符串
    terminology_template: str = ""

    # 预加载的训练数据模板字符串
    data_training_template: str = ""

    # 预加载的自定义提示词
    custom_prompt: str = ""

    # 预加载的聊天历史消息
    sql_history_messages: List[Dict[str, Any]] = []
    chart_history_messages: List[Dict[str, Any]] = []

    # 预加载的表结构 JSON 字符串
    tables_json: str = "[]"
    fields_json: str = "[]"

    # 原始格式的表结构字符串（与原结构一致，用于算法引擎）
    db_schema: str = ""

    # Chat 配置
    chat_brief_generate: bool = False
    chat_engine_type: str = ""

    # 预加载的历史问题（用于生成推荐问题）
    old_questions: List[str] = []

    class Config:
        arbitrary_types_allowed = True

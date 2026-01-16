"""
Algorithm Result DTO
Contains all data to be saved after algorithm processing completes.
"""

from dataclasses import dataclass
from typing import Optional, List, Any, Dict
from datetime import datetime

from pydantic import BaseModel


@dataclass
class ChatLogCreate:
    """聊天日志创建对象"""
    type: str  # TypeEnum value
    operate: str  # OperationEnum value
    pid: Optional[int] = None
    ai_modal_id: Optional[int] = None
    base_modal: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    reasoning_content: Optional[str] = None
    start_time: datetime = None
    finish_time: datetime = None
    token_usage: Optional[Dict[str, Any]] = None


@dataclass
class ChatUpdate:
    """聊天更新对象"""
    datasource: Optional[int] = None
    engine_type: Optional[str] = None
    brief: Optional[str] = None
    brief_generate: bool = False


class AlgorithmResult(BaseModel):
    """
    算法执行结果
    包含所有需要在算法结束后保存的数据
    """
    # 记录信息
    record_id: int
    chat_id: int

    # 生成结果
    sql: Optional[str] = None
    sql_answer: Optional[str] = None
    data: Optional[str] = None
    chart: Optional[str] = None
    chart_answer: Optional[str] = None
    analysis: Optional[str] = None
    predict_data: Optional[str] = None

    # 推荐问题
    recommended_question: Optional[str] = None
    recommended_question_answer: Optional[str] = None

    # 数据源选择答案
    datasource_select_answer: Optional[str] = None

    # 错误信息
    error: Optional[str] = None

    # 执行时间
    finish_time: Optional[datetime] = None

    # 完成标志
    finish: bool = False

    # 待保存的日志
    logs: List[ChatLogCreate] = []

    # 更新目标
    update_chat: Optional[ChatUpdate] = None

    # 关联记录ID
    analysis_record_id: Optional[int] = None
    predict_record_id: Optional[int] = None

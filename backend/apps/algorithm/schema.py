# backend/apps/algorithm/schema.py
from typing import Any

from pydantic import BaseModel


class AlgorithmInput(BaseModel):
    """算法层输入数据模型 - 包含算法处理所需的全部信息"""
    # 基础信息
    chat_id: int
    question: str
    chat_record_id: int | None = None  # 用于重新生成
    ai_modal_id: int
    ai_modal_name: str

    # 数据源信息
    datasource_id: int
    engine_type: str
    db_schema: str  # 表结构信息

    # 提示词相关
    terminologies: str  # 术语模板
    data_training: str  # 数据训练模板
    custom_prompt: str  # 自定义提示词
    error_msg: str  # 错误信息

    # 历史记录
    last_sql_messages: list[dict[str, Any]] = []  # SQL 生成历史消息
    last_chart_messages: list[dict[str, Any]] = []  # 图表生成历史消息
    old_questions: list[str] = []  # 用户历史问题列表（用于推荐问题生成）

    # 配置
    language: str = '简体中文'
    enable_row_limit: bool = True
    change_title: bool = False
    regenerate_record_id: int | None = None  # 重新生成关联的记录 ID
    articles_number: int = 4  # 推荐问题数量

    class Config:
        from_attributes = True

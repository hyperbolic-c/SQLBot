from enum import Enum
from typing import Any

from pydantic import BaseModel


class OperationType(str, Enum):
    """操作类型枚举"""
    GENERATE_SQL = "generate_sql"
    GENERATE_CHART = "generate_chart"
    EXECUTE_SQL = "execute_sql"
    CHOOSE_DATASOURCE = "choose_datasource"
    GENERATE_RECOMMENDED_QUESTIONS = "generate_recommended_questions"
    ANALYSIS = "analysis"
    PREDICT_DATA = "predict_data"

class AlgorithmLog(BaseModel):
    """算法日志记录"""
    operation: OperationType
    ai_modal_id: int
    ai_modal_name: str
    full_message: list[dict[str, Any]]  # 完整的消息历史
    reasoning_content: str | None = None
    token_usage: dict[str, int] = {}

class AlgorithmResult(BaseModel):
    """算法层输出结果模型 - 包含所有需要保存到业务数据库的内容"""

    # 基础信息
    record_id: int  # ChatRecord ID
    success: bool = True
    error_message: str | None = None

    # SQL 生成结果
    generated_sql: str | None = None
    sql_answer: str | None = None
    tables_used: list[str] = []  # 使用的表

    # SQL 执行结果
    sql_execution_result: dict[str, Any] | None = None  # {"fields": [...], "data": [...]}

    # 图表生成结果
    chart_config: dict[str, Any] | None = None
    chart_answer: str | None = None

    # 推荐问题
    recommended_questions: str | None = None

    # 分析/预测结果
    analysis_result: str | None = None
    predict_result: str | None = None
    predict_data: str | None = None

    # 聊天标题
    chat_brief: str | None = None
    brief_generated: bool = False

    # 数据源选择
    selected_datasource_id: int | None = None
    selected_engine_type: str | None = None

    # 日志
    logs: list[AlgorithmLog] = []

    class Config:
        from_attributes = True

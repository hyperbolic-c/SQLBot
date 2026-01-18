# Copyright 2024 SQLBot. All rights reserved.
# 算法层 API - 处理 page 来源的智能问数请求

import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import orjson
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from apps.algorithm.service import AlgorithmService
from apps.business_db import BusinessDataLayer
from apps.chat.models.chat_model import ChatQuestion
from apps.datasource.models.datasource import CoreDatasource
from common.core.deps import CurrentUser, SessionDep

# Thread pool executor - same as original implementation
executor = ThreadPoolExecutor(max_workers=200)

router = APIRouter(tags=["Algorithm Chat"], prefix="/algorithm/chat")


async def process_algorithm_task(
    session: Session,
    current_user: CurrentUser,
    request_question: ChatQuestion,
    in_chat: bool = True,
    stream: bool = True
):
    """
    处理算法任务的内部函数

    遵循原实现的方法和流程：
    - 使用线程池异步执行
    - 保持输入输出格式一致
    """
    try:
        # 初始化业务数据层
        business_db = BusinessDataLayer(session, current_user)

        # 准备算法输入（一次性获取所有需要的信息）
        algorithm_input, record = await business_db.prepare_algorithm_input(
            chat_id=request_question.chat_id,
            question=request_question.question,
            regenerate_record_id=getattr(request_question, 'regenerate_record_id', None),
            embedding=True
        )

        # 获取表结构
        db_schema = business_db.get_table_schema(
            algorithm_input.datasource_id,
            algorithm_input.question,
            embedding=True
        )
        algorithm_input.db_schema = db_schema

        # 获取术语和数据训练模板
        algorithm_input.terminologies = business_db.get_terminology_template(
            algorithm_input.question,
            algorithm_input.datasource_id
        )
        algorithm_input.data_training = business_db.get_data_training_template(
            algorithm_input.question,
            algorithm_input.datasource_id
        )

        # 获取 LLM 配置和数据源
        # TODO: 合并一次性获取
        from apps.ai_model.model_factory import get_default_config
        config = await get_default_config()
        ds = session.get(CoreDatasource, algorithm_input.datasource_id)

        # 创建算法服务
        algorithm_service = AlgorithmService(algorithm_input)
        algorithm_service.initialize(config, ds)

        # 使用线程池执行（遵循原实现）
        algorithm_service.run_task_async(in_chat=in_chat, stream=stream)

        # 等待任务完成并返回结果
        # 遵循原实现，使用 await_result 模式
        # run_task 返回 SSE 格式字符串，直接 yield
        def collect_result():
            # 首先等待任务完成
            while algorithm_service.future.done() is False:
                pass
            # 然后返回所有结果（SSE 格式已经是字符串）
            while True:
                chunk = algorithm_service.pop_chunk()
                if chunk is None:
                    break
                yield chunk

        if stream:
            return StreamingResponse(collect_result(), media_type="text/event-stream")
        else:
            res = collect_result()
            raw_data = {}
            for chunk in res:
                if chunk:
                    # SSE 格式字符串，需要解析
                    import orjson
                    try:
                        # 去除 "data: " 前缀和末尾的 "\n\n"
                        json_str = chunk.replace('data: ', '').strip()
                        if json_str.endswith('\n\n'):
                            json_str = json_str[:-2]
                        raw_data = orjson.loads(json_str)
                    except Exception:
                        pass
            status_code = 200 if raw_data.get('success', True) else 500
            return JSONResponse(content=raw_data, status_code=status_code)

    except Exception as e:
        traceback.print_exc()
        if stream:
            def _err(_e: Exception):
                yield {'content': str(_e), 'type': 'error'}

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )


async def process_recommend_questions(
    session: Session,
    current_user: CurrentUser,
    chat_record_id: int,
    articles_number: int = 4
):
    """
    处理推荐问题生成的内部函数

    遵循原实现的方法和流程
    """
    from apps.chat.curd.chat import get_chat_record_by_id

    def _return_empty():
        yield {'content': '[]', 'type': 'recommended_question'}

    try:
        # 获取记录
        record = get_chat_record_by_id(session, chat_record_id)
        if not record:
            return StreamingResponse(_return_empty(), media_type="text/event-stream")

        # 初始化业务数据层
        business_db = BusinessDataLayer(session, current_user)

        # 准备算法输入
        algorithm_input, _ = await business_db.prepare_algorithm_input(
            chat_id=record.chat_id,
            question=record.question or '',
            embedding=True
        )
        algorithm_input.articles_number = articles_number

        # 获取 LLM 配置和数据源
        from apps.ai_model.model_factory import get_default_config
        config = await get_default_config()
        ds = session.get(CoreDatasource, record.datasource)

        # 创建算法服务
        algorithm_service = AlgorithmService(algorithm_input)
        algorithm_service.initialize(config, ds)
        algorithm_service.set_record(record)
        algorithm_service.set_articles_number(articles_number)

        # 使用线程池执行（遵循原实现）
        algorithm_service.run_recommend_questions_task_async()

        # 等待任务完成并返回结果
        def collect_result():
            # 等待任务完成
            while algorithm_service.future.done() is False:
                pass
            # 返回所有结果
            while True:
                chunk = algorithm_service.pop_chunk()
                if chunk is None:
                    break
                yield chunk

        return StreamingResponse(collect_result(), media_type="text/event-stream")

    except Exception as e:
        traceback.print_exc()

        def _err(_e: Exception):
            yield {'content': str(_e), 'type': 'error'}

        return StreamingResponse(_err(e), media_type="text/event-stream")


@router.post("/question", summary="Algorithm: ask question")
async def algorithm_question_answer(
    session: SessionDep,
    current_user: CurrentUser,
    request_question: ChatQuestion
):
    """
    算法层问数接口 - 处理 page 来源的请求

    遵循原实现的输入输出格式：
    - 输入: ChatQuestion (chat_id, question 等)
    - 输出: 流式 SSE 响应
    """
    return await process_algorithm_task(
        session=session,
        current_user=current_user,
        request_question=request_question,
        in_chat=True,
        stream=True
    )


@router.post("/recommend_questions/{chat_record_id}", summary="Algorithm: generate recommend questions")
async def algorithm_ask_recommend_questions(
    session: SessionDep,
    current_user: CurrentUser,
    chat_record_id: int,
    articles_number: Optional[int] = 4
):
    """
    算法层推荐问题接口 - 处理 page 来源的请求

    遵循原实现的输入输出格式
    """
    return await process_recommend_questions(
        session=session,
        current_user=current_user,
        chat_record_id=chat_record_id,
        articles_number=articles_number or 4
    )

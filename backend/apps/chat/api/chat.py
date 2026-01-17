import asyncio
import io
import traceback
from typing import Optional, List

import orjson
import pandas as pd
from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from starlette.responses import JSONResponse

from apps.chat.curd.chat import delete_chat_with_user, get_chart_data_with_user, get_chat_predict_data_with_user, list_chats, get_chat_with_records, create_chat, rename_chat, \
    delete_chat, get_chat_chart_data, get_chat_predict_data, get_chat_with_records_with_data, get_chat_record_by_id, \
    format_json_data, format_json_list_data, get_chart_config, list_recent_questions,get_chat as get_chat_exec, rename_chat_with_user
from apps.chat.models.chat_model import CreateChat, ChatRecord, RenameChat, ChatQuestion, AxisObj, QuickCommand, \
    ChatInfo, Chat, ChatFinishStep
from apps.chat.task.llm import LLMService
from apps.swagger.i18n import PLACEHOLDER_PREFIX
from apps.system.schemas.permission import SqlbotPermission, require_permissions
from common.core.config import settings
from common.core.deps import CurrentAssistant, SessionDep, CurrentUser, Trans
from common.utils.command_utils import parse_quick_command
from common.utils.data_format import DataFormat
from common.utils.utils import SQLBotLogUtil
from common.audit.models.log_model import OperationType, OperationModules
from common.audit.schemas.logger_decorator import LogConfig, system_log

router = APIRouter(tags=["Data Q&A"], prefix="/chat")


@router.get("/list", response_model=List[Chat], summary=f"{PLACEHOLDER_PREFIX}get_chat_list")
async def chats(session: SessionDep, current_user: CurrentUser):
    return list_chats(session, current_user)


@router.get("/{chart_id}", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}get_chat")
async def get_chat(session: SessionDep, current_user: CurrentUser, chart_id: int, current_assistant: CurrentAssistant,
                   trans: Trans):
    def inner():
        return get_chat_with_records(chart_id=chart_id, session=session, current_user=current_user,
                                     current_assistant=current_assistant, trans=trans)

    return await asyncio.to_thread(inner)


@router.get("/{chart_id}/with_data", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}get_chat_with_data")
async def get_chat_with_data(session: SessionDep, current_user: CurrentUser, chart_id: int,
                             current_assistant: CurrentAssistant):
    def inner():
        return get_chat_with_records_with_data(chart_id=chart_id, session=session, current_user=current_user,
                                               current_assistant=current_assistant)

    return await asyncio.to_thread(inner)


""" @router.get("/record/{chat_record_id}/data", summary=f"{PLACEHOLDER_PREFIX}get_chart_data")
async def chat_record_data(session: SessionDep, chat_record_id: int):
    def inner():
        data = get_chat_chart_data(chat_record_id=chat_record_id, session=session)
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/predict_data", summary=f"{PLACEHOLDER_PREFIX}get_chart_predict_data")
async def chat_predict_data(session: SessionDep, chat_record_id: int):
    def inner():
        data = get_chat_predict_data(chat_record_id=chat_record_id, session=session)
        return format_json_list_data(data)

    return await asyncio.to_thread(inner) """

@router.get("/record/{chat_record_id}/data", summary=f"{PLACEHOLDER_PREFIX}get_chart_data")
async def chat_record_data(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    SQLBotLogUtil.info(f"[DEBUG] chat_record_data API called: record_id={chat_record_id}, user_id={current_user.id}")
    def inner():
        data = get_chart_data_with_user(chat_record_id=chat_record_id, session=session, current_user=current_user)
        SQLBotLogUtil.info(f"[DEBUG] chat_record_data returning: record_id={chat_record_id}, data={bool(data)}")
        return format_json_data(data)

    return await asyncio.to_thread(inner)


@router.get("/record/{chat_record_id}/predict_data", summary=f"{PLACEHOLDER_PREFIX}get_chart_predict_data")
async def chat_predict_data(session: SessionDep, current_user: CurrentUser, chat_record_id: int):
    def inner():
        data = get_chat_predict_data_with_user(chat_record_id=chat_record_id, session=session, current_user=current_user)
        return format_json_list_data(data)

    return await asyncio.to_thread(inner)


""" @router.post("/rename", response_model=str, summary=f"{PLACEHOLDER_PREFIX}rename_chat")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.CHAT,
    resource_id_expr="chat.id"
))
async def rename(session: SessionDep, chat: RenameChat):
    try:
        return rename_chat(session=session, rename_object=chat)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) """

@router.post("/rename", response_model=str, summary=f"{PLACEHOLDER_PREFIX}rename_chat")
@system_log(LogConfig(
    operation_type=OperationType.UPDATE,
    module=OperationModules.CHAT,
    resource_id_expr="chat.id"
))
async def rename(session: SessionDep, current_user: CurrentUser, chat: RenameChat):
    try:
        return rename_chat_with_user(session=session, current_user=current_user, rename_object=chat)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

""" @router.delete("/{chart_id}/{brief}", response_model=str, summary=f"{PLACEHOLDER_PREFIX}delete_chat")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.CHAT,
    resource_id_expr="chart_id",
    remark_expr="brief"
))
async def delete(session: SessionDep, chart_id: int, brief: str):
    try:
        return delete_chat(session=session, chart_id=chart_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) """

@router.delete("/{chart_id}/{brief}", response_model=str, summary=f"{PLACEHOLDER_PREFIX}delete_chat")
@system_log(LogConfig(
    operation_type=OperationType.DELETE,
    module=OperationModules.CHAT,
    resource_id_expr="chart_id",
    remark_expr="brief"
))
async def delete(session: SessionDep, current_user: CurrentUser, chart_id: int, brief: str):
    try:
        return delete_chat_with_user(session=session, current_user=current_user, chart_id=chart_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/start", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}start_chat")
@require_permissions(permission=SqlbotPermission(type='ds', keyExpression="create_chat_obj.datasource"))
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.CHAT,
    result_id_expr="id"
))
async def start_chat(session: SessionDep, current_user: CurrentUser, create_chat_obj: CreateChat):
    try:
        return create_chat(session, current_user, create_chat_obj)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/assistant/start", response_model=ChatInfo, summary=f"{PLACEHOLDER_PREFIX}assistant_start_chat")
@system_log(LogConfig(
    operation_type=OperationType.CREATE,
    module=OperationModules.CHAT,
    result_id_expr="id"
))
async def start_chat(session: SessionDep, current_user: CurrentUser):
    try:
        return create_chat(session, current_user, CreateChat(origin=2), False)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/recommend_questions/{chat_record_id}", summary=f"{PLACEHOLDER_PREFIX}ask_recommend_questions")
async def ask_recommend_questions(session: SessionDep, current_user: CurrentUser, chat_record_id: int,
                                  current_assistant: CurrentAssistant, articles_number: Optional[int] = 4):
    """
    生成推荐问题（使用新的业务数据层架构）

    流程：
    1. 获取聊天记录
    2. 通过 BusinessDBService 预加载所有业务数据
    3. 通过 AlgorithmEngine 生成推荐问题
    4. 返回 SSE 流
    5. 最后统一保存推荐问题到数据库
    """
    from apps.business_db.service import BusinessDBService
    import orjson

    def _return_empty():
        yield 'data: ' + orjson.dumps({'content': '[]', 'type': 'recommended_question'}).decode() + '\n\n'

    def _err(e: Exception):
        yield 'data: ' + orjson.dumps({'content': str(e), 'type': 'error'}).decode() + '\n\n'

    def generate_response():
        try:
            record = session.get(ChatRecord, chat_record_id)
            if not record:
                return

            # 创建业务数据服务
            business_service = BusinessDBService(session)

            # 调用处理流程
            for event_data in business_service.process_recommend_questions(
                record_id=chat_record_id,
                articles_number=articles_number,
                in_chat=True,
            ):
                # 转换为 SSE 格式
                json_str = orjson.dumps(event_data).decode()
                sse_data = f"data: {json_str}\n\n"
                yield sse_data

        except Exception as e:
            traceback.print_exc()
            yield from _err(e)

    return StreamingResponse(generate_response(), media_type="text/event-stream")


@router.get("/recent_questions/{datasource_id}", response_model=List[str],
            summary=f"{PLACEHOLDER_PREFIX}get_recommend_questions")
#@require_permissions(permission=SqlbotPermission(type='ds', keyExpression="datasource_id"))
async def recommend_questions(session: SessionDep, current_user: CurrentUser,
                              datasource_id: int = Path(..., description=f"{PLACEHOLDER_PREFIX}ds_id")):
    return list_recent_questions(session=session, current_user=current_user, datasource_id=datasource_id)


def find_base_question(record_id: int, session: SessionDep):
    stmt = select(ChatRecord.question, ChatRecord.regenerate_record_id).where(
        and_(ChatRecord.id == record_id))
    _record = session.execute(stmt).fetchone()
    if not _record:
        raise Exception(f'Cannot find base chat record')
    rec_question, rec_regenerate_record_id = _record
    if rec_regenerate_record_id:
        return find_base_question(rec_regenerate_record_id, session)
    else:
        return rec_question


@router.post("/question", summary=f"{PLACEHOLDER_PREFIX}ask_question")
@require_permissions(permission=SqlbotPermission(type='chat', keyExpression="request_question.chat_id"))
async def question_answer(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                          current_assistant: CurrentAssistant):
    return await question_answer_inner(session, current_user, request_question, current_assistant, embedding=True)


async def question_answer_inner(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                                current_assistant: Optional[CurrentAssistant] = None, in_chat: bool = True,
                                stream: bool = True,
                                finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, embedding: bool = False):
    try:
        command, text_before_command, record_id, warning_info = parse_quick_command(request_question.question)
        if command:
            # todo 对话界面下，暂不支持分析和预测，需要改造前端
            if in_chat and (command == QuickCommand.ANALYSIS or command == QuickCommand.PREDICT_DATA):
                raise Exception(f'Command: {command.value} temporary not supported')

            if record_id is not None:
                # 排除analysis和predict
                stmt = select(ChatRecord.id, ChatRecord.chat_id, ChatRecord.analysis_record_id,
                              ChatRecord.predict_record_id, ChatRecord.regenerate_record_id,
                              ChatRecord.first_chat).where(
                    and_(ChatRecord.id == record_id)).order_by(ChatRecord.create_time.desc())
                _record = session.execute(stmt).fetchone()
                if not _record:
                    raise Exception(f'Record id: {record_id} does not exist')

                rec_id, rec_chat_id, rec_analysis_record_id, rec_predict_record_id, rec_regenerate_record_id, rec_first_chat = _record

                if rec_chat_id != request_question.chat_id:
                    raise Exception(f'Record id: {record_id} does not belong to this chat')
                if rec_first_chat:
                    raise Exception(f'Record id: {record_id} does not support this operation')

                if rec_analysis_record_id:
                    raise Exception('Analysis record does not support this operation')
                if rec_predict_record_id:
                    raise Exception('Predict data record does not support this operation')

            else:  # get last record id
                stmt = select(ChatRecord.id, ChatRecord.chat_id, ChatRecord.regenerate_record_id).where(
                    and_(ChatRecord.chat_id == request_question.chat_id,
                         ChatRecord.first_chat == False,
                         ChatRecord.analysis_record_id.is_(None),
                         ChatRecord.predict_record_id.is_(None))).order_by(
                    ChatRecord.create_time.desc()).limit(1)
                _record = session.execute(stmt).fetchone()

                if not _record:
                    raise Exception(f'You have not ask any question')

                rec_id, rec_chat_id, rec_regenerate_record_id = _record

            # 没有指定的，就查询上一个
            if not rec_regenerate_record_id:
                rec_regenerate_record_id = rec_id

            # 针对已经是重新生成的提问，需要找到原来的提问是什么
            base_question_text = find_base_question(rec_regenerate_record_id, session)
            text_before_command = text_before_command + ("\n" if text_before_command else "") + base_question_text

            if command == QuickCommand.REGENERATE:
                request_question.question = text_before_command
                request_question.regenerate_record_id = rec_id
                return await stream_sql(session, current_user, request_question, current_assistant, in_chat, stream,
                                        finish_step, embedding)

            elif command == QuickCommand.ANALYSIS:
                return await analysis_or_predict(session, current_user, rec_id, 'analysis', current_assistant, in_chat,
                                                 stream)

            elif command == QuickCommand.PREDICT_DATA:
                return await analysis_or_predict(session, current_user, rec_id, 'predict', current_assistant, in_chat,
                                                 stream)
            else:
                raise Exception(f'Unknown command: {command.value}')
        else:
            return await stream_sql(session, current_user, request_question, current_assistant, in_chat, stream,
                                    finish_step, embedding)
    except Exception as e:
        traceback.print_exc()

        if stream:
            def _err(_e: Exception):
                if in_chat:
                    yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'
                else:
                    yield f'&#x274c; **ERROR:**\n'
                    yield f'> {str(_e)}\n'

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )


async def stream_sql_new(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                         in_chat: bool = True,
                         stream: bool = True,
                         finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, embedding: bool = False):
    """
    New architecture implementation using business_db + algorithm layers.

    Data flow:
    1. API Layer receives HTTP request
    2. BusinessDBService.process() [Main Entry Point]
       - preprocess() - Load all business data
       - AlgorithmEngine.run() - Algorithm processing
       - postprocess() - Batch save results
    3. StreamingResponse to Frontend
    """
    from apps.ai_model.model_factory import get_default_config
    from apps.business_db.service import BusinessDBService

    def generate_response():
        try:
            # 调用业务数据层主入口
            business_service = BusinessDBService(session)

            # 获取默认 AI 模型配置（复刻原 LLMService.create 的行为）
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            config = loop.run_until_complete(get_default_config())
            ai_model_id = config.model_id
            print(f"[DEBUG] stream_sql_new: ai_model_id={ai_model_id}, model_name={config.model_name}")

            # 调用 process，传入获取到的 ai_model_id
            SQLBotLogUtil.info(f"[stream_sql_new] 开始生成响应, stream={stream}")
            for event_data in business_service.process(
                current_user=current_user,
                chat_id=request_question.chat_id,
                question=request_question.question,
                datasource_id=None,
                ai_model_id=ai_model_id,
                regenerate_record_id=request_question.regenerate_record_id,
                language=request_question.lang,
                error_msg=request_question.error_msg,
                finish_step=finish_step,
                in_chat=in_chat,
                stream=stream,
            ):
                # event_data 是字典，直接序列化
                # orjson.dumps 返回 bytes，需要 decode 成 str，否则会变成 b'...' 格式
                json_str = orjson.dumps(event_data).decode()
                sse_data = f"data: {json_str}\n\n"
                event_type = event_data.get('type', '')
                event_data_content = event_data.get('data', {})
                if isinstance(event_data_content, dict):
                    data_len = len(str(event_data_content))
                elif isinstance(event_data_content, str):
                    data_len = len(event_data_content)
                else:
                    data_len = 0
                SQLBotLogUtil.info(f"[stream_sql_new] SSE输出: type={event_type}, data_len={data_len}")
                # 记录完整 SSE 数据用于调试
                SQLBotLogUtil.info(f"[stream_sql_new] SSE完整数据: {repr(sse_data[:200])}")
                yield sse_data
            SQLBotLogUtil.info(f"[stream_sql_new] 响应生成完成")

        except Exception as e:
            traceback.print_exc()
            yield f"data: {orjson.dumps({'content': str(e), 'type': 'error'})}\n\n"

    return StreamingResponse(generate_response(), media_type="text/event-stream")


async def stream_sql(session: SessionDep, current_user: CurrentUser, request_question: ChatQuestion,
                     current_assistant: Optional[CurrentAssistant] = None, in_chat: bool = True, stream: bool = True,
                     finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART, embedding: bool = False):
    """
    Main SQL streaming function. Uses new architecture if USE_NEW_ALGORITHM is enabled.
    """
    # Check if we should use the new architecture
    if settings.USE_NEW_ALGORITHM:
        return await stream_sql_new(
            session, current_user, request_question,
            in_chat, stream, finish_step, embedding
        )

    # Original implementation
    try:
        llm_service = await LLMService.create(session, current_user, request_question, current_assistant,
                                              embedding=embedding)
        llm_service.init_record(session=session)
        llm_service.run_task_async(in_chat=in_chat, stream=stream, finish_step=finish_step)
    except Exception as e:
        traceback.print_exc()

        if stream:
            def _err(_e: Exception):
                yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )
    if stream:
        return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")
    else:
        res = llm_service.await_result()
        raw_data = {}
        for chunk in res:
            if chunk:
                raw_data = chunk
        status_code = 200
        if not raw_data.get('success'):
            status_code = 500

        return JSONResponse(
            content=raw_data,
            status_code=status_code,
        )


@router.post("/record/{chat_record_id}/{action_type}", summary=f"{PLACEHOLDER_PREFIX}analysis_or_predict")
async def analysis_or_predict_question(session: SessionDep, current_user: CurrentUser,
                                       current_assistant: CurrentAssistant, chat_record_id: int,
                                       action_type: str = Path(...,
                                                               description=f"{PLACEHOLDER_PREFIX}analysis_or_predict_action_type")):
    return await analysis_or_predict(session, current_user, chat_record_id, action_type, current_assistant)


async def analysis_or_predict(session: SessionDep, current_user: CurrentUser, chat_record_id: int, action_type: str,
                              current_assistant: CurrentAssistant, in_chat: bool = True, stream: bool = True):
    try:
        if action_type != 'analysis' and action_type != 'predict':
            raise Exception(f"Type {action_type} Not Found")
        record: ChatRecord | None = None

        stmt = select(ChatRecord.id, ChatRecord.question, ChatRecord.chat_id, ChatRecord.datasource,
                      ChatRecord.engine_type,
                      ChatRecord.ai_modal_id, ChatRecord.create_by, ChatRecord.chart, ChatRecord.data).where(
            and_(ChatRecord.id == chat_record_id))
        result = session.execute(stmt)
        for r in result:
            record = ChatRecord(id=r.id, question=r.question, chat_id=r.chat_id, datasource=r.datasource,
                                engine_type=r.engine_type, ai_modal_id=r.ai_modal_id, create_by=r.create_by,
                                chart=r.chart,
                                data=r.data)

        if not record:
            raise Exception(f"Chat record with id {chat_record_id} not found")

        if not record.chart:
            raise Exception(
                f"Chat record with id {chat_record_id} has not generated chart, do not support to analyze it")

        request_question = ChatQuestion(chat_id=record.chat_id, question=record.question)

        llm_service = await LLMService.create(session, current_user, request_question, current_assistant)
        llm_service.run_analysis_or_predict_task_async(session, action_type, record, in_chat, stream)
    except Exception as e:
        traceback.print_exc()
        if stream:
            def _err(_e: Exception):
                if in_chat:
                    yield 'data:' + orjson.dumps({'content': str(_e), 'type': 'error'}).decode() + '\n\n'
                else:
                    yield f'&#x274c; **ERROR:**\n'
                    yield f'> {str(_e)}\n'

            return StreamingResponse(_err(e), media_type="text/event-stream")
        else:
            return JSONResponse(
                content={'message': str(e)},
                status_code=500,
            )
    if stream:
        return StreamingResponse(llm_service.await_result(), media_type="text/event-stream")
    else:
        res = llm_service.await_result()
        raw_data = {}
        for chunk in res:
            if chunk:
                raw_data = chunk
        status_code = 200
        if not raw_data.get('success'):
            status_code = 500

        return JSONResponse(
            content=raw_data,
            status_code=status_code,
        )


@router.get("/record/{chat_record_id}/excel/export/{chat_id}", summary=f"{PLACEHOLDER_PREFIX}export_chart_data")
@system_log(LogConfig(operation_type=OperationType.EXPORT,module=OperationModules.CHAT,resource_id_expr="chat_id",))
async def export_excel(session: SessionDep, current_user: CurrentUser, chat_record_id: int,chat_id: int,  trans: Trans):
    chat_record = session.get(ChatRecord, chat_record_id)
    if not chat_record:
        raise HTTPException(
            status_code=500,
            detail=f"ChatRecord with id {chat_record_id} not found"
        )
    if chat_record.create_by != current_user.id:
        raise HTTPException(
            status_code=500,
            detail=f"ChatRecord with id {chat_record_id} not Owned by the current user"
        )
    is_predict_data = chat_record.predict_record_id is not None

    _origin_data = format_json_data(get_chat_chart_data(chat_record_id=chat_record_id, session=session))

    _base_field = _origin_data.get('fields')
    _data = _origin_data.get('data')

    if not _data:
        raise HTTPException(
            status_code=500,
            detail=trans("i18n_excel_export.data_is_empty")
        )

    chart_info = get_chart_config(session, chat_record_id)

    _title = chart_info.get('title') if chart_info.get('title') else 'Excel'

    fields = []
    if chart_info.get('columns') and len(chart_info.get('columns')) > 0:
        for column in chart_info.get('columns'):
            fields.append(AxisObj(name=column.get('name'), value=column.get('value')))
    if chart_info.get('axis'):
        for _type in ['x', 'y', 'series']:
            if chart_info.get('axis').get(_type):
                column = chart_info.get('axis').get(_type)
                fields.append(AxisObj(name=column.get('name'), value=column.get('value')))

    _predict_data = []
    if is_predict_data:
        _predict_data = format_json_list_data(get_chat_predict_data(chat_record_id=chat_record_id, session=session))

    def inner():

        data_list = DataFormat.convert_large_numbers_in_object_array(_data + _predict_data)

        md_data, _fields_list = DataFormat.convert_object_array_for_pandas(fields, data_list)

        # data, _fields_list, col_formats = LLMService.format_pd_data(fields, _data + _predict_data)

        df = pd.DataFrame(md_data, columns=_fields_list)

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='xlsxwriter',
                            engine_kwargs={'options': {'strings_to_numbers': False}}) as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

            # 获取 xlsxwriter 的工作簿和工作表对象
            # workbook = writer.book
            # worksheet = writer.sheets['Sheet1']
            #
            # for col_idx, fmt_type in col_formats.items():
            #     if fmt_type == 'text':
            #         worksheet.set_column(col_idx, col_idx, None, workbook.add_format({'num_format': '@'}))
            #     elif fmt_type == 'number':
            #         worksheet.set_column(col_idx, col_idx, None, workbook.add_format({'num_format': '0'}))

        buffer.seek(0)
        return io.BytesIO(buffer.getvalue())

    result = await asyncio.to_thread(inner)
    return StreamingResponse(result, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

from fastapi import APIRouter, HTTPException
from sqlmodel import select
from apps.chat.schemas.chat_base_schema import LLMConfig
from apps.chat.schemas.chat_schema import ChatQuestion
from apps.chat.schemas.llm import LLMService
from apps.system.models.system_modle import AiModelDetail
from common.core.deps import SessionDep
# from sse_starlette.sse import EventSourceResponse
router = APIRouter(tags=["Data Q&A"], prefix="/chat")


@router.post("/question")
async def stream_sql(session: SessionDep, requestQuestion: ChatQuestion):
    question = requestQuestion.question
    
    # Use OpenAI model
    """ openai_config = LLMConfig(
        model_type="openai",
        model_name="gpt-4",
        api_key="your-api-key",
        additional_params={"temperature": 0.7}
    )
    openai_service = LLMService(openai_config) """

    aimodel = session.exec(select(AiModelDetail).where(AiModelDetail.status == True, AiModelDetail.api_key.is_not(None))).first()
    
    if not aimodel:
        raise HTTPException(
            status_code=400,
            detail="No available AI model configuration found"
        )
    
    # Use Tongyi Qianwen
    tongyi_config = LLMConfig(
        model_type="tongyi",
        model_name=aimodel.name,
        api_key=aimodel.api_key,
        additional_params={"temperature": aimodel.temperature}
    )
    llm_service = LLMService(tongyi_config)

    # Use Custom VLLM model
    """ vllm_config = LLMConfig(
        model_type="vllm",
        model_name="your-model-path",
        additional_params={
            "max_new_tokens": 200,
            "temperature": 0.3
        }
    )
    vllm_service = LLMService(vllm_config) """
    result = llm_service.generate_sql(question)
    return result
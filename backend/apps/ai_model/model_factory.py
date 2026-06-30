"""
脚本说明：这个脚本放AI 模型相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from functools import lru_cache
import json
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Type
from urllib.parse import urlparse

from langchain.chat_models.base import BaseChatModel
from pydantic import BaseModel
from sqlmodel import Session, select

from apps.ai_model.openai.llm import BaseChatOpenAI
from apps.system.models.system_model import AiModelDetail
from common.core.config import settings
from common.core.db import engine
from common.utils.crypto import shuzhi_decrypt
from common.utils.utils import prepare_model_arg
from langchain_community.llms import VLLMOpenAI
from langchain_openai import AzureChatOpenAI


# from langchain_community.llms import Tongyi, VLLM

class LLMConfig(BaseModel):
    """
    类说明：LLMConfig 放AI 模型的配置项，让后续流程能按同一套规则运行。
    """
    model_id: Optional[int] = None
    model_type: str  # 模型类型：openai/tongyi/vllm 等。
    model_name: str  # 具体模型名称
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    additional_params: Dict[str, Any] = {}

    class Config:
        """
        类说明：Config 放AI 模型的配置项，让后续流程能按同一套规则运行。
        """
        frozen = True

    def __hash__(self):
        """
        是什么：LLMConfig.__hash__ 是 LLMConfig 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：让这个对象能配合 Python 的特殊用法工作。
        """
        if hasattr(self, 'additional_params') and isinstance(self.additional_params, dict):
            hashable_params = frozenset((k, tuple(v) if isinstance(v, (list, dict)) else v)
                                        for k, v in self.additional_params.items())
        else:
            hashable_params = None

        return hash((
            self.model_id,
            self.model_type,
            self.model_name,
            self.api_key,
            self.api_base_url,
            hashable_params
        ))


class BaseLLM(ABC):
    """
    类说明：BaseLLM 把AI 模型相关的数据和行为放在一起，便于其他代码直接复用。
    """

    def __init__(self, config: LLMConfig):
        """
        是什么：BaseLLM.__init__ 是 BaseLLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：创建 BaseLLM 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.config = config
        self._llm = self._init_llm()

    @abstractmethod
    def _init_llm(self) -> BaseChatModel:
        """
        是什么：BaseLLM._init_llm 是 BaseLLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：拿到 BaseLLM 对象的代码，需要完成这个动作时会调用它。
        做了什么：创建或保存AI 模型需要的东西，让后续流程能继续往下走。
        """
        pass

    @property
    def llm(self) -> BaseChatModel:
        """
        是什么：BaseLLM.llm 是 BaseLLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把AI 模型里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self._llm


class OpenAIvLLM(BaseLLM):
    """
    类说明：OpenAIvLLM 把AI 模型相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def _init_llm(self) -> VLLMOpenAI:
        """
        是什么：OpenAIvLLM._init_llm 是 OpenAIvLLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：拿到 OpenAIvLLM 对象的代码，需要完成这个动作时会调用它。
        做了什么：创建或保存AI 模型需要的东西，让后续流程能继续往下走。
        """
        return VLLMOpenAI(
            openai_api_key=self.config.api_key or 'Empty',
            openai_api_base=self.config.api_base_url,
            model_name=self.config.model_name,
            streaming=True,
            **self.config.additional_params,
        )


class OpenAIAzureLLM(BaseLLM):
    """
    类说明：OpenAIAzureLLM 把AI 模型相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def _init_llm(self) -> AzureChatOpenAI:
        """
        是什么：OpenAIAzureLLM._init_llm 是 OpenAIAzureLLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：拿到 OpenAIAzureLLM 对象的代码，需要完成这个动作时会调用它。
        做了什么：创建或保存AI 模型需要的东西，让后续流程能继续往下走。
        """
        api_version = self.config.additional_params.get("api_version")
        deployment_name = self.config.additional_params.get("deployment_name")
        if api_version:
            self.config.additional_params.pop("api_version")
        if deployment_name:
            self.config.additional_params.pop("deployment_name")
        return AzureChatOpenAI(
            azure_endpoint=self.config.api_base_url,
            api_key=self.config.api_key or 'Empty',
            model_name=self.config.model_name,
            api_version=api_version,
            deployment_name=deployment_name,
            streaming=True,
            timeout=settings.LLM_REQUEST_TIMEOUT,
            max_retries=settings.LLM_MAX_RETRIES,
            **self.config.additional_params,
        )


class OpenAILLM(BaseLLM):
    """
    类说明：OpenAILLM 把AI 模型相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def _init_llm(self) -> BaseChatModel:
        """
        是什么：OpenAILLM._init_llm 是 OpenAILLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：拿到 OpenAILLM 对象的代码，需要完成这个动作时会调用它。
        做了什么：创建或保存AI 模型需要的东西，让后续流程能继续往下走。
        """
        return BaseChatOpenAI(
            model=self.config.model_name,
            api_key=self.config.api_key or 'Empty',
            base_url=self.config.api_base_url,
            stream_usage=True,
            timeout=settings.LLM_REQUEST_TIMEOUT,
            max_retries=settings.LLM_MAX_RETRIES,
            **self.config.additional_params,
        )

    def generate(self, prompt: str) -> str:
        """
        是什么：OpenAILLM.generate 是 OpenAILLM 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：拿到 OpenAILLM 对象的代码，需要完成这个动作时会调用它。
        做了什么：根据已有信息生成AI 模型的结果，比如答案、SQL、图表或建议。
        """
        return self.llm.invoke(prompt)


class LLMFactory:
    """
    类说明：LLMFactory 把AI 模型相关的数据和行为放在一起，便于其他代码直接复用。
    """

    _llm_types: Dict[str, Type[BaseLLM]] = {
        "openai": OpenAILLM,
        "tongyi": OpenAILLM,
        "vllm": OpenAIvLLM,
        "azure": OpenAIAzureLLM,
    }

    @classmethod
    @lru_cache(maxsize=32)
    def create_llm(cls, config: LLMConfig) -> BaseLLM:
        """
        是什么：LLMFactory.create_llm 是 LLMFactory 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：需要通过类本身做这件事时，代码会调用它。
        做了什么：创建或保存AI 模型需要的东西，让后续流程能继续往下走。
        """
        llm_class = cls._llm_types.get(config.model_type)
        if not llm_class:
            raise ValueError(f"Unsupported LLM type: {config.model_type}")
        return llm_class(config)

    @classmethod
    def register_llm(cls, model_type: str, llm_class: Type[BaseLLM]):
        """
        是什么：LLMFactory.register_llm 是 LLMFactory 里的一个步骤，帮它完成AI 模型相关的一件事。
        谁调用：需要通过类本身做这件事时，代码会调用它。
        做了什么：把AI 模型里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        cls._llm_types[model_type] = llm_class


def _normalize_api_base_url(raw_url: Optional[str]) -> Optional[str]:
    """
    是什么：_normalize_api_base_url 是一个可以复用的小步骤，负责AI 模型相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把AI 模型的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if raw_url is None:
        return None
    url = raw_url.strip()
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            "AI model API domain must start with http:// or https://"
        )
    if not parsed.netloc:
        raise ValueError("AI model API domain is missing host information")
    return url


# 待办
""" def get_llm_config(aimodel: AiModelDetail) -> LLMConfig:
    config = LLMConfig(
        model_type="openai",
        model_name=aimodel.name,
        api_key=aimodel.api_key,
        api_base_url=aimodel.endpoint,
        additional_params={"temperature": aimodel.temperature}
    )
    return config """


async def get_default_config(custom_model_id: Optional[int] = None) -> LLMConfig:
    """
    是什么：get_default_config 是一个可以复用的小步骤，负责AI 模型相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把AI 模型需要的数据找出来，整理成后面好用的样子。
    """
    with Session(engine) as session:
        db_model: AiModelDetail | None = None
        if custom_model_id:
            db_model = session.get(AiModelDetail, custom_model_id)
        if not db_model:
            db_model = session.exec(
                select(AiModelDetail).where(AiModelDetail.default_model == True)
            ).first()
        if not db_model:
            raise Exception("The system default model has not been set")

        additional_params = {}
        if db_model.config:
            try:
                config_raw = json.loads(db_model.config)
                additional_params = {item["key"]: prepare_model_arg(item.get('val')) for item in config_raw if
                                     "key" in item and "val" in item}
            except Exception:
                pass
        if db_model.api_domain:
            db_model.api_domain = await shuzhi_decrypt(db_model.api_domain)
        if db_model.api_key:
            db_model.api_key = await shuzhi_decrypt(db_model.api_key)
        db_model.api_domain = _normalize_api_base_url(db_model.api_domain)

        # 构造大语言模型配置
        return LLMConfig(
            model_id=db_model.id,
            model_type="openai" if db_model.protocol == 1 else "vllm",
            model_name=db_model.base_model,
            api_key=db_model.api_key,
            api_base_url=db_model.api_domain,
            additional_params=additional_params,
        )

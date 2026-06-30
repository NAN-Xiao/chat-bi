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
    """大语言模型基础配置类"""
    model_id: Optional[int] = None
    model_type: str  # 模型类型：openai/tongyi/vllm 等。
    model_name: str  # 具体模型名称
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    additional_params: Dict[str, Any] = {}

    class Config:
        frozen = True

    def __hash__(self):
        """
        是什么：LLMConfig.__hash__ 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由 Python 运行时、框架协议或相关内置操作按需调用。
        做了什么：实现 Python 协议方法，使对象可以参与对应的语言级操作。
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
    """大语言模型抽象基类"""

    def __init__(self, config: LLMConfig):
        """
        是什么：BaseLLM.__init__ 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由创建 BaseLLM 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.config = config
        self._llm = self._init_llm()

    @abstractmethod
    def _init_llm(self) -> BaseChatModel:
        """
        是什么：BaseLLM._init_llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由持有 BaseLLM 实例的业务代码、框架回调或测试代码调用。
        做了什么：创建、初始化或组装模型接入相关对象和数据，并返回或写入对应状态。
        """
        pass

    @property
    def llm(self) -> BaseChatModel:
        """
        是什么：BaseLLM.llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由 Python 属性访问语法或依赖该属性的业务代码调用。
        做了什么：围绕 llm 的语义处理模型接入相关逻辑，并把结果返回或写入状态。
        """
        return self._llm


class OpenAIvLLM(BaseLLM):
    def _init_llm(self) -> VLLMOpenAI:
        """
        是什么：OpenAIvLLM._init_llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由持有 OpenAIvLLM 实例的业务代码、框架回调或测试代码调用。
        做了什么：创建、初始化或组装模型接入相关对象和数据，并返回或写入对应状态。
        """
        return VLLMOpenAI(
            openai_api_key=self.config.api_key or 'Empty',
            openai_api_base=self.config.api_base_url,
            model_name=self.config.model_name,
            streaming=True,
            **self.config.additional_params,
        )


class OpenAIAzureLLM(BaseLLM):
    def _init_llm(self) -> AzureChatOpenAI:
        """
        是什么：OpenAIAzureLLM._init_llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由持有 OpenAIAzureLLM 实例的业务代码、框架回调或测试代码调用。
        做了什么：创建、初始化或组装模型接入相关对象和数据，并返回或写入对应状态。
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
    def _init_llm(self) -> BaseChatModel:
        """
        是什么：OpenAILLM._init_llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由持有 OpenAILLM 实例的业务代码、框架回调或测试代码调用。
        做了什么：创建、初始化或组装模型接入相关对象和数据，并返回或写入对应状态。
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
        是什么：OpenAILLM.generate 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由持有 OpenAILLM 实例的业务代码、框架回调或测试代码调用。
        做了什么：基于输入上下文生成模型接入相关结果，并保存或返回给调用方。
        """
        return self.llm.invoke(prompt)


class LLMFactory:
    """大语言模型工厂类"""

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
        是什么：LLMFactory.create_llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：创建、初始化或组装模型接入相关对象和数据，并返回或写入对应状态。
        """
        llm_class = cls._llm_types.get(config.model_type)
        if not llm_class:
            raise ValueError(f"Unsupported LLM type: {config.model_type}")
        return llm_class(config)

    @classmethod
    def register_llm(cls, model_type: str, llm_class: Type[BaseLLM]):
        """
        是什么：LLMFactory.register_llm 是 backend/apps/ai_model/model_factory.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：围绕 register_llm 的语义处理模型接入相关逻辑，并把结果返回或写入状态。
        """
        cls._llm_types[model_type] = llm_class


def _normalize_api_base_url(raw_url: Optional[str]) -> Optional[str]:
    """
    是什么：_normalize_api_base_url 是 backend/apps/ai_model/model_factory.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化模型接入相关数据，生成后续流程可使用的结构。
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
    是什么：get_default_config 是 backend/apps/ai_model/model_factory.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询模型接入相关数据，整理后返回给调用方。
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

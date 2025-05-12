from pydantic import BaseModel
from typing import Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseLLM as LangchainBaseLLM
from langchain_openai import ChatOpenAI
from langchain_community.llms import Tongyi, VLLM

class LLMConfig(BaseModel):
    """Base configuration class for large language models"""
    model_type: str  # Model type: openai/tongyi/vllm etc.
    model_name: str  # Specific model name
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    additional_params: Dict[str, Any] = {}
    

class BaseLLM(ABC):
    """Abstract base class for large language models"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._llm = self._init_llm()
    
    @abstractmethod
    def _init_llm(self) -> LangchainBaseLLM:
        """Initialize specific large language model instance"""
        pass
    
    @property
    def llm(self) -> LangchainBaseLLM:
        """Return the langchain LLM instance"""
        return self._llm

class OpenAILLM(BaseLLM):
    def _init_llm(self) -> LangchainBaseLLM:
        return ChatOpenAI(
            model=self.config.model_name,
            api_key=self.config.api_key,
            **self.config.additional_params
        )
    
    def generate(self, prompt: str) -> str:
        return self.llm.invoke(prompt)

class TongyiLLM(BaseLLM):
    def _init_llm(self) -> LangchainBaseLLM:
        return Tongyi(
            model_name=self.config.model_name,
            dashscope_api_key=self.config.api_key,
            **self.config.additional_params
        )
    
    def generate(self, prompt: str) -> str:
        return self.llm.invoke(prompt)

class VLLMLLM(BaseLLM):
    def _init_llm(self) -> LangchainBaseLLM:
        return VLLM(
            model=self.config.model_name,
            **self.config.additional_params
        )
    
    def generate(self, prompt: str) -> str:
        return self.llm.invoke(prompt)


class LLMFactory:
    """Large Language Model Factory Class"""
    
    _llm_types: Dict[str, Type[BaseLLM]] = {
        "openai": OpenAILLM,
        "tongyi": TongyiLLM,
        "vllm": VLLMLLM
    }
    
    @classmethod
    def create_llm(cls, config: LLMConfig) -> BaseLLM:
        llm_class = cls._llm_types.get(config.model_type)
        if not llm_class:
            raise ValueError(f"Unsupported LLM type: {config.model_type}")
        return llm_class(config)
    
    @classmethod
    def register_llm(cls, model_type: str, llm_class: Type[BaseLLM]):
        """Register new model type"""
        cls._llm_types[model_type] = llm_class
"""后端注册表。新增后端只需实现 BaseProvider 并在这里登记。"""

from .ark import ArkProvider
from .base import BaseProvider, ProviderError, ProviderResult
from .mock import MockProvider
from .openai_compat import OpenAICompatProvider

REGISTRY = {
    "ark": ArkProvider,
    "openai": OpenAICompatProvider,
    "mock": MockProvider,
}


def get_provider(name: str, model: str | None = None) -> BaseProvider:
    key = (name or "").strip().lower()
    if key not in REGISTRY:
        raise ProviderError(f"未知后端 {name!r}，可用：{', '.join(REGISTRY)}")
    return REGISTRY[key](model=model) if model else REGISTRY[key]()

"""出图后端：统一的 generate 接口。"""

import base64
from dataclasses import dataclass


class ProviderError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


@dataclass
class ProviderResult:
    data: bytes
    provider: str
    model: str
    # 真实后端有意义的附加信息（例如上游返回的 url），写进 manifest 便于追溯
    note: str = ""


class BaseProvider:
    name = "base"
    model = ""

    def generate(self, job, reference_image: str | None = None) -> ProviderResult:
        raise NotImplementedError

    def describe(self) -> str:
        return f"{self.name}:{self.model}" if self.model else self.name


def _b64(data: str) -> bytes:
    return base64.b64decode(data)

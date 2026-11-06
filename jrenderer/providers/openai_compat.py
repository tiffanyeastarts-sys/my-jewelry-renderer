"""OpenAI 兼容的 /images/generations 后端（可对接自建 SD、DashScope 兼容层、其他中转）。

环境变量：
  IMAGE_API_BASE   必填，例如 https://api.openai.com/v1
  IMAGE_API_KEY    必填
  IMAGE_API_MODEL  可选，默认 gpt-image-1
"""

import os

import requests

from .base import BaseProvider, ProviderError, ProviderResult, _b64


class OpenAICompatProvider(BaseProvider):
    name = "openai"

    def __init__(self, model: str | None = None, timeout: int = 180):
        self.base_url = os.environ.get("IMAGE_API_BASE", "").strip().rstrip("/")
        self.api_key = os.environ.get("IMAGE_API_KEY", "").strip()
        if not self.base_url or not self.api_key:
            raise ProviderError("需要同时设置 IMAGE_API_BASE 与 IMAGE_API_KEY")
        self.model = model or os.environ.get("IMAGE_API_MODEL", "gpt-image-1")
        self.timeout = timeout

    def generate(self, job, reference_image: str | None = None) -> ProviderResult:
        body = {
            "model": self.model,
            "prompt": job.prompt,
            "size": job.size,
            "n": 1,
            "response_format": "b64_json",
        }
        try:
            resp = requests.post(
                f"{self.base_url}/images/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"网络错误：{exc}", retryable=True) from exc

        if resp.status_code != 200:
            retryable = resp.status_code in (429, 500, 502, 503, 504)
            raise ProviderError(
                f"上游返回 {resp.status_code}：{resp.text[:300]}",
                retryable=retryable,
                status=resp.status_code,
            )

        try:
            item = resp.json()["data"][0]
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError(f"无法解析响应：{resp.text[:300]}", retryable=True) from exc

        if item.get("b64_json"):
            return ProviderResult(data=_b64(item["b64_json"]), provider=self.name, model=self.model)
        if item.get("url"):
            try:
                img = requests.get(item["url"], timeout=self.timeout)
                img.raise_for_status()
            except requests.RequestException as exc:
                raise ProviderError(f"下载生成结果失败：{exc}", retryable=True) from exc
            return ProviderResult(data=img.content, provider=self.name, model=self.model, note=item["url"])
        raise ProviderError("响应中没有图片数据", retryable=True)

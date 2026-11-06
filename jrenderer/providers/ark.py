"""火山方舟（豆包 Seedream）图像生成后端。

环境变量：
  ARK_API_KEY    必填，方舟 API Key
  ARK_BASE_URL   可选，默认 https://ark.cn-beijing.volces.com/api/v3
  ARK_IMAGE_MODEL 可选，默认 doubao-seedream-4-0-250828
"""

import base64
import os
from pathlib import Path

import requests

from .base import BaseProvider, ProviderError, ProviderResult, _b64

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedream-4-0-250828"


def _image_payload(reference_image: str | None) -> str | None:
    """参考图可以是 http(s) URL，也可以是本地文件——本地图转成 data URL。"""
    if not reference_image:
        return None
    if reference_image.startswith(("http://", "https://", "data:")):
        return reference_image
    path = Path(reference_image)
    if not path.exists():
        raise ProviderError(f"参考图不存在：{reference_image}")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


class ArkProvider(BaseProvider):
    name = "ark"

    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int = 180):
        self.api_key = os.environ.get("ARK_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderError("未设置 ARK_API_KEY 环境变量")
        self.model = model or os.environ.get("ARK_IMAGE_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.environ.get("ARK_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout

    def generate(self, job, reference_image: str | None = None) -> ProviderResult:
        body = {
            "model": self.model,
            "prompt": job.prompt,
            "size": job.size,
            "response_format": "b64_json",
            "watermark": False,
        }
        ref = _image_payload(reference_image)
        if ref:
            body["image"] = ref

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
                f"方舟返回 {resp.status_code}：{resp.text[:300]}",
                retryable=retryable,
                status=resp.status_code,
            )

        try:
            payload = resp.json()
            item = payload["data"][0]
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError(f"无法解析方舟响应：{resp.text[:300]}", retryable=True) from exc

        if item.get("b64_json"):
            return ProviderResult(data=_b64(item["b64_json"]), provider=self.name, model=self.model)
        if item.get("url"):
            try:
                img = requests.get(item["url"], timeout=self.timeout)
                img.raise_for_status()
            except requests.RequestException as exc:
                raise ProviderError(f"下载生成结果失败：{exc}", retryable=True) from exc
            return ProviderResult(
                data=img.content, provider=self.name, model=self.model, note=item["url"]
            )
        raise ProviderError("方舟响应中没有图片数据", retryable=True)

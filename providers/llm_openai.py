#!/usr/bin/env python3
"""
LLM Provider: OpenAI / OpenAI 兼容格式
支持：OpenAI GPT、DeepSeek、通义千问、文心一言等所有 OpenAI 格式兼容的模型。
"""

import requests
from .base import LLMProvider


class OpenAILLM(LLMProvider):
    """OpenAI 兼容 API 适配器（支持所有 /v1/chat/completions 格式的服务）"""

    def __init__(self, api_url: str, api_key: str, model: str = "gpt-4o"):
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return f"OpenAI Compatible ({self._model})"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def chat(self, prompt: str, max_tokens: int = 1024) -> str:
        if not self._api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            resp = requests.post(
                f"{self._api_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  ✗ OpenAI 兼容 API 调用失败: {e}")
            return None

#!/usr/bin/env python3
"""
LLM Provider: MiniMax-M2.7（Anthropic 兼容格式）
"""

import requests
from .base import LLMProvider


class MiniMaxLLM(LLMProvider):
    """MiniMax AI 大模型适配器（默认）"""

    def __init__(self, api_url: str, api_key: str, model: str = "MiniMax-M2.7"):
        self._api_url = api_url
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return f"MiniMax ({self._model})"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def chat(self, prompt: str, max_tokens: int = 1024) -> str:
        if not self._api_key:
            return None

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            resp = requests.post(
                f"{self._api_url}/v1/messages",
                json=payload,
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            # 过滤 thinking 块，只取 text 类型
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"].strip()
            return None
        except Exception as e:
            print(f"  ✗ MiniMax AI 调用失败: {e}")
            return None

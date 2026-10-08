from __future__ import annotations

import json
import urllib.request
from http.client import HTTPException
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, field_validator

from src.ai_agent.prompts_fa import SYSTEM_FA
from src.models import Model


class AgentConfig(Model):
    model: str = Field(default="mshojaei77/gemma3persian", min_length=1, max_length=200)
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = Field(default=45, gt=0, le=120)

    @field_validator("base_url")
    @classmethod
    def local_only(cls, value: str) -> str:
        parsed = urlparse(value)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1") or
                parsed.username or parsed.password or parsed.query or parsed.fragment or
                parsed.path not in ("", "/")):
            raise ValueError("فقط نشانی صریح loopback محلی مجاز است")
        return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise ValueError("تغییر مسیر شبکه مجاز نیست")


class FinancialAgent:
    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()

    def advise(self, computed_context: dict[str, Any]) -> dict[str, str]:
        context_text = json.dumps(computed_context, ensure_ascii=False, allow_nan=False)
        if len(context_text.encode("utf-8")) > 65536:
            raise ValueError("حجم زمینه مدل بیش از حد است")
        payload = {"model": self.config.model, "stream": False,
                   "messages": [{"role": "system", "content": SYSTEM_FA},
                                {"role": "user", "content": context_text}],
                   "options": {"temperature": 0, "num_predict": 1024}}
        request = urllib.request.Request(self.config.base_url + "/api/chat",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(65537)
        except HTTPException as exc:
            raise ValueError("انتقال پاسخ مدل کامل نشد") from exc
        if len(raw) > 65536:
            raise ValueError("پاسخ مدل بیش از حد مجاز است")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("done") is False:
            raise ValueError("پاسخ مدل ناقص یا نامعتبر است")
        message = result.get("message")
        if not isinstance(message, dict) or message.get("tool_calls"):
            raise ValueError("پاسخ مدل نامعتبر است؛ اجرای ابزار مجاز نیست")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 12000:
            raise ValueError("پاسخ مدل معتبر نیست")
        return {"status_fa": "پیش‌نویس تأییدنشده؛ اعداد متن باید با محاسبات تطبیق داده شوند",
                "text_fa": content, "model": self.config.model}

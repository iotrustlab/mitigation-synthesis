"""Small model-independent client for an OpenAI-compatible chat endpoint.

The Dr.ICS process deliberately has no dependency on the OpenAI Python SDK or
on a model-serving framework.  A local vLLM server is one compatible backend;
another local or remote implementation can be selected through configuration.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping, Sequence
from urllib.parse import urlparse

from .structured_output_schema import (
    INCOMPATIBLE,
    BackendSchemaCapabilities,
    ServingSchemaPlan,
    build_serving_schema,
)


class BackendError(RuntimeError):
    """Raised when the configured inference endpoint cannot return a response."""


class StructuredOutputCompatibilityError(BackendError):
    """Raised before HTTP when reviewed serving adaptation cannot be safe."""

    def __init__(self, plan: ServingSchemaPlan) -> None:
        details = ", ".join(
            f"{item.path}:{item.keyword}"
            for item in plan.unsupported_unhandled_constraints
        )
        super().__init__(
            "structured-output schema preflight is INCOMPATIBLE; "
            f"unhandled constraints: {details or 'unknown'}"
        )
        self.plan = plan


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 180.0
    temperature: float = 0.0
    top_p: float = 1.0
    max_output_tokens: int = 4096
    seed: int | None = 20260926
    disable_thinking: bool = True

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not embed credentials; use api_key instead")
        if not self.model.strip():
            raise ValueError("model must be nonempty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.temperature < 0:
            raise ValueError("temperature must be nonnegative")
        if not 0 < self.top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def public_dict(self) -> dict[str, object]:
        """Return reproducibility metadata without exposing an API key."""

        return {
            "base_url": self.normalized_base_url,
            "model": self.model,
            "api_key_configured": self.api_key is not None,
            "timeout_seconds": self.timeout_seconds,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": self.max_output_tokens,
            "seed": self.seed,
            "disable_thinking": self.disable_thinking,
        }


@dataclass(frozen=True)
class BackendResponse:
    content: str
    response_id: str | None
    model: str | None
    finish_reason: str | None
    usage: Mapping[str, object]
    elapsed_seconds: float
    raw_response: Mapping[str, object]
    schema_compatibility: Mapping[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "content": self.content,
            "response_id": self.response_id,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "usage": dict(self.usage),
            "elapsed_seconds": self.elapsed_seconds,
            "raw_response": dict(self.raw_response),
            "schema_compatibility": (
                None
                if self.schema_compatibility is None
                else dict(self.schema_compatibility)
            ),
        }


class OpenAICompatibleBackend:
    """HTTP client for the portable subset of the Chat Completions protocol."""

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        schema_capabilities: BackendSchemaCapabilities | None = None,
    ):
        self.config = config
        self.schema_capabilities = schema_capabilities or BackendSchemaCapabilities(
            "full JSON Schema"
        )

    def preflight_schema(
        self, canonical_schema: Mapping[str, object]
    ) -> ServingSchemaPlan:
        return build_serving_schema(canonical_schema, self.schema_capabilities)

    def list_models(self) -> Mapping[str, object]:
        return self._request_json("GET", "/models")

    def server_version(self) -> Mapping[str, object] | None:
        """Return optional vLLM-style version metadata when the server exposes it."""

        try:
            return self._request_json("GET", "/version")
        except BackendError:
            if not self.config.normalized_base_url.endswith("/v1"):
                return None
            try:
                root = self.config.normalized_base_url[:-3].rstrip("/")
                return self._request_json_at_url("GET", f"{root}/version")
            except BackendError:
                return None

    def complete_json(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        schema_name: str,
        json_schema: Mapping[str, object],
    ) -> BackendResponse:
        schema_plan = self.preflight_schema(json_schema)
        if schema_plan.status == INCOMPATIBLE:
            raise StructuredOutputCompatibilityError(schema_plan)
        request: dict[str, object] = {
            "model": self.config.model,
            "messages": [dict(message) for message in messages],
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema_plan.serving_schema,
                },
            },
        }
        if self.config.seed is not None:
            request["seed"] = self.config.seed
        if self.config.disable_thinking:
            # Supported by Qwen chat templates in vLLM/SGLang. Other compatible
            # servers may ignore or reject it; that is an explicit compatibility
            # result rather than a hidden model-specific code path.
            request["chat_template_kwargs"] = {"enable_thinking": False}

        started = time.perf_counter()
        raw = self._request_json("POST", "/chat/completions", request)
        elapsed = time.perf_counter() - started
        try:
            choices = raw["choices"]
            if not isinstance(choices, list) or not choices:
                raise TypeError("choices must be a nonempty list")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise TypeError("choice must be an object")
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError("message must be an object")
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError("message content must be text")
        except (KeyError, TypeError) as exc:
            raise BackendError(f"chat response has an unsupported shape: {exc}") from exc
        usage = raw.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        return BackendResponse(
            content=content,
            response_id=_optional_string(raw.get("id")),
            model=_optional_string(raw.get("model")),
            finish_reason=_optional_string(choice.get("finish_reason")),
            usage=usage,
            elapsed_seconds=elapsed,
            raw_response=raw,
            schema_compatibility=schema_plan.report_dict(),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        url = f"{self.config.normalized_base_url}{path}"
        return self._request_json_at_url(method, url, payload)

    def _request_json_at_url(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            raise BackendError(f"{method} {url} returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(f"{method} {url} failed: {exc}") from exc
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise BackendError(f"{method} {url} returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise BackendError(f"{method} {url} returned a non-object JSON response")
        return parsed


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None

"""
AWS Bedrock – Claude 3.5 Sonnet wrapper (streaming + non-streaming)
"""
import json
from collections.abc import AsyncGenerator
from typing import Any

import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import TokenQuotaExceededError
from app.core.logging import get_logger

logger = get_logger(__name__)


class BedrockService:
    def __init__(self):
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def invoke(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Tek seferlik (non-streaming) Bedrock çağrısı."""
        body = self._build_body(messages, system_prompt, max_tokens, temperature)
        try:
            response = self._client.invoke_model(
                modelId=settings.BEDROCK_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("ThrottlingException", "ServiceQuotaExceededException"):
                raise TokenQuotaExceededError(f"Bedrock kota aşıldı: {code}")
            raise

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming token üretimi – SSE için."""
        body = self._build_body(messages, system_prompt, max_tokens, temperature)
        try:
            response = self._client.invoke_model_with_response_stream(
                modelId=settings.BEDROCK_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            for event in response["body"]:
                chunk = json.loads(event["chunk"]["bytes"])
                if chunk.get("type") == "content_block_delta":
                    delta = chunk.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta.get("text", "")
                elif chunk.get("type") == "message_stop":
                    break
        except ClientError as e:
            logger.error("bedrock_stream_error", error=str(e))
            raise

    def _build_body(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None,
        max_tokens: int | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens or settings.BEDROCK_MAX_TOKENS,
            "temperature": temperature if temperature is not None else settings.BEDROCK_TEMPERATURE,
            "messages": messages,
        }
        if system_prompt:
            body["system"] = system_prompt
        return body


bedrock_service = BedrockService()

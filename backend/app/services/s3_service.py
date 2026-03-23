"""
S3Service — Şifreli yükleme / indirme / imzalı URL

Güvenlik:
  - Tüm nesneler SSE-KMS (AWS Key Management Service) ile şifrelenir
  - KMS_KEY_ID yapılandırılmamışsa SSE-S3 (AES-256) kullanılır
  - Her büro kendi S3 prefix'ine erişir: tenants/{tenant_id}/...
"""
from __future__ import annotations

import asyncio
from functools import partial

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Şifreleme tipi — KMS key varsa KMS, yoksa S3-managed AES256
_SSE_TYPE    = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
_SSE_EXTRA: dict = (
    {"SSEKMSKeyId": settings.AWS_KMS_KEY_ID}
    if getattr(settings, "AWS_KMS_KEY_ID", None)
    else {}
)


class S3Service:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            region_name=settings.AWS_S3_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self._bucket = settings.AWS_S3_BUCKET
        self._loop = None

    # ── Upload ────────────────────────────────────────────────────

    async def upload_encrypted(
        self,
        content: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream",
        extra_metadata: dict | None = None,
    ) -> str:
        """
        Dosyayı S3'e şifreli yükle.
        Returns: s3_key (başarılı yükleme)
        """
        put_kwargs: dict = {
            "Bucket": self._bucket,
            "Key": s3_key,
            "Body": content,
            "ContentType": content_type,
            "ServerSideEncryption": _SSE_TYPE,
            **_SSE_EXTRA,
        }
        if extra_metadata:
            put_kwargs["Metadata"] = {k: str(v) for k, v in extra_metadata.items()}

        await asyncio.get_event_loop().run_in_executor(
            None,
            partial(self._client.put_object, **put_kwargs),
        )

        logger.info(
            "s3_upload_complete",
            key=s3_key,
            size_bytes=len(content),
            encryption=_SSE_TYPE,
        )
        return s3_key

    # ── Download ──────────────────────────────────────────────────

    async def download(self, s3_key: str) -> bytes:
        """S3'ten içerik indir."""
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                self._client.get_object,
                Bucket=self._bucket,
                Key=s3_key,
            ),
        )
        content = response["Body"].read()
        logger.debug("s3_download_complete", key=s3_key, size_bytes=len(content))
        return content

    # ── Presigned URL ─────────────────────────────────────────────

    async def generate_presigned_url(
        self,
        s3_key: str,
        expires_in: int = 3600,
    ) -> str:
        """İndirme için imzalı URL üret (varsayılan 1 saat)."""
        url = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": s3_key},
                ExpiresIn=expires_in,
            ),
        )
        return url

    # ── Exists check ──────────────────────────────────────────────

    async def exists(self, s3_key: str) -> bool:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                partial(self._client.head_object, Bucket=self._bucket, Key=s3_key),
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise


s3_service = S3Service()

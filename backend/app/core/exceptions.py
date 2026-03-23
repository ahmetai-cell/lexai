from typing import Any


class LexAIError(Exception):
    """Base exception."""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: Any = None):
        self.message = message
        self.details = details
        super().__init__(message)


class TenantNotFoundError(LexAIError):
    status_code = 404
    code = "TENANT_NOT_FOUND"


class TenantAccessDeniedError(LexAIError):
    status_code = 403
    code = "TENANT_ACCESS_DENIED"


class DocumentNotFoundError(LexAIError):
    status_code = 404
    code = "DOCUMENT_NOT_FOUND"


class DocumentProcessingError(LexAIError):
    status_code = 422
    code = "DOCUMENT_PROCESSING_ERROR"


class OCRFailureError(LexAIError):
    status_code = 422
    code = "OCR_FAILURE"


class EmbeddingError(LexAIError):
    status_code = 500
    code = "EMBEDDING_ERROR"


class RAGRetrievalError(LexAIError):
    status_code = 500
    code = "RAG_RETRIEVAL_ERROR"


class HallucinationDetectedError(LexAIError):
    status_code = 422
    code = "HALLUCINATION_DETECTED"

    def __init__(self, message: str, flagged_claims: list[str] | None = None):
        super().__init__(message, details={"flagged_claims": flagged_claims or []})


class TemplateNotFoundError(LexAIError):
    status_code = 404
    code = "TEMPLATE_NOT_FOUND"


class TokenQuotaExceededError(LexAIError):
    status_code = 429
    code = "TOKEN_QUOTA_EXCEEDED"


class AuthenticationError(LexAIError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"


class AuthorizationError(LexAIError):
    status_code = 403
    code = "AUTHORIZATION_FAILED"

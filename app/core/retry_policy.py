"""Retry policy cho job engine."""


class RetryPolicy:
    """Cấu hình retry/backoff/timeout cho từng step."""

    def __init__(
        self,
        max_retry: int = 3,
        backoff_seconds: float = 30.0,
        step_timeout: float = 600.0,
    ):
        self.max_retry = max_retry
        self.backoff_seconds = backoff_seconds
        self.step_timeout = step_timeout

    def get_backoff(self, attempt: int) -> float:
        """Exponential backoff: base * 2^(attempt-1)."""
        return self.backoff_seconds * (2 ** (attempt - 1))

    def should_retry(self, attempt: int, error_code: str) -> bool:
        """Quyết định có retry không dựa vào attempt count và error code."""
        if attempt >= self.max_retry:
            return False
        retryable_codes = {"TIMEOUT", "UPSTREAM_UNAVAILABLE", "NETWORK_ERROR"}
        return error_code in retryable_codes

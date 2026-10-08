from app.core.domain_types import IngestionErrorCode


class IngestionError(Exception):
    def __init__(self, code: IngestionErrorCode, safe_message: str):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message[:500]

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    query_event_retention_days: int = Field(default=30, ge=1)
    source_storage_root: str = Field(
        default="../../siong-gpt-data/source-storage", min_length=1
    )
    source_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    ingestion_job_max_attempts: int = Field(default=3, ge=1)
    ingestion_job_lease_seconds: int = Field(default=300, ge=1)
    ingestion_job_poll_seconds: float = Field(default=5, gt=0)
    ingestion_retry_base_seconds: int = Field(default=30, ge=1)
    ingestion_worker_batch_size: int = Field(default=1, ge=1, le=100)
    ingestion_max_pdf_pages: int = Field(default=250, ge=1)
    ingestion_max_extracted_chars: int = Field(default=2_000_000, ge=1)
    ingestion_max_zip_entries: int = Field(default=5_000, ge=1)
    ingestion_max_uncompressed_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    ingestion_max_compression_ratio: float = Field(default=100, gt=0)
    ingestion_max_xlsx_sheets: int = Field(default=50, ge=1)
    ingestion_max_xlsx_rows_per_sheet: int = Field(default=100_000, ge=1)
    ingestion_max_xlsx_cells_per_row: int = Field(default=1_000, ge=1)
    ingestion_max_xlsx_nonempty_cells: int = Field(default=500_000, ge=1)
    ingestion_max_cell_chars: int = Field(default=32_767, ge=1)
    chunk_max_chars: int = Field(default=2_000, ge=1)
    chunk_overlap_chars: int = Field(default=200, ge=0)
    xlsx_rows_per_chunk: int = Field(default=50, ge=1)
    embedding_provider: str = Field(default="local_e5", pattern="^local_e5$")
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    embedding_model_local_path: str = "../../siong-gpt-models/multilingual-e5-small"
    embedding_model_revision: str = Field(
        default="fd1525a9fd15316a2d503bf26ab031a61d056e98",
        min_length=40,
        max_length=64,
    )
    embedding_allow_download: bool = False
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    embedding_max_sequence_length: int = Field(default=512, ge=8, le=8192)
    vector_search_mode: str = Field(default="exact", pattern="^(exact|hnsw)$")
    vector_hnsw_ef_search: int = Field(default=40, ge=1, le=1000)
    vector_candidate_limit: int = Field(default=50, ge=1, le=500)
    retrieval_fts_weight: float = Field(default=1.0, gt=0)
    retrieval_vector_weight: float = Field(default=1.0, gt=0)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=10000)
    retrieval_candidate_limit: int = Field(default=50, ge=1, le=500)
    retrieval_result_limit: int = Field(default=10, ge=1, le=100)
    retrieval_max_result_limit: int = Field(default=50, ge=1, le=100)
    retrieval_max_query_chars: int = Field(default=500, ge=1, le=5000)
    retrieval_snippet_chars: int = Field(default=500, ge=50, le=5000)
    retrieval_max_rerank_boost: float = Field(default=0.01, ge=0, le=0.1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context) -> None:
        if self.chunk_overlap_chars >= self.chunk_max_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS must be less than CHUNK_MAX_CHARS")
        if self.retrieval_candidate_limit < self.retrieval_result_limit:
            raise ValueError("RETRIEVAL_CANDIDATE_LIMIT must be >= RETRIEVAL_RESULT_LIMIT")
        if self.retrieval_max_result_limit < self.retrieval_result_limit:
            raise ValueError("RETRIEVAL_MAX_RESULT_LIMIT must be >= RETRIEVAL_RESULT_LIMIT")
        if self.retrieval_candidate_limit < self.retrieval_max_result_limit:
            raise ValueError("RETRIEVAL_CANDIDATE_LIMIT must be >= RETRIEVAL_MAX_RESULT_LIMIT")
        if self.vector_candidate_limit < self.retrieval_max_result_limit:
            raise ValueError("VECTOR_CANDIDATE_LIMIT must be >= RETRIEVAL_MAX_RESULT_LIMIT")


settings = Settings()

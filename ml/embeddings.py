from functools import lru_cache
from pathlib import Path
from typing import Any
import math

from ml.constants import (
    EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL_ID, PASSAGE_PREFIX, QUERY_PREFIX,
)


class EmbeddingConfigurationError(RuntimeError):
    pass


def validate_embedding(values: list[float]) -> list[float]:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} embedding dimensions")
    if not all(math.isfinite(value) for value in values) or not any(values):
        raise ValueError("Embedding must contain finite values and have nonzero norm")
    return values


class LegalEmbedder:
    def __init__(self, model: Any) -> None:
        self.model = model
        if model.get_sentence_embedding_dimension() != EMBEDDING_DIMENSIONS:
            raise ValueError("The model is incompatible with the database vector dimension")
        model.max_seq_length = EMBEDDING_MAX_TOKENS

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("Text must not be blank")
        tokenized = self.model.tokenizer(texts, add_special_tokens=True, truncation=False)
        if any(len(tokens) > EMBEDDING_MAX_TOKENS for tokens in tokenized["input_ids"]):
            raise ValueError(f"Split text into chunks of at most {EMBEDDING_MAX_TOKENS} tokens")
        vectors = self.model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return [validate_embedding([float(value) for value in vector]) for vector in vectors]

    def encode_query(self, query: str) -> list[float]:
        if not query.strip():
            raise ValueError("Query must not be blank")
        return self._encode([QUERY_PREFIX + query.strip()])[0]

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        if any(not text.strip() for text in texts):
            raise ValueError("Text must not be blank")
        return self._encode([PASSAGE_PREFIX + text.strip() for text in texts])


@lru_cache(maxsize=1)
def get_embedder(model_path: str = "", device: str = "cpu") -> LegalEmbedder:
    if model_path and not Path(model_path).is_dir():
        raise EmbeddingConfigurationError("EMBEDDING_MODEL_PATH должен указывать на каталог модели")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingConfigurationError("Установите ml/requirements.txt для поиска по эмбеддингам") from exc
    try:
        model = SentenceTransformer(
            model_path or EMBEDDING_MODEL_ID, device=device,
            local_files_only=bool(model_path), trust_remote_code=False,
        )
        return LegalEmbedder(model)
    except (OSError, RuntimeError, ValueError) as exc:
        raise EmbeddingConfigurationError("Не удалось загрузить multilingual-e5-small-ru-law; проверьте модель и доступ к Hugging Face") from exc

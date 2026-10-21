from functools import lru_cache
from pathlib import Path
from typing import Any
import math
import re

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
        tokenized = self.model.tokenizer(texts, add_special_tokens=True, truncation=False, verbose=False)
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
        documents = [self.split_document(text.strip()) for text in texts]
        parts = [part for document in documents for part in document]
        vectors = self._encode([PASSAGE_PREFIX + part.strip() for part in parts])
        if len(vectors) != len(parts):
            raise ValueError("The model returned an unexpected number of embeddings")
        result = []
        offset = 0
        prefix_size = self._document_size("") if any(len(parts) > 1 for parts in documents) else 0
        for document in documents:
            selected = vectors[offset:offset + len(document)]
            offset += len(document)
            if len(document) == 1:
                result.append(selected[0])
                continue
            weights = [max(1, self._document_size(part) - prefix_size) for part in document]
            pooled = [sum(vector[index] * weight for vector, weight in zip(selected, weights, strict=True))
                      for index in range(EMBEDDING_DIMENSIONS)]
            norm = math.hypot(*pooled)
            if not math.isfinite(norm) or norm == 0:
                raise ValueError("Cannot normalize the pooled document embedding")
            result.append(validate_embedding([value / norm for value in pooled]))
        return result

    def _document_size(self, text: str) -> int:
        tokens = self.model.tokenizer(
            [PASSAGE_PREFIX + text.strip()], add_special_tokens=True, truncation=False, verbose=False,
        )
        return len(tokens["input_ids"][0])

    def split_document(self, text: str, *, context: str = "") -> list[str]:
        """Split oversized documents without losing text or exceeding the token budget."""
        parts = []
        remaining = text
        while remaining:
            if self._document_size(context + remaining) <= EMBEDDING_MAX_TOKENS:
                parts.append(context + remaining)
                break
            low, high = 0, len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                if self._document_size(context + remaining[:middle]) <= EMBEDDING_MAX_TOKENS:
                    low = middle
                else:
                    high = middle - 1
            if low == 0:
                raise ValueError("The passage prefix exceeds the 512-token budget")
            boundaries = list(re.finditer(r"\n+|(?<=[.!?])\s+", remaining[:low]))
            boundary = boundaries[-1].end() if boundaries else remaining.rfind(" ", 0, low) + 1
            if (boundary >= low // 2 and remaining[:boundary].strip()
                    and self._document_size(context + remaining[:boundary]) <= EMBEDDING_MAX_TOKENS):
                low = boundary
            parts.append(context + remaining[:low])
            remaining = remaining[low:]
        return parts


@lru_cache(maxsize=1)
def get_embedder(model_path: str = "", device: str = "cpu") -> LegalEmbedder:
    if not model_path and Path("/opt/embedding-model").is_dir():
        model_path = "/opt/embedding-model"
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

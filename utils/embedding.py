"""Embedding client — lazy-loads model only when actually used."""

import numpy as np
import logging

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Optional embedding model wrapper. Only loads model on first use."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name} ...")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded, dim={self._model.get_sentence_embedding_dimension()}")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def embed_single(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


# Singleton (lazy - model loaded on first use)
embedding_client = EmbeddingClient()

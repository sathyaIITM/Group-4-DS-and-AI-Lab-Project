"""Hybrid retrieval: BM25 lexical ranking fused with embedding similarity from pgvector.

Ranks are fused with reciprocal rank fusion (RRF), which needs no score scaling between the
two retrievers. A domain label can boost entries of that domain; it never removes an entry.
If Postgres is unreachable the store falls back to in-memory cosine similarity and the result
records it, as in the specification's fallback table.
"""

import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from analyst.retrieval.knowledge import Entry

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384
# BGE's recommended instruction for short queries against passages.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RRF_K = 60
DOMAIN_BOOST = 0.005
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    """Okapi BM25 over a fixed list of documents."""

    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.docs), 1)
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            s = 0.0
            for t in terms:
                if t in doc:
                    tf = doc[t]
                    norm = tf + self.k1 * (1 - self.b + self.b * length / self.avg_len)
                    s += self.idf[t] * tf * (self.k1 + 1) / norm
            out.append(s)
        return out


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal rank fusion of several ranked id lists."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, entry_id in enumerate(ranking, 1):
            fused[entry_id] = fused.get(entry_id, 0.0) + 1.0 / (k + rank)
    return fused


@dataclass
class Hit:
    entry: Entry
    score: float
    bm25_rank: int | None
    vector_rank: int | None


@dataclass
class HybridIndex:
    """Entries indexed for BM25 in memory and for vectors in pgvector (or memory)."""

    entries: list[Entry]
    database_url: str | None = None
    backend: str = field(init=False, default="memory")
    _embedder: Any = field(init=False, default=None, repr=False)
    _vectors: np.ndarray | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {e.id: e for e in self.entries}
        self._bm25 = {
            kind: (ids, BM25([self._by_id[i].text for i in ids]))
            for kind in {e.kind for e in self.entries}
            for ids in [[e.id for e in self.entries if e.kind == kind]]
        }

    # -- embeddings ------------------------------------------------------------------------
    def _model(self) -> Any:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer  # heavy import, load lazily

            self._embedder = SentenceTransformer(EMBED_MODEL, device="cpu")
        return self._embedder

    def embed(self, texts: Sequence[str], query: bool = False) -> np.ndarray:
        prefixed = [QUERY_PREFIX + t for t in texts] if query else list(texts)
        return np.asarray(self._model().encode(prefixed, normalize_embeddings=True))

    # -- indexing --------------------------------------------------------------------------
    def build(self) -> str:
        """Embed every entry and store it; return the backend used ('pgvector' or 'memory')."""
        vectors = self.embed([e.text for e in self.entries])
        self._vectors = vectors
        if self.database_url:
            try:
                self._write_pgvector(vectors)
                self.backend = "pgvector"
            except Exception as error:
                self.backend = f"memory (pgvector unavailable: {type(error).__name__})"
        return self.backend

    def _connect(self) -> Any:
        import psycopg
        from pgvector.psycopg import register_vector

        con = psycopg.connect(self.database_url, connect_timeout=3, autocommit=True)
        register_vector(con)
        return con

    def _write_pgvector(self, vectors: np.ndarray) -> None:
        with self._connect() as con:
            con.execute(
                f"CREATE TABLE IF NOT EXISTS rag_entries (id text PRIMARY KEY, kind text NOT NULL,"
                f" dataset_id text, text text NOT NULL, embedding vector({EMBED_DIM}) NOT NULL)"
            )
            con.execute("TRUNCATE rag_entries")
            with con.cursor() as cur:
                cur.executemany(
                    "INSERT INTO rag_entries (id, kind, dataset_id, text, embedding)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    [
                        (e.id, e.kind, e.dataset_id, e.text, v)
                        for e, v in zip(self.entries, vectors, strict=True)
                    ],
                )

    # -- search ----------------------------------------------------------------------------
    def _vector_ranking(self, query_vec: np.ndarray, kind: str, n: int) -> list[str]:
        if self.backend == "pgvector":
            with self._connect() as con:
                rows = con.execute(
                    "SELECT id FROM rag_entries WHERE kind = %s ORDER BY embedding <=> %s LIMIT %s",
                    (kind, query_vec, n),
                ).fetchall()
            return [r[0] for r in rows]
        if self._vectors is None:
            msg = "call build() first"
            raise RuntimeError(msg)
        idx = [i for i, e in enumerate(self.entries) if e.kind == kind]
        sims = self._vectors[idx] @ query_vec
        return [self.entries[idx[j]].id for j in np.argsort(-sims)[:n]]

    def search(
        self,
        query: str,
        kind: str,
        k: int,
        domain_of: dict[str, str] | None = None,
        boost_domain: str | None = None,
        dataset_ids: set[str] | None = None,
        depth: int = 50,
    ) -> list[Hit]:
        """Top-k entries of one kind. `dataset_ids` keeps entries of those tables (or general
        entries with no table); `boost_domain` re-ranks without removing anything."""
        ids, bm25 = self._bm25[kind]
        lexical = sorted(zip(ids, bm25.scores(query), strict=True), key=lambda p: -p[1])
        bm25_rank = [i for i, s in lexical if s > 0][:depth]
        vector_rank = self._vector_ranking(self.embed([query], query=True)[0], kind, depth)
        fused = rrf([bm25_rank, vector_rank])
        if boost_domain and domain_of:
            for entry_id in fused:
                ds = self._by_id[entry_id].dataset_id
                if ds and domain_of.get(ds) == boost_domain:
                    fused[entry_id] += DOMAIN_BOOST
        hits = []
        for entry_id, score in sorted(fused.items(), key=lambda p: -p[1]):
            entry = self._by_id[entry_id]
            if dataset_ids is not None and entry.dataset_id not in dataset_ids | {None}:
                continue
            hits.append(
                Hit(
                    entry,
                    score,
                    bm25_rank.index(entry_id) + 1 if entry_id in bm25_rank else None,
                    vector_rank.index(entry_id) + 1 if entry_id in vector_rank else None,
                )
            )
        return hits[:k]


def database_url_from_env() -> str | None:
    """Local POC database (see scripts/rag_poc_db.sh); None when no password is set."""
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        return None
    user = os.environ.get("POSTGRES_USER", "analyst")
    db = os.environ.get("POSTGRES_DB", "analyst")
    port = os.environ.get("RAG_POC_DB_PORT", "5433")
    return f"postgresql://{user}:{password}@127.0.0.1:{port}/{db}"

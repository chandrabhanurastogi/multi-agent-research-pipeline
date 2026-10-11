"""Document search over the mock corpus.

BM25 is the standard keyword-ranking algorithm (the default in Elasticsearch and
OpenSearch). It scores a document higher when it contains the query's words,
especially words that are rare across the corpus, and normalises for length.

In production this module would wrap a hybrid (keyword + vector) search service
with entitlement filtering and a reranker. Callers only depend on
`Corpus.search()`, so that swap does not touch the rest of the pipeline.
"""

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from research_pipeline.domain.research.source import Source

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[3] / "data" / "corpus.json"

# Words too common to help ranking. Kept short on purpose: BM25 already
# down-weights words that appear in many documents.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was what which with".split()
)


def _stem(token: str) -> str:
    """Crude plural stemming so "ships" matches "ship" and "rates" matches "rate".

    Exact-word matching otherwise treats them as different words, and a plural
    that happens to be rare in the corpus gets an inflated score. Production
    search engines use a proper stemmer or lemmatiser; this is enough here.
    """
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokenise(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


class Corpus:
    """The document collection plus its search index (built once at start-up)."""

    def __init__(self, sources: list[Source]) -> None:
        ids = [s.source_id for s in sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source_id in corpus")
        self._sources = sources
        self._by_id = {s.source_id: s for s in sources}
        self._index = BM25Okapi([_tokenise(f"{s.title} {s.text}") for s in sources])

    @classmethod
    def load(cls, path: Path = DEFAULT_CORPUS_PATH) -> "Corpus":
        """Load and validate every document. A malformed corpus fails here, not mid-run."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([Source.model_validate(item) for item in raw])

    def get(self, source_id: str) -> Source | None:
        return self._by_id.get(source_id)

    def search(self, query: str, top_k: int = 5) -> list[Source]:
        """Return up to top_k documents ranked by BM25, best first.

        top_k=5, not 3: documents are short, and a missed document can hide one
        side of a disagreement. Higher recall is worth a few hundred extra tokens.

        Documents with no matching words (score 0) are never returned, so an
        unrelated query yields an empty list -> a coverage gap, not noise.
        """
        scores = self._index.get_scores(_tokenise(query))
        ranked = sorted(zip(scores, self._sources), key=lambda pair: pair[0], reverse=True)
        return [source for score, source in ranked[:top_k] if score > 0]

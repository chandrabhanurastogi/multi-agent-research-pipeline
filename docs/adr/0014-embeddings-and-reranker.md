# 0014. Embedding model and reranker chosen by evaluation

- **Status:** Proposed (decide at A8)
- **Date:** 2026-10-15
- **Related:** SEC-3, QUAL-5; ADR 0002, 0012; plan step A8

## Context
BM25 over 12 documents is replaced by hybrid search (keyword + vector) with a reranker in OpenSearch, with entitlement filtering inside the query.

## Decision (proposed)
- Use OpenSearch **hybrid queries** (keyword + vector, scores normalised and combined) behind the existing `search()` interface.
- Embeddings are produced through the **gateway** (an `embedding-default` alias), at ingestion and query time.
- Choose the embedding model and reranker by **retrieval metrics on the golden set** (does search return the documents an expert would cite?), not by leaderboard.
- Store the embedding model version with each index; re-embed into a new index and switch an **index alias** for zero-downtime changes.

## Alternatives considered
To be compared in A8: provider embedding models via the gateway, self-hosted open models; reranker as a cross-encoder model via the gateway or self-hosted, or no reranker if metrics show no gain.

## Consequences
- Changing the embedding model means re-indexing the corpus; ingestion must be repeatable.

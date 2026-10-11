"""Tools: access to external systems. Here, only document search.

    search.py   load data/corpus.json; BM25 search(query, top_k) -> list[Source]
                         (production: OpenSearch / vector store client behind the same function)
"""

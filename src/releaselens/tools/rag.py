"""ChromaDB-backed RAG store (architecture.md §9).

Two collections: PEP corpus (used by feature_extract, verify) and connector docs
(used by impact_scope). Embeddings via Bedrock Titan. Implementation deferred.
"""

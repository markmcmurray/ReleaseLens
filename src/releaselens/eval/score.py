"""Comparison procedure for eval (architecture.md §11.3).

Pure-Python set arithmetic. NO LLM, NO embedding similarity, NO overlap heuristics.
TP/FP/FN over Feature.id matches and (feature_id, tool, found, version_first_seen)
tuples. Reports precision, recall, F1, with per-tool and per-method facets.

Implementation deferred to a later block.
"""

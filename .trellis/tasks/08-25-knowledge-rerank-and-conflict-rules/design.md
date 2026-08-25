# Design

## Retrieval Flow

`KnowledgeRetrievalService` keeps permission and applicability filtering before loading chunk content. It computes vector similarity, orders candidates, keeps a configurable initial candidate window, calls `OpenAICompatibleReranker`, then filters and orders by rerank score before applying the existing context character bound.

## Rerank Contract

The client posts `{model, query, documents, top_n}` to an OpenAI-compatible `/rerank` endpoint and accepts a response containing `results` or `data` items with `index` and `relevance_score` (or `score`). Invalid, incomplete, duplicate, or out-of-range results are errors.

The rerank client uses explicit knowledge-rerank settings, falling back only to the configured embedding API endpoint/key because both are OpenAI-compatible provider credentials, not to a different model or an unranked path.

## Failure Policy

When rerank is enabled and the request cannot produce a valid complete score list, retrieval returns an explicit `RERANK_UNAVAILABLE` failure with no citations/context. Operators can explicitly disable reranking to use the vector-only compatibility mode.

## Prompt Contract

Knowledge chunks remain reference-only. The SQL prompt states that unrelated chunks must be ignored and contradictions must be reported rather than resolved by model guesswork. Higher-authority permission, schema, tracking configuration, and Data Skill rules remain authoritative.

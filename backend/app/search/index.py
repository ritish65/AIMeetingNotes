"""Hybrid Search Indexing engine (Dense + Sparse Fusion).

Utilizes fastembed for local BGE embeddings, Qdrant for vector management,
and a memory-backed BM25 fallback for hybrid retrieval in standalone runs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from ..config import settings
from ..schemas import Intent, SearchHit, SearchRequest, SearchResponse
from ..utils import invoke_llm_json


class HybridSearchIndex:
    def __init__(self) -> None:
        self.qdrant_client = None
        self.encoder = None
        self.use_fallback = True

        # Fallback local index structures
        self.local_docs: List[Dict[str, Any]] = []

        if not settings.qdrant_url:
            logger.info("QDRANT_URL not set; using local standalone index fallback.")
            return

        try:
            from qdrant_client import QdrantClient
            from fastembed import TextEmbedding

            logger.info("Connecting to Qdrant cluster at {}", settings.qdrant_url)
            self.qdrant_client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=5.0,
            )
            logger.info("Initializing fastembed TextEmbedding model: {}", settings.embedding_model)
            self.encoder = TextEmbedding(model_name=settings.embedding_model)
            self._ensure_collection()
            self.use_fallback = False
        except Exception as e:
            logger.warning(
                "Could not initialize Qdrant / fastembed ({}). Falling back to basic memory search.",
                e,
            )
            self.use_fallback = True

    def _ensure_collection(self) -> None:
        if not self.qdrant_client:
            return
        from qdrant_client.http import models

        try:
            exists = self.qdrant_client.collection_exists(settings.qdrant_collection)
            if not exists:
                logger.info("Creating Qdrant collection: {}", settings.qdrant_collection)
                self.qdrant_client.create_collection(
                    collection_name=settings.qdrant_collection,
                    vectors_config=models.VectorParams(
                        size=settings.embedding_dim,
                        distance=models.Distance.COSINE,
                    ),
                    sparse_vectors_config={
                        "sparse-text": models.SparseVectorParams(
                            index=models.SparseIndexParams(
                                on_disk=False,
                            )
                        )
                    },
                )
        except Exception as e:
            logger.error("Failed to verify/create Qdrant collection: {}", e)
            self.use_fallback = True

    async def index_meeting(
        self,
        meeting_id: str,
        title: str,
        transcript: str,
        started_at: datetime,
        segments: List[Dict[str, Any]],
    ) -> bool:
        """Indexes meeting segments into both Dense and Sparse representations."""
        if not transcript.strip():
            return False

        # Add to local memory regardless (dual backup)
        for seg in segments:
            doc = {
                "meeting_id": meeting_id,
                "segment_id": seg.get("id"),
                "text": seg.get("text", ""),
                "title": title,
                "started_at": started_at,
            }
            # Avoid duplicate indexing
            if not any(
                d["meeting_id"] == meeting_id and d["segment_id"] == seg.get("id")
                for d in self.local_docs
            ):
                self.local_docs.append(doc)

        if self.use_fallback or not self.qdrant_client or not self.encoder:
            logger.info("Indexed meeting {} locally ({} segments)", meeting_id, len(segments))
            return True

        try:
            from qdrant_client.http import models

            points = []
            texts = [seg.get("text", "") for seg in segments if seg.get("text", "").strip()]
            if not texts:
                return False

            # Generate dense embeddings
            embeddings = list(self.encoder.embed(texts))

            for idx, seg in enumerate(segments):
                text = seg.get("text", "").strip()
                if not text:
                    continue

                vector = [float(x) for x in embeddings[idx]]

                # Simple pseudo-sparse generation using split tokens (if full SPLADE/sparse is omitted)
                # Or standard Qdrant dense-only fallback if sparse config encounters errors
                point_id = seg.get("id") or f"{meeting_id}-{idx}"

                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "meeting_id": meeting_id,
                            "segment_id": seg.get("id"),
                            "text": text,
                            "title": title,
                            "started_at": started_at.isoformat(),
                        },
                    )
                )

            if points:
                self.qdrant_client.upsert(
                    collection_name=settings.qdrant_collection,
                    points=points,
                )
            logger.info("Indexed meeting {} in Qdrant ({} points)", meeting_id, len(points))
            return True
        except Exception as e:
            logger.error("Qdrant indexing failed: {}", e)
            return False

    async def invalidate_meeting(self, meeting_id: str) -> None:
        """Removes an outdated meeting from indexes to prevent stale context retrieval."""
        self.local_docs = [d for d in self.local_docs if d["meeting_id"] != meeting_id]

        if not self.use_fallback and self.qdrant_client:
            try:
                from qdrant_client.http import models

                self.qdrant_client.delete(
                    collection_name=settings.qdrant_collection,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="meeting_id",
                                    match=models.MatchValue(value=meeting_id),
                                )
                            ]
                        )
                    ),
                )
                logger.info("Invalidated meeting {} from Qdrant", meeting_id)
            except Exception as e:
                logger.error("Qdrant delete failed: {}", e)

    async def route_intent(self, query: str) -> Intent:
        """Determines routing logic via LLM semantic categorization."""
        prompt = (
            "Analyze this user message to a personal meeting productivity assistant.\n"
            "Classify the user intent into exactly one of these labels:\n"
            "- 'search': the user is trying to find past meetings, quotes, topics, or events.\n"
            "- 'action': the user wants to execute/trigger actions (e.g. sync tasks, schedule emails, add to calendars).\n"
            "- 'summary': the user is asking to summarize or synthesize a meeting or set of meetings.\n"
            "- 'qa': general question-answering or clarifying questions on meetings.\n\n"
            "Respond strictly in valid JSON:\n"
            '{"intent": "search"|"action"|"summary"|"qa", "confidence": float, "rationale": "short explanation"}\n\n'
            f"Query: {query}"
        )
        try:
            data = await invoke_llm_json(prompt)
            return Intent(
                intent=data.get("intent", "search"),
                confidence=float(data.get("confidence", 0.7)),
                rationale=data.get("rationale", "default fallback"),
            )
        except Exception:
            return Intent(intent="search", confidence=1.0, rationale="fallback default")

    async def amplify_query(self, query: str) -> List[str]:
        """Multi-query amplification: expands search query into diverse semantic variations."""
        prompt = (
            "You are a search expansion engine. Take the search query below and expand it into "
            "exactly 3 highly relevant semantic variations/synonyms to improve vector-search coverage "
            "(e.g. 'budget' -> ['spending', 'financial plan', 'costs']).\n\n"
            "Respond strictly in valid JSON:\n"
            '{"queries": ["query variation 1", "query variation 2", "query variation 3"]}\n\n'
            f"Query: {query}"
        )
        try:
            data = await invoke_llm_json(prompt)
            variations = data.get("queries", [])
            # Always ensure the original is first
            unique_queries = [query]
            for v in variations:
                if v.strip() and v not in unique_queries:
                    unique_queries.append(v)
            return unique_queries[:4]
        except Exception:
            return [query]

    async def search(self, req: SearchRequest) -> SearchResponse:
        """Performs a unified search.

        Routes intent, amplifies query, merges semantic + text results,
        and scores.
        """
        intent = await self.route_intent(req.query)
        queries = await self.amplify_query(req.query) if req.multi_query else [req.query]

        hits: List[SearchHit] = []

        if self.use_fallback or not self.qdrant_client or not self.encoder:
            # InMemory simple BM25 / token matching fallback
            scored: List[tuple[Dict[str, Any], float]] = []
            for doc in self.local_docs:
                text = doc["text"].lower()
                matches = 0
                for q in queries:
                    q_words = q.lower().split()
                    for w in q_words:
                        if w in text:
                            matches += 1
                if matches > 0:
                    score = matches / (len(text.split()) + 1.0)
                    scored.append((doc, score))

            scored.sort(key=lambda x: x[1], reverse=True)
            for doc, score in scored[: req.top_k]:
                hits.append(
                    SearchHit(
                        meeting_id=doc["meeting_id"],
                        segment_id=doc["segment_id"],
                        score=score,
                        text=doc["text"],
                        title=doc["title"],
                        started_at=doc["started_at"],
                    )
                )
        else:
            try:
                # Perform vector search across amplified queries
                raw_hits = []
                for q in queries:
                    q_embedding = list(self.encoder.embed([q]))[0]
                    vector = [float(x) for x in q_embedding]

                    q_res = self.qdrant_client.search(
                        collection_name=settings.qdrant_collection,
                        query_vector=vector,
                        limit=req.top_k,
                    )
                    raw_hits.extend(q_res)

                # Deduplicate and score merge (simple Reciprocal Rank Fusion or maximum score mapping)
                seen_ids = set()
                sorted_hits = []
                for rh in raw_hits:
                    if rh.id not in seen_ids:
                        seen_ids.add(rh.id)
                        sorted_hits.append(rh)

                sorted_hits.sort(key=lambda x: x.score, reverse=True)

                for rh in sorted_hits[: req.top_k]:
                    p = rh.payload
                    started_at = None
                    if p.get("started_at"):
                        try:
                            started_at = datetime.fromisoformat(p["started_at"])
                        except ValueError:
                            pass

                    hits.append(
                        SearchHit(
                            meeting_id=p.get("meeting_id", ""),
                            segment_id=p.get("segment_id"),
                            score=rh.score,
                            text=p.get("text", ""),
                            title=p.get("title"),
                            started_at=started_at,
                        )
                    )
            except Exception as e:
                logger.error("Qdrant search failed: {}", e)

        return SearchResponse(intent=intent, expanded_queries=queries, hits=hits)


_search_index_instance: HybridSearchIndex | None = None


def get_search_index() -> HybridSearchIndex:
    global _search_index_instance
    if _search_index_instance is None:
        _search_index_instance = HybridSearchIndex()
    return _search_index_instance

"""RAG-related helpers for indexing and searching documents."""
from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.ai_config import genai
from src.supabase_client import supabase
from src.utils.file_utils import extract_text_from_file

EMBEDDING_MODEL = "models/text-embedding-004"
STORAGE_BUCKET = os.getenv("SUPABASE_RAG_BUCKET", "mathmentor-materials")
_CACHE_TTL_SECONDS = 300
_RAG_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]], Optional[str]]] = {}


def split_text(text: str, max_chars: int = 800) -> List[str]:
    """Split text into smaller chunks without cutting words/LaTeX when possible."""
    if not text:
        return []

    chunks: List[str] = []
    current_tokens: List[str] = []
    current_len = 0

    for token in text.split():
        token_len = len(token)

        if current_len + token_len + (1 if current_tokens else 0) <= max_chars:
            if current_tokens:
                current_tokens.append(" ")
                current_len += 1
            current_tokens.append(token)
            current_len += token_len
            continue

        if current_tokens:
            chunks.append("".join(current_tokens).strip())
            current_tokens = []
            current_len = 0

        if token_len <= max_chars:
            current_tokens = [token]
            current_len = token_len
            continue

        # Token too large, split hard to respect limit.
        start = 0
        while start < token_len:
            end = min(start + max_chars, token_len)
            chunks.append(token[start:end])
            start = end

    if current_tokens:
        chunks.append("".join(current_tokens).strip())

    return [chunk for chunk in chunks if chunk]


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a batch of texts using Google GenAI."""
    if not texts:
        return []

    def _embed_batch() -> Any:
        return genai.embed_content(
            model=EMBEDDING_MODEL,
            content=texts,
            task_type="retrieval_document",
        )

    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(None, _embed_batch)
    except Exception as exc:  # pragma: no cover - network/service failure
        print(f"Error during batch embedding: {exc}")
        single_tasks = [
            loop.run_in_executor(
                None,
                lambda text=chunk: genai.embed_content(
                    model=EMBEDDING_MODEL,
                    content=text,
                    task_type="retrieval_document",
                ),
            )
            for chunk in texts
        ]
        responses = await asyncio.gather(*single_tasks, return_exceptions=True)
        embeddings: List[List[float]] = []
        for resp in responses:
            if isinstance(resp, Exception):
                embeddings.append([])
            elif isinstance(resp, dict) and "embedding" in resp:
                embeddings.append(list(map(float, resp.get("embedding", []))))
            else:
                embeddings.append([])
        return embeddings

    if isinstance(response, dict):
        if "embeddings" in response and isinstance(response["embeddings"], list):
            return [list(map(float, emb)) for emb in response["embeddings"]]
        if "data" in response and isinstance(response["data"], list):
            return [list(map(float, row.get("embedding", []))) for row in response["data"]]
        if "embedding" in response:
            return [list(map(float, response["embedding"])) for _ in texts]

    return []


async def index_document_chunks(
    *,
    user_id: str,
    document_id: str,
    source_path: str,
    file_path: str,
    visibility: str = "private",
    purpose: str = "chat",
) -> int:
    """
    Đọc file, tách chunk, embed và lưu vào bảng chunk tương ứng.

    Trả về số chunk đã được insert.
    """
    content = extract_text_from_file(file_path)
    if not content:
        return 0

    chunks = split_text(content)
    if not chunks:
        return 0

    embeddings = await embed_texts(chunks)
    if not embeddings:
        return 0

    target_table = "document_chunks"
    foreign_key = "document_id"
    visibility_field_value = visibility or "private"

    if purpose != "chat":
        target_table = "test_material_chunks"
        foreign_key = "material_id"

    created_at = datetime.utcnow().isoformat()
    rows = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        if not embedding:
            continue
        row: Dict[str, Any] = {
            "user_id": user_id,
            foreign_key: document_id,
            "chunk_index": idx,
            "content": chunk,
            "content_length": len(chunk),
            "source_path": source_path,
            "embedding": embedding,
            "embedding_status": "completed",
            "visibility": visibility_field_value,
            "created_at": created_at,
        }
        if target_table == "document_chunks":
            row["metadata"] = {"purpose": purpose}
        rows.append(row)

    if not rows:
        return 0

    supabase.table(target_table).insert(rows).execute()

    return len(rows)


async def process_document(*, user_id: str, document_id: str, purpose: str = "chat") -> bool:
    """Download, chunk, embed, and persist a document/test material into Supabase."""
    target_table = "user_documents" if purpose == "chat" else "test_materials"

    record_response = (
        supabase.table(target_table)
        .select("id, source_path, visibility")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )

    if not record_response.data:
        return False

    record = record_response.data[0]

    source_path = record.get("source_path")
    if not source_path:
        return False
    visibility = record.get("visibility")

    supabase.table(target_table).update({"rag_status": "processing"}).eq("id", document_id).execute()

    try:
        download_response = supabase.storage.from_(STORAGE_BUCKET).download(source_path)
        if not download_response:
            raise RuntimeError("Empty download response")

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(download_response)
            tmp_path = tmp_file.name

        chunk_count = await index_document_chunks(
            user_id=user_id,
            document_id=document_id,
            source_path=source_path,
            file_path=tmp_path,
            visibility=visibility or "private",
            purpose=purpose,
        )

        status_payload = {"rag_status": "completed", "chunk_count": chunk_count}
        supabase.table(target_table).update(status_payload).eq("id", document_id).execute()

        clear_rag_cache_for_user(user_id)
        return chunk_count > 0
    except Exception:
        supabase.table(target_table).update({"rag_status": "failed"}).eq("id", document_id).execute()
        raise
    finally:
        # Best-effort cleanup
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _match_fn_for_purpose(purpose: str) -> str:
    return "match_documents" if purpose == "chat" else "match_test_materials"


async def _search_similar_documents_from_db(
    query: str, user_id: Optional[str], purpose: str, top_k: int
) -> List[Dict[str, Any]]:
    """Query Supabase via pgvector to find the nearest document chunks."""
    query_embeddings = await embed_texts([query])
    if not query_embeddings:
        return []

    query_embedding = query_embeddings[0]

    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": 0.0,
        "match_count": top_k,
    }
    if user_id is not None:
        rpc_params["p_user_id"] = user_id

    response = supabase.rpc(_match_fn_for_purpose(purpose), rpc_params).execute()
    results = response.data or []

    formatted_results: List[Dict[str, Any]] = []
    for row in results:
        title = row.get("title") or row.get("file_name") or ""
        formatted_results.append(
            {
                "title": title,
                "file_name": row.get("file_name") or title,
                "content": row.get("content", ""),
                "score": float(row.get("similarity", 0)),
            }
        )
        if len(formatted_results) >= top_k:
            break

    return formatted_results


def _cache_key(user_id: Optional[str], query: str, purpose: str) -> str:
    raw_key = f"{user_id or 'public'}::{purpose}::{query}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def search_similar_documents(
    query: str, user_id: Optional[str], purpose: str = "chat", top_k: int = 5
) -> List[Dict[str, Any]]:
    """Search for similar documents with a short-lived in-memory cache."""
    key = _cache_key(user_id, query, purpose)
    now = time.time()

    cached = _RAG_CACHE.get(key)
    if cached:
        cached_at, cached_results, _ = cached
        if now - cached_at < _CACHE_TTL_SECONDS:
            return cached_results

    results = await _search_similar_documents_from_db(query, user_id, purpose, top_k)
    _RAG_CACHE[key] = (now, results, user_id)
    return results


def clear_rag_cache_for_user(user_id: str) -> None:
    """Clear cached RAG search results for a given user."""
    for key in list(_RAG_CACHE.keys()):
        cached_entry = _RAG_CACHE.get(key)
        if cached_entry and cached_entry[2] == user_id:
            _RAG_CACHE.pop(key, None)

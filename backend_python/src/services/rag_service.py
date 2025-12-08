"""RAG-related helpers for indexing and searching documents."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.ai_config import genai
from src.supabase_client import supabase
from src.utils.file_utils import extract_text_from_file

EMBEDDING_MODEL = "models/text-embedding-004"
STORAGE_BUCKET = os.getenv("SUPABASE_RAG_BUCKET", "mathmentor-materials")


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
    except Exception as exc:
        print(f"[RAG] Error during batch embedding: {exc}")
        # Fallback: embed từng chunk một
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
                print(f"[RAG] Single embedding error: {resp}")
                embeddings.append([])
            elif isinstance(resp, dict) and "embedding" in resp:
                embeddings.append(list(map(float, resp.get("embedding", []))))
            # Handle object response from SDK
            elif hasattr(resp, "embedding"): 
                 embeddings.append(list(map(float, resp.embedding)))
            else:
                embeddings.append([])
        return embeddings

    # --- PHẦN SỬA LỖI PARSING RESPONSE ---
    if isinstance(response, dict):
        # Trường hợp 1: Key là "embeddings" (số nhiều)
        if "embeddings" in response and isinstance(response["embeddings"], list):
            return [list(map(float, emb)) for emb in response["embeddings"]]
        
        # Trường hợp 2: Key là "data" (một số phiên bản cũ)
        if "data" in response and isinstance(response["data"], list):
            return [list(map(float, row.get("embedding", []))) for row in response["data"]]
        
        # Trường hợp 3 (GÂY LỖI): Key là "embedding" (số ít) nhưng chứa Batch (List of Lists)
        if "embedding" in response:
            emb_data = response["embedding"]
            # Kiểm tra nếu phần tử đầu tiên là list -> đây là batch embedding
            if isinstance(emb_data, list) and len(emb_data) > 0 and isinstance(emb_data[0], list):
                return [list(map(float, vec)) for vec in emb_data]
            
            # Ngược lại, nó là vector đơn -> duplicate cho tất cả texts (fallback hiếm gặp)
            single_emb = list(map(float, emb_data))
            return [single_emb for _ in texts]

    # Trường hợp response là Object (Google GenAI SDK mới)
    if hasattr(response, "embedding"):
        emb_data = response.embedding
        # Kiểm tra nếu là batch (List of Lists)
        if isinstance(emb_data, list) and len(emb_data) > 0 and isinstance(emb_data[0], list):
             return [list(map(float, vec)) for vec in emb_data]
        
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
    """
    try:
        # 1. Trích xuất text
        content = extract_text_from_file(file_path)
        print(f"[RAG] Extracted text length: {len(content) if content else 0}")
        
        if not content or len(content.strip()) < 50:
            print("[RAG] ⚠️ File quá ngắn hoặc không có nội dung văn bản")
            return 0

        # 2. Tách chunks
        chunks = split_text(content)
        print(f"[RAG] Created {len(chunks)} chunks")
        
        if not chunks:
            return 0

        # 3. Tạo embeddings (với retry logic)
        max_retries = 3
        embeddings = []
        
        for attempt in range(max_retries):
            try:
                embeddings = await embed_texts(chunks)
                if embeddings and len(embeddings) == len(chunks):
                    break
                print(f"[RAG] Retry {attempt + 1}/{max_retries}: Embedding mismatch")
            except Exception as e:
                print(f"[RAG] Retry {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        if not embeddings or len(embeddings) != len(chunks):
            print("[RAG] ❌ Không tạo được embeddings")
            return 0

        # 4. Xác định bảng
        target_table = "document_chunks" if purpose == "chat" else "test_material_chunks"
        foreign_key = "document_id" if purpose == "chat" else "material_id"

        # 5. Chuẩn bị rows
        created_at = datetime.utcnow().isoformat()
        rows = []
        
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            if not embedding or len(embedding) == 0:
                continue
                
            row = {
                "user_id": user_id,
                foreign_key: document_id,
                "chunk_index": idx,
                "content": chunk,
                "content_length": len(chunk),
                "source_path": source_path,
                "embedding": embedding,
                "embedding_status": "completed",
                "visibility": visibility,
                "created_at": created_at,
            }
            
            if target_table == "document_chunks":
                row["metadata"] = {"purpose": purpose}
                
            rows.append(row)

        if not rows:
            print("[RAG] ⚠️ Không có row hợp lệ để insert")
            return 0

        # 6. Insert vào database
        print(f"[RAG] Inserting {len(rows)} rows into {target_table}")
        supabase.table(target_table).insert(rows).execute()
        
        return len(rows)
        
    except Exception as e:
        print(f"[RAG] ❌ Error in index_document_chunks: {e}")
        import traceback
        traceback.print_exc()
        return 0

async def process_document(*, user_id: str, document_id: str, purpose: str = "chat") -> dict:
    """
    Download, chunk, embed, and persist a document/test material into Supabase.
    Returns dict with success status and error message if any.
    """
    target_table = "user_documents" if purpose == "chat" else "test_materials"
    print(f"[RAG] Start processing document {document_id} (purpose={purpose}, table={target_table})")

    # 1. Lấy thông tin file từ DB
    try:
        record_response = (
            supabase.table(target_table)
            .select("id, source_path, visibility, file_name")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )

        if not getattr(record_response, "data", None):
            error_msg = f"Không tìm thấy file trong database (ID: {document_id})"
            print(f"[RAG] {error_msg}")
            return {"success": False, "message": error_msg}

        record = record_response.data[0]
        source_path = record.get("source_path")
        file_name = record.get("file_name", "unknown.pdf")
        
        if not source_path:
            error_msg = "File không có đường dẫn lưu trữ"
            print(f"[RAG] {error_msg}")
            return {"success": False, "message": error_msg}
            
        visibility = record.get("visibility", "private")

    except Exception as e:
        error_msg = f"Lỗi truy vấn database: {str(e)}"
        print(f"[RAG] {error_msg}")
        return {"success": False, "message": error_msg}

    # 2. Cập nhật trạng thái đang xử lý
    try:
        supabase.table(target_table).update({"rag_status": "processing"}).eq("id", document_id).execute()
    except Exception as e:
        print(f"[RAG] Warning: Cannot update status to processing: {e}")

    tmp_path: Optional[str] = None
    
    try:
        # 3. Download file từ Storage
        print(f"[RAG] Downloading file: {source_path}")
        download_response = supabase.storage.from_(STORAGE_BUCKET).download(source_path)
        
        if not download_response:
            raise RuntimeError("File tải về rỗng hoặc không tồn tại")

        # 4. ✅ FIX: Lấy extension từ source_path HOẶC file_name
        file_ext = os.path.splitext(source_path)[1].lower()
        if not file_ext or file_ext not in ['.pdf', '.docx', '.doc', '.txt']:
            # Fallback: thử lấy từ file_name
            file_ext = os.path.splitext(file_name)[1].lower()
            if not file_ext:
                raise ValueError(f"Không xác định được định dạng file. Chỉ hỗ trợ: .pdf, .docx, .doc, .txt")
        
        print(f"[RAG] Detected file extension: {file_ext}")

        # 5. Tạo file tạm với extension chính xác
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            tmp_file.write(download_response)
            tmp_path = tmp_file.name

        print(f"[RAG] Temp file created: {tmp_path}")

        # 6. ✅ FIX: Kiểm tra file tồn tại và có kích thước
        if not os.path.exists(tmp_path):
            raise RuntimeError("Không tạo được file tạm")
        
        file_size = os.path.getsize(tmp_path)
        if file_size == 0:
            raise RuntimeError("File tải về có kích thước 0 byte")
        
        print(f"[RAG] File size: {file_size} bytes")

        # 7. Index chunks
        chunk_count = await index_document_chunks(
            user_id=user_id,
            document_id=document_id,
            source_path=source_path,
            file_path=tmp_path,
            visibility=visibility,
            purpose=purpose,
        )

        # 8. Cập nhật trạng thái cuối
        if chunk_count > 0:
            status_payload = {"rag_status": "ready", "chunk_count": chunk_count}
            print(f"[RAG] ✅ Success: {chunk_count} chunks indexed")
            supabase.table(target_table).update(status_payload).eq("id", document_id).execute()
            return {"success": True, "message": f"Đã tạo {chunk_count} chunks", "chunk_count": chunk_count}
        else:
            status_payload = {"rag_status": "failed", "chunk_count": 0}
            error_msg = "Không trích xuất được nội dung từ file (file rỗng hoặc định dạng không hỗ trợ)"
            print(f"[RAG] ⚠️ {error_msg}")
            supabase.table(target_table).update(status_payload).eq("id", document_id).execute()
            return {"success": False, "message": error_msg}

    except ValueError as ve:
        # Lỗi định dạng file
        error_msg = str(ve)
        print(f"[RAG] ❌ Validation Error: {error_msg}")
        try:
            supabase.table(target_table).update({"rag_status": "failed"}).eq("id", document_id).execute()
        except:
            pass
        return {"success": False, "message": error_msg}
        
    except Exception as exc:
        # Lỗi không xác định
        error_msg = f"Lỗi xử lý file: {str(exc)}"
        print(f"[RAG] ❌ Error: {error_msg}")
        import traceback
        traceback.print_exc()
        
        try:
            supabase.table(target_table).update({"rag_status": "failed"}).eq("id", document_id).execute()
        except:
            pass
            
        return {"success": False, "message": error_msg}
        
    finally:
        # 9. Dọn dẹp file tạm
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                print(f"[RAG] 🧹 Cleaned up temp file: {tmp_path}")
            except OSError as e:
                print(f"[RAG] Warning: Cannot delete temp file: {e}")


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
        "match_threshold": 0.3, # Ngưỡng tương đồng (0.0 -> 1.0)
        "match_count": top_k,
    }
    if user_id is not None:
        rpc_params["p_user_id"] = user_id

    try:
        rpc_name = _match_fn_for_purpose(purpose)
        response = supabase.rpc(rpc_name, rpc_params).execute()
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
    except Exception as e:
        print(f"[RAG] Search error (RPC {rpc_name}): {e}")
        return []


async def search_similar_documents(
    query: str, user_id: Optional[str], purpose: str = "chat", top_k: int = 5
) -> List[Dict[str, Any]]:
    """Search for similar documents directly from DB."""
    return await _search_similar_documents_from_db(query, user_id, purpose, top_k)

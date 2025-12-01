import hashlib
import random
from typing import Any, Dict, List, Optional
from src.ai_config import genai
from src.supabase_client import supabase
from .cache_service import cache, CacheKey

EMBEDDING_DIM = 768


def _fake_embedding(text: str) -> List[float]:
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
    random.seed(seed)
    return [random.random() for _ in range(EMBEDDING_DIM)]


def _generate_embedding(question: str) -> List[float]:
    if genai is None:
        return _fake_embedding(question)
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=question,
            task_type="retrieval_query",
        )
        return result.get("embedding", _fake_embedding(question))
    except Exception:
        return _fake_embedding(question)


def _fetch_documents(user_id: str, embedding: List[float]) -> List[Dict[str, Any]]:
    if supabase is None:
        return []
    try:
        response = supabase.rpc(
            "match_documents",
            {
                "query_embedding": embedding,
                "match_threshold": 0.5,
                "match_count": 5,
                "p_user_id": user_id,
            },
        ).execute()
        return response.data or []
    except Exception:
        return []


def _call_model(prompt: str) -> Dict[str, Any]:
    fallback = {
        "analysis": {"summary": "Không thể gọi Gemini, đây là phản hồi mô phỏng."},
        "stepHints": ["Xác định dạng bài toán", "Tóm tắt giả thiết", "Thử áp dụng công thức liên quan"],
        "finalAnswer": "",
        "theoryNeeded": ["Đạo hàm", "Hàm số mũ/log"],
        "graphInfo": {},
        "weakSkills": ["phân tích đề", "nhận diện dạng bài"],
    }
    if genai is None:
        return fallback
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        completion = model.generate_content(prompt)
        text = completion.text if hasattr(completion, "text") else str(completion)
        return fallback | {"finalAnswer": text}
    except Exception:
        return fallback


def _build_prompt(question: str, documents: List[Dict[str, Any]], exam_goal: Optional[str], target_score: Optional[float]) -> str:
    context = "\n\n".join([doc.get("content", "") for doc in documents])
    goal_text = f"Mục tiêu: {exam_goal or ''}, target score: {target_score or ''}"
    return (
        "Bạn là gia sư toán THPT Việt Nam. Hãy phân tích đề, gợi ý từng bước và liệt kê kiến thức nền."\
        f"\n{goal_text}\nNgữ cảnh tham khảo:\n{context}\nCâu hỏi: {question}"
    )


def chat_with_cache(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = payload.get("user_id", "anonymous")
    question = payload.get("question", "")
    exam_goal = payload.get("exam_goal")
    target_score = payload.get("target_score")

    normalized_question = question.strip().lower()
    cache_key: CacheKey = (user_id, normalized_question)
    cached = cache.get(cache_key)
    if cached:
        return cached

    embedding = _generate_embedding(question)
    documents = _fetch_documents(user_id, embedding)
    prompt = _build_prompt(question, documents, exam_goal, target_score)
    model_response = _call_model(prompt)

    response = {
        **model_response,
        "usedDocuments": documents,
    }

    cache.set(cache_key, response)

    # Lưu lịch sử chat/weak skills nếu có kết nối Supabase
    if supabase is not None:
        try:
            supabase.table("chat_history").insert(
                {
                    "user_id": user_id,
                    "question": question,
                    "analysis": response.get("analysis"),
                    "weak_skills": response.get("weakSkills", []),
                }
            ).execute()
        except Exception:
            pass

    return response

"""FastAPI entrypoint for Math Mentor backend.
This file exposes the core API surface expected by the frontend
while keeping logic small and debuggable for the challenge.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.ai_config import GOOGLE_API_KEY, genai
from src.models import NodeProgress
from src.services import rag_service
from src.supabase_client import supabase

app = FastAPI(title="Math Tutor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Simple in-memory caches
# -------------------------------------------------
CHAT_CACHE_TTL_SECONDS = 600
_chat_cache: Dict[str, Dict[str, Any]] = {}
_generated_tests: Dict[str, Dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.utcnow()


def _cache_key(user_id: str, question: str) -> str:
    normalized = question.strip().lower()
    return f"{user_id}:{normalized}"


# -------------------------------------------------
# Schemas
# -------------------------------------------------
class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Supabase user id")
    question: str
    exam_goal: Optional[str] = None
    target_score: Optional[float] = None


class ChatDocument(BaseModel):
    content: str
    similarity: Optional[float] = None
    file_name: Optional[str] = None


class ChatResponse(BaseModel):
    analysis: Dict[str, Any]
    stepHints: List[str]
    finalAnswer: Optional[str] = None
    theoryNeeded: List[str]
    graphInfo: Optional[Dict[str, Any]] = None
    weakSkills: List[str] = Field(default_factory=list)
    usedDocuments: List[ChatDocument] = Field(default_factory=list)


class TestQuestion(BaseModel):
    id: str
    questionType: str
    prompt: str
    topic: str
    difficulty: str
    options: Optional[List[str]] = None
    correctAnswer: Any


class GenerateTestRequest(BaseModel):
    user_id: str
    exam_type: str


class TestAnswerInput(BaseModel):
    questionId: str
    userAnswer: Any


class SubmitTestRequest(BaseModel):
    user_id: str
    test_id: str
    answers: List[TestAnswerInput]


class MindmapNode(BaseModel):
    id: str
    label: str
    parent: Optional[str]
    status: str = "learning"
    score: Optional[float] = None
    opened: bool = False


# -------------------------------------------------
# Helper functions
# -------------------------------------------------
async def _call_chat_model(prompt: str) -> Dict[str, Any]:
    if not GOOGLE_API_KEY:
        return {
            "analysis": {"summary": "AI key missing; returning fallback analysis."},
            "stepHints": ["Xác định yêu cầu đề bài", "Liệt kê dữ kiện", "Chọn công cụ giải phù hợp"],
            "finalAnswer": None,
            "theoryNeeded": ["Ôn lại đạo hàm", "Định nghĩa giới hạn"],
            "graphInfo": None,
            "weakSkills": [],
        }

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async(prompt)
        text = response.text or ""
        return {
            "analysis": {"summary": text[:400]},
            "stepHints": ["Phân tích điều kiện", "Đặt ẩn", "Kiểm tra kết quả"],
            "finalAnswer": None,
            "theoryNeeded": ["Công thức cơ bản"],
            "graphInfo": None,
            "weakSkills": [],
        }
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[MathMentor] Gemini error: {exc}")
        return {
            "analysis": {"summary": "Không thể gọi mô hình AI, hiển thị gợi ý cơ bản."},
            "stepHints": ["Đọc kỹ đề", "Thử tính nhanh bằng phép thế"],
            "finalAnswer": None,
            "theoryNeeded": [],
            "graphInfo": None,
            "weakSkills": [],
        }


def _store_chat_history(user_id: str, question: str, result: Dict[str, Any]):
    if supabase is None:
        return
    try:
        supabase.table("chat_history").insert(
            {
                "user_id": user_id,
                "question": question,
                "analysis": result.get("analysis"),
                "step_hints": result.get("stepHints"),
                "weak_skills": result.get("weakSkills"),
                "created_at": _now().isoformat(),
            }
        ).execute()
    except Exception as exc:
        print(f"[MathMentor] Failed to store chat history: {exc}")


async def _merge_mindmap_with_progress(user_id: str) -> List[MindmapNode]:
    base_nodes = [
        MindmapNode(id="ung-dung-dao-ham", label="Ứng dụng đạo hàm", parent=None),
        MindmapNode(id="tinh-don-dieu", label="Tính đơn điệu", parent="ung-dung-dao-ham"),
        MindmapNode(id="cuc-tri", label="Cực trị", parent="ung-dung-dao-ham"),
        MindmapNode(id="max-min", label="GTNN - GTLN", parent="ung-dung-dao-ham"),
    ]

    if supabase is None:
        return base_nodes

    try:
        res = supabase.table("node_progress").select("node_id, score, status, opened").eq("user_id", user_id).execute()
        progress_map = {row["node_id"]: row for row in (res.data or [])}
    except Exception as exc:
        print(f"[MathMentor] Failed to load node progress: {exc}")
        progress_map = {}

    merged: List[MindmapNode] = []
    for node in base_nodes:
        if node.id in progress_map:
            row = progress_map[node.id]
            node.status = row.get("status", node.status)
            node.score = row.get("score")
            node.opened = bool(row.get("opened", node.opened))
        merged.append(node)
    return merged


# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "supabase": bool(supabase)}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    cache_key = _cache_key(payload.user_id, payload.question)
    cached = _chat_cache.get(cache_key)
    if cached and cached["expires_at"] > _now():
        return cached["result"]

    docs = await rag_service.search_similar_documents(payload.question, payload.user_id, purpose="chat", limit=5)
    context_snippets = "\n\n".join([d.get("content", "") for d in docs])
    prompt = (
        "Bạn là gia sư toán THPT Việt Nam. Phân tích đề, đưa gợi ý từng bước, ưu tiên tương tác.\n"
        f"Mục tiêu: {payload.exam_goal or 'ôn thi THPTQG'}, target score: {payload.target_score or 'N/A'}.\n"
        f"Ngữ cảnh tài liệu:\n{context_snippets}\n\nCâu hỏi: {payload.question}"
    )

    model_result = await _call_chat_model(prompt)
    result = {
        **model_result,
        "usedDocuments": [ChatDocument(**{
            "content": doc.get("content", ""),
            "similarity": doc.get("similarity"),
            "file_name": doc.get("file_name"),
        }) for doc in docs],
    }

    _chat_cache[cache_key] = {"result": result, "expires_at": _now() + timedelta(seconds=CHAT_CACHE_TTL_SECONDS)}
    _store_chat_history(payload.user_id, payload.question, result)
    return result


@app.post("/api/tests/generate")
async def generate_test(payload: GenerateTestRequest):
    docs = await rag_service.search_similar_documents(payload.exam_type, payload.user_id, purpose="test", limit=3)
    topic_hint = docs[0]["content"][:60] if docs else "Ôn tập đạo hàm"

    questions: List[TestQuestion] = []
    for i in range(1, 11):
        qid = str(uuid.uuid4())
        questions.append(
            TestQuestion(
                id=qid,
                questionType="MCQ",
                prompt=f"[{payload.exam_type.upper()}] Câu {i}: {topic_hint} - tính đạo hàm của x^2?",
                topic="dao-ham",
                difficulty="medium",
                options=["2x", "x^2", "2", "x"],
                correctAnswer="2x",
            )
        )
    test_id = str(uuid.uuid4())
    _generated_tests[test_id] = {"questions": questions, "user_id": payload.user_id, "exam_type": payload.exam_type}
    return {"test_id": test_id, "questions": [q.dict() for q in questions]}


@app.post("/api/tests/submit")
async def submit_test(payload: SubmitTestRequest):
    if payload.test_id not in _generated_tests:
        raise HTTPException(status_code=404, detail="Test not found or expired")

    test_data = _generated_tests[payload.test_id]
    questions: List[TestQuestion] = test_data["questions"]
    correct_map = {q.id: q for q in questions}
    score = 0
    answer_details = []
    for answer in payload.answers:
        question = correct_map.get(answer.questionId)
        if not question:
            continue
        is_correct = str(answer.userAnswer).strip().lower() == str(question.correctAnswer).strip().lower()
        if is_correct:
            score += 1
        answer_details.append(
            {
                "questionId": question.id,
                "userAnswer": answer.userAnswer,
                "correctAnswer": question.correctAnswer,
                "explanation": "Đáp án đúng theo đề sinh tự động.",
            }
        )

    total = len(questions)
    percent = int((score / total) * 100) if total else 0
    weak_topics = ["dao-ham"] if percent < 80 else []

    if supabase is not None:
        try:
            attempt_row = {
                "id": payload.test_id,
                "user_id": payload.user_id,
                "score": percent,
                "exam_type": test_data.get("exam_type"),
                "created_at": _now().isoformat(),
            }
            supabase.table("test_attempts").upsert(attempt_row).execute()
            for detail in answer_details:
                supabase.table("test_answers").upsert({
                    "test_id": payload.test_id,
                    "user_id": payload.user_id,
                    "question_id": detail["questionId"],
                    "user_answer": detail["userAnswer"],
                    "correct_answer": detail["correctAnswer"],
                }).execute()
        except Exception as exc:
            print(f"[MathMentor] Failed to persist test results: {exc}")

    response = {
        "score": percent,
        "timeSpent": 0,
        "strengths": ["Ôn tập tốt"] if percent >= 80 else [],
        "weakTopics": weak_topics,
        "advice": "Tiếp tục luyện các chủ đề còn yếu và xem lại bước giải.",
        "answerDetails": answer_details,
    }
    return response


@app.get("/api/mindmap")
async def get_mindmap(user_id: str):
    nodes = await _merge_mindmap_with_progress(user_id)
    return {"nodes": [n.dict() for n in nodes]}


@app.post("/api/mindmap/node-progress")
async def update_node_progress(data: NodeProgress):
    status = data.status or "learning"
    if data.score is not None and data.score >= 80:
        status = "mastered"

    payload = {
        "user_id": data.user_id,
        "node_id": data.node_id,
        "opened": data.opened,
        "score": data.score,
        "status": status,
        "updated_at": _now().isoformat(),
    }

    if supabase is not None:
        try:
            supabase.table("node_progress").upsert(payload, on_conflict="user_id, node_id").execute()
        except Exception as exc:
            print(f"[MathMentor] Failed to upsert node progress: {exc}")
            raise HTTPException(status_code=500, detail="Cannot update node progress")
    return {"status": "ok", "data": payload}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

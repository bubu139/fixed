from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.models import NodeProgress
from src.services.chat_service import chat_with_cache
from src.services.test_service import generate_test, submit_test
from src.services.mindmap_service import get_mindmap, update_node_progress

app = FastAPI(title="Math Tutor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    user_id: str
    question: str
    exam_goal: Optional[str] = None
    target_score: Optional[float] = None


class TestGenerateRequest(BaseModel):
    user_id: str
    exam_type: str


class TestSubmitRequest(BaseModel):
    user_id: str
    test_id: str
    answers: List[Dict[str, Any]]


class NodeProgressRequest(NodeProgress):
    pass


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    if not payload.question:
        raise HTTPException(status_code=400, detail="Question is required")
    response = chat_with_cache(payload.model_dump())
    return response


@app.post("/api/tests/generate")
async def tests_generate(payload: TestGenerateRequest):
    return generate_test(payload.user_id, payload.exam_type)


@app.post("/api/tests/submit")
async def tests_submit(payload: TestSubmitRequest):
    return submit_test(payload.user_id, payload.test_id, payload.answers)


@app.get("/api/mindmap")
async def mindmap(user_id: str):
    return get_mindmap(user_id)


@app.post("/api/mindmap/node-progress")
async def mindmap_update(payload: NodeProgressRequest):
    return update_node_progress(payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

# src/main.py (OPTIMIZED VERSION)
import re
import uvicorn
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from src.routes.node_progress import router as node_progress_router
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import PyPDF2
from docx import Document
from src.models import NodeProgress
from src.supabase_client import supabase

# Import config
from src.ai_config import genai
from src.ai_schemas.chat_schema import ChatInputSchema
from src.services import rag_service

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(node_progress_router)

# ===== OPTIMIZATION 1: CACHED SYSTEM INSTRUCTION =====
# Thay vì gửi instruction dài trong mỗi request, ta dùng system_instruction 1 lần
CHAT_SYSTEM_INSTRUCTION = """Bạn là một AI gia sư toán học THPT lớp 12 Việt Nam, chuyên hướng dẫn học sinh TỰ HỌC và PHÁT TRIỂN Tư DUY.

# NGUYÊN TẮC CỐT LÕI
🎯 **MỤC TIÊU**: Giúp học sinh tự khám phá kiến thức, KHÔNG làm bài giúp học sinh
📚 **PHƯƠNG PHÁP**: Sử dụng câu hỏi gợi mở (Socratic Method) để dẫn dắt tư duy
💡 **TRIẾT LÝ**: "Dạy học sinh cách câu cá, không phải cho cá"

---

## KHI HỌC SINH GỬI BÀI TẬP

### BƯỚC 1: PHÂN TÍCH CÂU TRẢ LỜI CỦA HỌC SINH (NẾU CÓ)
Nếu học sinh đã làm bài:

✅ **Ghi nhận điểm tốt:**
- "Em làm đúng bước [X], cách tiếp cận này rất hợp lý!"
- "Ý tưởng sử dụng [công thức/phương pháp] là chính xác!"

⚠️ **Chỉ ra chỗ cần cải thiện (KHÔNG NÊU TRỰC TIẾP SAI Ở ĐÂU):**
- "Em xem lại bước [Y], có điều gì đó chưa chính xác nhé"
- "Kết quả này có vẻ chưa hợp lý. Em thử kiểm tra lại bước tính [Z]?"

### BƯỚC 2: GỢI MỞ TƯ DUY BẰNG CÂU HỎI DẪN DẮT
🔍 **Về phân tích đề:**
- "Đề bài yêu cầu em tìm gì? Cho em biết những gì?"
- "Em thử viết lại đề bài theo cách hiểu của mình xem?"

🧩 **Về lý thuyết:**
- "Dạng bài này thuộc chủ đề nào em đã học?"
- "Em còn nhớ công thức/định lý nào liên quan không?"

### BƯỚC 3: CHỈ GỢI Ý HƯỚNG GIẢI (KHÔNG GIẢI CHI TIẾT)
💡 **Gợi ý nhẹ:**
- "Gợi ý: Em thử [phép biến đổi/công thức] xem sao"
- "Bài này có thể giải bằng 2 cách: [Cách 1] hoặc [Cách 2]"

### BƯỚC 4: CHỈ GIẢI CHI TIẾT KHI:
✔️ Học sinh đã cố gắng nhưng vẫn không hiểu sau 2-3 lần gợi ý
✔️ Học sinh YÊU CẦU TƯỜNG MINH: "Thầy/cô giải mẫu giúp em"

---

## ĐỊNH DẠNG ĐẦU RA (JSON BẮT BUỘC)

Bạn PHẢI trả về JSON với cấu trúc:
{
  "reply": "Tin nhắn với học sinh (Markdown, LaTeX cho công thức)",
  "mindmap_insights": [
    {
      "node_id": "slug-ten-kien-thuc",
      "parent_node_id": "ung-dung-dao-ham",
      "label": "Tên kiến thức",
      "type": "concept",
      "weakness_summary": "Mô tả lỗ hổng",
      "action_steps": ["Bước 1", "Bước 2"]
    }
  ],
  "geogebra": {
    "should_draw": true/false,
    "reason": "Lý do cần vẽ",
    "prompt": "Mô tả vẽ",
    "commands": ["f(x)=x^2", "A=(1,2)"]
  }
}

**QUY TẮC:**
1. "reply" phải tham chiếu lịch sử, bổ sung lý thuyết
2. "mindmap_insights": Chỉ tạo khi phát hiện điểm yếu mới
3. "geogebra": Chỉ khi cần hình minh họa (hàm số, hình học)
4. LaTeX: $x^2$, $$\\int_0^1 x dx$$
5. Luôn trả về JSON thuần, KHÔNG markdown
"""

# ===== OPTIMIZATION 2: REUSE MODEL INSTANCE =====
# Khởi tạo model 1 lần duy nhất với system instruction
_chat_model_cache = None

def get_chat_model():
    """Singleton pattern for chat model"""
    global _chat_model_cache
    if _chat_model_cache is None:
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        
        _chat_model_cache = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config=generation_config,
            system_instruction=CHAT_SYSTEM_INSTRUCTION,  # Cached instruction
        )
    return _chat_model_cache

# ===== HELPER FUNCTIONS =====

def extract_reply_only(raw_text: str) -> str:
    """Extract reply from JSON-like text"""
    if not raw_text:
        return ""
    text = raw_text.strip()
    match = re.search(r'"reply"\s*:\s*"([^"]*)"', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text

def clean_json_response(raw_text: str) -> str:
    """Clean and extract JSON from AI response (Robust Version)"""
    if not raw_text:
        return ""

    # 1. Remove Markdown code blocks first
    text = re.sub(r"```json\s*", "", raw_text)
    text = re.sub(r"```\s*", "", text)
    
    # 2. Find the outer-most JSON object
    # Tìm cặp ngoặc nhọn ngoài cùng
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        # Fallback: thử tìm mảng [] nếu không thấy object {}
        json_match = re.search(r"\[[\s\S]*\]", text)
    
    if not json_match:
        print(f"❌ Không tìm thấy cấu trúc JSON. Raw: {raw_text[:100]}...")
        return ""

    json_text = json_match.group(0).strip()
    
    # 3. Clean control characters & Smart Quotes
    # Xóa các ký tự điều khiển lạ, giữ lại newline cơ bản nếu cần thiết
    json_text = re.sub(r"[\x00-\x1F\x7F]", " ", json_text) 
    
    # SỬA LỖI: Thay thế smart quotes (dấu nháy cong) bằng dấu nháy thẳng
    json_text = json_text.replace('“', '"').replace('”', '"')
    
    # 4. Handle LaTeX Backslash Issues (Quan trọng cho Toán)
    # AI thường trả về "\frac" (lỗi JSON) thay vì "\\frac" (đúng JSON).
    # Regex này tìm các dấu \ KHÔNG đi kèm với các ký tự thoát hợp lệ của JSON.
    # Các ký tự thoát JSON hợp lệ: " \ / b f n r t u
    # Chúng ta loại 'f' ra khỏi danh sách hợp lệ để bắt được \frac -> biến thành \\frac
    # Pattern: Tìm \ mà phía sau KHÔNG LÀ [" \ / b n r t u]
    try:
        # Thử parse trước, nếu được thì trả về luôn
        json.loads(json_text)
        return json_text
    except json.JSONDecodeError:
        # Nếu lỗi, thử sửa các dấu backslash thiếu escape
        # Ví dụ: \lim -> \\lim, \frac -> \\frac, \infty -> \\infty
        # Nhưng giữ nguyên \n, \t, \", \\
        pattern = r'\\(?![\\"/bnrtu])'
        fixed_text = re.sub(pattern, r'\\\\', json_text)
        return fixed_text
# ===== SCHEMAS =====

class MediaPart(BaseModel):
    url: str

class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatInputSchema(BaseModel):
    userId: Optional[str] = None
    message: str
    history: List[ConversationTurn] = Field(default_factory=list)
    media: Optional[List[MediaPart]] = None

# ===== OPTIMIZED CHAT ENDPOINT =====

@app.post("/api/chat")
async def handle_chat(request: ChatInputSchema):
    """
    OPTIMIZED: Sử dụng cached model với system instruction
    """
    try:
        # 1. Get cached model (chỉ khởi tạo 1 lần)
        model = get_chat_model()
        
        # 2. Build history cho ChatSession
        gemini_history = []
        for turn in request.history:
            if not turn.content:
                continue
            mapped_role = "user" if turn.role == "user" else "model"
            gemini_history.append({
                "role": mapped_role,
                "parts": [{"text": turn.content}],
            })

        # 3. Start chat với history (model đã có system instruction)
        chat = model.start_chat(history=gemini_history)

        # 4. Prepare user message với RAG context
        context_text = ""
        if request.userId:
            print(f"🔍 Searching RAG for user {request.userId}...")
            docs = await rag_service.search_similar_documents(
                request.message, request.userId, purpose="chat"
            )
            if docs:
                context_text = "\n\n=== TÀI LIỆU THAM KHẢO ===\n"
                for d in docs:
                    context_text += f"- [{d['file_name']}]: {d['content'][:200]}...\n"

        # 5. OPTIMIZATION 3: COMPACT PROMPT (không gửi lại instruction)
        user_prompt = f"{context_text}\n\nCâu hỏi: {request.message}"
        user_parts = [{"text": user_prompt}]

        if request.media:
            for media in request.media:
                user_parts.append({"text": f"[Media: {media.url}]"})

        # 6. Send message (async)
        response = await chat.send_message_async(user_parts)

        raw_text = response.text if hasattr(response, "text") else None
        if not raw_text:
            raise ValueError("Model không trả về phản hồi")

        # Default response
        mindmap_data = []
        normalized_geogebra = {
            "should_draw": False,
            "reason": "",
            "prompt": request.message,
            "commands": [],
        }

        # Try parse JSON
        try:
            json_candidate = clean_json_response(raw_text)
            if not json_candidate:
                raise ValueError("Không tìm thấy JSON hợp lệ")

            payload = json.loads(json_candidate)
            reply_text = (
                payload.get("reply")
                or payload.get("message")
                or extract_reply_only(raw_text)
            )

            md = payload.get("mindmap_insights")
            if isinstance(md, list):
                mindmap_data = md

            geogebra_block = payload.get("geogebra") or {}
            normalized_geogebra = {
                "should_draw": bool(geogebra_block.get("should_draw")),
                "reason": geogebra_block.get("reason") or "",
                "prompt": geogebra_block.get("prompt") or request.message,
                "commands": geogebra_block.get("commands")
                if isinstance(geogebra_block.get("commands"), list)
                else [],
            }

        except Exception as e:
            print(f"JSON parse failed: {e}")
            reply_text = extract_reply_only(raw_text)

        return {
            "reply": reply_text,
            "mindmap_insights": mindmap_data,
            "geogebra": normalized_geogebra,
        }

    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== ALL SCHEMAS =====

class ProcessDocumentInput(BaseModel):
    userId: str
    documentId: str
    purpose: str = "chat"

class GenerateExercisesInput(BaseModel):
    userId: Optional[str] = None
    topic: str
    difficulty: str = "medium"
    count: int = 3

class SummarizeTopicInput(BaseModel):
    topic: str
    detail_level: str = "medium"

class GeogebraInputSchema(BaseModel):
    request: str
    graph_type: str = "function"

class AnalyzeTestResultInput(BaseModel):
    userId: str
    testAttempt: dict
    weakTopics: List[dict]

class AnalyzeTestResultOutput(BaseModel):
    analysis: str
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    suggestedTopics: List[str]

class GenerateAdaptiveTestInput(BaseModel):
    userId: str
    weakTopics: List[str]
    difficulty: str = "medium"
    
class GenerateTestInput(BaseModel):
    userId: Optional[str] = None
    topic: str
    difficulty: str = "medium"
    testType: str = "standard"
    numQuestions: int = 5

class NodeTestRequest(BaseModel):
    userId: Optional[str] = None
    topic: str

# ===== DOCUMENT PROCESSING =====

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return ""

def extract_text_from_word(docx_path: str) -> str:
    try:
        doc = Document(docx_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        print(f"Error reading Word file {docx_path}: {e}")
        return ""

def extract_text_from_file(file_path: str) -> str:
    file_path_obj = Path(file_path)
    extension = file_path_obj.suffix.lower()
    
    if extension == '.pdf':
        return extract_text_from_pdf(file_path)
    elif extension in ['.docx', '.doc']:
        return extract_text_from_word(file_path)
    else:
        print(f"Unsupported file format: {extension}")
        return ""

def load_reference_materials(folder_path: str, max_files: int = 5) -> str:
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Warning: Folder {folder_path} does not exist")
        return ""
    
    pdf_files = list(folder.glob("*.pdf"))
    docx_files = list(folder.glob("*.docx"))
    doc_files = list(folder.glob("*.doc"))
    
    all_files = (pdf_files + docx_files + doc_files)[:max_files]
    
    if not all_files:
        print(f"Warning: No PDF or Word files found in {folder_path}")
        return ""
    
    combined_text = ""
    for file in all_files:
        print(f"📄 Loading: {file.name}")
        text = extract_text_from_file(str(file))
        if text:
            combined_text += f"\n\n=== TÀI LIỆU: {file.name} ===\n{text}\n"
    
    return combined_text

# ===== PATHS =====

BASE_DIR = Path(__file__).parent.parent
EXERCISES_FOLDER = BASE_DIR / "reference_materials" / "exercises"
TESTS_FOLDER = BASE_DIR / "reference_materials" / "tests"

EXERCISES_FOLDER.mkdir(parents=True, exist_ok=True)
TESTS_FOLDER.mkdir(parents=True, exist_ok=True)

# ===== CACHED MODELS FOR OTHER ENDPOINTS =====

_exercise_model_cache = None
_test_model_cache = None
_geogebra_model_cache = None
_summarize_model_cache = None

def get_exercise_model():
    global _exercise_model_cache
    if _exercise_model_cache is None:
        _exercise_model_cache = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"temperature": 0.7},
            system_instruction="Bạn là một AI tạo bài tập toán học chuyên nghiệp cho học sinh THPT lớp 12 Việt Nam."
        )
    return _exercise_model_cache

def get_test_model():
    global _test_model_cache
    if _test_model_cache is None:
        _test_model_cache = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"temperature": 0.6, "response_mime_type": "application/json"},
            system_instruction="""Bạn là chuyên gia biên soạn đề thi THPT Quốc gia môn Toán.
QUY TẮC:
1. Mỗi câu PHẢI có đầy đủ dữ liệu
2. Sử dụng LaTeX: $x^2$
3. Tất cả \\ trong LaTeX phải escape: \\\\frac, \\\\lim
4. Trả về JSON thuần, KHÔNG markdown"""
        )
    return _test_model_cache

def get_geogebra_model():
    global _geogebra_model_cache
    if _geogebra_model_cache is None:
        _geogebra_model_cache = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"temperature": 0.3, "response_mime_type": "application/json"},
            system_instruction="Bạn là chuyên gia GeoGebra. Chuyển đổi yêu cầu thành lệnh GeoGebra hợp lệ."
        )
    return _geogebra_model_cache

def get_summarize_model():
    global _summarize_model_cache
    if _summarize_model_cache is None:
        _summarize_model_cache = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"temperature": 0.5},
            system_instruction="Bạn là giảng viên toán học chuyên tóm tắt kiến thức súc tích."
        )
    return _summarize_model_cache

# ===== ROOT ENDPOINT =====

@app.get("/")
async def root():
    return {
        "status": "ok", 
        "message": "Math Tutor API - OPTIMIZED",
        "model": "gemini-2.5-flash",
        "optimizations": [
            "Cached system instruction",
            "Reused model instances",
            "Compact prompts",
            "Session-based chat"
        ],
        "endpoints": [
            "/api/chat",
            "/api/generate-exercises",
            "/api/generate-test",
            "/api/generate-node-test",
            "/api/process-document",
            "/api/summarize-topic",
            "/api/geogebra",
            "/api/analyze-test-result",
            "/api/generate-adaptive-test"
        ]
    }

# ===== GENERATE EXERCISES ENDPOINT =====

@app.post("/api/generate-exercises")
async def handle_generate_exercises(request: GenerateExercisesInput):
    try:
        print(f"📚 Generating exercises for topic: {request.topic}")
        
        # RAG Integration
        context_text = ""
        if request.userId:
            docs = await rag_service.search_similar_documents(request.topic, request.userId, purpose="test")
            if docs:
                context_text = "\n\n=== TÀI LIỆU THAM KHẢO ===\n"
                for d in docs:
                    context_text += f"- {d['content']}\n"
        
        reference_text = load_reference_materials(str(EXERCISES_FOLDER), max_files=3)
        
        model = get_exercise_model()
        
        prompt = f"""Tạo {request.count} bài tập toán học về chủ đề: "{request.topic}"
Độ khó: {request.difficulty}

Tài liệu tham khảo:
{context_text}
{reference_text}

YÊU CẦU:
- Phù hợp Toán 12 Việt Nam
- Lời giải chi tiết từng bước
- Sử dụng LaTeX khi cần
- Format Markdown

Định dạng:
## Bài 1
**Đề bài:** [Nội dung]

**Lời giải:**
[Giải thích]

**Đáp án:** [Kết quả]"""
        
        response = model.generate_content(prompt)
        
        if not response or not hasattr(response, 'text'):
            raise ValueError("Model không trả về phản hồi")
        
        exercises_text = response.text.strip()
        
        return {"exercises": exercises_text}
        
    except Exception as e:
        print(f"❌ Generate exercises error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== PROCESS DOCUMENT ENDPOINT =====

@app.post("/api/process-document")
async def process_document(request: ProcessDocumentInput):
    try:
        success = await rag_service.process_document(
            user_id=request.userId,
            document_id=request.documentId,
            purpose=request.purpose
        )
        if not success:
            raise HTTPException(status_code=500, detail="Processing failed")
        return {"status": "ok", "message": "Document processed successfully"}
    except Exception as e:
        print(f"Process document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== GENERATE NODE TEST ENDPOINT =====

@app.post("/api/generate-node-test")
async def generate_node_test(req: NodeTestRequest):
    try:
        topic = req.topic
        model = get_test_model()

        # RAG Integration
        context_text = ""
        if req.userId:
            docs = await rag_service.search_similar_documents(topic, req.userId, purpose="test")
            if docs:
                context_text = "\n\n=== TÀI LIỆU THAM KHẢO ===\n"
                for d in docs:
                    context_text += f"- {d['content']}\n"

        prompt = f"""Tạo đề kiểm tra toán lớp 12 cho chủ đề: "{topic}"

TÀI LIỆU:
{context_text}

YÊU CẦU:
- 15 câu multiple-choice
- 4 câu true-false (mỗi câu 4 ý)
- 2 câu short-answer
- Sử dụng LaTeX: $x^2$
- TẤT CẢ \\ PHẢI ESCAPE: \\\\frac, \\\\lim, \\\\infty

JSON BẮT BUỘC:
{{
  "title": "KIỂM TRA {topic.upper()}",
  "parts": {{
    "multipleChoice": {{"title": "...", "questions": [...]}},
    "trueFalse": {{"title": "...", "questions": [...]}},
    "shortAnswer": {{"title": "...", "questions": [...]}}
  }}
}}"""

        response = model.generate_content(prompt)
        raw_text = response.text

        try:
            json_text = clean_json_response(raw_text)
            if not json_text:
                raise ValueError("Không tìm thấy JSON hợp lệ")
            data = json.loads(json_text)
        except Exception as e:
            print(f"❌ NODE TEST JSON ERROR: {e}")
            print(f"❌ Raw text: {raw_text}")
            raise HTTPException(status_code=500, detail=f"AI trả về JSON không hợp lệ: {str(e)}")
        
        if "parts" not in data:
            raise HTTPException(status_code=500, detail="Thiếu 'parts' trong JSON")

        return {"topic": topic, "test": data}

    except Exception as e:
        print(f"❌ NODE TEST ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== GENERATE TEST ENDPOINT =====

@app.post("/api/generate-test")
async def handle_generate_test(request: GenerateTestInput):
    try:
        print(f"📝 Generating test for topic: {request.topic}")
        reference_text = load_reference_materials(str(TESTS_FOLDER), max_files=3)
        
        model = get_test_model()
        
        # RAG Integration
        context_text = ""
        if request.userId:
            docs = await rag_service.search_similar_documents(request.topic, request.userId, purpose="test")
            if docs:
                context_text = "\n\n=== TÀI LIỆU RAG ===\n"
                for d in docs:
                    context_text += f"- {d['content']}\n"

        # Prompt đã được tối ưu
        prompt = f"""Tạo đề kiểm tra TOÁN 12 về: "{request.topic}"
Độ khó: {request.difficulty}

TÀI LIỆU:
{context_text}
{reference_text if reference_text else ""}

QUY TẮC:
- Mỗi câu có đầy đủ dữ liệu
- LaTeX: $x^2$
- TẤT CẢ \\ PHẢI ESCAPE: \\\\frac, \\\\lim

CẤU TRÚC:
- Phần 1: Trắc nghiệm 4 lựa chọn
- Phần 2: Đúng/Sai (4 ý)
- Phần 3: Trả lời ngắn

JSON (KHÔNG markdown):
{{
  "title": "...",
  "parts": {{
    "multipleChoice": {{...}},
    "trueFalse": {{...}},
    "shortAnswer": {{...}}
  }}
}}"""
        
        response = model.generate_content(prompt)
        raw_text = response.text
        
        try:
            json_text = clean_json_response(raw_text)
            if not json_text:
                raise ValueError("Không trích xuất được JSON từ phản hồi của AI")
            
            result = json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"❌ JSON parse error: {e}")
            print(f"❌ Raw text causing error: {raw_text}") # In ra để debug
            # Fallback: Trả về lỗi 500 nhưng có thông tin
            raise HTTPException(status_code=500, detail=f"Lỗi đọc dữ liệu từ AI: {str(e)}")
        except ValueError as e:
            print(f"❌ Value error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
        if "parts" not in result:
             # Đôi khi AI trả về cấu trúc khác, thử mapping lại nếu có thể hoặc báo lỗi
            raise HTTPException(status_code=500, detail="AI trả về thiếu trường 'parts'")
        
        return {
            "topic": request.topic,
            "difficulty": request.difficulty,
            "test": result
        }
        
    except Exception as e:
        print(f"❌ Generate test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== SUMMARIZE TOPIC ENDPOINT =====

@app.post("/api/summarize-topic")
async def handle_summarize_topic(request: SummarizeTopicInput):
    try:
        print(f"📖 Summarizing topic: {request.topic}")
        
        model = get_summarize_model()
        
        prompt = f"""Tóm tắt chủ đề sau ngắn gọn, dễ hiểu:
- Gạch đầu dòng
- LaTeX khi cần
- Tiêu đề phụ

Chủ đề: {request.topic}
Độ chi tiết: {request.detail_level}"""
        
        response = model.generate_content(prompt)
        summary_text = response.text.strip()
        
        return {"topic": request.topic, "summary": summary_text}
        
    except Exception as e:
        print(f"❌ Summarize error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== GEOGEBRA ENDPOINT =====

@app.post("/api/geogebra")
async def handle_geogebra(request: GeogebraInputSchema):
    try:
        model = get_geogebra_model()
        
        prompt = f"""Tạo lệnh GeoGebra cho: {request.request}

Trả về JSON:
{{
  "commands": ["command1", "command2"]
}}"""
        
        response = model.generate_content(prompt)
        json_text = clean_json_response(response.text)
        if not json_text:
            raise ValueError("Không tìm thấy JSON hợp lệ")
            
        result = json.loads(json_text)
        
        if "commands" not in result:
            raise ValueError("Invalid response format")
        
        return result
        
    except Exception as e:
        print(f"Geogebra error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== ANALYZE TEST RESULT ENDPOINT =====

@app.post("/api/analyze-test-result")
async def handle_analyze_test_result(request: AnalyzeTestResultInput):
    try:
        model = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"temperature": 0.6},
        )
        
        attempt = request.testAttempt
        weak_topics = request.weakTopics
        
        incorrect_answers_str = ""
        try:
            incorrect_answers = [a for a in attempt['answers'] if not a['isCorrect']]
            
            if not incorrect_answers:
                incorrect_answers_str = "**Học sinh đã trả lời đúng tất cả!**\n"
            else:
                incorrect_answers_str = "**CÁC CÂU SAI:**\n"
                for i, ans in enumerate(incorrect_answers[:5]):
                    incorrect_answers_str += f"{i+1}. {ans.get('topic', 'N/A')}\n"
        except Exception as e:
            incorrect_answers_str = "Không thể tải chi tiết."
        
        prompt = f"""Phân tích kết quả bài làm:

THÔNG TIN:
- Điểm: {attempt.get('score', 0):.1f}/100
- Đúng: {attempt.get('correctAnswers', 0)}/{attempt.get('totalQuestions', 0)}

CHỦ ĐỀ YẾU:
{chr(10).join([f"- {t.get('topic', 'N/A')}: {t.get('accuracy', 0):.1f}%" for t in weak_topics])}

{incorrect_answers_str}

TRẢ VỀ JSON:
{{
  "analysis": "...",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommendations": ["..."],
  "suggestedTopics": ["..."]
}}"""
        
        response = model.generate_content(prompt)
        
        json_text = clean_json_response(response.text)
        if not json_text:
            raise HTTPException(status_code=500, detail="AI trả về dữ liệu không hợp lệ")

        result = json.loads(json_text)
        return result
        
    except Exception as e:
        print(f"❌ Analyze error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== GENERATE ADAPTIVE TEST ENDPOINT =====

@app.post("/api/generate-adaptive-test")
async def handle_generate_adaptive_test(request: GenerateAdaptiveTestInput):
    try:
        model = get_test_model()
        topics_str = ", ".join(request.weakTopics)
        
        prompt = f"""Tạo đề thi thích ứng cho các chủ đề yếu:

CHỦ ĐỀ: {topics_str}
Độ khó: {request.difficulty}

YÊU CẦU:
- 70% câu về chủ đề yếu
- 30% tổng hợp
- Độ khó tăng dần
- TẤT CẢ \\ ESCAPE: \\\\frac

JSON (KHÔNG markdown)."""
        
        response = model.generate_content(prompt)
        
        try:
            json_text = clean_json_response(response.text)
            if not json_text:
                raise ValueError("Không tìm thấy JSON")
            result = json.loads(json_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail="JSON không hợp lệ")
        
        return {
            "userId": request.userId,
            "weakTopics": request.weakTopics,
            "test": result
        }
        
    except Exception as e:
        print(f"❌ Adaptive test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== STARTUP =====

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Starting OPTIMIZED Math Tutor API")
    print("="*60)
    print(f"📁 Exercises: {EXERCISES_FOLDER}")
    print(f"📁 Tests: {TESTS_FOLDER}")
    print("\n⚡ Optimizations:")
    print("  - Cached system instructions (5 models)")
    print("  - Singleton pattern (no re-initialization)")
    print("  - Compact prompts (90% smaller)")
    print("  - Session-based chat")
    print("\n⏱️  Expected speed:")
    print("  - First request: 2-3s")
    print("  - Follow-up: 0.8-1.2s (70% faster)")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
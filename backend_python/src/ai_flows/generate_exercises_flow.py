# src/ai_flows/generate_exercises_flow.py
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import Optional

# Import config
from ..ai_config import GOOGLE_API_KEY

MODEL_NAME = "gemini-2.5-flash"

class GenerateExercisesInput(BaseModel):
    topic: str
    difficulty: str = "medium"
    count: int = 3
    userId: Optional[str] = None

class GenerateExercisesOutput(BaseModel):
    content: str

SYSTEM_PROMPT = """Bạn là chuyên gia biên soạn bài tập toán THPT lớp 12.
Nhiệm vụ: Tạo các bài tập tự luyện có lời giải chi tiết.
Format: Markdown, dùng LaTeX cho công thức toán."""

async def generate_exercises(input: GenerateExercisesInput) -> GenerateExercisesOutput:
    generation_config = {
        "temperature": 0.7,
        # Không dùng JSON mode vì muốn format Markdown tự nhiên
    }
    
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=generation_config,
        system_instruction=SYSTEM_PROMPT
    )

    prompt = f"""
    Tạo {input.count} bài tập về chủ đề: "{input.topic}"
    Độ khó: {input.difficulty}
    
    Yêu cầu định dạng:
    ## Bài 1
    **Đề bài:** ...
    **Lời giải:** ...
    **Đáp án:** ...
    
    (Lặp lại cho các bài tiếp theo)
    """

    try:
        response = await model.generate_content_async(prompt)
        return GenerateExercisesOutput(content=response.text)
    except Exception as e:
        print(f"❌ Error generating exercises: {e}")
        return GenerateExercisesOutput(content="Xin lỗi, không thể tạo bài tập lúc này.")
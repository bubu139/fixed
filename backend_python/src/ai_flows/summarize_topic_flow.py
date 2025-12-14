# src/ai_flows/summarize_topic_flow.py
import google.generativeai as genai
from pydantic import BaseModel
from typing import Literal

from ..ai_config import GOOGLE_API_KEY

MODEL_NAME = "gemini-2.5-flash"

class SummarizeTopicInput(BaseModel):
    topic: str
    detail_level: str = "medium" # 'brief', 'medium', 'detailed'

class SummarizeTopicOutput(BaseModel):
    summary: str

SYSTEM_PROMPT = """Bạn là giáo viên Toán 12 giỏi tóm tắt kiến thức.
Nhiệm vụ: Tóm tắt lý thuyết, công thức trọng tâm một cách súc tích.
Format: Markdown, dùng bullet points và LaTeX."""

async def summarize_topic(input: SummarizeTopicInput) -> SummarizeTopicOutput:
    generation_config = {
        "temperature": 0.5,
    }
    
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=generation_config,
        system_instruction=SYSTEM_PROMPT
    )

    prompt = f"""
    Tóm tắt chủ đề: {input.topic}
    Mức độ chi tiết: {input.detail_level}
    
    Yêu cầu:
    - Định nghĩa ngắn gọn.
    - Các công thức quan trọng nhất.
    - Một ví dụ minh hoạ nhỏ (nếu cần).
    """

    try:
        response = await model.generate_content_async(prompt)
        return SummarizeTopicOutput(summary=response.text)
    except Exception as e:
        print(f"❌ Error summarizing: {e}")
        return SummarizeTopicOutput(summary="Không thể tóm tắt nội dung này.")
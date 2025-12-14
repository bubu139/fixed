# src/ai_flows/generate_test_flow.py
import json
import os
from typing import Literal

from pydantic import BaseModel, Field
import google.generativeai as genai

# Import config (để load API Key)
from ..ai_config import GOOGLE_API_KEY
from ..ai_schemas.test_schema import TestSchema

# Cấu hình model
MODEL_NAME = "gemini-2.5-flash"

class GenerateTestInput(BaseModel):
    topic: str = Field(description='Chủ đề bài kiểm tra.')
    testType: Literal['standard', 'thptqg', 'node'] = Field(
        default='standard', 
        description='Loại bài kiểm tra (standard, thptqg, hoặc node).'
    )
    numQuestions: int = Field(
        default=5, 
        description='Số lượng câu hỏi ước lượng (dùng cho THPTQG hoặc node).'
    )

class GenerateTestOutput(BaseModel):
    test: TestSchema = Field(description='Bài kiểm tra đã được tạo.')

# --- PROMPT TEMPLATES ---
PROMPT_BASE = """Bạn là một AI chuyên tạo đề kiểm tra toán học cho học sinh lớp 12 ở Việt Nam.
Chủ đề: {topic}

YÊU CẦU CHUNG:
1. Nội dung bám sát chương trình Toán 12.
2. Sử dụng LaTeX cho công thức (ví dụ $x^2$).
3. JSON trả về phải khớp với schema yêu cầu.
"""

PROMPT_STANDARD_FORMAT = """
CẤU TRÚC (STANDARD):
- Phần 1: 4 câu Trắc nghiệm (multipleChoice).
- Phần 2: 1 câu Đúng/Sai (trueFalse).
- Phần 3: 1 câu Trả lời ngắn (shortAnswer).
"""

PROMPT_THPTQG_FORMAT = """
CẤU TRÚC (THPTQG/NODE):
- Chỉ gồm 1 phần Trắc nghiệm (multipleChoice) với {num_questions} câu.
- Không có phần trueFalse hay shortAnswer.
"""

async def generate_test(input: GenerateTestInput) -> GenerateTestOutput:
    # 1. Cấu hình
    generation_config = {
        "temperature": 0.5,
        "response_mime_type": "application/json", # Bắt buộc trả về JSON
    }
    
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=generation_config,
        system_instruction=PROMPT_BASE.format(topic=input.topic)
    )

    # 2. Xây dựng prompt
    prompt_text = f"Hãy tạo đề kiểm tra về chủ đề: {input.topic}.\n"
    if input.testType in ['thptqg', 'node']:
        prompt_text += PROMPT_THPTQG_FORMAT.format(num_questions=input.numQuestions)
    else:
        prompt_text += PROMPT_STANDARD_FORMAT
    
    prompt_text += "\nTrả về JSON đầy đủ theo cấu trúc đề thi."

    # 3. Gọi AI
    try:
        response = await model.generate_content_async(prompt_text)
        
        # 4. Parse kết quả
        # Gemini ở chế độ JSON trả về text là chuỗi JSON hợp lệ
        json_data = json.loads(response.text)
        
        # Validate với Pydantic schema
        test_obj = TestSchema(**json_data)
        
        return GenerateTestOutput(test=test_obj)

    except Exception as e:
        print(f"❌ Error generating test: {e}")
        # Trả về đề rỗng hoặc raise lỗi tuỳ logic app
        raise e
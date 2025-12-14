# src/ai_flows/geogebra_flow.py
import json
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List

from ..ai_config import GOOGLE_API_KEY

MODEL_NAME = "gemini-2.5-flash"

class GeogebraInput(BaseModel):
    request: str = Field(description="Mô tả hình vẽ bằng lời")
    graph_type: str = "function"

class GeogebraOutput(BaseModel):
    commands: List[str]

SYSTEM_PROMPT = """Bạn là chuyên gia GeoGebra. 
Nhiệm vụ: Chuyển đổi mô tả của người dùng thành danh sách lệnh GeoGebra Classic hợp lệ.
Quy tắc:
1. Trả về JSON object duy nhất: {"commands": ["lệnh 1", "lệnh 2"]}
2. Dùng tên biến ngắn gọn (A, B, f, d).
3. Không giải thích thêm."""

async def generate_geogebra_commands(input: GeogebraInput) -> GeogebraOutput:
    generation_config = {
        "temperature": 0.2, # Thấp để chính xác cú pháp
        "response_mime_type": "application/json",
    }
    
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=generation_config,
        system_instruction=SYSTEM_PROMPT
    )

    prompt = f"Vẽ hình cho yêu cầu: {input.request}"

    try:
        response = await model.generate_content_async(prompt)
        data = json.loads(response.text)
        
        # Đảm bảo data có key 'commands'
        commands = data.get("commands", [])
        return GeogebraOutput(commands=commands)
        
    except Exception as e:
        print(f"❌ Error generating geogebra: {e}")
        return GeogebraOutput(commands=[])
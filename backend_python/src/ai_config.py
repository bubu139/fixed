# src/ai_config.py
import os
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Tìm file .env ở thư mục root của project
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Lấy API key
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

if not GOOGLE_API_KEY:
    print("[MathMentor] GOOGLE_API_KEY not found; AI endpoints will return fallback content.")
else:
    genai.configure(api_key=GOOGLE_API_KEY)
    print("✅ Google Generative AI configured successfully")
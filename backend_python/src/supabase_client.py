import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY:
  supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
  print("[MathMentor] SUPABASE_URL or SUPABASE_SERVICE_KEY is missing. API will run in degraded mode without Supabase persistence.")

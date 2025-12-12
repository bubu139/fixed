# src/routes/node_progress.py
from fastapi import APIRouter, HTTPException
from src.models import NodeProgress
from src.supabase_client import supabase
from datetime import datetime

router = APIRouter(prefix="/node-progress", tags=["node-progress"])

# ---------------------------------
# POST /node-progress/update
# Tối ưu: Sử dụng UPSERT để xử lý 1 lần gọi DB
# ---------------------------------
@router.post("/update")
def update_node_progress(data: NodeProgress):
    try:
        # Calculate status & color
        status = "learning"
        node_color = 1 # Mặc định là đang học (Vàng) nếu gọi update

        # Nếu chưa mở thì là 0 (Blue), nhưng hàm update thường gọi khi đã tương tác
        if not data.opened:
             node_color = 0

        # Logic Mastered (Xanh lá)
        if data.score is not None and data.score >= 80:
            status = "mastered"
            node_color = 2
        
        # Chuẩn bị dữ liệu
        payload = {
            "user_id": data.user_id,
            "node_id": data.node_id,
            "opened": data.opened,
            "score": data.score,
            "status": status,
            "node_color": node_color, # [MỚI] Lưu màu
            "updated_at": datetime.utcnow().isoformat()
        }

        response = supabase.table("node_progress").upsert(
            payload, 
            on_conflict="user_id, node_id"
        ).execute()

        return {"status": "ok", "data": response.data}

    except Exception as e:
        print(f"❌ Error updating node progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------
# GET /node-progress/{user_id}
# ---------------------------------
@router.get("/{user_id}")
def get_all_progress(user_id: str):
    try:
        res = supabase.table("node_progress") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        return res.data or []
    except Exception as e:
        print(f"❌ Error fetching progress: {e}")
        return [] # Trả về mảng rỗng thay vì lỗi để FE không bị crash
from typing import Any, Dict, List
from src.supabase_client import supabase
from src.models import NodeProgress

STATIC_NODES = [
    {"id": "ung-dung-dao-ham", "label": "Ứng dụng đạo hàm", "parent": None},
    {"id": "tinh-don-dieu", "label": "Tính đơn điệu", "parent": "ung-dung-dao-ham"},
    {"id": "cuc-tri", "label": "Cực trị", "parent": "ung-dung-dao-ham"},
    {"id": "max-min", "label": "GTNN/GTNL", "parent": "ung-dung-dao-ham"},
]


def get_mindmap(user_id: str) -> List[Dict[str, Any]]:
    statuses: Dict[str, Dict[str, Any]] = {}
    if supabase is not None:
        try:
            res = supabase.table("node_progress").select("node_id,status,score,opened").eq("user_id", user_id).execute()
            for row in res.data or []:
                statuses[row["node_id"]] = row
        except Exception:
            pass

    nodes = []
    for node in STATIC_NODES:
        progress = statuses.get(node["id"], {})
        nodes.append(
            {
                **node,
                "status": progress.get("status", "learning"),
                "score": progress.get("score"),
                "opened": progress.get("opened", False),
            }
        )
    return nodes


def update_node_progress(progress: NodeProgress) -> Dict[str, Any]:
    payload = progress.model_dump()
    if supabase is not None:
        try:
            supabase.table("node_progress").upsert(payload, on_conflict="node_id, user_id").execute()
        except Exception:
            pass
    return payload

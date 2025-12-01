# backend/src/models.py
from pydantic import BaseModel, Field
from typing import Optional

class NodeProgress(BaseModel):
    user_id: str
    node_id: str
    opened: bool = False
    score: Optional[float] = None
    status: str = Field(default="learning", description="learning|mastered|review")

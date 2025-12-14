from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.supabase_client import supabase

router = APIRouter(prefix="/student-profile", tags=["student-profile"])


class StudentProfileUpdate(BaseModel):
    targetScore: Optional[float] = Field(default=None, ge=0, le=100)
    goalText: Optional[str] = Field(default=None, max_length=2000)


def _normalize_completion_rate_to_pct(completion_rate: Optional[float]) -> Optional[float]:
    if completion_rate is None:
        return None
    # view có thể trả 0..1 hoặc 0..100 tuỳ nơi build
    if completion_rate <= 1:
        return round(completion_rate * 100, 1)
    return round(completion_rate, 1)


def _study_status(
    target_score: Optional[float],
    average_score: Optional[float],
    completion_rate: Optional[float],
    total_tests: Optional[int],
) -> Dict[str, Any]:
    completion_pct = _normalize_completion_rate_to_pct(completion_rate)

    if not total_tests or average_score is None:
        return {
            "level": "unknown",
            "label": "Chưa đủ dữ liệu",
            "message": "Hiện chưa có đủ bài làm/đề đã luyện để đánh giá ổn định. Hãy làm thêm 1–2 đề để hệ thống đánh giá chính xác hơn.",
            "recommendations": [
                "Làm thêm ít nhất 1 đề/tuần để có dữ liệu đánh giá.",
                "Sau khi làm đề, xem lại câu sai theo chủ đề yếu.",
            ],
            "completionRatePct": completion_pct,
        }

    # Nếu có target_score: ưu tiên đánh giá theo khoảng cách mục tiêu
    if target_score is not None:
        gap = target_score - float(average_score)
        # average >= target => tốt
        if gap <= 0:
            return {
                "level": "good",
                "label": "Đang vượt/đạt mục tiêu",
                "message": f"Điểm trung bình hiện tại (~{average_score:.1f}) đang đạt hoặc vượt mục tiêu ({target_score:.1f}). Duy trì nhịp luyện và tăng độ khó dần.",
                "recommendations": [
                    "Tăng dần độ khó hoặc thêm câu vận dụng/vận dụng cao.",
                    "Duy trì 2–3 buổi/tuần: 1 buổi lý thuyết + 1–2 buổi luyện đề.",
                ],
                "completionRatePct": completion_pct,
            }

        # gap nhỏ: ổn
        if gap <= 5:
            return {
                "level": "good",
                "label": "Đang bám sát mục tiêu",
                "message": f"Bạn đang khá sát mục tiêu: thiếu khoảng {gap:.1f} điểm so với mục tiêu ({target_score:.1f}).",
                "recommendations": [
                    "Tập trung chữa kỹ các câu sai và luyện lại theo chủ đề yếu.",
                    "Mỗi tuần ít nhất 1 đề + 1 buổi sửa đề.",
                ],
                "completionRatePct": completion_pct,
            }

        # gap vừa: cảnh báo
        if gap <= 15:
            return {
                "level": "warning",
                "label": "Cần cải thiện để kịp mục tiêu",
                "message": f"Điểm trung bình (~{average_score:.1f}) đang thấp hơn mục tiêu ({target_score:.1f}) khoảng {gap:.1f} điểm.",
                "recommendations": [
                    "Ưu tiên ôn 2–3 chủ đề yếu nhất trong 7 ngày tới.",
                    "Luyện bài theo dạng (không chỉ làm đề), sau đó quay lại làm đề tổng hợp.",
                ],
                "completionRatePct": completion_pct,
            }

        # gap lớn: nguy cơ
        return {
            "level": "critical",
            "label": "Đang tụt xa mục tiêu",
            "message": f"Khoảng cách mục tiêu đang khá lớn (~{gap:.1f} điểm). Nên điều chỉnh kế hoạch và học theo lộ trình từ nền tảng → dạng bài → đề.",
            "recommendations": [
                "Giảm độ khó tạm thời để củng cố nền tảng, sau đó tăng dần.",
                "Chia nhỏ mục tiêu theo tuần (ví dụ +3 đến +5 điểm/tuần).",
                "Mỗi buổi: 30% lý thuyết + 70% bài tập theo dạng.",
            ],
            "completionRatePct": completion_pct,
        }

    # Không có target_score: đánh giá theo ngưỡng
    avg = float(average_score)
    if avg >= 75:
        return {
            "level": "good",
            "label": "Tình hình học ổn",
            "message": f"Điểm trung bình hiện tại (~{avg:.1f}) đang ở mức tốt. Tiếp tục luyện đề đều để ổn định phong độ.",
            "recommendations": [
                "Duy trì 1–2 đề/tuần và sửa đề đầy đủ.",
                "Tăng dần câu vận dụng cao khi đã chắc nền tảng.",
            ],
            "completionRatePct": completion_pct,
        }

    if avg >= 60:
        return {
            "level": "warning",
            "label": "Cần tăng nhịp luyện",
            "message": f"Điểm trung bình (~{avg:.1f}) ở mức trung bình-khá. Nếu muốn tăng nhanh, cần luyện theo chủ đề yếu và sửa đề kỹ hơn.",
            "recommendations": [
                "Tập trung cải thiện các chủ đề yếu nhất (2–3 chủ đề).",
                "Sau mỗi đề, ghi lại lỗi sai (công thức, tư duy, tính toán).",
            ],
            "completionRatePct": completion_pct,
        }

    return {
        "level": "critical",
        "label": "Cần củng cố nền tảng",
        "message": f"Điểm trung bình (~{avg:.1f}) còn thấp. Nên ưu tiên củng cố nền tảng và luyện theo dạng trước khi làm đề tổng hợp.",
        "recommendations": [
            "Học lại công thức/các dạng cơ bản theo chương.",
            "Làm bài tập theo dạng (tăng dần độ khó) rồi mới quay lại luyện đề.",
        ],
        "completionRatePct": completion_pct,
    }


@router.get("/{user_id}")
def get_student_profile(user_id: str) -> Dict[str, Any]:
    try:
        prof_res = (
            supabase.from_("student_profiles")
            .select("user_id,target_score,goal_text")
            .eq("user_id", user_id)
            .execute()
        )
        profile = prof_res.data[0] if prof_res.data else {}

        perf_res = (
            supabase.from_("user_performance_summary")
            .select("average_score,completion_rate,total_tests")
            .eq("user_id", user_id)
            .execute()
        )
        perf = perf_res.data[0] if perf_res.data else {}

        study_status = _study_status(
            target_score=profile.get("target_score"),
            average_score=perf.get("average_score"),
            completion_rate=perf.get("completion_rate"),
            total_tests=perf.get("total_tests"),
        )

        return {
            "userId": user_id,
            "targetScore": profile.get("target_score"),
            "goalText": profile.get("goal_text"),
            "performance": {
                "averageScore": perf.get("average_score"),
                "completionRate": perf.get("completion_rate"),
                "totalTests": perf.get("total_tests"),
            },
            "studyStatus": study_status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load student profile: {e}")


@router.put("/{user_id}")
def update_student_profile(user_id: str, payload: StudentProfileUpdate) -> Dict[str, Any]:
    try:
        # chuẩn hoá
        goal_text = (payload.goalText or "").strip() or None
        target_score = payload.targetScore

        # xem có row chưa
        existing = (
            supabase.from_("student_profiles")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase.from_("student_profiles").update(
                {"goal_text": goal_text, "target_score": target_score}
            ).eq("user_id", user_id).execute()
        else:
            supabase.from_("student_profiles").insert(
                {"user_id": user_id, "goal_text": goal_text, "target_score": target_score}
            ).execute()

        # trả lại profile mới
        return get_student_profile(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update student profile: {e}")

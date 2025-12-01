import random
import time
import uuid
from typing import Any, Dict, List

from src.supabase_client import supabase
from .cache_service import cache

GENERATED_TESTS: Dict[str, Dict[str, Any]] = {}

QUESTION_BANK = [
    {
        "topic": "dao-ham",
        "stem": "Tính đạo hàm của hàm số f(x) = x^3 - 3x^2 + 1.",
        "options": ["3x^2-6x", "3x^2-6", "2x-3", "x^2-3"],
        "answer": "3x^2-6x",
        "type": "mcq",
    },
    {
        "topic": "cuc-tri",
        "stem": "Hàm số y = x^3 - 3x có bao nhiêu cực trị?",
        "options": ["0", "1", "2", "3"],
        "answer": "2",
        "type": "mcq",
    },
    {
        "topic": "tich-phan",
        "stem": "Khẳng định sau đúng hay sai: ∫_0^1 x dx = 1/2",
        "answer": "Đúng",
        "type": "tf",
    },
    {
        "topic": "logarit",
        "stem": "Giải thích ngắn gọn vì sao log_a(bc) = log_a b + log_a c.",
        "answer": "Tính chất nhân của logarit",
        "type": "short",
    },
]


def _pick_questions(count: int, qtype: str) -> List[Dict[str, Any]]:
    filtered = [q for q in QUESTION_BANK if q["type"] == qtype]
    if not filtered:
        return []
    random.shuffle(filtered)
    selected = filtered * ((count // len(filtered)) + 1)
    return [
        {
            "id": f"{qtype}-{idx}",
            "questionType": qtype,
            "topic": q["topic"],
            "difficulty": random.choice(["easy", "medium", "hard"]),
            "stem": q["stem"],
            "options": q.get("options", []),
            "correctAnswer": q["answer"],
        }
        for idx, q in enumerate(selected[:count])
    ]


def generate_test(user_id: str, exam_type: str) -> Dict[str, Any]:
    # basic counts depending on exam type
    mcq_count = 10 if exam_type == "thptqg" else 8
    tf_count = 5
    short_count = 3

    questions = _pick_questions(mcq_count, "mcq") + _pick_questions(tf_count, "tf") + _pick_questions(short_count, "short")
    test_id = str(uuid.uuid4())
    test_payload = {"testId": test_id, "examType": exam_type, "questions": questions, "createdAt": time.time()}
    GENERATED_TESTS[test_id] = test_payload

    if supabase is not None:
        try:
            supabase.table("generated_tests").insert({"id": test_id, "user_id": user_id, "payload": test_payload}).execute()
        except Exception:
            pass

    return test_payload


def submit_test(user_id: str, test_id: str, answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    test = GENERATED_TESTS.get(test_id)
    if not test:
        return {
            "score": 0,
            "timeSpent": 0,
            "strengths": [],
            "weakTopics": [],
            "advice": "Không tìm thấy đề. Vui lòng tạo đề mới.",
            "answerDetails": [],
        }

    question_map = {q["id"]: q for q in test["questions"]}
    total = len(question_map) or 1
    correct = 0
    details = []
    weak_topics = []

    for ans in answers:
        qid = ans.get("questionId")
        user_answer = ans.get("answer")
        question = question_map.get(qid)
        if not question:
            continue
        is_correct = str(user_answer).strip().lower() == str(question["correctAnswer"]).strip().lower()
        if is_correct:
            correct += 1
        else:
            weak_topics.append(question["topic"])
        details.append(
            {
                "questionId": qid,
                "userAnswer": user_answer,
                "correctAnswer": question["correctAnswer"],
                "explanation": "Ôn lại lý thuyết và thử giải lại từng bước.",
                "isCorrect": is_correct,
            }
        )

    score = round((correct / total) * 100, 2)
    result = {
        "score": score,
        "timeSpent": 0,
        "strengths": [t for t in set(question_map[q]["topic"] for q in question_map if question_map[q]["topic"] not in weak_topics)],
        "weakTopics": list(set(weak_topics)),
        "advice": "Tập trung ôn các chủ đề yếu và luyện thêm bài tương tự.",
        "answerDetails": details,
    }

    if supabase is not None:
        try:
            attempt = {"id": str(uuid.uuid4()), "user_id": user_id, "test_id": test_id, "score": score, "weak_topics": result["weakTopics"]}
            supabase.table("test_attempts").insert(attempt).execute()
        except Exception:
            pass

    cache.set((user_id, f"test-{test_id}"), result)
    return result

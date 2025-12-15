'use client';

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { TestAttempt } from "@/types/test-history";
import type { Test, Question } from "@/types/test-schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ArrowLeft, Lightbulb, Loader2, AlertCircle } from "lucide-react";
import { QuestionComponent } from "./Question";
import ReactMarkdown from "react-markdown";
import { API_BASE_URL } from "@/lib/utils";

interface AnswerReviewProps {
  attempt: TestAttempt;
  testData: Test;
}

export function AnswerReviewPage({ attempt, testData }: AnswerReviewProps) {
  const router = useRouter();
  const [isExpanded, setIsExpanded] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [explanations, setExplanations] = useState<Record<string, {
    solution: string;
    explanation: string;
    references?: string[];
  }>>({});

  const allQuestions: Question[] = [
    ...testData.parts.multipleChoice.questions,
    ...testData.parts.trueFalse.questions,
    ...testData.parts.shortAnswer.questions,
  ];

  const handleToggleExplain = async (question: Question, userAnswer: any) => {
    const qid = String(question.id);
    const alreadyLoaded = explanations[qid];

    setIsExpanded(prev => ({ ...prev, [qid]: !prev[qid] }));
    setErrors(prev => ({ ...prev, [qid]: "" }));

    if (alreadyLoaded) {
      return;
    }

    setIsLoading(prev => ({ ...prev, [qid]: true }));
    try {
      const response = await fetch(`${API_BASE_URL}/api/explain-question`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId: attempt.userId,
          questionId: qid,
          prompt: (question as any).prompt || (question as any).question || "",
          questionType: (question as any).type || "unknown",
          correctAnswer: userAnswer?.correctAnswer,
          userAnswer: userAnswer?.userAnswer,
          topic: attempt.topic,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Không thể tải lời giải.");
      }

      const data = await response.json();
      setExplanations(prev => ({ ...prev, [qid]: data }));
    } catch (err: any) {
      setErrors(prev => ({ ...prev, [qid]: err.message || "Không thể tải lời giải." }));
      setIsExpanded(prev => ({ ...prev, [qid]: false }));
    } finally {
      setIsLoading(prev => ({ ...prev, [qid]: false }));
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-6">
      
      <div className="flex items-center gap-3">
        <Button variant="ghost" onClick={() => router.back()} className="flex items-center gap-2">
          <ArrowLeft className="w-4 h-4" /> Quay lại
        </Button>

        <h1 className="text-2xl font-bold">Đáp án bài làm</h1>
      </div>

      {allQuestions.map((q, idx) => {
        const userAns = attempt.answers.find(a => a.questionId === q.id);

        return (
          <Card key={q.id}>
            <CardHeader>
              <CardTitle>Câu {idx + 1}</CardTitle>
            </CardHeader>
            <CardContent>
              <QuestionComponent
                question={q}
                questionNumber={idx + 1}
                isSubmitted={true}
                userAnswer={userAns?.userAnswer}
                correctAnswer={userAns?.correctAnswer}
                highlightMode="review"
                onAnswerChange={() => {}}
              />

              <div className="mt-4 flex flex-col gap-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Button
                    variant="secondary"
                    onClick={() => handleToggleExplain(q, userAns)}
                    disabled={isLoading[q.id]}
                    className="flex items-center gap-2"
                  >
                    {isLoading[q.id] ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lightbulb className="w-4 h-4" />}
                    {isExpanded[q.id] ? "Ẩn lời giải & giải thích" : "Xem lời giải & giải thích"}
                  </Button>
                </div>

                {errors[q.id] && (
                  <Alert variant="destructive" className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 mt-0.5" />
                    <div>
                      <AlertTitle>Lỗi</AlertTitle>
                      <AlertDescription>{errors[q.id]}</AlertDescription>
                    </div>
                  </Alert>
                )}

                {isExpanded[q.id] && explanations[q.id] && (
                  <div className="space-y-3 rounded-lg border border-muted-foreground/20 bg-muted/30 p-4">
                    <div>
                      <p className="text-sm font-semibold mb-1">Lời giải</p>
                      <ReactMarkdown className="prose prose-sm max-w-none">
                        {explanations[q.id].solution || "Chưa có lời giải."}
                      </ReactMarkdown>
                    </div>
                    <div>
                      <p className="text-sm font-semibold mb-1">Giải thích & lưu ý</p>
                      <ReactMarkdown className="prose prose-sm max-w-none">
                        {explanations[q.id].explanation || "Chưa có giải thích."}
                      </ReactMarkdown>
                    </div>
                    {explanations[q.id].references && explanations[q.id].references!.length > 0 && (
                      <div>
                        <p className="text-sm font-semibold mb-1">Tài liệu tham khảo</p>
                        <ul className="list-disc pl-5 space-y-1 text-sm text-muted-foreground">
                          {explanations[q.id].references!.map((ref, refIdx) => (
                            <li key={refIdx}>
                              <a
                                href={ref}
                                className="text-primary hover:underline"
                                target="_blank"
                                rel="noreferrer"
                              >
                                {ref}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

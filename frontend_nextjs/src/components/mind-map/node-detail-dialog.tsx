'use client';

import Link from "next/link";
import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MindMapNode } from '@/types/mindmap';
import ReactMarkdown from 'react-markdown';
import { Loader, Sparkles, PencilRuler, BrainCircuit, Clapperboard } from 'lucide-react';
import { Separator } from '../ui/separator';
import { API_BASE_URL } from '@/lib/utils';
// 🔥 FIX 1: Import API trực tiếp thay vì hook cũ
import { openNode, type NodeProgress, updateNodeScore } from "@/lib/nodeProgressApi";
import { useUser } from "@/supabase/auth/use-user"; // Import hook user nếu có, hoặc dùng context

type NodeDetailDialogProps = {
  node: MindMapNode;
  isOpen: boolean;
  onClose: () => void;
  // 🔥 FIX 2: Nhận progress từ cha để đảm bảo đồng bộ dữ liệu
  currentProgress?: NodeProgress;
};

type NodeContent = {
  overview: string;
  deepDive: string;
  references: string[];
};

type ExerciseItem = {
  id: string;
  prompt: string;
  level: string;
  rationale: string;
  tags: string[];
};

type GeneratedTest = {
  scope: string;
  passThreshold: number;
  questions: { id: string; stem: string; options: string[]; answer: string; explanation: string }[];
};

export function NodeDetailDialog({ node, isOpen, onClose, currentProgress }: NodeDetailDialogProps) {
  // Lấy user thật thay vì hardcode "test-user"
  const { user } = useUser(); 
  const userId = user?.id;

  // Khi mở dialog -> Gọi API mở node (đánh dấu là đang học)
  useEffect(() => {
    if (isOpen && node && userId) {
      // Gọi API ngầm, không cần chờ kết quả để chặn UI
      openNode(userId, node.id).catch(console.error);
    }
  }, [isOpen, node, userId]);

  // 🔥 FIX 3: Ưu tiên hiển thị Max Score
  // Nếu không có max_score thì mới lấy score, fallback về 0
  const rawScore = Math.round(currentProgress?.max_score ?? currentProgress?.score ?? 0);

  // 🔥 FIX 4: Cập nhật thang màu giống MindMapCanvas (>=80, >=50)
  let colorClass = "text-gray-400 bg-gray-100 border-gray-200"; // Default
  if (rawScore >= 80) {
    colorClass = "text-green-700 bg-green-100 border-green-300"; // Mastered
  } else if (rawScore >= 50) {
    colorClass = "text-yellow-700 bg-yellow-100 border-yellow-300"; // Learning (Good)
  } else if (rawScore > 0) {
    colorClass = "text-orange-700 bg-orange-100 border-orange-300"; // Started (Low)
  }

  const [content, setContent] = useState<NodeContent>({ overview: '', deepDive: '', references: [] });
  const [exerciseItems, setExerciseItems] = useState<ExerciseItem[]>([]);
  const [testData, setTestData] = useState<GeneratedTest | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [isExercisesLoading, setIsExercisesLoading] = useState(false);
  const [isTestLoading, setIsTestLoading] = useState(false);

  useEffect(() => {
    if (isOpen && node) {
      setContent({ overview: '', deepDive: '', references: [] });
      setExerciseItems([]);
      setTestData(null);

      const fetchSummary = async () => {
        setIsSummaryLoading(true);
        try {
          const response = await fetch(`${API_BASE_URL}/api/learning/node-content`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: node.label, nodeId: node.id, userId }),
          });

          if (!response.ok) throw new Error('Failed to fetch summary');
          const data = await response.json();
          setContent({
            overview: data.overview || data.summary || '',
            deepDive: data.deepDive || data.deep_dive || '',
            references: data.references || [],
          });
        } catch {
          setContent({
            overview: 'Không thể tải tóm tắt kiến thức. Vui lòng thử lại.',
            deepDive: '',
            references: [],
          });
        } finally {
          setIsSummaryLoading(false);
        }
      };

      fetchSummary();
    }
  }, [isOpen, node]);

  const handleGenerateExercises = async () => {
    setIsExercisesLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/learning/node-exercises`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: node.label, userId, targetScore: 8.5, difficulty: 'adaptive' }),
      });

      if (!response.ok) throw new Error('Failed to fetch exercises');
      const data = await response.json();
      setExerciseItems(data.exercises || []);
    } catch {
      setExerciseItems([]);
    } finally {
      setIsExercisesLoading(false);
    }
  };

  const handleGenerateTest = async () => {
    setIsTestLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/learning/node-test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: node.label, userId, nodeId: node.id, numQuestions: 4 })
      });
      if (!response.ok) throw new Error('Failed to fetch test');
      const data: GeneratedTest = await response.json();
      setTestData(data);
    } catch (error) {
      console.error(error);
      setTestData(null);
    } finally {
      setIsTestLoading(false);
    }
  };

  const handleMarkMastered = async () => {
    if (!userId) return;
    try {
      await updateNodeScore(userId, node.id, 85);
    } catch (error) {
      console.error('Không thể cập nhật trạng thái node', error);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl h-[80vh] flex flex-col p-0">
        <DialogHeader className="p-6 pb-4">
          <DialogTitle className="flex items-center gap-3 text-lg font-bold">
            <BrainCircuit className="w-6 h-6 text-primary" />
            {node.label}
          </DialogTitle>

          <div className="mt-2 text-sm">
            <span className="font-semibold">Mức độ thành thạo: </span>
            <span className={`font-bold px-2 py-1 rounded-lg border ${colorClass}`}>
              {rawScore > 0 ? `${rawScore}%` : "Chưa kiểm tra"}
            </span>
          </div>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6">
          <div className="prose dark:prose-invert max-w-none text-sm leading-relaxed">
            {node.description && (
              <div className="mb-4 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900">
                {node.description}
              </div>
            )}

          <h3 className="flex items-center gap-2 font-semibold text-md mb-2">
            <Sparkles className="w-5 h-5 text-yellow-500" />
            Kiến thức chi tiết
          </h3>

          {isSummaryLoading ? (
            <div className="flex items-center justify-center p-8">
              <Loader className="animate-spin" />
            </div>
          ) : (
            <div className="space-y-3">
              <ReactMarkdown>{content.overview}</ReactMarkdown>
              {content.deepDive && (
                <div className="p-3 rounded-lg bg-blue-50 border border-blue-200">
                  <p className="text-sm font-semibold text-blue-800 mb-2">Đi sâu bản chất</p>
                  <ReactMarkdown className="text-sm text-blue-900">{content.deepDive}</ReactMarkdown>
                </div>
              )}
              {content.references.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-slate-700">Tài liệu tham khảo uy tín</p>
                  <ul className="list-disc list-inside text-sm text-slate-600">
                    {content.references.map((ref, idx) => (
                      <li key={idx}>
                        <a href={ref} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                          {ref}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <Separator className="my-6" />

          <h3 className="flex items-center gap-2 font-semibold text-md mb-4">
              <PencilRuler className="w-5 h-5 text-green-500" />
              Bài tập vận dụng
            </h3>

            {isExercisesLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader className="animate-spin" />
              </div>
            ) : exerciseItems.length > 0 ? (
              <div className="space-y-3">
                {exerciseItems.map((item) => (
                  <div key={item.id} className="p-3 border rounded-lg bg-white shadow-sm">
                    <p className="font-semibold text-slate-800">{item.prompt}</p>
                    <p className="text-xs text-slate-500 mt-1">Độ khó: {item.level}</p>
                    <p className="text-xs text-slate-500">{item.rationale}</p>
                    <div className="flex flex-wrap gap-2 mt-2">
                      {item.tags.map((tag) => (
                        <span key={tag} className="text-[11px] px-2 py-1 bg-slate-100 rounded-full border">#{tag}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center text-gray-500 italic p-4">
                Nhấn nút bên dưới để tạo bài tập.
              </div>
            )}

            <Separator className="my-6" />

            <h3 className="flex items-center gap-2 font-semibold text-md mb-4">
              <PencilRuler className="w-5 h-5 text-blue-500" />
              Bài kiểm tra kiến thức
            </h3>

            {isTestLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader className="animate-spin" />
              </div>
            ) : testData ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">Phạm vi: {testData.scope} · Đạt >= {Math.round(testData.passThreshold * 100)}% sẽ chuyển node sang trạng thái đạt.</p>
                <div className="space-y-2">
                  {testData.questions.map((q) => (
                    <div key={q.id} className="p-3 border rounded-lg bg-slate-50">
                      <p className="font-semibold text-slate-800">{q.stem}</p>
                      <p className="text-xs text-slate-600 mt-1">Đáp án mẫu: {q.answer}</p>
                      <p className="text-xs text-slate-500">{q.explanation}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center text-gray-500 italic p-4">
                Sinh nhanh bài kiểm tra để đánh giá đã nắm vững node.
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="p-6 pt-4 border-t bg-background flex gap-3">
          <Link href={`/videos/${node.id}?title=${encodeURIComponent(node.label)}`}>
            <Button variant="default" className="w-full">
              <Clapperboard className="mr-2 h-4 w-4" />
              Tạo video bài giảng
            </Button>
          </Link>

          <Button onClick={handleGenerateExercises} disabled={isExercisesLoading}>
            {isExercisesLoading ? <Loader className="animate-spin mr-2" /> : <Sparkles className="mr-2" />}
            {isExercisesLoading ? "Đang tạo..." : "Tạo bài tập mới"}
          </Button>

          <Button onClick={handleGenerateTest} disabled={isTestLoading} variant="outline">
            {isTestLoading ? <Loader className="animate-spin mr-2" /> : <Sparkles className="mr-2 text-blue-500" />}
            {isTestLoading ? "Đang tạo bài kiểm tra..." : "Sinh bài kiểm tra"}
          </Button>

          <Link href={`/tests/custom-node-test?nodeId=${node.id}&title=${encodeURIComponent(node.label)}`}>
            <Button variant="secondary" className="w-full">
              🎯 Làm bài kiểm tra
            </Button>
          </Link>

          {testData && (
            <Button variant="ghost" className="w-full" onClick={handleMarkMastered}>
              ✅ Đánh dấu đã đạt (>=80%)
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
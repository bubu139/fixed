"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  UploadCloud,
  Database,
  Sparkles,
  ShieldCheck,
  FileText,
  CheckCircle2,
  Bot,
  FileSignature,
  AlertCircle,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useSupabase } from "@/supabase";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

const STORAGE_BUCKET = "mathmentor-materials";
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Visibility = "private" | "shared";
type UploadPurpose = "chat" | "test";

interface DocumentRecord {
  id: string;
  file_name: string;
  rag_status: string;
  created_at: string;
  source_path: string;
  mime_type?: string | null;
  chunk_count?: number | null;
  visibility?: Visibility | null;
}

const statusVariant: Record<string, { label: string; className: string }> = {
  ready: { label: "Sẵn sàng", className: "bg-emerald-100 text-emerald-700" },
  uploaded: { label: "Đã tải lên", className: "bg-blue-100 text-blue-700" },
  processing: { label: "Đang xử lý", className: "bg-amber-100 text-amber-700" },
  failed: { label: "Lỗi", className: "bg-red-100 text-red-700" },
};

const sanitizeFileName = (fileName: string): string => {
  const dotIndex = fileName.lastIndexOf(".");
  const name = dotIndex > -1 ? fileName.slice(0, dotIndex) : fileName;
  const extension = dotIndex > -1 ? fileName.slice(dotIndex) : "";

  let sanitized = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D");

  sanitized = sanitized
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");

  if (!sanitized) {
    sanitized = `file-${Date.now()}`;
  }

  return `${sanitized}${extension}`;
};

export default function LibraryPage() {
  const { client, user, isInitialized } = useSupabase();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [testMaterials, setTestMaterials] = useState<DocumentRecord[]>([]);

  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadVisibility, setUploadVisibility] =
    useState<Visibility>("private");
  const [uploadPurpose, setUploadPurpose] =
    useState<UploadPurpose>("chat");

  const fetchChatDocuments = useCallback(async () => {
    if (!client || !user) return;

    try {
      const { data, error } = await client
        .from("user_documents")
        .select(
          "id, file_name, rag_status, created_at, source_path, mime_type, chunk_count, visibility",
        )
        .eq("user_id", user.id)
        .order("created_at", { ascending: false });

      if (!error && data) {
        setDocuments(data as DocumentRecord[]);
      } else if (error) {
        console.error("Error fetching documents:", error);
      }
    } catch (err) {
      console.error("Unexpected error fetching documents:", err);
    }
  }, [client, user]);

  const fetchTestMaterials = useCallback(async () => {
    if (!client || !user) return;

    try {
      const { data, error } = await client
        .from("test_materials")
        .select(
          "id, file_name, rag_status, created_at, source_path, mime_type, chunk_count, visibility",
        )
        .eq("user_id", user.id)
        .order("created_at", { ascending: false });

      if (!error && data) {
        setTestMaterials(data as DocumentRecord[]);
      } else if (error) {
        console.error("Error fetching test materials:", error);
      }
    } catch (err) {
      console.error("Unexpected error fetching test materials:", err);
    }
  }, [client, user]);

  useEffect(() => {
    void fetchChatDocuments();
    void fetchTestMaterials();
  }, [fetchChatDocuments, fetchTestMaterials]);

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    if (!client || !user) {
      setErrorMessage("Vui lòng đăng nhập để tải tài liệu.");
      return;
    }

    const files = event.target.files;
    if (!files || files.length === 0) return;

    const MAX_FILE_SIZE = 50 * 1024 * 1024;
    const ALLOWED_TYPES = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/msword",
      "text/plain",
    ];

    for (const file of Array.from(files)) {
      if (file.size > MAX_FILE_SIZE) {
        setErrorMessage(
          `File "${file.name}" vượt quá 50MB. Vui lòng chọn file nhỏ hơn.`,
        );
        event.target.value = "";
        return;
      }

      const hasValidExtension = /\.(pdf|docx|doc|txt)$/i.test(file.name);
      const hasValidMimeType = ALLOWED_TYPES.includes(file.type);

      if (!hasValidExtension && !hasValidMimeType) {
        setErrorMessage(
          `File "${file.name}" không được hỗ trợ. Chỉ chấp nhận: PDF, DOCX, DOC, TXT`,
        );
        event.target.value = "";
        return;
      }
    }

    setUploading(true);
    setUploadProgress(0);
    setStatusMessage(`Đang chuẩn bị tải ${files.length} tệp...`);
    setErrorMessage(null);

    try {
      const isChatUpload = uploadPurpose === "chat";
      const metadataTable = isChatUpload ? "user_documents" : "test_materials";

      let successCount = 0;
      const errorMessages: string[] = [];
      const totalFiles = files.length;

      for (let i = 0; i < totalFiles; i++) {
        const file = files[i];
        const sanitizedName = sanitizeFileName(file.name);
        const timestamp = Date.now();
        const storagePath = `${user.id}/${timestamp}-${sanitizedName}`;

        setStatusMessage(
          `Đang tải ${file.name}... (${i + 1}/${totalFiles})`,
        );
        setUploadProgress(((i + 0.3) / totalFiles) * 100);

        try {
          // 1. Upload vào Supabase Storage
          console.log(`📤 Uploading to storage: ${storagePath}`);
          const { data: uploadData, error: uploadError } = await client.storage
            .from(STORAGE_BUCKET)
            .upload(storagePath, file, {
              cacheControl: "3600",
              upsert: false,
              contentType: file.type || "application/octet-stream",
            });

          if (uploadError) {
            console.error("Supabase storage upload error:", uploadError);
            throw new Error(`Storage upload failed: ${uploadError.message}`);
          }

          console.log("✅ Storage upload success:", uploadData);
          setUploadProgress(((i + 0.5) / totalFiles) * 100);

          // 2. Insert metadata
          const insertPayload = {
            user_id: user.id,
            file_name: file.name,
            file_size: file.size,
            mime_type: file.type || "application/octet-stream",
            source_path: storagePath,
            rag_status: "uploaded",
            visibility: uploadVisibility,
          };

          console.log("📝 Inserting metadata:", insertPayload);
          const { data: metadata, error: insertError } = await client
            .from(metadataTable)
            .insert(insertPayload)
            .select("id")
            .single();

          if (insertError || !metadata?.id) {
            console.error("Supabase metadata insert error:", insertError);
            throw new Error(
              `Metadata insert failed: ${
                insertError?.message || "Unknown error"
              }`,
            );
          }

          console.log(`✅ Metadata created: ${metadata.id}`);
          setUploadProgress(((i + 0.7) / totalFiles) * 100);

          // 3. Gọi API backend để xử lý RAG
          console.log(`🤖 Triggering RAG processing for ${metadata.id}`);
          const processResponse = await fetch(
            `${API_BASE_URL}/api/process-document`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                userId: user.id,
                documentId: String(metadata.id), // 👈 ép sang string
                purpose: uploadPurpose,
              }),
            },
          );

          if (!processResponse.ok) {
            let errorDetail: string = `HTTP ${processResponse.status}`;
            try {
              const errorData = await processResponse.json();
              if (errorData?.detail !== undefined) {
                if (typeof errorData.detail === "string") {
                  errorDetail = errorData.detail;
                } else {
                  errorDetail = JSON.stringify(errorData.detail);
                }
              } else {
                errorDetail = JSON.stringify(errorData);
              }
            } catch {
              try {
                errorDetail = await processResponse.text();
              } catch {
                // giữ default
              }
            }
            throw new Error(`RAG processing failed: ${errorDetail}`);
          }

          const result = await processResponse.json();
          console.log("✅ RAG processed:", result);

          successCount += 1;
          setUploadProgress(((i + 1) / totalFiles) * 100);
        } catch (fileError) {
          const message =
            fileError instanceof Error ? fileError.message : String(fileError);
          console.error(`❌ Error processing ${file.name}:`, message);
          errorMessages.push(`${file.name}: ${message}`);

          // Cleanup: xóa file khỏi storage nếu có lỗi
          try {
            await client.storage
              .from(STORAGE_BUCKET)
              .remove([storagePath]);
            console.log(`🧹 Cleaned up failed upload: ${storagePath}`);
          } catch (cleanupError) {
            console.warn(
              `Warning: Could not cleanup ${storagePath}`,
              cleanupError,
            );
          }
        }
      }

      // Refresh lists
      console.log("🔄 Refreshing document lists...");
      await Promise.all([fetchChatDocuments(), fetchTestMaterials()]);
      event.target.value = "";

      // Status tổng
      if (successCount > 0) {
        setStatusMessage(
          `✅ Đã xử lý thành công ${successCount}/${totalFiles} tệp.`,
        );
        setUploadProgress(100);
      }

      if (errorMessages.length > 0) {
        setErrorMessage(`Một số file gặp lỗi:\n${errorMessages.join("\n")}`);
      } else if (successCount === 0) {
        setErrorMessage("Không có file nào được xử lý thành công.");
      } else {
        setErrorMessage(null);
      }
    } catch (err) {
      console.error("❌ Upload error:", err);
      const message = err instanceof Error ? err.message : String(err);
      setErrorMessage(`Có lỗi xảy ra: ${message}`);
    } finally {
      setUploading(false);
      setTimeout(() => setUploadProgress(0), 2000);
    }
  };

  const helperText = useMemo(() => {
    if (!user && isInitialized) {
      return "Đăng nhập để đồng bộ tài liệu với tài khoản MathMentor.";
    }
    if (!client && isInitialized) {
      return "Không thể kết nối Supabase. Kiểm tra lại biến môi trường.";
    }
    return null;
  }, [client, user, isInitialized]);

  const renderDocumentList = (docList: DocumentRecord[]) => {
    if (docList.length === 0) {
      return (
        <div className="text-center py-8 text-muted-foreground">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-sm">Chưa có tài liệu nào.</p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        {docList.map((doc) => {
          const variant =
            statusVariant[doc.rag_status] ?? statusVariant.uploaded;
          const isShared = doc.visibility === "shared";

          return (
            <div
              key={doc.id}
              className="p-4 border rounded-lg flex flex-wrap items-start gap-4 justify-between hover:bg-accent/50 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <p className="font-medium truncate">{doc.file_name}</p>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    📅 {new Date(doc.created_at).toLocaleString("vi-VN")}
                  </span>
                  {doc.chunk_count ? (
                    <span>📦 {doc.chunk_count} chunks</span>
                  ) : null}
                  <span>{isShared ? "🌐 Kho chung" : "🔒 Riêng tư"}</span>
                </div>

                <p className="text-xs text-muted-foreground mt-1 truncate">
                  <code className="text-[10px]">{doc.source_path}</code>
                </p>
              </div>

              <div className="flex flex-col items-end gap-2">
                <Badge className={variant.className}>{variant.label}</Badge>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <main className="p-4 md:p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <section className="space-y-3">
        <Badge variant="outline" className="w-fit">
          <Database className="w-3 h-3 mr-1" />
          Kho tài liệu RAG
        </Badge>
        <h1 className="text-3xl md:text-4xl font-bold">
          Tải lên và lập chỉ mục tài liệu
        </h1>
        <p className="text-muted-foreground max-w-3xl">
          Tải lên tài liệu PDF, DOCX... Hệ thống sẽ tự động cắt nhỏ và lập chỉ
          mục để AI Chat và AI Sinh Đề Thi có thể sử dụng.
        </p>
        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-primary" />
            Đồng bộ thời gian thực
          </div>
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-primary" />
            Lưu trữ trên Supabase
          </div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            Sẵn sàng cho AI
          </div>
        </div>
      </section>

      {/* Upload card */}
      <Card>
        <CardHeader>
          <CardTitle>Tải tài liệu mới</CardTitle>
          <CardDescription>
            Chọn mục đích tải lên, chế độ chia sẻ, sau đó chọn tệp của bạn.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Purpose */}
          <div className="space-y-3">
            <Label className="font-medium">Mục đích tải lên</Label>
            <RadioGroup
              value={uploadPurpose}
              onValueChange={(val) =>
                setUploadPurpose(val as UploadPurpose)
              }
              className="flex gap-4"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="chat" id="r-chat" />
                <Label
                  htmlFor="r-chat"
                  className="cursor-pointer flex items-center gap-2"
                >
                  <Bot className="w-4 h-4" /> Cho AI Chat
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="test" id="r-test" />
                <Label
                  htmlFor="r-test"
                  className="cursor-pointer flex items-center gap-2"
                >
                  <FileSignature className="w-4 h-4" /> Cho Sinh Đề Thi
                </Label>
              </div>
            </RadioGroup>
          </div>

          {/* Visibility */}
          <div className="flex items-start justify-between gap-4 p-4 rounded-lg border bg-muted/50">
            <div>
              <p className="font-medium text-sm">Chế độ chia sẻ</p>
              <p className="text-xs text-muted-foreground mt-1">
                Bật <strong>Kho chung</strong> nếu bạn muốn tài liệu này được
                dùng cho tất cả học sinh.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Riêng tư</span>
              <Switch
                checked={uploadVisibility === "shared"}
                onCheckedChange={(checked) =>
                  setUploadVisibility(checked ? "shared" : "private")
                }
              />
              <span className="text-xs text-muted-foreground">Kho chung</span>
            </div>
          </div>

          {/* File input */}
          <div className="space-y-2">
            <Label htmlFor="file-upload">Chọn tệp</Label>
            <Input
              id="file-upload"
              type="file"
              accept=".pdf,.doc,.docx,.txt"
              disabled={uploading || !client || !user}
              onChange={handleFileChange}
              multiple
              className="cursor-pointer"
            />
            {helperText && (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{helperText}</AlertDescription>
              </Alert>
            )}
          </div>

          {/* Progress */}
          {uploading && (
            <div className="space-y-2">
              <Progress value={uploadProgress} className="h-2" />
              <p className="text-sm text-muted-foreground flex items-center gap-2">
                <span className="animate-pulse">⏳</span>
                {statusMessage ?? "Đang xử lý..."}
              </p>
            </div>
          )}

          {/* Success */}
          {!uploading && statusMessage && (
            <Alert className="border-emerald-200 bg-emerald-50">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <AlertDescription className="text-emerald-700">
                {statusMessage}
              </AlertDescription>
            </Alert>
          )}

          {/* Error */}
          {errorMessage && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="whitespace-pre-line">
                {errorMessage}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Lists */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="w-5 h-5" />
            Danh sách tài liệu AI Chat
          </CardTitle>
          <CardDescription>
            Những tài liệu này sẽ được dùng khi bạn trò chuyện với AI.
          </CardDescription>
        </CardHeader>
        <CardContent>{renderDocumentList(documents)}</CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSignature className="w-5 h-5" />
            Danh sách Đề mẫu (Sinh bài kiểm tra)
          </CardTitle>
          <CardDescription>
            Những tài liệu này sẽ được dùng làm RAG khi AI tạo bài kiểm tra.
          </CardDescription>
        </CardHeader>
        <CardContent>{renderDocumentList(testMaterials)}</CardContent>
      </Card>
    </main>
  );
}

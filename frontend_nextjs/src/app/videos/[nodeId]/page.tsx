"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import {
  Gauge,
  Loader2,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from "lucide-react";

type SegmentState = {
  index: number;
  start: number;
  end: number;
  status: "ready" | "generating" | "pending";
  videoUrl?: string;
};

const DEMO_VIDEO_URL = "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4";

export default function LectureVideoPage() {
  const params = useParams<{ nodeId: string }>();
  const searchParams = useSearchParams();
  const topicTitle = searchParams.get("title") ?? "Bài giảng";

  const [segments, setSegments] = useState<SegmentState[]>([
    { index: 0, start: 0, end: 30, status: "ready", videoUrl: DEMO_VIDEO_URL },
    { index: 1, start: 30, end: 60, status: "pending" },
  ]);
  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playback, setPlayback] = useState({
    isPlaying: false,
    volume: 0.8,
    rate: 1,
    progress: 0,
    duration: 30,
  });

  const currentSegment = useMemo(() => segments[currentSegmentIndex], [segments, currentSegmentIndex]);
  const nextSegment = segments[currentSegmentIndex + 1];

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !currentSegment?.videoUrl) return;

    video.src = currentSegment.videoUrl;
    video.currentTime = 0;
    video.playbackRate = playback.rate;
    video.volume = playback.volume;
    setPlayback((state) => ({ ...state, progress: 0 }));

    if (playback.isPlaying) {
      void video.play();
    }
  }, [currentSegment?.videoUrl, currentSegmentIndex, playback.isPlaying, playback.rate, playback.volume]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = playback.volume;
  }, [playback.volume]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = playback.rate;
  }, [playback.rate]);

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;

    const duration = video.duration || currentSegment.end - currentSegment.start;
    setPlayback((state) => ({ ...state, progress: video.currentTime, duration }));

    if (nextSegment && nextSegment.status === "pending" && video.currentTime >= 20) {
      startGeneratingNext(currentSegmentIndex + 1);
    }
  };

  const startGeneratingNext = (segmentIndex: number) => {
    setSegments((prev) => {
      const target = prev[segmentIndex];
      if (!target || target.status !== "pending") return prev;
      const updated = [...prev];
      updated[segmentIndex] = { ...target, status: "generating" };
      return updated;
    });

    setTimeout(() => {
      setSegments((prev) => {
        const updated = [...prev];
        const target = updated[segmentIndex];
        if (!target) return prev;

        updated[segmentIndex] = {
          ...target,
          status: "ready",
          videoUrl: DEMO_VIDEO_URL,
        };

        if (!updated[segmentIndex + 1]) {
          updated.push({
            index: segmentIndex + 1,
            start: target.end,
            end: target.end + 30,
            status: "pending",
          });
        }

        return updated;
      });
    }, 1200);
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;

    if (playback.isPlaying) {
      video.pause();
      setPlayback((state) => ({ ...state, isPlaying: false }));
    } else {
      void video.play();
      setPlayback((state) => ({ ...state, isPlaying: true }));
    }
  };

  const seek = (delta: number) => {
    const video = videoRef.current;
    if (!video) return;

    const duration = video.duration || currentSegment.end - currentSegment.start;
    const nextTime = Math.min(Math.max(0, video.currentTime + delta), duration);
    video.currentTime = nextTime;
    setPlayback((state) => ({ ...state, progress: nextTime, duration }));
  };

  const handleSegmentEnd = () => {
    const video = videoRef.current;
    const readyNext = segments[currentSegmentIndex + 1];

    if (readyNext?.videoUrl) {
      setCurrentSegmentIndex((index) => index + 1);
      setPlayback((state) => ({ ...state, progress: 0 }));
      return;
    }

    if (video) {
      video.pause();
      video.currentTime = video.duration;
      setPlayback((state) => ({ ...state, isPlaying: false }));
    }
  };

  const changeVolume = (value: number) => {
    const video = videoRef.current;
    if (!video) return;
    const normalized = Math.min(Math.max(value, 0), 1);
    video.volume = normalized;
    setPlayback((state) => ({ ...state, volume: normalized }));
  };

  const changeRate = (rate: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = rate;
    setPlayback((state) => ({ ...state, rate }));
  };

  const progressPercent = playback.duration
    ? Math.min(100, (playback.progress / playback.duration) * 100)
    : 0;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Node #{params.nodeId}</p>
          <h1 className="text-2xl font-bold">{topicTitle}</h1>
          <p className="text-muted-foreground">
            Video bài giảng được chia thành các đoạn 30 giây. Hệ thống sẽ tạo sẵn đoạn đầu, và tự động
            chuẩn bị đoạn tiếp theo khi bạn xem gần hết.
          </p>
        </div>
        <Badge variant="secondary" className="self-start">Bản demo</Badge>
      </div>

      <Card className="overflow-hidden border shadow-lg">
        <CardHeader className="bg-gradient-to-r from-indigo-50 to-white">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="text-xl">Trình phát bài giảng</CardTitle>
              <CardDescription>Điều khiển phát, tua nhanh/chậm, âm lượng và tốc độ.</CardDescription>
            </div>
            <Badge className="bg-indigo-100 text-indigo-700 hover:bg-indigo-100">30s/segment</Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-4 p-6">
          <div className="relative overflow-hidden rounded-xl border bg-black/5">
            <video
              ref={videoRef}
              className="aspect-video h-full w-full bg-black"
              onTimeUpdate={handleTimeUpdate}
              onEnded={handleSegmentEnd}
              preload="metadata"
            />
            <div className="absolute left-4 top-4 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-xs text-white">
              <Gauge className="h-4 w-4" />
              Đoạn {currentSegment?.index ?? 0} ({currentSegment?.start}s - {currentSegment?.end}s)
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{progressPercent.toFixed(0)}% đoạn hiện tại</span>
              <span>
                {currentSegment.start + Math.round(playback.progress)}s / {currentSegment.end}s tổng
              </span>
            </div>
            <Progress value={progressPercent} />
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg bg-muted/50 p-4">
            <Button size="icon" variant="secondary" onClick={() => seek(-5)}>
              <SkipBack className="h-5 w-5" />
            </Button>

            <Button size="lg" onClick={togglePlay} className="min-w-[140px] justify-center gap-2">
              {playback.isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
              {playback.isPlaying ? "Dừng" : "Phát"}
            </Button>

            <Button size="icon" variant="secondary" onClick={() => seek(5)}>
              <SkipForward className="h-5 w-5" />
            </Button>

            <Separator orientation="vertical" className="h-8" />

            <div className="flex flex-1 items-center gap-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                {playback.volume === 0 ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                Âm lượng
              </div>
              <Slider
                className="max-w-sm"
                value={[playback.volume]}
                min={0}
                max={1}
                step={0.05}
                onValueChange={(values) => changeVolume(values[0])}
              />
            </div>

            <Separator orientation="vertical" className="h-8" />

            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">Tốc độ:</span>
              {[0.75, 1, 1.25, 1.5].map((rate) => (
                <Button
                  key={rate}
                  size="sm"
                  variant={playback.rate === rate ? "default" : "outline"}
                  onClick={() => changeRate(rate)}
                >
                  {rate}x
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-2 rounded-lg border p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Tiến trình đoạn video</h3>
              <p className="text-xs text-muted-foreground">Tự động chuẩn bị đoạn tiếp theo khi xem được 20s</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {segments.map((segment) => (
                <Badge
                  key={segment.index}
                  variant={
                    segment.status === "ready"
                      ? segment.index === currentSegmentIndex
                        ? "default"
                        : "secondary"
                      : "outline"
                  }
                  className="flex items-center gap-2"
                >
                  Đoạn {segment.index}: {segment.start}s-{segment.end}s
                  {segment.status === "generating" && <Loader2 className="h-3 w-3 animate-spin" />}
                  {segment.status === "pending" && <span className="text-[11px] text-muted-foreground">chờ</span>}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Gợi ý triển khai thực tế</CardTitle>
          <CardDescription>
            Liên kết API backend để tạo video theo node, trả về segment đầu tiên và cung cấp URL khi hoàn tất.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Khi người dùng click "Tạo video bài giảng", frontend gọi API tạo video (segment 0–30s). Khi xem được
            20s của đoạn hiện tại, frontend gửi yêu cầu tạo/gửi tiếp segment tiếp theo để phát nối tiếp.
          </p>
          <p>
            Trang phát hỗ trợ tua ±5s, điều chỉnh âm lượng, tốc độ 0.75–1.5x và hiển thị trạng thái từng đoạn để
            phù hợp với luồng sinh video nền.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

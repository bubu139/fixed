// Ưu tiên NEXT_PUBLIC_API_BASE_URL; nếu chưa đặt sẽ rơi về NEXT_PUBLIC_API_URL hoặc localhost để tránh crash
const FALLBACK_API_BASE_URL = 'http://localhost:8000';
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  FALLBACK_API_BASE_URL;

import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
// ... (hàm 'cn' của bạn)


// Ưu tiên biến môi trường, nếu không có thì dùng link Render cứng
// lib/utils.ts
const FALLBACK_API_BASE_URL = 'http://localhost:8000';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  FALLBACK_API_BASE_URL;

export const getApiBaseUrl = () => {
  if (
    !process.env.NEXT_PUBLIC_API_BASE_URL &&
    !process.env.NEXT_PUBLIC_API_URL
  ) {
    console.warn(
      '[MathMentor] API base URL is not configured. Falling back to http://localhost:8000. Set NEXT_PUBLIC_API_BASE_URL to silence this warning.'
    );
  }

  return API_BASE_URL;
};


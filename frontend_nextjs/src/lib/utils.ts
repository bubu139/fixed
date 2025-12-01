import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const envApiUrl = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
if (!envApiUrl) {
  console.warn("⚠️ NEXT_PUBLIC_API_URL is not set. Falling back to http://localhost:8000");
}

export const API_URL = envApiUrl || "http://localhost:8000";

export function getApiUrl(path: string) {
  return `${API_URL}${path}`;
}

// API base URL configuration
const envApiUrl = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
export const API_URL = envApiUrl || "http://localhost:8000";

if (!envApiUrl) {
  console.warn("⚠️ NEXT_PUBLIC_API_URL is not set. Falling back to http://localhost:8000");
}

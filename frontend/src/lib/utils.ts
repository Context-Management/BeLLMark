import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format a date string as local ISO datetime: "YYYY-MM-DD HH:MM:SS" */
export function formatISODateTime(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Extract short host label from a base_url, e.g. "http://mini.local:1234/v1/..." → "mini.local" */
export function getHostLabel(baseUrl: string): string | null {
  try {
    const host = new URL(baseUrl).hostname;
    if (host === 'localhost' || host === '127.0.0.1') return null;
    return host;
  } catch {
    return null;
  }
}

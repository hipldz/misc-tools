import { t } from "./i18n.js";

const base = document.querySelector('meta[name="app-base-path"]').content;
export class ApiError extends Error {
  constructor(message, data = {}) {
    super(message);
    this.data = data;
  }
}
export async function request(
  path,
  { method = "GET", body, signal, timeout = 45000, raw = false } = {},
) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = timeout > 0 ? setTimeout(abort, timeout) : null;
  const form = body instanceof FormData;
  try {
    const response = await fetch(`${base}${path}`, {
      method,
      signal: controller.signal,
      cache: "no-store",
      headers: body && !form ? { "Content-Type": "application/json" } : {},
      body: body ? (form ? body : JSON.stringify(body)) : undefined,
    });
    if (raw && response.ok) return await response.blob();
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
      throw new ApiError(
        data.detail ||
          data.result?.stderr ||
          data.result?.stdout ||
          data.stderr ||
          (response.status === 401 ? t("unauthorized") : t("requestFailed")),
        data,
      );
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError" && !signal?.aborted)
      throw new ApiError(t("timeout"));
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
export const post = (path, body = {}) =>
  request(path, { method: "POST", body });

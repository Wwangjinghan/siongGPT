const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api/v1";

interface ApiErrorBody {
  detail?: unknown;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    let message = "Request failed";

    try {
      const data = (await response.json()) as ApiErrorBody;
      if (typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      // The fallback message is used when the response has no JSON body.
    }

    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
}

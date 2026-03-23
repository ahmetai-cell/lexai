const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  private headers(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    return headers;
  }

  async get<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: this.headers(),
    });
    if (!res.ok) throw await this.handleError(res);
    return res.json();
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw await this.handleError(res);
    return res.json();
  }

  async delete(path: string): Promise<void> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      headers: this.headers(),
    });
    if (!res.ok) throw await this.handleError(res);
  }

  async uploadFile(path: string, file: File): Promise<unknown> {
    const formData = new FormData();
    formData.append("file", file);
    const headers: Record<string, string> = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: formData,
    });
    if (!res.ok) throw await this.handleError(res);
    return res.json();
  }

  streamChat(
    sessionId: string,
    body: { query: string; template_slug: string; document_ids?: string[] },
    onToken: (token: string) => void,
    onDone: () => void,
  ): EventSource {
    const url = new URL(`${API_BASE}/api/v1/chat/sessions/${sessionId}/messages`);
    // Not: EventSource doesn't support custom headers; use POST with fetch streams instead
    const controller = new AbortController();

    fetch(url.toString(), {
      method: "POST",
      headers: { ...this.headers() },
      body: JSON.stringify({ ...body, stream: true }),
      signal: controller.signal,
    }).then(async (res) => {
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;
      while (true) {
        const { done, value } = await reader.read();
        if (done) { onDone(); break; }
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") { onDone(); return; }
            onToken(data);
          }
        }
      }
    });

    return { close: () => controller.abort() } as unknown as EventSource;
  }

  private async handleError(res: Response): Promise<Error> {
    try {
      const data = await res.json();
      return new Error(data?.error?.message || "Bilinmeyen hata");
    } catch {
      return new Error(`HTTP ${res.status}`);
    }
  }
}

export const apiClient = new ApiClient();

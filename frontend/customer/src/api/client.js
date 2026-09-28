// Empty is intentional for Docker: Nginx proxies the same-origin /api path.
const baseUrl = import.meta.env?.VITE_API_BASE_URL || "";

export class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
export const apiUrl = (path) => `${baseUrl}/api/v1${path}`;

export async function request(path, { token, method = "GET", body } = {}) {
  const response = await fetch(apiUrl(path), { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.detail || "We could not complete that request.", response.status);
  return data;
}

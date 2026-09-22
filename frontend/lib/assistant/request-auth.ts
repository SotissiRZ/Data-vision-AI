export function assistantAuthHeaders(
  extra: Record<string, string> = {},
): Record<string, string> {
  if (typeof window === "undefined") return { ...extra };

  const token = window.sessionStorage.getItem("dv_enterprise_token") || "";
  const workspace =
    window.localStorage.getItem("dv_enterprise_workspace") || "";

  const headers: Record<string, string> = { ...extra };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (workspace) headers["X-Workspace-ID"] = workspace;
  return headers;
}

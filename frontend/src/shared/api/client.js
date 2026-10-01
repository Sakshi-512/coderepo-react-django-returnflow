const baseUrl = import.meta.env.VITE_API_URL || "/api/v1";
let sessionToken = localStorage.getItem("returnflow-session-token") || "";

export function setSessionToken(token) {
    sessionToken = token || "";
    if (sessionToken) localStorage.setItem("returnflow-session-token", sessionToken);
    else localStorage.removeItem("returnflow-session-token");
}

export const hasSessionToken = () => Boolean(sessionToken);

export async function request(path, options = {}) {
    const response = await fetch(`${baseUrl}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
            ...options.headers,
        },
    });

    if (response.status === 204) return null;

    const contentType = response.headers?.get?.("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;

    if (!response.ok) {
        const code = payload?.error?.code;
        const message = payload?.error?.message || `ReturnFlow service returned ${response.status}.`;

        if (response.status === 401 && ["AUTH_REQUIRED", "INVALID_TOKEN", "ACCOUNT_UNAVAILABLE"].includes(code)) {
            setSessionToken("");
            window.dispatchEvent(new CustomEvent("returnflow-session-expired", { detail: message }));
        }

        const error = new Error(message);
        error.code = code;
        error.details = payload?.error?.details;
        error.status = response.status;
        throw error;
    }

    if (!payload || !("data" in payload)) throw new Error("ReturnFlow service returned an invalid response.");

    return payload.data;
}

import { request } from "../../shared/api/client.js";

export const authApi = {
    login: (email, password) => request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
    session: () => request("/auth/session"),
    logout: () => request("/auth/logout", { method: "POST" }),
};

import { request } from "../../shared/api/client.js";

function toQueryString(params) {
    const entries = Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== "" && value !== null);

    if (!entries.length) return "";

    return `?${new URLSearchParams(entries).toString()}`;
}

export const returnsApi = {
    list: (params) => request(`/return-requests${toQueryString(params)}`),
    get: (id) => request(`/return-requests/${id}`),
    submit: (body) => request("/return-requests", { method: "POST", body: JSON.stringify(body) }),
    cancel: (id) => request(`/return-requests/${id}/cancel`, { method: "POST" }),
    approve: (id) => request(`/return-requests/${id}/approve`, { method: "POST" }),
    reject: (id, body) => request(`/return-requests/${id}/reject`, { method: "POST", body: JSON.stringify(body) }),
    receive: (id) => request(`/return-requests/${id}/receive`, { method: "POST" }),
    inspect: (id, body) => request(`/return-requests/${id}/inspect`, { method: "POST", body: JSON.stringify(body) }),
    refundAttempt: (id) => request(`/return-requests/${id}/refund/attempt`, { method: "POST" }),
    refundRetry: (id) => request(`/return-requests/${id}/refund/retry`, { method: "POST" }),
    refundHistory: (id) => request(`/return-requests/${id}/refund`),
    exchangeRetry: (id) => request(`/return-requests/${id}/exchange/retry-reservation`, { method: "POST" }),
    reservation: (id) => request(`/return-requests/${id}/reservation`),
};

export const ordersApi = {
    list: (params) => request(`/orders${toQueryString(params)}`),
};

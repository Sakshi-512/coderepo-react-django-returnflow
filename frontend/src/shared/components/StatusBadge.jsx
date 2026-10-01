const LABELS = {
    REQUESTED: "Requested",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    CANCELLED: "Cancelled",
    ITEM_RECEIVED: "Item received",
    INSPECTED: "Inspected",
    REFUND_PROCESSING: "Refund processing",
    REFUND_FAILED: "Refund failed",
    EXCHANGE_RESERVING: "Reserving exchange",
    EXCHANGE_AWAITING_INVENTORY: "Awaiting inventory",
    COMPLETED: "Completed",
};

const TONES = {
    REQUESTED: "info",
    APPROVED: "info",
    ITEM_RECEIVED: "info",
    INSPECTED: "info",
    REFUND_PROCESSING: "pending",
    EXCHANGE_RESERVING: "pending",
    EXCHANGE_AWAITING_INVENTORY: "warning",
    REFUND_FAILED: "danger",
    REJECTED: "danger",
    CANCELLED: "neutral",
    COMPLETED: "success",
};

export function StatusBadge({ status }) {
    const tone = TONES[status] || "neutral";

    return <span className={`status-badge status-badge--${tone}`}>{LABELS[status] || status}</span>;
}

import { useEffect, useState } from "react";
import { ErrorBanner } from "../../shared/components/ErrorBanner.jsx";
import { StatusBadge } from "../../shared/components/StatusBadge.jsx";
import { formatDateTime, humanize } from "../../shared/utils/format.js";
import { returnsApi } from "../returns/returns.api.js";

const STATUS_OPTIONS = [
    "REQUESTED",
    "APPROVED",
    "ITEM_RECEIVED",
    "INSPECTED",
    "REFUND_PROCESSING",
    "REFUND_FAILED",
    "EXCHANGE_RESERVING",
    "EXCHANGE_AWAITING_INVENTORY",
    "COMPLETED",
    "REJECTED",
    "CANCELLED",
];

export function ReturnsQueue({ account, onSelect, refreshKey }) {
    const [filters, setFilters] = useState({ status: "", resolutionType: "", customerEmail: "", orderId: "" });
    const [page, setPage] = useState(1);
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");

    const load = async () => {
        try {
            setError("");
            setResult(await returnsApi.list({ ...filters, page, pageSize: 20 }));
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters, page, refreshKey]);

    const updateFilter = (key, value) => {
        setPage(1);
        setFilters((current) => ({ ...current, [key]: value }));
    };

    const totalPages = result ? Math.max(1, Math.ceil(result.total / 20)) : 1;

    return (
        <main className="page">
            <header className="page-header">
                <h1>Operations queue</h1>
                <span className="muted">Signed in as {account.name} ({account.role})</span>
            </header>

            <form className="queue-filters" onSubmit={(event) => event.preventDefault()}>
                <div className="filter-field">
                    <label htmlFor="statusFilter">Status</label>
                    <select id="statusFilter" value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}>
                        <option value="">All statuses</option>
                        {STATUS_OPTIONS.map((status) => (
                            <option key={status} value={status}>
                                {humanize(status)}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="filter-field">
                    <label htmlFor="resolutionFilter">Resolution</label>
                    <select
                        id="resolutionFilter"
                        value={filters.resolutionType}
                        onChange={(event) => updateFilter("resolutionType", event.target.value)}
                    >
                        <option value="">All</option>
                        <option value="refund">Refund</option>
                        <option value="exchange">Exchange</option>
                    </select>
                </div>

                <div className="filter-field">
                    <label htmlFor="customerEmailFilter">Customer email</label>
                    <input
                        id="customerEmailFilter"
                        type="email"
                        value={filters.customerEmail}
                        onChange={(event) => updateFilter("customerEmail", event.target.value)}
                    />
                </div>

                <div className="filter-field">
                    <label htmlFor="orderIdFilter">Order ID</label>
                    <input id="orderIdFilter" type="text" value={filters.orderId} onChange={(event) => updateFilter("orderId", event.target.value)} />
                </div>
            </form>

            <ErrorBanner message={error} onRetry={load} />

            {result === null && !error && <p className="loading-state" role="status">Loading queue...</p>}

            {result && result.items.length === 0 && (
                <div className="empty-state">
                    <h2>No returns match these filters</h2>
                    <p>Try widening your filters.</p>
                </div>
            )}

            {result && result.items.length > 0 && (
                <>
                    <table className="queue-table">
                        <thead>
                            <tr>
                                <th>SKU</th>
                                <th>Status</th>
                                <th>Reason</th>
                                <th>Resolution</th>
                                <th>Submitted</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.items.map((item) => (
                                <tr
                                    key={item._id}
                                    tabIndex={0}
                                    role="button"
                                    aria-label={`Open return for ${item.sku}, status ${humanize(item.status)}`}
                                    onClick={() => onSelect(item._id)}
                                    onKeyDown={(event) => event.key === "Enter" && onSelect(item._id)}
                                >
                                    <td>{item.sku}</td>
                                    <td>
                                        <StatusBadge status={item.status} />
                                    </td>
                                    <td>{humanize(item.reason)}</td>
                                    <td>{humanize(item.resolutionType)}</td>
                                    <td>{formatDateTime(item.createdAt)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    <div className="pagination">
                        <button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
                            Previous
                        </button>
                        <span>
                            Page {page} of {totalPages}
                        </span>
                        <button type="button" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>
                            Next
                        </button>
                    </div>
                </>
            )}
        </main>
    );
}

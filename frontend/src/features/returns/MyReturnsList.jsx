import { useEffect, useState } from "react";
import { ErrorBanner } from "../../shared/components/ErrorBanner.jsx";
import { StatusBadge } from "../../shared/components/StatusBadge.jsx";
import { formatDateTime } from "../../shared/utils/format.js";
import { returnsApi } from "./returns.api.js";

export function MyReturnsList({ onSelect, onCreate, refreshKey }) {
    const [items, setItems] = useState(null);
    const [error, setError] = useState("");

    const load = async () => {
        try {
            setError("");
            const page = await returnsApi.list({});
            setItems(page.items);
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [refreshKey]);

    return (
        <main className="page">
            <header className="page-header">
                <h1>My returns</h1>
                <button type="button" onClick={onCreate}>
                    Start a return
                </button>
            </header>

            <ErrorBanner message={error} onRetry={load} />

            {items === null && !error && <p className="loading-state" role="status">Loading your returns...</p>}

            {items && items.length === 0 && (
                <div className="empty-state">
                    <h2>No returns yet</h2>
                    <p>Start a return from one of your orders to see it here.</p>
                </div>
            )}

            {items && items.length > 0 && (
                <ul className="return-list">
                    {items.map((item) => (
                        <li key={item._id}>
                            <button type="button" className="return-list-item" onClick={() => onSelect(item._id)}>
                                <div>
                                    <strong>{item.sku}</strong>
                                    <span className="muted"> &middot; qty {item.quantity}</span>
                                </div>
                                <StatusBadge status={item.status} />
                                <span className="muted">{formatDateTime(item.createdAt)}</span>
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </main>
    );
}

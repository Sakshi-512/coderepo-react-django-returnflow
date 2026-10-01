import { useEffect, useState } from "react";
import { ErrorBanner } from "../../shared/components/ErrorBanner.jsx";
import { formatCurrency, humanize } from "../../shared/utils/format.js";
import { ordersApi, returnsApi } from "./returns.api.js";

const REASONS = ["defective", "wrong_item", "not_as_described", "no_longer_needed", "changed_mind"];

export function ReturnRequestForm({ onClose, onSubmitted }) {
    const [orders, setOrders] = useState(null);
    const [loadError, setLoadError] = useState("");
    const [orderId, setOrderId] = useState("");
    const [orderItemId, setOrderItemId] = useState("");
    const [quantity, setQuantity] = useState(1);
    const [reason, setReason] = useState(REASONS[0]);
    const [resolutionType, setResolutionType] = useState("refund");
    const [exchangeSku, setExchangeSku] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState(null);

    const loadOrders = async () => {
        try {
            setLoadError("");
            setOrders(await ordersApi.list());
        } catch (error) {
            setLoadError(error.message);
        }
    };

    useEffect(() => {
        loadOrders();
    }, []);

    const selectedOrder = orders?.find((order) => order._id === orderId);
    const selectedItem = selectedOrder?.items.find((item) => item.orderItemId === orderItemId);

    const submit = async (event) => {
        event.preventDefault();
        setSubmitting(true);
        setSubmitError(null);

        try {
            const created = await returnsApi.submit({
                orderId,
                orderItemId,
                quantity: Number(quantity),
                reason,
                resolutionType,
                ...(resolutionType === "exchange" ? { exchangeSku } : {}),
            });
            onSubmitted(created);
        } catch (error) {
            setSubmitError(error);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <main className="page">
            <header className="page-header">
                <h1>Start a return</h1>
                <button type="button" className="secondary" onClick={onClose}>
                    Cancel
                </button>
            </header>

            <ErrorBanner message={loadError} onRetry={loadOrders} />

            {orders === null && !loadError && <p className="loading-state" role="status">Loading your orders...</p>}

            {orders && orders.length === 0 && (
                <div className="empty-state">
                    <h2>No orders found</h2>
                    <p>There are no orders on this account to start a return from.</p>
                </div>
            )}

            {orders && orders.length > 0 && (
                <form className="return-form" onSubmit={submit}>
                    <label htmlFor="order">Order</label>
                    <select
                        id="order"
                        value={orderId}
                        onChange={(event) => {
                            setOrderId(event.target.value);
                            setOrderItemId("");
                        }}
                        required
                    >
                        <option value="" disabled>
                            Choose an order
                        </option>
                        {orders.map((order) => (
                            <option key={order._id} value={order._id}>
                                Order {order._id.slice(-6)}
                            </option>
                        ))}
                    </select>

                    {selectedOrder && (
                        <>
                            <label htmlFor="orderItem">Item</label>
                            <select
                                id="orderItem"
                                value={orderItemId}
                                onChange={(event) => setOrderItemId(event.target.value)}
                                required
                            >
                                <option value="" disabled>
                                    Choose an item
                                </option>
                                {selectedOrder.items.map((item) => (
                                    <option key={item.orderItemId} value={item.orderItemId}>
                                        {item.sku} &middot; qty {item.quantity} &middot; {formatCurrency(item.unitPrice)}
                                    </option>
                                ))}
                            </select>
                        </>
                    )}

                    {selectedItem && (
                        <>
                            <label htmlFor="quantity">Quantity to return</label>
                            <input
                                id="quantity"
                                type="number"
                                min={1}
                                max={selectedItem.quantity}
                                value={quantity}
                                onChange={(event) => setQuantity(event.target.value)}
                                required
                            />

                            <label htmlFor="reason">Reason</label>
                            <select id="reason" value={reason} onChange={(event) => setReason(event.target.value)}>
                                {REASONS.map((value) => (
                                    <option key={value} value={value}>
                                        {humanize(value)}
                                    </option>
                                ))}
                            </select>

                            <fieldset className="resolution-fieldset">
                                <legend>Resolution</legend>
                                <label>
                                    <input
                                        type="radio"
                                        name="resolutionType"
                                        value="refund"
                                        checked={resolutionType === "refund"}
                                        onChange={() => setResolutionType("refund")}
                                    />
                                    Refund
                                </label>
                                <label>
                                    <input
                                        type="radio"
                                        name="resolutionType"
                                        value="exchange"
                                        checked={resolutionType === "exchange"}
                                        onChange={() => setResolutionType("exchange")}
                                    />
                                    Exchange
                                </label>
                            </fieldset>

                            {resolutionType === "exchange" && (
                                <>
                                    <label htmlFor="exchangeSku">Replacement SKU</label>
                                    <input
                                        id="exchangeSku"
                                        type="text"
                                        value={exchangeSku}
                                        onChange={(event) => setExchangeSku(event.target.value)}
                                        placeholder="e.g. RF-JCKT-BLK-L"
                                        required
                                    />
                                </>
                            )}

                            {submitError && (
                                <p className="form-error" role="alert">
                                    {submitError.message}
                                    {submitError.details?.fieldErrors &&
                                        Object.entries(submitError.details.fieldErrors).map(([field, messages]) => (
                                            <span key={field} className="field-error">
                                                {field}: {messages.join(", ")}
                                            </span>
                                        ))}
                                </p>
                            )}

                            <button type="submit" disabled={submitting}>
                                {submitting ? "Submitting..." : "Submit return"}
                            </button>
                        </>
                    )}
                </form>
            )}
        </main>
    );
}

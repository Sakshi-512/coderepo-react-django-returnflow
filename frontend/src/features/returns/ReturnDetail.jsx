import { useCallback, useEffect, useState } from "react";
import { Modal } from "../../shared/components/Modal.jsx";
import { ErrorBanner } from "../../shared/components/ErrorBanner.jsx";
import { StatusBadge } from "../../shared/components/StatusBadge.jsx";
import { formatDateTime, humanize } from "../../shared/utils/format.js";
import { returnsApi } from "./returns.api.js";

const REJECT_REASONS = ["policy_violation", "return_window_expired", "item_not_eligible", "duplicate_request", "other"];

function Timeline({ history }) {
    if (!history?.length) return <p className="muted">No history yet.</p>;

    return (
        <ol className="timeline">
            {history.map((entry, index) => (
                <li key={index}>
                    <div className="timeline-marker" aria-hidden="true" />
                    <div>
                        <strong>{humanize(entry.action)}</strong>
                        <span className="muted"> &middot; {formatDateTime(entry.at)}</span>
                        <div className="muted">by {entry.actorRole}</div>
                        {entry.metadata && Object.keys(entry.metadata).length > 0 && (
                            <div className="timeline-metadata">
                                {Object.entries(entry.metadata).map(([key, value]) => (
                                    <span key={key}>
                                        {humanize(key)}: {String(value)}
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
                </li>
            ))}
        </ol>
    );
}

function RejectDialog({ onClose, onConfirm, pending }) {
    const [reasonCode, setReasonCode] = useState(REJECT_REASONS[0]);
    const [reasonNote, setReasonNote] = useState("");

    return (
        <Modal title="Reject return" onClose={onClose}>
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    onConfirm(reasonCode, reasonNote);
                }}
            >
                <label htmlFor="reasonCode">Reason</label>
                <select id="reasonCode" value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
                    {REJECT_REASONS.map((value) => (
                        <option key={value} value={value}>
                            {humanize(value)}
                        </option>
                    ))}
                </select>

                <label htmlFor="reasonNote">Note (optional)</label>
                <textarea id="reasonNote" value={reasonNote} onChange={(event) => setReasonNote(event.target.value)} maxLength={1000} />

                <div className="modal-actions">
                    <button type="button" className="secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="submit" className="danger" disabled={pending}>
                        {pending ? "Rejecting..." : "Reject return"}
                    </button>
                </div>
            </form>
        </Modal>
    );
}

function InspectDialog({ onClose, onConfirm, pending }) {
    const [verdict, setVerdict] = useState("pass");
    const [notes, setNotes] = useState("");

    return (
        <Modal title="Record inspection" onClose={onClose}>
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    onConfirm(verdict, notes);
                }}
            >
                <fieldset className="resolution-fieldset">
                    <legend>Verdict</legend>
                    <label>
                        <input type="radio" name="verdict" value="pass" checked={verdict === "pass"} onChange={() => setVerdict("pass")} />
                        Pass
                    </label>
                    <label>
                        <input type="radio" name="verdict" value="fail" checked={verdict === "fail"} onChange={() => setVerdict("fail")} />
                        Fail
                    </label>
                </fieldset>

                <label htmlFor="notes">Notes (optional)</label>
                <textarea id="notes" value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={1000} />

                <div className="modal-actions">
                    <button type="button" className="secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="submit" disabled={pending}>
                        {pending ? "Saving..." : "Save inspection"}
                    </button>
                </div>
            </form>
        </Modal>
    );
}

export function ReturnDetail({ returnId, account, onBack, onChanged }) {
    const [returnDoc, setReturnDoc] = useState(null);
    const [refundOps, setRefundOps] = useState(null);
    const [reservation, setReservation] = useState(null);
    const [error, setError] = useState("");
    const [pendingAction, setPendingAction] = useState("");
    const [actionError, setActionError] = useState("");
    const [showReject, setShowReject] = useState(false);
    const [showInspect, setShowInspect] = useState(false);

    const load = useCallback(async () => {
        try {
            setError("");
            const doc = await returnsApi.get(returnId);
            setReturnDoc(doc);

            const refundRelevant = doc.resolutionType === "refund" && ["REFUND_PROCESSING", "REFUND_FAILED", "COMPLETED"].includes(doc.status);
            const exchangeRelevant =
                doc.resolutionType === "exchange" && ["EXCHANGE_RESERVING", "EXCHANGE_AWAITING_INVENTORY", "COMPLETED"].includes(doc.status);

            if (refundRelevant) {
                setRefundOps(await returnsApi.refundHistory(returnId).catch(() => []));
            }

            if (exchangeRelevant) {
                setReservation(await returnsApi.reservation(returnId).catch(() => null));
            }
        } catch (requestError) {
            setError(requestError.message);
        }
    }, [returnId]);

    useEffect(() => {
        load();
    }, [load]);

    const runAction = async (name, action) => {
        setPendingAction(name);
        setActionError("");

        try {
            await action();
            await load();
            onChanged?.();
        } catch (requestError) {
            setActionError(requestError.message);
        } finally {
            setPendingAction("");
        }
    };

    if (error) return <ErrorBanner message={error} onRetry={load} />;

    if (!returnDoc) return <p className="loading-state" role="status">Loading return...</p>;

    const isOwner = account.role === "customer" && returnDoc.customerId === account._id;
    const isStaff = account.role !== "customer";
    const canCancel = isOwner && returnDoc.status === "REQUESTED";
    const canApproveReject = ["agent", "manager"].includes(account.role) && returnDoc.status === "REQUESTED";
    const canReceive = ["warehouse", "manager"].includes(account.role) && returnDoc.status === "APPROVED";
    const canInspect = ["warehouse", "manager"].includes(account.role) && returnDoc.status === "ITEM_RECEIVED";
    const canCheckRefund = (isOwner || isStaff) && returnDoc.status === "REFUND_PROCESSING";
    const canRetryRefund = account.role === "manager" && returnDoc.status === "REFUND_FAILED";
    const canAdvanceExchange = ["agent", "manager"].includes(account.role) && returnDoc.status === "EXCHANGE_RESERVING";
    const canRetryExchange = ["agent", "manager"].includes(account.role) && returnDoc.status === "EXCHANGE_AWAITING_INVENTORY";
    const showRefundProgress =
        returnDoc.resolutionType === "refund" && ["REFUND_PROCESSING", "REFUND_FAILED", "COMPLETED"].includes(returnDoc.status);
    const showExchangeProgress =
        returnDoc.resolutionType === "exchange" &&
        ["EXCHANGE_RESERVING", "EXCHANGE_AWAITING_INVENTORY", "COMPLETED"].includes(returnDoc.status);

    return (
        <main className="page">
            <header className="page-header">
                <button type="button" className="secondary" onClick={onBack}>
                    &larr; Back
                </button>
                <h1>
                    {returnDoc.sku} <StatusBadge status={returnDoc.status} />
                </h1>
            </header>

            <section className="return-summary">
                <dl>
                    <dt>Quantity</dt>
                    <dd>{returnDoc.quantity}</dd>
                    <dt>Reason</dt>
                    <dd>{humanize(returnDoc.reason)}</dd>
                    <dt>Resolution</dt>
                    <dd>{humanize(returnDoc.resolutionType)}</dd>
                    {returnDoc.exchangeSku && (
                        <>
                            <dt>Replacement SKU</dt>
                            <dd>{returnDoc.exchangeSku}</dd>
                        </>
                    )}
                    {returnDoc.inspection && (
                        <>
                            <dt>Inspection</dt>
                            <dd>
                                {humanize(returnDoc.inspection.verdict)}
                                {returnDoc.inspection.notes ? ` -- ${returnDoc.inspection.notes}` : ""}
                            </dd>
                        </>
                    )}
                </dl>
            </section>

            <ErrorBanner message={actionError} />

            {showRefundProgress && (
                <section className="progress-panel">
                    <h2>Refund progress</h2>
                    {refundOps === null || refundOps.length === 0 ? (
                        <p className="muted">Preparing refund...</p>
                    ) : (
                        <ul className="attempt-list">
                            {refundOps.map((operation) => (
                                <li key={operation._id}>
                                    Cycle {operation.cycle}: {humanize(operation.status)}
                                    {operation.attempts?.length > 0 && (
                                        <span className="muted"> ({operation.attempts.length} attempt(s))</span>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                    {canCheckRefund && (
                        <button
                            type="button"
                            disabled={pendingAction === "refundAttempt"}
                            onClick={() => runAction("refundAttempt", () => returnsApi.refundAttempt(returnId))}
                        >
                            {pendingAction === "refundAttempt" ? "Checking..." : "Check for update"}
                        </button>
                    )}
                    {canRetryRefund && (
                        <button
                            type="button"
                            disabled={pendingAction === "refundRetry"}
                            onClick={() => runAction("refundRetry", () => returnsApi.refundRetry(returnId))}
                        >
                            {pendingAction === "refundRetry" ? "Retrying..." : "Retry refund"}
                        </button>
                    )}
                </section>
            )}

            {showExchangeProgress && (
                <section className="progress-panel">
                    <h2>Exchange progress</h2>
                    {reservation ? (
                        <p>Reservation: {humanize(reservation.status)}</p>
                    ) : (
                        <p className="muted">Preparing reservation...</p>
                    )}
                    {canAdvanceExchange && (
                        <button
                            type="button"
                            disabled={pendingAction === "exchangeCheck"}
                            onClick={() => runAction("exchangeCheck", () => returnsApi.exchangeRetry(returnId))}
                        >
                            {pendingAction === "exchangeCheck" ? "Checking..." : "Check for update"}
                        </button>
                    )}
                    {canRetryExchange && (
                        <button
                            type="button"
                            disabled={pendingAction === "exchangeRetry"}
                            onClick={() => runAction("exchangeRetry", () => returnsApi.exchangeRetry(returnId))}
                        >
                            {pendingAction === "exchangeRetry" ? "Retrying..." : "Retry reservation"}
                        </button>
                    )}
                </section>
            )}

            <section className="action-bar">
                {canCancel && (
                    <button
                        type="button"
                        className="secondary"
                        disabled={pendingAction === "cancel"}
                        onClick={() => runAction("cancel", () => returnsApi.cancel(returnId))}
                    >
                        {pendingAction === "cancel" ? "Cancelling..." : "Cancel return"}
                    </button>
                )}
                {canApproveReject && (
                    <>
                        <button
                            type="button"
                            disabled={pendingAction === "approve"}
                            onClick={() => runAction("approve", () => returnsApi.approve(returnId))}
                        >
                            {pendingAction === "approve" ? "Approving..." : "Approve"}
                        </button>
                        <button type="button" className="danger" onClick={() => setShowReject(true)}>
                            Reject
                        </button>
                    </>
                )}
                {canReceive && (
                    <button
                        type="button"
                        disabled={pendingAction === "receive"}
                        onClick={() => runAction("receive", () => returnsApi.receive(returnId))}
                    >
                        {pendingAction === "receive" ? "Recording..." : "Mark item received"}
                    </button>
                )}
                {canInspect && (
                    <button type="button" onClick={() => setShowInspect(true)}>
                        Record inspection
                    </button>
                )}
            </section>

            <section className="return-history">
                <h2>History</h2>
                <Timeline history={returnDoc.history} />
            </section>

            {showReject && (
                <RejectDialog
                    onClose={() => setShowReject(false)}
                    pending={pendingAction === "reject"}
                    onConfirm={(reasonCode, reasonNote) => {
                        setShowReject(false);
                        runAction("reject", () => returnsApi.reject(returnId, { reasonCode, reasonNote }));
                    }}
                />
            )}

            {showInspect && (
                <InspectDialog
                    onClose={() => setShowInspect(false)}
                    pending={pendingAction === "inspect"}
                    onConfirm={(verdict, notes) => {
                        setShowInspect(false);
                        runAction("inspect", () => returnsApi.inspect(returnId, { verdict, notes }));
                    }}
                />
            )}
        </main>
    );
}

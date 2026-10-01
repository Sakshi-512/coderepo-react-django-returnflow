import { useCallback, useEffect, useState } from "react";
import { authApi } from "./features/auth/auth.api.js";
import { LoginScreen } from "./features/auth/LoginScreen.jsx";
import { ReturnsQueue } from "./features/operations/ReturnsQueue.jsx";
import { MyReturnsList } from "./features/returns/MyReturnsList.jsx";
import { ReturnDetail } from "./features/returns/ReturnDetail.jsx";
import { ReturnRequestForm } from "./features/returns/ReturnRequestForm.jsx";
import { hasSessionToken, setSessionToken } from "./shared/api/client.js";

function AppBootScreen() {
    return (
        <main className="app-boot" role="status" aria-label="Loading ReturnFlow">
            <strong>ReturnFlow</strong>
        </main>
    );
}

function AppHeader({ account, onLogout }) {
    return (
        <header className="app-header">
            <span className="app-brand">ReturnFlow</span>
            <div className="app-header-actions">
                <span className="muted">{account.email}</span>
                <button type="button" className="secondary" onClick={onLogout}>
                    Sign out
                </button>
            </div>
        </header>
    );
}

export default function App() {
    const [account, setAccount] = useState(null);
    const [bootstrapping, setBootstrapping] = useState(true);
    const [authLoading, setAuthLoading] = useState(false);
    const [authError, setAuthError] = useState("");
    const [view, setView] = useState({ name: "list" });
    const [refreshKey, setRefreshKey] = useState(0);

    useEffect(() => {
        const expire = (event) => {
            setAccount(null);
            setAuthError(event.detail || "Your ReturnFlow session has expired.");
        };

        window.addEventListener("returnflow-session-expired", expire);

        return () => window.removeEventListener("returnflow-session-expired", expire);
    }, []);

    useEffect(() => {
        let active = true;

        const restore = async () => {
            if (!hasSessionToken()) {
                if (active) setBootstrapping(false);

                return;
            }

            try {
                const session = await authApi.session();

                if (active) {
                    setAccount(session.account);
                    setView({ name: session.account.role === "customer" ? "list" : "queue" });
                }
            } catch {
                setSessionToken("");
            } finally {
                if (active) setBootstrapping(false);
            }
        };

        restore();

        return () => {
            active = false;
        };
    }, []);

    const login = async (email, password) => {
        try {
            setAuthLoading(true);
            setAuthError("");
            const result = await authApi.login(email, password);
            setSessionToken(result.token);
            setAccount(result.account);
            setView({ name: result.account.role === "customer" ? "list" : "queue" });
        } catch (error) {
            setAuthError(error.message);
        } finally {
            setAuthLoading(false);
        }
    };

    const logout = async () => {
        try {
            await authApi.logout();
        } catch {
            // Best-effort: still clear local session state even if the
            // request itself fails (e.g. the token already expired).
        }

        setSessionToken("");
        setAccount(null);
        setView({ name: "list" });
    };

    const bumpRefresh = useCallback(() => setRefreshKey((value) => value + 1), []);

    if (bootstrapping) return <AppBootScreen />;

    if (!account) return <LoginScreen onLogin={login} loading={authLoading} error={authError} />;

    const isCustomer = account.role === "customer";
    const goHome = () => setView({ name: isCustomer ? "list" : "queue" });

    return (
        <div className="app-shell">
            <AppHeader account={account} onLogout={logout} />

            {view.name === "list" && isCustomer && (
                <MyReturnsList
                    refreshKey={refreshKey}
                    onCreate={() => setView({ name: "submit" })}
                    onSelect={(id) => setView({ name: "detail", id })}
                />
            )}

            {view.name === "queue" && !isCustomer && (
                <ReturnsQueue account={account} refreshKey={refreshKey} onSelect={(id) => setView({ name: "detail", id })} />
            )}

            {view.name === "submit" && (
                <ReturnRequestForm
                    onClose={goHome}
                    onSubmitted={(created) => {
                        bumpRefresh();
                        setView({ name: "detail", id: created._id });
                    }}
                />
            )}

            {view.name === "detail" && (
                <ReturnDetail returnId={view.id} account={account} onBack={goHome} onChanged={bumpRefresh} />
            )}
        </div>
    );
}

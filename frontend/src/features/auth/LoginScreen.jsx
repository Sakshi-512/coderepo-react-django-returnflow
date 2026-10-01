import { useState } from "react";

export function LoginScreen({ onLogin, loading, error }) {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");

    const submit = (event) => {
        event.preventDefault();
        onLogin(email, password);
    };

    return (
        <main className="auth-screen">
            <form className="auth-card" onSubmit={submit}>
                <h1>ReturnFlow</h1>
                <p className="auth-subtitle">Sign in to manage returns and exchanges.</p>

                <label htmlFor="email">Email</label>
                <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                />

                <label htmlFor="password">Password</label>
                <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                />

                {error && (
                    <p className="form-error" role="alert">
                        {error}
                    </p>
                )}

                <button type="submit" disabled={loading}>
                    {loading ? "Signing in..." : "Sign in"}
                </button>
            </form>
        </main>
    );
}

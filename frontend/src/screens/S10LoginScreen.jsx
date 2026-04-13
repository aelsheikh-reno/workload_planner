import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { requestJson } from "../api";

export function S10LoginScreen({ onLogin }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await requestJson("/api/auth/login", {
        method: "POST",
        body: { email, password },
      });
      localStorage.setItem("float_token", result.token);
      localStorage.setItem("float_user", JSON.stringify(result.user));
      onLogin?.(result.user);
      navigate("/s06");
    } catch (err) {
      setError(err.message || "Login failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <span className="login-brand__icon">📋</span>
          <h1 className="login-brand__name">Resource Planner</h1>
          <p className="login-brand__tagline">Team scheduling &amp; capacity management</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="field-group">
            <label className="field-label" htmlFor="email">Email address</label>
            <input
              className="field-input"
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="password">Password</label>
            <input
              className="field-input"
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </div>

          {error ? (
            <p className="login-error">{error}</p>
          ) : null}

          <button
            className="primary-button login-submit"
            type="submit"
            disabled={loading}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="login-hint">
          Demo: <code>manager@demo.com</code> / <code>password</code>
        </p>
      </div>
    </div>
  );
}

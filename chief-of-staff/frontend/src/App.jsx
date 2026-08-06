import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bell,
  BookOpenText,
  Boxes,
  Cable,
  ChevronRight,
  CircleUserRound,
  Compass,
  FileSearch,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  X,
} from "lucide-react";
import {
  completeBootstrap,
  getAuthSession,
  getBootstrapStatus,
  loginWithPassword,
  logoutSession,
} from "./apiClient";
import BuilderConsole from "./components/BuilderConsole";
import ExecutiveDashboard from "./components/ExecutiveDashboard";
import { ExecutiveRouteView } from "./components/ExecutiveViews";
import { runtimeConfig } from "./runtimeConfig";
import "./App.css";

const EXECUTIVE_ROUTES = Object.freeze([
  { key: "dashboard", label: "Dashboard", description: "Current priorities and operating position", icon: LayoutDashboard },
  { key: "daily-brief", label: "Daily Brief", description: "The most important changes and next actions", icon: BookOpenText },
  { key: "evidence", label: "Evidence", description: "Trace facts, sources, and supporting records", icon: FileSearch },
  { key: "decisions", label: "Decision Center", description: "Review decisions, recommendations, and approvals", icon: Compass },
  { key: "connectors", label: "Connectors", description: "Monitor enterprise data connections", icon: Cable },
  { key: "system-health", label: "System Health", description: "Runtime readiness and platform status", icon: HeartPulse },
]);

function parseHash() {
  const rawHash = window.location.hash.replace(/^#\/?/, "");
  const [hashPath] = rawHash.split("?");
  if (hashPath === "builder" || hashPath.startsWith("builder/")) return { workspace: "builder", page: "console" };
  const page = hashPath.startsWith("executive/") ? hashPath.replace("executive/", "") : "dashboard";
  return { workspace: "executive", page: EXECUTIVE_ROUTES.some((route) => route.key === page) ? page : "dashboard" };
}

function LoginScreen({ reason, onAuthenticated }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [bootstrapSecret, setBootstrapSecret] = useState("");
  const [bootstrapPassword, setBootstrapPassword] = useState("");
  const [bootstrapAvailable, setBootstrapAvailable] = useState(false);
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);
  const [error, setError] = useState(reason === "expired" ? "Your session expired. Sign in again." : "");
  const [bootstrapMessage, setBootstrapMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let mounted = true;
    getBootstrapStatus()
      .then((status) => { if (mounted) setBootstrapAvailable(Boolean(status.available)); })
      .catch(() => { if (mounted) setBootstrapAvailable(false); })
      .finally(() => { if (mounted) setCheckingBootstrap(false); });
    return () => { mounted = false; };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      const session = await loginWithPassword({ email: email.trim(), password });
      window.location.hash = "#executive/connectors";
      onAuthenticated(session);
    } catch (requestError) {
      setError(requestError.message || "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBootstrap(event) {
    event.preventDefault();
    if (!bootstrapSecret || bootstrapPassword.length < 12) {
      setBootstrapMessage("Bootstrap secret and a 12+ character password are required.");
      return;
    }
    try {
      setSubmitting(true);
      setBootstrapMessage("");
      await completeBootstrap({ bootstrapSecret, password: bootstrapPassword });
      setBootstrapAvailable(false);
      setBootstrapSecret("");
      setBootstrapPassword("");
      setBootstrapMessage("First administrator created. Remove the bootstrap secret from Render, then sign in.");
    } catch (requestError) {
      setBootstrapMessage(requestError.message || "Bootstrap failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="workspace-brand login-brand">
          <div className="workspace-brand-mark" aria-hidden="true"><Boxes size={24} /></div>
          <div><strong>POLARIS</strong><span>Executive OS</span></div>
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <h1 id="login-title">Sign in</h1>
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" type="email" required />
          </label>
          <label>
            Password
            <input value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" type="password" required />
          </label>
          {error && <div className="auth-message" role="alert">{error}</div>}
          <button type="submit" className="primary-button" disabled={submitting}>{submitting ? "Signing in..." : "Sign In"}</button>
        </form>
        {!checkingBootstrap && bootstrapAvailable && (
          <form className="login-form bootstrap-form" onSubmit={handleBootstrap}>
            <h2>First administrator bootstrap</h2>
            <label>
              One-time bootstrap secret
              <input value={bootstrapSecret} onChange={(event) => setBootstrapSecret(event.target.value)} autoComplete="one-time-code" type="password" required />
            </label>
            <label>
              Admin password
              <input value={bootstrapPassword} onChange={(event) => setBootstrapPassword(event.target.value)} autoComplete="new-password" type="password" minLength={12} required />
            </label>
            {bootstrapMessage && <div className="auth-message" role="status">{bootstrapMessage}</div>}
            <button type="submit" className="primary-button secondary" disabled={submitting}>{submitting ? "Creating..." : "Create First Admin"}</button>
          </form>
        )}
        {!bootstrapAvailable && bootstrapMessage && <div className="auth-message success" role="status">{bootstrapMessage}</div>}
      </section>
    </main>
  );
}

function ExecutiveWorkspace({ page, session, forbiddenMessage, onOpenMenu, onLogout }) {
  const activeRoute = EXECUTIVE_ROUTES.find((route) => route.key === page) ?? EXECUTIVE_ROUTES[0];
  return (
    <div className="executive-workspace">
      <header className="workspace-topbar">
        <div className="workspace-topbar-title">
          <button type="button" className="mobile-menu-button" onClick={onOpenMenu} aria-label="Open workspace navigation"><Menu size={20} /></button>
          <div><span>{runtimeConfig.workspace.organizationName}</span><strong>{activeRoute.label}</strong></div>
        </div>
        <div className="workspace-topbar-actions">
          <span className="observer-badge"><Activity size={15} aria-hidden="true" /> Observer mode</span>
          <button type="button" aria-label="Notifications" disabled><Bell size={19} /></button>
          <div className="workspace-profile" aria-label="Active workspace user"><CircleUserRound size={21} aria-hidden="true" /><span>{runtimeConfig.workspace.userName}</span></div>
          <button type="button" aria-label="Sign out" onClick={onLogout}><LogOut size={19} /></button>
        </div>
      </header>
      {forbiddenMessage && <div className="forbidden-banner" role="alert">{forbiddenMessage}</div>}
      <main className="workspace-main">{page === "dashboard" ? <ExecutiveDashboard /> : <ExecutiveRouteView page={page} />}</main>
      <footer className="workspace-statusbar"><span><span className="status-dot" aria-hidden="true" />{runtimeConfig.workspace.workspaceName}</span><span>Evidence · Intelligence · Action</span></footer>
    </div>
  );
}

function WorkspaceSidebar({ route, mobileOpen, onClose }) {
  return (
    <>
      {mobileOpen && <button type="button" className="workspace-overlay" onClick={onClose} aria-label="Close workspace navigation" />}
      <aside className={`workspace-sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="workspace-brand">
          <div className="workspace-brand-mark" aria-hidden="true"><Boxes size={24} /></div>
          <div><strong>POLARIS</strong><span>Executive OS</span></div>
          <button type="button" className="mobile-close-button" onClick={onClose} aria-label="Close workspace navigation"><X size={20} /></button>
        </div>
        <div className="workspace-identity"><span>Active workspace</span><strong>{runtimeConfig.workspace.workspaceName}</strong><small>{runtimeConfig.workspace.organizationName}</small></div>
        <nav className="workspace-navigation" aria-label="Executive workspace navigation">
          <p>Executive</p>
          {EXECUTIVE_ROUTES.map((item) => {
            const Icon = item.icon;
            const active = route.workspace === "executive" && route.page === item.key;
            return <a key={item.key} className={active ? "is-active" : ""} href={`#executive/${item.key}`} onClick={onClose}><Icon size={18} aria-hidden="true" /><span>{item.label}</span>{active && <ChevronRight size={16} aria-hidden="true" />}</a>;
          })}
        </nav>
        <div className="workspace-sidebar-footer">
          <a className={route.workspace === "builder" ? "is-active" : ""} href="#builder" onClick={onClose}><Settings size={18} aria-hidden="true" /><span>Builder Console</span></a>
          <small>Controlled Mor Logistics advisory environment</small>
        </div>
      </aside>
    </>
  );
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [session, setSession] = useState(getAuthSession);
  const [authReason, setAuthReason] = useState("");
  const [forbiddenMessage, setForbiddenMessage] = useState("");

  useEffect(() => {
    const handleHashChange = () => { setRoute(parseHash()); setMobileOpen(false); };
    const handleAuthChange = (event) => {
      setSession(getAuthSession());
      setAuthReason(event.detail?.reason || "");
    };
    const handleForbidden = (event) => setForbiddenMessage(event.detail?.message || "You do not have permission to access that resource.");
    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("polaris-auth-changed", handleAuthChange);
    window.addEventListener("polaris-forbidden", handleForbidden);
    return () => {
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("polaris-auth-changed", handleAuthChange);
      window.removeEventListener("polaris-forbidden", handleForbidden);
    };
  }, []);

  async function handleLogout() {
    await logoutSession();
    setForbiddenMessage("");
  }

  const content = useMemo(() => {
    if (!session.authenticated) {
      return <LoginScreen reason={authReason} onAuthenticated={setSession} />;
    }

    if (route.workspace === "builder") {
      return (
        <div className="builder-workspace">
          <header className="workspace-topbar builder-topbar">
            <div className="workspace-topbar-title">
              <button type="button" className="mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open workspace navigation"><Menu size={20} /></button>
              <div><span>Polaris Builder Platform</span><strong>Builder Console</strong></div>
            </div>
            <div className="workspace-topbar-actions">
              <a className="return-to-executive" href="#executive/dashboard">Executive Workspace</a>
              <button type="button" aria-label="Sign out" onClick={handleLogout}><LogOut size={19} /></button>
            </div>
          </header>
          {forbiddenMessage && <div className="forbidden-banner" role="alert">{forbiddenMessage}</div>}
          <main className="workspace-main builder-main"><BuilderConsole /></main>
        </div>
      );
    }
    return <ExecutiveWorkspace page={route.page} session={session} forbiddenMessage={forbiddenMessage} onOpenMenu={() => setMobileOpen(true)} onLogout={handleLogout} />;
  }, [route, session, authReason, forbiddenMessage]);

  if (!session.authenticated) return content;

  return <div className="polaris-app-shell"><WorkspaceSidebar route={route} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />{content}</div>;
}

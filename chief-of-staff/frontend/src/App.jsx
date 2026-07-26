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
  Menu,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import BuilderConsole from "./components/BuilderConsole";
import ExecutiveDashboard from "./components/ExecutiveDashboard";
import { runtimeConfig } from "./runtimeConfig";
import "./App.css";

const EXECUTIVE_ROUTES = Object.freeze([
  {
    key: "dashboard",
    label: "Dashboard",
    description: "Current priorities and operating position",
    icon: LayoutDashboard,
  },
  {
    key: "daily-brief",
    label: "Daily Brief",
    description: "The most important changes and next actions",
    icon: BookOpenText,
  },
  {
    key: "evidence",
    label: "Evidence",
    description: "Trace facts, sources, and supporting records",
    icon: FileSearch,
  },
  {
    key: "decisions",
    label: "Decision Center",
    description: "Review decisions, recommendations, and approvals",
    icon: Compass,
  },
  {
    key: "connectors",
    label: "Connectors",
    description: "Monitor enterprise data connections",
    icon: Cable,
  },
  {
    key: "system-health",
    label: "System Health",
    description: "Runtime readiness and platform status",
    icon: HeartPulse,
  },
]);

function parseHash() {
  const rawHash = window.location.hash.replace(/^#\/?/, "");

  if (rawHash === "builder" || rawHash.startsWith("builder/")) {
    return { workspace: "builder", page: "console" };
  }

  const page = rawHash.startsWith("executive/")
    ? rawHash.replace("executive/", "")
    : "dashboard";

  const knownPage = EXECUTIVE_ROUTES.some((route) => route.key === page)
    ? page
    : "dashboard";

  return { workspace: "executive", page: knownPage };
}

function PlaceholderView({ route }) {
  const Icon = route.icon;

  return (
    <section className="workspace-placeholder" aria-labelledby={`${route.key}-title`}>
      <div className="workspace-placeholder-icon" aria-hidden="true">
        <Icon size={28} />
      </div>
      <p className="workspace-kicker">MISSION 003</p>
      <h1 id={`${route.key}-title`}>{route.label}</h1>
      <p>{route.description}.</p>
      <div className="workspace-state-card">
        <ShieldCheck size={20} aria-hidden="true" />
        <div>
          <strong>Workspace route is ready</strong>
          <span>
            The governed MVP content for this view will be added in the next
            Mission 003 increment.
          </span>
        </div>
      </div>
    </section>
  );
}

function ExecutiveWorkspace({ page, onOpenMenu }) {
  const activeRoute =
    EXECUTIVE_ROUTES.find((route) => route.key === page) ?? EXECUTIVE_ROUTES[0];

  return (
    <div className="executive-workspace">
      <header className="workspace-topbar">
        <div className="workspace-topbar-title">
          <button
            type="button"
            className="mobile-menu-button"
            onClick={onOpenMenu}
            aria-label="Open workspace navigation"
          >
            <Menu size={20} />
          </button>
          <div>
            <span>{runtimeConfig.workspace.organizationName}</span>
            <strong>{activeRoute.label}</strong>
          </div>
        </div>

        <div className="workspace-topbar-actions">
          <span className="observer-badge">
            <Activity size={15} aria-hidden="true" /> Observer mode
          </span>
          <button type="button" aria-label="Notifications" disabled>
            <Bell size={19} />
          </button>
          <div className="workspace-profile" aria-label="Active workspace user">
            <CircleUserRound size={21} aria-hidden="true" />
            <span>{runtimeConfig.workspace.userName}</span>
          </div>
        </div>
      </header>

      <main className="workspace-main">
        {page === "dashboard" ? (
          <ExecutiveDashboard />
        ) : (
          <PlaceholderView route={activeRoute} />
        )}
      </main>

      <footer className="workspace-statusbar">
        <span>
          <span className="status-dot" aria-hidden="true" />
          {runtimeConfig.workspace.workspaceName}
        </span>
        <span>Evidence · Intelligence · Action</span>
      </footer>
    </div>
  );
}

function WorkspaceSidebar({ route, mobileOpen, onClose }) {
  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="workspace-overlay"
          onClick={onClose}
          aria-label="Close workspace navigation"
        />
      )}
      <aside className={`workspace-sidebar ${mobileOpen ? "is-open" : ""}`}>
        <div className="workspace-brand">
          <div className="workspace-brand-mark" aria-hidden="true">
            <Boxes size={24} />
          </div>
          <div>
            <strong>POLARIS</strong>
            <span>Executive OS</span>
          </div>
          <button
            type="button"
            className="mobile-close-button"
            onClick={onClose}
            aria-label="Close workspace navigation"
          >
            <X size={20} />
          </button>
        </div>

        <div className="workspace-identity">
          <span>Active workspace</span>
          <strong>{runtimeConfig.workspace.workspaceName}</strong>
          <small>{runtimeConfig.workspace.organizationName}</small>
        </div>

        <nav className="workspace-navigation" aria-label="Executive workspace navigation">
          <p>Executive</p>
          {EXECUTIVE_ROUTES.map((item) => {
            const Icon = item.icon;
            const active = route.workspace === "executive" && route.page === item.key;

            return (
              <a
                key={item.key}
                className={active ? "is-active" : ""}
                href={`#executive/${item.key}`}
                onClick={onClose}
              >
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
                {active && <ChevronRight size={16} aria-hidden="true" />}
              </a>
            );
          })}
        </nav>

        <div className="workspace-sidebar-footer">
          <a
            className={route.workspace === "builder" ? "is-active" : ""}
            href="#builder"
            onClick={onClose}
          >
            <Settings size={18} aria-hidden="true" />
            <span>Builder Console</span>
          </a>
          <small>Controlled Mor Logistics advisory environment</small>
        </div>
      </aside>
    </>
  );
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(parseHash());
      setMobileOpen(false);
    };

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const content = useMemo(() => {
    if (route.workspace === "builder") {
      return (
        <div className="builder-workspace">
          <header className="workspace-topbar builder-topbar">
            <div className="workspace-topbar-title">
              <button
                type="button"
                className="mobile-menu-button"
                onClick={() => setMobileOpen(true)}
                aria-label="Open workspace navigation"
              >
                <Menu size={20} />
              </button>
              <div>
                <span>Polaris Builder Platform</span>
                <strong>Builder Console</strong>
              </div>
            </div>
            <a className="return-to-executive" href="#executive/dashboard">
              Executive Workspace
            </a>
          </header>
          <main className="workspace-main builder-main">
            <BuilderConsole />
          </main>
        </div>
      );
    }

    return (
      <ExecutiveWorkspace
        page={route.page}
        onOpenMenu={() => setMobileOpen(true)}
      />
    );
  }, [route]);

  return (
    <div className="polaris-app-shell">
      <WorkspaceSidebar
        route={route}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />
      {content}
    </div>
  );
}

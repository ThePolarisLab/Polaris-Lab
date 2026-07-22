import { useEffect, useState } from "react";
import BuilderConsole from "./components/BuilderConsole";
import ExecutiveDashboard from "./components/ExecutiveDashboard";
import "./App.css";

function routeFromHash() {
  return window.location.hash === "#builder" ? "builder" : "executive";
}

export default function App() {
  const [route, setRoute] = useState(routeFromHash);

  useEffect(() => {
    const handleHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  return (
    <div className="polaris-app-shell">
      <nav className="polaris-app-nav" aria-label="Polaris workspaces">
        <a className={route === "executive" ? "is-active" : ""} href="#executive">
          Executive Dashboard
        </a>
        <a className={route === "builder" ? "is-active" : ""} href="#builder">
          Builder Console
        </a>
      </nav>
      {route === "builder" ? <BuilderConsole /> : <ExecutiveDashboard />}
    </div>
  );
}

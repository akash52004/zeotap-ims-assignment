import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Database, ServerCrash, ShieldCheck, Siren, Workflow } from "lucide-react";
import "./styles.css";

type Status = "OPEN" | "INVESTIGATING" | "RESOLVED" | "CLOSED";
type Severity = "P0" | "P1" | "P2" | "P3";

type Incident = {
  id: string;
  component_id: string;
  component_type: string;
  severity: Severity;
  status: Status;
  title: string;
  signal_count: number;
  alert_target: string;
  first_signal_at: string;
  last_signal_at: string;
  mttr_seconds?: number | null;
  rca?: Rca | null;
};

type Rca = {
  start_time: string;
  end_time: string;
  root_cause_category: string;
  fix_applied: string;
  prevention_steps: string;
};

type Dashboard = {
  active: Incident[];
  counts_by_status: Record<string, number>;
  signal_rate_per_sec: number;
  queue_depth: number;
};

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";
const nextStatus: Record<Status, Status[]> = {
  OPEN: ["INVESTIGATING", "RESOLVED"],
  INVESTIGATING: ["RESOLVED", "OPEN"],
  RESOLVED: ["CLOSED", "INVESTIGATING"],
  CLOSED: []
};

function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [signals, setSignals] = useState<unknown[]>([]);
  const [error, setError] = useState<string>("");

  async function load() {
    const [dashboardRes, incidentsRes] = await Promise.all([
      fetch(`${apiBase}/api/dashboard`),
      fetch(`${apiBase}/api/incidents`)
    ]);
    setDashboard(await dashboardRes.json());
    const list = await incidentsRes.json();
    setIncidents(list);
    if (!selectedId && list.length) setSelectedId(list[0].id);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
    const interval = window.setInterval(() => load().catch((err) => setError(err.message)), 3000);
    return () => window.clearInterval(interval);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    fetch(`${apiBase}/api/incidents/${selectedId}`)
      .then((res) => res.json())
      .then((detail) => setSignals(detail.signals ?? []))
      .catch((err) => setError(err.message));
  }, [selectedId, incidents]);

  const selected = useMemo(() => incidents.find((incident) => incident.id === selectedId), [incidents, selectedId]);

  async function updateStatus(status: Status) {
    if (!selected) return;
    setError("");
    const res = await fetch(`${apiBase}/api/incidents/${selected.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    });
    if (!res.ok) {
      const body = await res.json();
      setError(body.detail ?? "Status update failed");
      return;
    }
    await load();
  }

  async function submitRca(rca: Rca) {
    if (!selected) return;
    setError("");
    const res = await fetch(`${apiBase}/api/incidents/${selected.id}/rca`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rca)
    });
    if (!res.ok) {
      const body = await res.json();
      setError(body.detail ?? "RCA submission failed");
      return;
    }
    await load();
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Mission-Critical IMS</p>
          <h1>Incident Command Dashboard</h1>
        </div>
        <div className="health">
          <ShieldCheck size={18} />
          <span>{dashboard ? `${dashboard.signal_rate_per_sec.toFixed(1)} signals/sec` : "Connecting"}</span>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="metrics">
        <Metric icon={<Siren />} label="Open" value={dashboard?.counts_by_status.OPEN ?? 0} />
        <Metric icon={<Workflow />} label="Investigating" value={dashboard?.counts_by_status.INVESTIGATING ?? 0} />
        <Metric icon={<Activity />} label="Queue Depth" value={dashboard?.queue_depth ?? 0} />
        <Metric icon={<Database />} label="Active" value={dashboard?.active.length ?? 0} />
      </section>

      <section className="workspace">
        <aside className="feed">
          <div className="section-title">
            <ServerCrash size={18} />
            <h2>Live Feed</h2>
          </div>
          {incidents.map((incident) => (
            <button
              className={`incident-row ${selectedId === incident.id ? "selected" : ""}`}
              key={incident.id}
              onClick={() => setSelectedId(incident.id)}
            >
              <span className={`badge ${incident.severity}`}>{incident.severity}</span>
              <span>
                <strong>{incident.component_id}</strong>
                <small>{incident.status} · {incident.signal_count} signals</small>
              </span>
            </button>
          ))}
        </aside>

        <section className="detail">
          {selected ? (
            <>
              <div className="detail-head">
                <div>
                  <span className={`badge ${selected.severity}`}>{selected.severity}</span>
                  <h2>{selected.title}</h2>
                  <p>{selected.component_type} · {selected.alert_target}</p>
                </div>
                <div className="actions">
                  {nextStatus[selected.status].filter((status) => status !== "CLOSED").map((status) => (
                    <button key={status} onClick={() => updateStatus(status)}>
                      {status}
                    </button>
                  ))}
                </div>
              </div>
              <div className="status-strip">
                <span>Status: <strong>{selected.status}</strong></span>
                <span>Signals: <strong>{selected.signal_count}</strong></span>
                <span>MTTR: <strong>{selected.mttr_seconds ? `${Math.round(selected.mttr_seconds / 60)} min` : "Pending"}</strong></span>
              </div>
              <RcaForm key={selected.id} incident={selected} onSubmit={submitRca} />
              <RawSignals signals={signals} />
            </>
          ) : (
            <div className="empty">Run the sample data script to populate incidents.</div>
          )}
        </section>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RcaForm({ incident, onSubmit }: { incident: Incident; onSubmit: (rca: Rca) => Promise<void> }) {
  const start = new Date(incident.first_signal_at).toISOString().slice(0, 16);
  const end = new Date().toISOString().slice(0, 16);
  const [form, setForm] = useState({
    start_time: start,
    end_time: end,
    root_cause_category: "Capacity",
    fix_applied: "",
    prevention_steps: ""
  });

  return (
    <form
      className="rca"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          ...form,
          start_time: new Date(form.start_time).toISOString(),
          end_time: new Date(form.end_time).toISOString()
        });
      }}
    >
      <div className="section-title">
        <ShieldCheck size={18} />
        <h2>RCA Closure</h2>
      </div>
      <label>
        Start
        <input type="datetime-local" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
      </label>
      <label>
        End
        <input type="datetime-local" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
      </label>
      <label>
        Category
        <select value={form.root_cause_category} onChange={(e) => setForm({ ...form, root_cause_category: e.target.value })}>
          <option>Capacity</option>
          <option>Configuration</option>
          <option>Dependency Failure</option>
          <option>Code Regression</option>
          <option>Network</option>
        </select>
      </label>
      <label className="wide">
        Fix Applied
        <textarea value={form.fix_applied} onChange={(e) => setForm({ ...form, fix_applied: e.target.value })} />
      </label>
      <label className="wide">
        Prevention Steps
        <textarea value={form.prevention_steps} onChange={(e) => setForm({ ...form, prevention_steps: e.target.value })} />
      </label>
      <button className="close-btn" type="submit" disabled={incident.status !== "RESOLVED"}>Close With RCA</button>
    </form>
  );
}

function RawSignals({ signals }: { signals: unknown[] }) {
  return (
    <section className="raw">
      <div className="section-title">
        <Database size={18} />
        <h2>Raw Signals</h2>
      </div>
      <pre>{JSON.stringify(signals, null, 2)}</pre>
    </section>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

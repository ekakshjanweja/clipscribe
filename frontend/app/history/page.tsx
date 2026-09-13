"use client";

import { useEffect, useState } from "react";

type Segment = { start: string; end: string; text: string };
type Job = { id: string; filename: string; engine: string; status: string; progress: number; stage: string; error?: string; partial?: { segments: Segment[]; frames_done: number; frames_total: number } | null; created_at?: string };
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5001";
const ACTIVE = ["queued", "processing", "pause_requested", "cancel_requested"];

export default function History() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  async function refresh() {
    const response = await fetch(`${API_URL}/jobs?limit=50`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load history.");
    setJobs(data.jobs);
  }
  async function control(id: string, action: "pause" | "resume" | "cancel") {
    try {
      const response = await fetch(`${API_URL}/jobs/${id}/${action}`, { method: "POST" });
      if (!response.ok && response.status !== 204) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Could not update this task.");
      }
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update this task."); }
  }
  useEffect(() => { refresh().catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load history.")); const timer = window.setInterval(() => refresh().catch(() => undefined), 2000); return () => window.clearInterval(timer); }, []);
  return <main className="shell"><header><a className="brand" href="/">clipscribe</a><nav><a href="/">scanner</a><a href="/history">history</a></nav></header><section className="models"><div className="modelHeading"><p className="eyebrow">HISTORY</p><h2>Past transcripts</h2></div>{error && <p className="modelMessage">{error}</p>}<div className="modelList">{jobs.length === 0 && <div className="empty"><p>No jobs yet.</p></div>}{jobs.map((job) => <div className="model" key={job.id}><a href={`/?job=${job.id}`} className="modelLink"><div><strong>{job.filename}</strong><p>{job.engine} · {job.created_at ? new Date(job.created_at).toLocaleString() : ""}</p></div><div className="modelAction"><span className={`status ${job.status}`}>{job.status === "processing" ? `${job.progress}%` : job.status.replace("_", " ")}</span><p>{job.error || job.stage}{job.partial?.segments.length ? ` · ${job.partial.segments.length} partial blocks` : ""}</p></div></a>{ACTIVE.includes(job.status) || job.status === "paused" ? <div className="jobControls">{job.status === "paused" ? <button type="button" onClick={() => control(job.id, "resume")}>Resume</button> : <button type="button" onClick={() => control(job.id, "pause")} disabled={job.status !== "queued" && job.status !== "processing"}>Pause</button>}<button type="button" onClick={() => control(job.id, "cancel")} disabled={job.status === "cancel_requested"}>Cancel</button></div> : null}</div>)}</div></section></main>;
}

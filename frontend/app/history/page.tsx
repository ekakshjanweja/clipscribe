"use client";

import { useEffect, useState } from "react";

type Job = { id: string; filename: string; engine: string; status: string; progress: number; stage: string; error?: string; created_at?: string };
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5001";

export default function History() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  async function refresh() {
    const response = await fetch(`${API_URL}/jobs?limit=50`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load history.");
    setJobs(data.jobs);
  }
  useEffect(() => { refresh().catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load history.")); const timer = window.setInterval(() => refresh().catch(() => undefined), 2000); return () => window.clearInterval(timer); }, []);
  return <main className="shell"><header><a className="brand" href="/">clipscribe</a><nav><a href="/">scanner</a><a href="/history">history</a></nav></header><section className="models"><div className="modelHeading"><p className="eyebrow">HISTORY</p><h2>Past transcripts</h2></div>{error && <p className="modelMessage">{error}</p>}<div className="modelList">{jobs.length === 0 && <div className="empty"><p>No jobs yet.</p></div>}{jobs.map((job) => <a className="model" href={`/?job=${job.id}`} key={job.id}><div><strong>{job.filename}</strong><p>{job.engine} · {job.created_at ? new Date(job.created_at).toLocaleString() : ""}</p></div><div className="modelAction"><span className={`status ${job.status}`}>{job.status === "processing" ? `${job.progress}%` : job.status}</span><p>{job.error || job.stage}</p></div></a>)}</div></section></main>;
}

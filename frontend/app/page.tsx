"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useState } from "react";

type Segment = { start: string; end: string; text: string };
type Scan = { text: string; segments: Segment[]; language: string; duration: string; frames_processed: number; cleaned_blocks: number };
type Job = { id: string; filename: string; status: "queued" | "processing" | "complete" | "failed"; progress: number; stage: string; error?: string; result?: Scan | null };
type Queue = { counts: Record<"queued" | "processing" | "complete" | "failed", number>; active: Job[] };
type Model = { id: string; name: string; description: string; status: "ready" | "installing" | "not-installed" | "unavailable"; size: string; log?: string };

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5001";
const engineHelp = { vision: "Fast and built in.", tesseract: "Fastest for clear English text.", "paddle-mobile": "Fast neural OCR for everyday clips.", "paddle-vl": "Best for complex pages. Takes longer." };

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [engine, setEngine] = useState<"vision" | "tesseract" | "paddle-mobile" | "paddle-vl">("paddle-mobile");
  const [scan, setScan] = useState<Scan | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [models, setModels] = useState<Model[]>([]);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [modelMessage, setModelMessage] = useState("");
  const working = job?.status === "queued" || job?.status === "processing";

  async function refreshModels() {
    const response = await fetch(`${API_URL}/models`);
    const data = await response.json();
    setModels(data.models);
    if (data.models.find((model: Model) => model.id === "apple-vision")?.status === "unavailable") setEngine("paddle-mobile");
  }
  async function refreshJob(id: string) {
    const response = await fetch(`${API_URL}/jobs/${id}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not find this job.");
    setJob(data.job);
    if (data.job.status === "complete") { setScan(data.job.result); localStorage.removeItem("clipscribe-job"); }
    if (data.job.status === "failed") { setError(data.job.error || "The scan could not finish."); localStorage.removeItem("clipscribe-job"); }
  }
  async function refreshQueue() {
    const response = await fetch(`${API_URL}/queue`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not read the queue.");
    setQueue(data);
  }
  async function cancelQueuedJob(id: string) {
    try {
      const response = await fetch(`${API_URL}/jobs/${id}`, { method: "DELETE" });
      if (!response.ok) { const data = await response.json(); throw new Error(data.error || "Could not cancel this task."); }
      if (job?.id === id) { setJob(null); localStorage.removeItem("clipscribe-job"); setError("Queued task cancelled."); }
      await refreshQueue();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not cancel this task."); }
  }

  useEffect(() => {
    refreshModels().catch(() => setModelMessage("Model manager is unavailable. Start the Python API first."));
    refreshQueue().catch(() => undefined);
    const stored = new URLSearchParams(window.location.search).get("job") || localStorage.getItem("clipscribe-job");
    if (stored) refreshJob(stored).catch(() => localStorage.removeItem("clipscribe-job"));
  }, []);
  useEffect(() => { const timer = window.setInterval(() => refreshQueue().catch(() => undefined), 1500); return () => window.clearInterval(timer); }, []);
  useEffect(() => {
    if (!working || !job) return;
    const timer = window.setInterval(() => refreshJob(job.id).catch((reason) => setError(reason instanceof Error ? reason.message : "Could not read job status.")), 1200);
    return () => window.clearInterval(timer);
  }, [working, job?.id]);
  useEffect(() => {
    if (!models.some((model) => model.status === "installing")) return;
    const timer = window.setInterval(() => refreshModels(), 2000);
    return () => window.clearInterval(timer);
  }, [models]);

  async function installPaddle() {
    setModelMessage("");
    try {
      const response = await fetch(`${API_URL}/models/paddle-vl/install`, { method: "POST" });
      if (!response.ok) throw new Error("Could not start download.");
      setModelMessage("Download started. This may take a few minutes.");
      await refreshModels();
    } catch (reason) { setModelMessage(reason instanceof Error ? reason.message : "Could not start download."); }
  }
  function selectFile(next: File | undefined) { if (next) { setFile(next); setScan(null); setJob(null); setError(""); } }
  function onDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); selectFile(event.dataTransfer.files[0]); }
  function download(extension: "txt" | "md") { if (job?.status === "complete") window.location.assign(`${API_URL}/jobs/${job.id}/download/${extension}`); }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file || working) return;
    setError(""); setScan(null);
    try {
      const body = new FormData(); body.append("video", file); body.append("engine", engine);
      const response = await fetch(`${API_URL}/jobs`, { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not queue the scan.");
      setJob(data.job); setQueue(null); localStorage.setItem("clipscribe-job", data.job.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not queue the scan."); }
  }

  return <main className="shell">
    <header><a className="brand" href="/">clipscribe</a><nav><button type="button" onClick={() => document.querySelector("#scanner")?.scrollIntoView({ behavior: "smooth" })}>scanner</button><button type="button" onClick={() => document.querySelector("#queue")?.scrollIntoView({ behavior: "smooth" })}>queue</button><a href="/history">history</a><button type="button" onClick={() => document.querySelector("#models")?.scrollIntoView({ behavior: "smooth" })}>models</button></nav></header>
    <section id="queue" className="queue" aria-live="polite"><div><p className="eyebrow">QUEUE</p><strong>{queue?.counts.processing ?? 0} running · {queue?.counts.queued ?? 0} queued</strong></div><div className="queueCounts"><span>{queue?.counts.complete ?? 0} done</span><span>{queue?.counts.failed ?? 0} failed</span></div>{queue && queue.active.length > 0 && <div className="queueActive">{queue.active.map((item) => <div className="queueItem" key={item.id}><a href={`/?job=${item.id}`}>{item.filename} · {item.status === "processing" ? `${item.progress}%` : "queued"}</a>{item.status === "queued" && <button type="button" onClick={() => cancelQueuedJob(item.id)} aria-label={`Cancel queued task ${item.filename}`}>Cancel</button>}</div>)}</div>}</section>
    <section id="scanner" className="workbench">
      <form onSubmit={submit} className="source">
        <p className="eyebrow">01 / UPLOAD</p><h2>Video or photo</h2>
        <input id="video" type="file" accept="video/*,image/jpeg,image/png,image/heic,image/heif,image/tiff,image/bmp,image/gif" hidden onChange={(event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0])} />
        <label htmlFor="video" className="drop" onDrop={onDrop} onDragOver={(event) => event.preventDefault()}><b>+</b><strong>{file ? file.name : "Drop a video or photo"}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · click to replace` : "video or image · MP4, MOV, JPG, PNG, HEIC"}</small></label>
        <label className="field">OCR ENGINE<select value={engine} onChange={(event) => setEngine(event.target.value as "vision" | "tesseract" | "paddle-mobile" | "paddle-vl")}><option value="vision" disabled={models.find((model) => model.id === "apple-vision")?.status === "unavailable"}>Apple Vision — native & fast</option><option value="tesseract">Tesseract — fastest</option><option value="paddle-mobile">PaddleOCR Mobile — fast</option><option value="paddle-vl">PaddleOCR-VL 1.6 — advanced</option></select></label>
        <p className="hint">{engineHelp[engine]}</p><button disabled={!file || working}>{working ? `${job?.progress ?? 0}% · ${job?.stage ?? "Queued"}` : "Get text ↗"}</button>
      </form>
      <section className="results" aria-live="polite"><div className="resultTitle"><div><p className="eyebrow">02 / TRANSCRIPT</p><h2>{scan ? "Ready" : "Your text"}</h2></div>{scan && <div className="actions"><button onClick={() => navigator.clipboard.writeText(scan.text)}>Copy</button><button onClick={() => download("txt")}>.txt</button><button onClick={() => download("md")}>.md</button></div>}</div>
      {working && <div className="empty progress"><strong>{job?.progress ?? 0}%</strong><p>{job?.stage || "Queued"}</p><div className="progressTrack" role="progressbar" aria-label="OCR progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job?.progress ?? 0}><i style={{ width: `${job?.progress ?? 0}%` }}/></div><small>This will keep running if you close this page.</small></div>}
      {!working && !scan && <div className="empty"><div className="bars">|||||</div><p>{error || "Text will appear here."}</p></div>}
      {scan && <><div className="stats"><span>{scan.language}</span><span>{scan.frames_processed} FRAMES → {scan.cleaned_blocks} CLEAN BLOCKS</span><span>ENDS {scan.duration}</span></div><div className="transcript">{scan.segments.map((segment, index) => <article key={`${segment.start}-${index}`}><time>{segment.start}</time><p>{segment.text}</p></article>)}</div></>}
      </section>
    </section>
    <section id="models" className="models" aria-labelledby="models-heading"><div className="modelHeading"><p className="eyebrow">MODELS</p><h2 id="models-heading">OCR engines</h2></div><div className="modelList">{models.map((model) => <article key={model.id} className="model"><div><strong>{model.name}</strong><p>{model.id === "apple-vision" ? "Built into your Mac." : "For harder layouts."}</p></div><div className="modelAction"><span className={`status ${model.status}`}>{model.status.replace("-", " ")}</span>{model.id === "paddle-vl" && model.status !== "ready" && <button type="button" onClick={installPaddle} disabled={model.status === "installing"}>{model.status === "installing" ? "Downloading…" : "Download ↗"}</button>}</div></article>)}</div>{modelMessage && <p className="modelMessage">{modelMessage}</p>}</section>
    <footer><span>LOCAL ONLY</span><span>FILES ARE TEMPORARY</span></footer>
  </main>;
}

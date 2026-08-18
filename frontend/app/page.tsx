"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useState } from "react";

type Segment = { start: string; end: string; text: string };
type Scan = { text: string; segments: Segment[]; language: string; duration: string; frames_processed: number; cleaned_blocks: number };
type Model = { id: string; name: string; description: string; status: "ready" | "installing" | "not-installed" | "unavailable"; size: string; log?: string };

const engineHelp = {
  vision: "Fast and built in.",
  "paddle-vl": "Better for complex pages. Takes longer.",
};
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5001";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [engine, setEngine] = useState<"vision" | "paddle-vl">("vision");
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<Model[]>([]);
  const [modelMessage, setModelMessage] = useState("");
  async function refreshModels() { const response = await fetch(`${API_URL}/models`); const data = await response.json(); setModels(data.models); if (data.models.find((model: Model) => model.id === "apple-vision")?.status === "unavailable") setEngine("paddle-vl"); }
  useEffect(() => { refreshModels().catch(() => setModelMessage("Model manager is unavailable. Start the Python API first.")); }, []);
  useEffect(() => { if (!models.some((model) => model.status === "installing")) return; const timer = window.setInterval(() => refreshModels(), 2000); return () => window.clearInterval(timer); }, [models]);
  async function installPaddle() { setModelMessage(""); try { const response = await fetch(`${API_URL}/models/paddle-vl/install`, { method: "POST" }); if (!response.ok) throw new Error("Could not start download."); setModelMessage("Download started. This may take a few minutes."); await refreshModels(); } catch (reason) { setModelMessage(reason instanceof Error ? reason.message : "Could not start download."); } }

  function selectFile(next: File | undefined) { if (next) { setFile(next); setScan(null); setError(""); } }
  function onDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); selectFile(event.dataTransfer.files[0]); }
  function download(extension: "txt" | "md") {
    if (!scan) return;
    const content = extension === "txt"
      ? scan.segments.map(({ start, text }) => `[${start}] ${text}`).join("\n\n")
      : `# ClipScribe clean transcript\n\n${scan.segments.map(({ start, text }) => `## ${start}\n\n${text}`).join("\n\n")}`;
    const url = URL.createObjectURL(new Blob([content], { type: `text/${extension};charset=utf-8` }));
    const link = document.createElement("a"); link.href = url; link.download = `clipscribe-clean.${extension}`; link.click(); URL.revokeObjectURL(url);
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file) return;
    setLoading(true); setError(""); setScan(null);
    try {
      const body = new FormData(); body.append("video", file); body.append("engine", engine);
      const response = await fetch(`${API_URL}/scan`, { method: "POST", body });
      const contentType = response.headers.get("content-type") ?? "";
      const data = contentType.includes("application/json") ? await response.json() : { error: await response.text() };
      if (!response.ok) throw new Error(data.error || "The scan could not finish. Please try again.");
      setScan(data);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The scan could not finish."); }
    finally { setLoading(false); }
  }
  return <main className="shell">
    <header><a className="brand" href="/">clipscribe</a><nav><button type="button" onClick={() => document.querySelector("#scanner")?.scrollIntoView({ behavior: "smooth" })}>scanner</button><button type="button" onClick={() => document.querySelector("#models")?.scrollIntoView({ behavior: "smooth" })}>models</button></nav></header>
    <section id="scanner" className="workbench">
      <form onSubmit={submit} className="source">
        <p className="eyebrow">01 / UPLOAD</p><h2>Video or photo</h2>
        <input id="video" type="file" accept="video/*,image/jpeg,image/png,image/heic,image/heif,image/tiff,image/bmp,image/gif" hidden onChange={(event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0])} />
        <label htmlFor="video" className="drop" onDrop={onDrop} onDragOver={(event) => event.preventDefault()}><b>+</b><strong>{file ? file.name : "Drop a video or photo"}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · click to replace` : "video or image · MP4, MOV, JPG, PNG, HEIC"}</small></label>
        <label className="field">OCR ENGINE<select value={engine} onChange={(event) => setEngine(event.target.value as "vision" | "paddle-vl")}><option value="vision" disabled={models.find((model) => model.id === "apple-vision")?.status === "unavailable"}>Apple Vision — native & fast</option><option value="paddle-vl">PaddleOCR-VL 1.6 — advanced</option></select></label>
        <p className="hint">{engineHelp[engine]}</p><button disabled={!file || loading}>{loading ? "Reading…" : "Get text ↗"}</button>
      </form>
      <section className="results" aria-live="polite"><div className="resultTitle"><div><p className="eyebrow">02 / TRANSCRIPT</p><h2>{scan ? "Ready" : "Your text"}</h2></div>{scan && <div className="actions"><button onClick={() => navigator.clipboard.writeText(scan.text)}>Copy</button><button onClick={() => download("txt")}>.txt</button><button onClick={() => download("md")}>.md</button></div>}</div>
      {loading && <div className="empty"><i className="spinner"/><p>Reading your file…</p></div>}
      {!loading && !scan && <div className="empty"><div className="bars">|||||</div><p>{error || "Text will appear here."}</p></div>}
      {scan && <><div className="stats"><span>{scan.language}</span><span>{scan.frames_processed} FRAMES → {scan.cleaned_blocks} CLEAN BLOCKS</span><span>ENDS {scan.duration}</span></div><div className="transcript">{scan.segments.map((segment, index) => <article key={`${segment.start}-${index}`}><time>{segment.start}</time><p>{segment.text}</p></article>)}</div></>}
      </section>
    </section>
    <section id="models" className="models" aria-labelledby="models-heading"><div className="modelHeading"><p className="eyebrow">MODELS</p><h2 id="models-heading">OCR engines</h2></div><div className="modelList">{models.map((model) => <article key={model.id} className="model"><div><strong>{model.name}</strong><p>{model.id === "apple-vision" ? "Built into your Mac." : "For harder layouts."}</p></div><div className="modelAction"><span className={`status ${model.status}`}>{model.status.replace("-", " ")}</span>{model.id === "paddle-vl" && model.status !== "ready" && <button type="button" onClick={installPaddle} disabled={model.status === "installing"}>{model.status === "installing" ? "Downloading…" : "Download ↗"}</button>}</div></article>)}</div>{modelMessage && <p className="modelMessage">{modelMessage}</p>}</section>
    <footer><span>LOCAL ONLY</span><span>FILES ARE TEMPORARY</span></footer>
  </main>;
}

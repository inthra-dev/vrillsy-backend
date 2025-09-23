"use client";
import { useEffect, useRef, useState } from "react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";

type GenResp = { ok: boolean; job_id: string; task_id: string };

export default function Page() {
  const [audio, setAudio] = useState<File | null>(null);
  const [videos, setVideos] = useState<FileList | null>(null);
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<GenResp | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<any>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setJob(null); setStatus(null);
    if (!audio || !videos || videos.length === 0) {
      setErr("Dodaj audio i co najmniej jedno wideo."); return;
    }
    const fd = new FormData();
    fd.append("audio", audio);
    Array.from(videos).forEach(v => fd.append("videos", v));

    setLoading(true);
    try {
      const r = await fetch(`${BACKEND}/generate`, { method: "POST", body: fd });
      const data = await r.json() as GenResp;
      if (!r.ok || !data?.ok) throw new Error(`HTTP ${r.status}`);
      setJob(data);
    } catch (e:any) { setErr(e?.message || "Błąd połączenia"); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    if (!job?.task_id) return;
    const poll = async () => {
      try {
        const r = await fetch(`${BACKEND}/status/${job.task_id}`);
        const s = await r.json();
        setStatus(s);
        if (s.ready && s.state === "SUCCESS") {
          clearInterval(timer.current);
          timer.current = null;
        }
      } catch { /* ignore */ }
    };
    timer.current = setInterval(poll, 1500);
    poll();
    return () => timer.current && clearInterval(timer.current);
  }, [job?.task_id]);

  const downloadHref = job?.job_id ? `${BACKEND}/download/${job.job_id}` : "#";

  return (
    <main style={{maxWidth: 720, margin: "40px auto", fontFamily: "ui-sans-serif, system-ui", color:"#eaeaea", background:"#0b0b0b"}}>
      <h1 style={{fontSize: 28, fontWeight: 700, marginBottom: 16}}>Vrillsy — 10s reel generator</h1>
      <form onSubmit={submit} style={{display: "grid", gap: 12}}>
        <label>Audio (mp3/wav):
          <input type="file" accept="audio/*" onChange={e=>setAudio(e.target.files?.[0]||null)} />
        </label>
        <label>Videos (mp4/mov) — multi:
          <input type="file" accept="video/*" multiple onChange={e=>setVideos(e.target.files)} />
        </label>
        <button type="submit" disabled={loading} style={{padding:"10px 16px"}}>
          {loading ? "Uploading..." : "Generate"}
        </button>
      </form>

      {err && <pre style={{color:"crimson", marginTop:16}}>ERROR: {err}</pre>}

      {job && (
        <section style={{marginTop:16}}>
          <div><b>job_id:</b> {job.job_id}</div>
          <div><b>task_id:</b> {job.task_id}</div>
        </section>
      )}

      {status && (
        <section style={{marginTop:12}}>
          <div><b>status:</b> {status.state} {status.ready ? "(ready)" : "(processing...)"}</div>
          {status.result?.output && (
            <div style={{marginTop:8}}>
              <a href={downloadHref} target="_blank" rel="noreferrer">⬇️ Download MP4</a>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

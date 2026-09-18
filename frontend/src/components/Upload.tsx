import { useEffect, useState } from "react";
import { createJob, type Job } from "../api";

export function Upload({ onSubmitted }: { onSubmitted: (job: Job) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function submit() {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      onSubmitted(await createJob(file));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <p className="muted">Take a photo of one page of printed sheet music, or pick a scan or screenshot. One page at a time.</p>
      <div
        className={"dropzone" + (over ? " over" : "")}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
      >
        {preview ? <img className="preview" src={preview} alt="Selected page" /> : <span className="muted">Drop an image here</span>}
        <div className="controls">
          <label className="filelabel">
            <input id="camera" type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span className="muted" style={{ cursor: "pointer", textDecoration: "underline" }}>Take a photo</span>
          </label>
          <label className="filelabel">
            <input id="picker" type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span className="muted" style={{ cursor: "pointer", textDecoration: "underline" }}>Choose a file</span>
          </label>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="controls">
        <button className="primary" disabled={!file || busy} onClick={submit}>{busy ? "Uploading…" : "Read the score"}</button>
        {file && <span className="muted">{file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB</span>}
      </div>
    </section>
  );
}

import { useEffect, useState } from "react";
import { getJob, type Job, type JobStatus } from "../api";

const STEPS: { key: JobStatus; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "preprocessing", label: "Preparing image" },
  { key: "recognizing", label: "Reading notes" },
  { key: "postprocessing", label: "Checking measures" },
];

export function Progress({ jobId, onDone }: { jobId: string; onDone: (job: Job) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    async function poll() {
      try {
        const j = await getJob(jobId);
        if (stopped) return;
        setJob(j);
        if (j.status === "done") { onDone(j); return; }
        if (j.status === "failed") return;
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
      timer = window.setTimeout(poll, 2000);
    }
    poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [jobId, onDone]);

  const idx = job ? STEPS.findIndex((s) => s.key === job.status) : 0;
  return (
    <section className="card progress">
      <div className="steps">
        {STEPS.map((s, i) => (
          <span key={s.key} className={"step" + (i < idx ? " done" : i === idx ? " active" : "")}>{s.label}</span>
        ))}
      </div>
      <p className="muted">{job?.message ?? "Contacting the server"}</p>
      {job?.status === "failed" && <div className="error">{job.error ?? "Recognition failed"}</div>}
      {error && <div className="error">{error}</div>}
      <p className="muted">Reading a page takes from a few seconds to a couple of minutes depending on the server. You can keep this tab open in the background.</p>
    </section>
  );
}

import { useEffect, useState } from "react";
import { getJob, type Job, type JobSource, type JobStatus } from "../api";

type Step = { key: JobStatus; label: string };
const PHOTO_STEPS: Step[] = [
  { key: "queued", label: "Queued" },
  { key: "preprocessing", label: "Preparing image" },
  { key: "recognizing", label: "Reading notes" },
  { key: "postprocessing", label: "Checking measures" },
];
/** An imported file has nothing to read: it is opened and checked (plan 0010). */
const FILE_STEPS: Step[] = [
  { key: "queued", label: "Queued" },
  { key: "importing", label: "Opening the file" },
  { key: "postprocessing", label: "Checking measures" },
];

function stepsFor(source: JobSource | undefined): Step[] {
  return source === "musicxml" ? FILE_STEPS : PHOTO_STEPS;
}

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

  const steps = stepsFor(job?.source);
  const idx = job ? steps.findIndex((s) => s.key === job.status) : 0;
  return (
    <section className="card progress">
      <div className="steps">
        {steps.map((s, i) => (
          <span key={s.key} className={"step" + (i < idx ? " done" : i === idx ? " active" : "")}>{s.label}</span>
        ))}
      </div>
      <p className="muted">{job?.message ?? "Contacting the server"}</p>
      {job?.status === "failed" && <div className="error">{job.error ?? "Recognition failed"}</div>}
      {error && <div className="error">{error}</div>}
      <p className="muted">{job?.source === "musicxml"
        ? "Opening a file takes a moment: there is nothing to read, only the measures to check."
        : "Reading a page takes from a few seconds to a couple of minutes depending on the server. You can keep this tab open in the background."}</p>
    </section>
  );
}

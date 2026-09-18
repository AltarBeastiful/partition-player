import { useState } from "react";
import { Upload } from "./components/Upload";
import { Progress } from "./components/Progress";
import { ScoreView } from "./components/ScoreView";
import type { Job } from "./api";

type Screen = { kind: "upload" } | { kind: "progress"; jobId: string } | { kind: "score"; job: Job };

export function App() {
  const [screen, setScreen] = useState<Screen>({ kind: "upload" });

  return (
    <div className="app">
      <header className="topbar">
        <h1>Partition Player</h1>
        {screen.kind !== "upload" && (
          <button onClick={() => setScreen({ kind: "upload" })}>New photo</button>
        )}
      </header>
      {screen.kind === "upload" && <Upload onSubmitted={(job) => setScreen({ kind: "progress", jobId: job.id })} />}
      {screen.kind === "progress" && (
        <Progress jobId={screen.jobId} onDone={(job) => setScreen({ kind: "score", job })} />
      )}
      {screen.kind === "score" && <ScoreView job={screen.job} />}
    </div>
  );
}

import { Upload } from "./components/Upload";
import { Library } from "./components/Library";
import { ScorePage } from "./components/ScorePage";
import { navigate, onLinkClick, scorePath, useRoute } from "./router";

export function App() {
  const route = useRoute();
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/" onClick={onLinkClick}><h1>Partition Player</h1></a>
        {route.kind !== "home" && <a className="button" href="/" onClick={onLinkClick}>Library</a>}
      </header>
      {route.kind === "home" && (
        <>
          <Upload onSubmitted={(job) => navigate(scorePath(job.id))} />
          <Library />
        </>
      )}
      {route.kind === "score" && <ScorePage id={route.id} key={route.id} />}
      {route.kind === "missing" && (
        <section className="card">
          <p>There is nothing at this address.</p>
          <a className="button" href="/" onClick={onLinkClick}>Back to the library</a>
        </section>
      )}
    </div>
  );
}

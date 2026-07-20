/**
 * Knowledge base — the corpus every verdict cites.
 *
 * Exposed as a browsable screen because a citation the user cannot follow is
 * not really a citation. Every `source` string that appears anywhere in the
 * app — on a finding, a passport check, a coach line — resolves to a section
 * on this page.
 *
 * The retrieval backend is shown rather than hidden: BM25 and dense
 * embeddings return the same citations but rank paraphrased queries
 * differently, and a user comparing two searches deserves to know which one
 * they got.
 */

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Search } from "lucide-react";
import * as api from "@/lib/api";
import type { KnowledgeHit } from "@/lib/api";

/** Chunks carry their own heading as the first line so retrieval can match on
 *  it. The citation above the body already shows that heading, so printing it
 *  again reads as a duplication bug. */
function stripHeading(text: string, source: string): string {
  const heading = source.split("§").pop()?.trim();
  const [first, ...rest] = text.split("\n");
  return heading && first.trim() === heading ? rest.join("\n").trim() : text;
}

const EXAMPLES = [
  "Do I need a PIN to receive money?",
  "Is digital arrest real?",
  "Can the RBI hold my savings for verification?",
  "What does an isolation attempt sound like?",
  "Who do I report a fraudulent transfer to?",
];

export function Knowledge() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KnowledgeHit[] | null>(null);
  const [backend, setBackend] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docs, setDocs] = useState<
    { name: string; sections: { source: string; text: string; tags: string[] }[] }[]
  >([]);

  useEffect(() => {
    listAll();
  }, []);

  async function listAll() {
    const res = await api.listDocuments();
    if (res.ok) setDocs(res.data.documents);
    else setError(res.error);
  }

  const search = useCallback(async (q: string) => {
    if (!q.trim()) {
      setHits(null);
      return;
    }
    setBusy(true);
    setError(null);
    const res = await api.searchKnowledge(q, 6);
    setBusy(false);
    if (res.ok) {
      setHits(res.data.results);
      setBackend(res.data.backend);
    } else {
      setError(res.error);
      setHits(null);
    }
  }, []);

  return (
    <div className="page">
      <header className="page__head">
        <p className="label">Understand</p>
        <h1 className="page__title">Knowledge base</h1>
        <p className="page__lede">
          The curated corpus behind every verdict. Each entry is a checkable
          fact about how Indian institutions actually operate, which is what
          makes it usable as evidence rather than as advice.
        </p>
      </header>

      <div className="card">
        <div className="row" style={{ gap: "var(--s-2)" }}>
          <div
            className="row"
            style={{ flex: 1, gap: "var(--s-2)", minWidth: 240, flexWrap: "nowrap" }}
          >
            <Search size={16} className="faint" style={{ flex: "none" }} />
            <input
              className="field"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search(query)}
              placeholder="Ask something — “is a PIN needed to receive money?”"
            />
          </div>
          <button className="btn2 btn2--primary" onClick={() => search(query)} disabled={busy}>
            {busy ? <span className="spinner" /> : <Search size={15} />} Search
          </button>
        </div>

        <div className="row" style={{ marginTop: "var(--s-3)" }}>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              className="btn2 btn2--ghost small"
              onClick={() => {
                setQuery(example);
                search(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>

        {backend && hits && (
          <p className="small faint" style={{ marginTop: "var(--s-3)", marginBottom: 0 }}>
            Ranked by <span className="mono">{backend}</span>
            {backend === "bm25" &&
              " — dense embeddings are not installed, so paraphrased queries rank worse. Citations are exact either way."}
          </p>
        )}
      </div>

      {error && (
        <div className="banner banner--bad" style={{ marginTop: "var(--s-4)" }}>
          <div className="small">{error}</div>
        </div>
      )}

      {hits && (
        <section style={{ marginTop: "var(--s-6)" }}>
          <p className="label" style={{ marginBottom: "var(--s-3)" }}>
            {hits.length} result{hits.length === 1 ? "" : "s"}
          </p>
          <div className="stack">
            {hits.map((hit) => (
              <article className="kbhit" key={hit.source}>
                <div className="kbhit__src">{hit.source}</div>
                <p className="kbhit__text">{stripHeading(hit.text, hit.source)}</p>
              </article>
            ))}
            {!hits.length && (
              <p className="muted small">
                Nothing matched. The corpus is small and deliberately so — every
                section is human-reviewed, which does not scale to everything.
              </p>
            )}
          </div>
        </section>
      )}

      {!hits && docs.length > 0 && (
        <section style={{ marginTop: "var(--s-6)" }}>
          {docs.map((doc) => (
            <div key={doc.name} style={{ marginBottom: "var(--s-6)" }}>
              <p className="label row" style={{ gap: 8, marginBottom: "var(--s-3)" }}>
                <BookOpen size={13} /> {doc.name} · {doc.sections.length} sections
              </p>
              <div className="stack">
                {doc.sections.map((section) => (
                  <details className="kbhit" key={section.source}>
                    <summary className="kbhit__src" style={{ cursor: "pointer" }}>
                      {section.source}
                    </summary>
                    <p className="kbhit__text">
                      {stripHeading(section.text, section.source)}
                    </p>
                  </details>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

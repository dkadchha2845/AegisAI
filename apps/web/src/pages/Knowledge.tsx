/**
 * Knowledge base — the corpus every verdict cites, plus a grounded assistant.
 *
 * Two ways in, one source of truth. The assistant answers a plain-language
 * question, but only from passages it actually retrieved from this corpus — the
 * same passages are shown beneath the answer as citations, so nothing the model
 * says is un-checkable. When no LLM backend is configured it degrades to the
 * passages alone (extractive), never to a made-up answer. Below that, the whole
 * corpus is browsable, because a citation the user cannot follow is not really
 * a citation.
 */

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Search, Sparkles } from "lucide-react";
import * as api from "@/lib/api";
import type { KnowledgeAnswer } from "@/lib/api";

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
  const [result, setResult] = useState<KnowledgeAnswer | null>(null);
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

  const ask = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResult(null);
      return;
    }
    setBusy(true);
    setError(null);
    const res = await api.askKnowledge(q, 6);
    setBusy(false);
    if (res.ok) setResult(res.data);
    else {
      setError(res.error);
      setResult(null);
    }
  }, []);

  return (
    <div className="page">
      <header className="page__head">
        <h1 className="page__title">Learn</h1>
        <p className="page__lede">
          Ask anything about how these scams work and how real banks, police, and
          government offices actually operate. Every answer is drawn from trusted
          advisories and shows exactly where it came from — so you can trust it.
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
              onKeyDown={(e) => e.key === "Enter" && ask(query)}
              placeholder="Ask something — “is a PIN needed to receive money?”"
            />
          </div>
          <button className="btn2 btn2--primary" onClick={() => ask(query)} disabled={busy}>
            {busy ? <span className="spinner" /> : <Sparkles size={15} />} Ask
          </button>
        </div>

        <div className="row" style={{ marginTop: "var(--s-3)" }}>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              className="btn2 btn2--ghost small"
              onClick={() => {
                setQuery(example);
                ask(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="banner banner--bad" style={{ marginTop: "var(--s-4)" }}>
          <div className="small">{error}</div>
        </div>
      )}

      {result && (
        <section style={{ marginTop: "var(--s-5)" }}>
          {/* The synthesized answer, when an LLM is available. */}
          {result.answer && (
            <div className="assistant" data-grounded={result.grounded || undefined}>
              <div className="assistant__head">
                <Sparkles size={15} />
                <span>Answer</span>
                <span className="assistant__src mono">
                  {result.answer_source === "extractive"
                    ? "extractive"
                    : result.answer_source.replace("llm:", "")}{" "}
                  · {result.retrieval_backend}
                </span>
              </div>
              <p className="assistant__body">{result.answer}</p>
              <p className="assistant__foot small faint">
                Grounded in the cited sections below. The assistant phrases; it
                never scores and never adds facts outside this corpus.
              </p>
            </div>
          )}

          {/* Extractive fallback note when no LLM is configured. */}
          {!result.answer && result.grounded && (
            <div className="banner" style={{ marginBottom: "var(--s-4)" }}>
              <Sparkles size={16} />
              <div className="small">
                No language model is configured, so here are the exact corpus
                sections that match — read from the top. Set{" "}
                <span className="mono">PRESAGE_LLM</span> to get a synthesized
                answer.
              </div>
            </div>
          )}

          <p className="label" style={{ margin: "var(--s-4) 0 var(--s-3)" }}>
            {result.citations.length} cited section{result.citations.length === 1 ? "" : "s"}
          </p>
          <div className="stack">
            {result.citations.map((hit) => (
              <article className="kbhit" key={hit.source}>
                <div className="kbhit__src">{hit.source}</div>
                <p className="kbhit__text">{stripHeading(hit.text, hit.source)}</p>
              </article>
            ))}
            {!result.citations.length && (
              <p className="muted small">
                Nothing in the corpus matched. It is small and deliberately so —
                every section is human-reviewed. For a live fraud, call 1930.
              </p>
            )}
          </div>
        </section>
      )}

      {!result && docs.length > 0 && (
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

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
import { BookOpen, ChevronDown, Search, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/States";
import * as api from "@/lib/api";
import type { KnowledgeAnswer } from "@/lib/api";

/** Chunks carry their own heading as the first line so retrieval can match on
 *  it. The citation above the body already shows that heading, so printing it
 *  again reads as a duplication bug. */
function stripHeading(text: string, source: string): string {
  const heading = sectionTitle(source);
  const [first, ...rest] = text.split("\n");
  return heading && first.trim() === heading ? rest.join("\n").trim() : text;
}

/**
 * A citation id is `rbi-advisories.md § No agency conducts a "digital arrest"`.
 * The half after the § is a sentence a person can read; the half before it is
 * a filename in our repository.
 *
 * The audit found this page — the *citizen education* page — rendering the
 * whole id in monospace as the headline of every row, so what someone
 * frightened by a phone call actually saw was a list of
 * `scam-playbooks.md § PAYMENT_EXECUTION`. The heading leads now and the
 * filename becomes provenance underneath, which is what it is. It is not
 * dropped: a citation you cannot trace is not a citation, and the same id is
 * still what `stripHeading` and the retrieval layer key on.
 */
function sectionTitle(source: string): string {
  const tail = source.split("§").pop()?.trim() ?? source;
  if (tail === "intro") return "Overview";
  // Stage labels arrive as contract constants (PAYMENT_EXECUTION).
  if (/^[A-Z][A-Z_]+$/.test(tail)) {
    const words = tail.toLowerCase().replace(/_/g, " ");
    return words.charAt(0).toUpperCase() + words.slice(1);
  }
  return tail;
}

/** `rbi-advisories.md` → `RBI advisories`. Presentation only. */
function docTitle(name: string): string {
  const base = name.replace(/\.md$/, "").replace(/[-_]/g, " ");
  const titled = base.charAt(0).toUpperCase() + base.slice(1);
  return titled
    .replace(/\brbi\b/gi, "RBI")
    .replace(/\bupi\b/gi, "UPI");
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
    <div className="page page--doc">
      <PageHeader
        title="Learn"
        lede="Ask anything about how these scams work and how real banks, police, and government offices actually operate. Every answer is drawn from trusted advisories and shows exactly where it came from — so you can check it."
      />

      <div className="card">
        <div className="row" style={{ gap: "var(--s-2)" }}>
          <div
            className="row"
            style={{ flex: 1, gap: "var(--s-2)", minWidth: 240, flexWrap: "nowrap" }}
          >
            <Search size={16} className="faint" style={{ flex: "none" }} />
            {/* A placeholder is not a label: it is gone the moment there is a
                value, which is exactly when someone re-checking the field
                needs to know what it is. */}
            <label className="vh" htmlFor="kb-ask">Ask a question about these scams</label>
            <input
              id="kb-ask"
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
                <span className="mono">AEGIS_LLM</span> to get a synthesized
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
                <div className="kbhit__head">{sectionTitle(hit.source)}</div>
                <p className="kbhit__text">{stripHeading(hit.text, hit.source)}</p>
                <div className="kbhit__src mono">{hit.source}</div>
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
        <section style={{ marginTop: "var(--s-6)" }} aria-label="Guides">
          {docs.map((doc) => (
            <div key={doc.name} className="guide">
              <h2 className="guide__title">
                <BookOpen size={16} aria-hidden="true" /> {docTitle(doc.name)}
              </h2>
              <p className="guide__meta">
                {doc.sections.length} section{doc.sections.length === 1 ? "" : "s"} ·
                human-reviewed · cited by every verdict
              </p>
              <div className="guide__list">
                {doc.sections.map((section) => (
                  <details className="guide__item" key={section.source}>
                    <summary>
                      <span className="guide__q">{sectionTitle(section.source)}</span>
                      <ChevronDown size={15} aria-hidden="true" className="guide__chev" />
                    </summary>
                    <p className="guide__a">{stripHeading(section.text, section.source)}</p>
                    <p className="guide__src mono">{section.source}</p>
                  </details>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {!result && !docs.length && !error && (
        <div style={{ marginTop: "var(--s-6)" }}>
          <Skeleton lines={5} label="Loading guides" />
        </div>
      )}
    </div>
  );
}

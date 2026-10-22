/**
 * The evidence viewer (G-03) — one submitted artefact beside what the system
 * read from it.
 *
 * A finding is only as good as the reading under it: OCR at 62% confidence and
 * a verbatim paste are different evidence, and a reviewer has to be able to
 * see which one a verdict stands on. So the artefact and every extraction of
 * it sit side by side, each extraction naming its extractor and confidence.
 *
 * Evidence is data, never instructions (invariant 8): text from an artefact is
 * rendered as text — never as HTML, never as a link — whatever it contains.
 * The bytes are shown only from `src`, a URL the caller has already
 * authorised; this component fetches nothing. When the declared type and the
 * bytes disagree, that disagreement is shown, because it is itself a finding.
 */

import { AlertTriangle, FileText } from "lucide-react";
import type { EvidenceItem, ExtractedText } from "@/types/contract";
import { EmptyState, ErrorState, Skeleton } from "./States";

interface Props {
  item: EvidenceItem;
  /** Where the bytes can be read, already authorised. Absent: metadata only. */
  src?: string | null;
  /** Text recovered from this item — `source_ref` should be `item.id`. */
  extracted?: ExtractedText[];
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

function bytes(n: number | null): string | null {
  if (n === null) return null;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function Preview({ item, src }: { item: EvidenceItem; src?: string | null }) {
  const type = item.media_type ?? "";
  const name = item.filename ?? item.id;
  if (item.text && !src) {
    return <pre className="evv__text" tabIndex={0} aria-label={`Submitted text, ${name}`}>{item.text}</pre>;
  }
  if (!src) {
    return <EmptyState inline title="No preview" body="The file is stored, but its bytes are not shown here." icon={<FileText size={20} />} />;
  }
  if (type.startsWith("image/")) return <img className="evv__img" src={src} alt={`Submitted evidence: ${name}`} />;
  if (type.startsWith("audio/")) {
    return (
      <audio className="evv__audio" controls preload="metadata" src={src} aria-label={`Submitted recording: ${name}`}>
        Your browser cannot play this recording.
      </audio>
    );
  }
  return (
    <a className="btn2" href={src} target="_blank" rel="noreferrer noopener">
      Open {name}
    </a>
  );
}

export function EvidenceViewer({ item, src, extracted = [], loading, error, onRetry }: Props) {
  if (loading) return <Skeleton block label="Loading the evidence" />;
  if (error) return <ErrorState inline title="This evidence could not be loaded" detail={error} onRetry={onRetry} />;

  const mismatch = item.declared_type && item.media_type && item.declared_type !== item.media_type;
  const mine = extracted.filter((e) => e.source_ref === item.id);
  const size = bytes(item.size_bytes);

  return (
    <article className="evv" aria-label={`Evidence ${item.filename ?? item.id}`}>
      <div className="evv__media">
        <Preview item={item} src={src} />
      </div>
      <div className="evv__side">
        <dl className="kv evv__meta">
          <dt>Item</dt><dd className="mono">{item.id}</dd>
          <dt>Detected as</dt><dd className="mono">{item.kind}{item.media_type ? ` · ${item.media_type}` : ""}</dd>
          {size && (<><dt>Size</dt><dd className="mono">{size}</dd></>)}
          {item.sha256 && (<><dt>SHA-256</dt><dd className="mono evv__hash" title={item.sha256}>{item.sha256.slice(0, 16)}…</dd></>)}
        </dl>
        {mismatch && (
          <p className="fieldmsg fieldmsg--bad evv__mismatch">
            <AlertTriangle size={14} aria-hidden="true" /> Declared <span className="mono">{item.declared_type}</span>, but the bytes are <span className="mono">{item.media_type}</span>.
          </p>
        )}
        <h3 className="evv__heading">What was read from it</h3>
        {mine.length === 0 ? (
          <p className="small muted">Nothing yet — no extractor has read this item.</p>
        ) : (
          mine.map((e, i) => (
            <section key={`${e.extractor}-${i}`} className="evv__extract">
              <p className="evv__extractmeta small">
                <span className="chip">{e.extractor}</span>
                <span className="mono">{Math.round(e.confidence * 100)}% confidence</span>
                {e.language && <span className="mono">{e.language}</span>}
              </p>
              <pre className="evv__text" tabIndex={0} aria-label={`Text read by ${e.extractor}`}>{e.text}</pre>
            </section>
          ))
        )}
      </div>
    </article>
  );
}

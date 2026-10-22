/**
 * The file dropzone, built once (G-01).
 *
 * Shield and Investigate each had their own. This one keeps what the better
 * of the two got right — a real `<button>` that opens the native file input,
 * so it is reachable and operable by keyboard and every assistive technology
 * already understands what happens — and adds the state both lacked: a
 * **rejected file**, named, with the reason, announced.
 *
 * The checks here are a courtesy so a person learns at once that a 40 MB
 * video will not go. They are not the boundary: the server validates every
 * upload by its magic bytes and size again (CLAUDE.md, Security).
 */

import { FileUp } from "lucide-react";
import { useId, useRef, useState } from "react";

export interface Rejection {
  name: string;
  reason: string;
}

interface Props {
  /** Accepted types: MIME types ("image/png"), wildcards ("image/*") or extensions (".pdf"). */
  accept: string[];
  /** Per-file size cap in bytes. */
  maxBytes: number;
  /** How many files may be chosen at once. */
  maxFiles?: number;
  onFiles: (files: File[]) => void;
  label?: string;
  /** One sentence on what is accepted, shown under the zone. */
  hint?: string;
  disabled?: boolean;
}

function matches(file: File, accept: string[]): boolean {
  const name = file.name.toLowerCase();
  const type = (file.type || "").toLowerCase();
  return accept.some((rule) => {
    const r = rule.toLowerCase();
    if (r.startsWith(".")) return name.endsWith(r);
    if (r.endsWith("/*")) return type.startsWith(r.slice(0, -1));
    return type === r;
  });
}

function size(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

export function Dropzone({
  accept,
  maxBytes,
  maxFiles = 1,
  onFiles,
  label = "Drop a file here, or press to choose",
  hint,
  disabled,
}: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [rejected, setRejected] = useState<Rejection[]>([]);
  const hintId = useId();
  const errId = useId();

  function take(list: FileList | File[]) {
    const files = Array.from(list);
    const ok: File[] = [];
    const bad: Rejection[] = [];
    for (const file of files) {
      if (ok.length >= maxFiles) bad.push({ name: file.name, reason: `at most ${maxFiles} file${maxFiles === 1 ? "" : "s"} at a time` });
      else if (!matches(file, accept)) bad.push({ name: file.name, reason: "this type is not accepted" });
      else if (file.size > maxBytes) bad.push({ name: file.name, reason: `${size(file.size)} is over the ${size(maxBytes)} limit` });
      else ok.push(file);
    }
    setRejected(bad);
    if (ok.length) onFiles(ok);
  }

  return (
    <div className="dz">
      <button
        type="button"
        className="dropzone"
        data-over={over || undefined}
        data-invalid={rejected.length ? true : undefined}
        disabled={disabled}
        aria-describedby={`${hint ? hintId : ""} ${rejected.length ? errId : ""}`.trim() || undefined}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!disabled && e.dataTransfer.files.length) take(e.dataTransfer.files);
        }}
      >
        <FileUp size={22} aria-hidden="true" />
        <span>{label}</span>
      </button>
      <input
        ref={input}
        type="file"
        hidden
        multiple={maxFiles > 1}
        accept={accept.join(",")}
        data-testid="dropzone-input"
        onChange={(e) => {
          if (e.target.files?.length) take(e.target.files);
          e.target.value = "";
        }}
      />
      {hint && <p className="fieldhint" id={hintId}>{hint}</p>}
      <div id={errId} aria-live="polite">
        {rejected.length > 0 && (
          <ul className="fieldmsg fieldmsg--bad dz__rejected">
            {rejected.map((r) => (
              <li key={r.name}>
                <span className="mono">{r.name}</span> — {r.reason}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

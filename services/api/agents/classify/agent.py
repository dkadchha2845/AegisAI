"""
The input classifier as a registered agent, and the one thing it is allowed to
do that no other agent is: change what runs next.

**Why it exists.** ARCHITECTURE.md §2 draws the classifier as the first node,
before the tiers, with every routing edge leaving it. It is an agent so that it
gets the same timeout, error containment, trace span and version pinning as
everything else (task 1.2), and a special node so that its output can reach
`state.input_types` — which is what `can_handle()` reads.

**What it consumes.** `state.inputs` — each `EvidenceItem`'s bytes (read back
from the blob store through `uri`), inline `text`, filename and declared type.

**What it outputs.** An `AgentResult` whose findings carry one `detected_type`
per evidence item, plus a `type_conflict` finding wherever the declared type or
the extension contradicts the bytes. `apply_to_state()` turns those findings
back into `inputs[].kind` and `input_types`.

**How it connects.** The graph's classify node runs it, then applies it. That
coupling — findings out, state in — is deliberate and one-directional, and
`test_input_classifier.py` pins it, because a text format between two modules is
exactly what drifts silently.

**How it is evaluated.** ≥98% on a 200-item corpus with 20 adversarial members,
measured in `test_input_classifier.py`, which prints every miss.

**Limitations, stated.** An item whose bytes are gone — never stored, or
erased since — and which carries no inline text is UNKNOWN, which routes to the
text agent rather than crashing; that is the third acceptance criterion, and it
is the same outcome an unreadable blob produces. The agent does not open the
network, does not decompress anything, and never executes an upload.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from schema.models import (
    AgentResult,
    AgentStatus,
    EvidenceItem,
    Finding,
    InputType,
    InvestigationState,
)
from services.api.agents import registry
from services.api.agents.base import AgentContext, Stage
from services.api.agents.classify.sniff import (
    UNKNOWN_WITH_TEXT,
    Detection,
    classify_bytes,
    classify_inline_text,
)
from services.api.stores.blobs import BlobRejected, EvidenceBlobs

#: Findings are the agent's output vocabulary, so the labels are part of the
#: contract between this agent and the graph node that applies it.
TYPE_FINDING = "detected_type"
CONFLICT_FINDING = "type_conflict"
MEDIA_FINDING = "detected_media_type"


def detect_item(item: EvidenceItem, blob: Optional[bytes] = None) -> Detection:
    """Classify one evidence item.

    `blob` is a parameter rather than something this function fetches, so the
    200-case corpus can be classified from bytes in a test without a store, a
    filesystem or a tenant. `_blob_of` is the one place that reaches storage.
    """
    if blob:
        return classify_bytes(blob, filename=item.filename, declared_type=item.declared_type)
    if item.text is not None:
        return classify_inline_text(item.text)
    return Detection(types=UNKNOWN_WITH_TEXT, reason="no_content", confidence=0.0)


@registry.register
class InputClassifierAgent:
    """Decides what each piece of evidence is. Every routing edge starts here."""

    name = "input_classifier"
    version = "1.0.0"
    stage = Stage.EXTRACT

    def can_handle(self, state: InvestigationState) -> bool:
        """Anything with evidence attached. Notably *not* keyed on
        `input_types` — this is the agent that produces them."""
        return bool(state.inputs)

    async def run(self, state: InvestigationState, ctx: AgentContext) -> AgentResult:
        findings: List[Finding] = []
        counts: Dict[str, float] = {}
        conflicts = 0

        for item in state.inputs:
            detection = detect_item(item, blob=_blob_of(item, state.org_id))
            for kind in detection.types:
                findings.append(
                    Finding(
                        label=TYPE_FINDING,
                        value=kind.value,
                        confidence=detection.confidence,
                        source=detection.reason,
                        detail=item.id,
                    )
                )
                counts[f"input_type:{kind.value}"] = counts.get(f"input_type:{kind.value}", 0.0) + 1.0
            if detection.media_type:
                findings.append(
                    Finding(
                        label=MEDIA_FINDING,
                        value=detection.media_type,
                        confidence=detection.confidence,
                        source=detection.reason,
                        detail=item.id,
                    )
                )
            for conflict in detection.conflicts:
                conflicts += 1
                findings.append(
                    Finding(
                        label=CONFLICT_FINDING,
                        value=conflict,
                        confidence=1.0,
                        source="declared_vs_detected",
                        detail=item.id,
                    )
                )

        counts["type_conflicts"] = float(conflicts)
        return AgentResult(
            agent=self.name,
            version=self.version,
            status=AgentStatus.OK,
            confidence=1.0 if state.inputs else 0.0,
            findings=findings,
            features=counts,
            provenance=["magic_bytes", "extension", "content"],
        )


def _blob_of(item: EvidenceItem, org_id: str) -> Optional[bytes]:
    """The bytes behind an evidence item's `uri`, or None.

    Task 1.6 filled this in. It used to be a hook returning nothing, because
    there was nowhere for an upload's bytes to live and pretending otherwise
    would have meant an agent that silently classified nothing; the lifecycle
    API's blob store is what changed that, and magic-byte routing only became
    real for uploads at that moment.

    Scoped to the state's own organisation, so an item carrying another
    tenant's uri reads as absent rather than as evidence — the store refuses it,
    and the item falls through to its inline text or to UNKNOWN, which is the
    documented safe route. A missing blob is likewise not an error: erasure may
    have removed it between the write and this read, and an investigation that
    crashed because a file was legitimately deleted would be worse than one that
    classifies from what is left.
    """
    if not item.uri:
        return None
    try:
        return EvidenceBlobs(org_id).read(item.uri)
    except (BlobRejected, ValueError, OSError):
        return None


# --------------------------------------------------------------------------
# Applying the result back onto the state
# --------------------------------------------------------------------------


def apply_to_state(state: InvestigationState, result: AgentResult) -> Dict[str, object]:
    """Turn the classifier's findings into `inputs[].kind` and `input_types`.

    The union across items is ordered by `InputType`'s own declaration order
    rather than by discovery, so two runs over the same evidence produce the
    same list — determinism starts at the first node, not at the fan-out.

    A result that is not OK leaves the state alone and yields no types. That is
    the honest outcome: routing on a partial classification would silently run
    the wrong agents, where routing on nothing runs the text agent, which is the
    documented fallback.
    """
    if result.status is not AgentStatus.OK:
        return {}

    per_item: Dict[str, List[InputType]] = {}
    media: Dict[str, str] = {}
    for finding in result.findings:
        item_id = finding.detail or ""
        if finding.label == TYPE_FINDING and finding.value:
            per_item.setdefault(item_id, []).append(InputType(finding.value))
        elif finding.label == MEDIA_FINDING and finding.value:
            media[item_id] = finding.value

    updated: List[EvidenceItem] = []
    for item in state.inputs:
        kinds = per_item.get(item.id) or [InputType.UNKNOWN]
        updated.append(
            item.model_copy(
                update={
                    "kind": kinds[0],
                    "media_type": media.get(item.id, item.media_type),
                }
            )
        )

    found = {k for kinds in per_item.values() for k in kinds}
    ordered = [t for t in InputType if t in found]
    return {"inputs": updated, "input_types": ordered}


def types_for(state: InvestigationState) -> Sequence[Tuple[str, InputType]]:
    """`(item_id, kind)` pairs — for the report and the trace view."""
    return [(item.id, item.kind) for item in state.inputs]

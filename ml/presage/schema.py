"""
PRESAGE — output schema for generated calls.

Enforced server-side via `output_config.format`, so the generator never has to
defend against malformed JSON, markdown fences, or a chatty preamble. Note the
structured-output constraints: every object needs `additionalProperties: false`
and an explicit `required` list, and string length/pattern constraints are not
supported (validate those client-side instead).
"""

from __future__ import annotations

from .taxonomy import LABELS

# Victim emotional state, labelled per turn. This is a second free supervision
# signal riding along with the stage label: it trains the text side of the
# Coercion Radar without a separate generation pass. CALLER turns use "NA".
VICTIM_STATES: list[str] = [
    "NA",
    "CALM",
    "CONFUSED",
    "ANXIOUS",
    "PANICKED",
    "COMPLIANT",
    "RESISTING",
]

CALL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "turns": {
            "type": "array",
            "description": "The call transcript in order, alternating naturally.",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {
                        "type": "string",
                        "enum": ["CALLER", "VICTIM"],
                    },
                    "text": {
                        "type": "string",
                        "description": (
                            "The utterance as romanised Hinglish, exactly as a "
                            "speech-to-text system would transcribe it. No "
                            "Devanagari, no stage directions, no speaker labels."
                        ),
                    },
                    "stage": {
                        "type": "string",
                        "enum": LABELS,
                        "description": (
                            "The scam stage this utterance belongs to. Applies to "
                            "victim turns too -- label the stage of the exchange "
                            "the utterance sits in, not the victim's own intent."
                        ),
                    },
                    "victim_state": {
                        "type": "string",
                        "enum": VICTIM_STATES,
                        "description": "Victim emotional state. 'NA' for CALLER turns.",
                    },
                },
                "required": ["speaker", "text", "stage", "victim_state"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["turns"],
    "additionalProperties": False,
}

OUTPUT_CONFIG: dict = {"format": {"type": "json_schema", "schema": CALL_SCHEMA}}

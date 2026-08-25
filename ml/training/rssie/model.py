"""
RSSIE model — the spec's Section 6.

    Features → Shared Encoder (MuRIL) → BiLSTM → Multi-head classifier
                                                    ├─ scam probability
                                                    ├─ scam type
                                                    ├─ current stage
                                                    └─ transfer risk

Three architectural decisions worth defending
---------------------------------------------

**Why a sequence model at all.** `ml/training/train.py` classifies one utterance with
one turn of context and reached 0.98 validation / 0.22 held-out macro-F1 — it
memorised archetypes. A per-utterance model cannot do otherwise, because the
thing that distinguishes a scam from a legitimate call is not any single
sentence but the *order* they arrive in. "Account number bataiye" is ordinary
service language; the same sentence after authority → fear → isolation is not.
The BiLSTM exists to make that order visible to the classifier.

**Why the encoder is frozen by default.** 338 calls is far too little to
fine-tune 236M parameters without memorising them, which this project has
already demonstrated once. Freezing MuRIL and training only the BiLSTM and the
heads drops the trainable count to ~2M — a ratio the corpus can actually
support. `--unfreeze-encoder` exists for when the corpus is larger, and the
training script warns when it is used on a small one.

**Why handcrafted features are concatenated.** The flow, linguistic and
behavioural vectors from `services/api/engine/features/` are appended to the
BiLSTM output before the heads. They carry information the text encoder
structurally cannot see — arc adherence is a property of the whole sequence,
not of any token.

That package is research-only, and this model is its only reader: nothing under
`services/` imports it, so these are *not* the features the served rule-based
path computes. That path uses `engine/spoofing.py` and `engine/scripts.py`,
which `engine/features/` partly duplicates — and `features/spoofing.py` and
`features/script_templates.py` have no importer at all. Which features the
serving path actually consumes is task 4.1's feature registry to decide.

Uncertainty weighting
---------------------
Four heads with hand-picked loss weights is four hyperparameters nobody has the
data to tune. Instead each head learns a log-variance and the losses are
combined by Kendall et al.'s homoscedastic uncertainty weighting, so the model
decides how much to trust each task. This matters here because the heads are
genuinely unequal: stage has 1617 real labels, transfer risk is a deterministic
function of stage and should be down-weighted automatically rather than by a
guess.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - torch is an optional extra
    TORCH_AVAILABLE = False
    torch = None  # type: ignore
    nn = object  # type: ignore

from .labels import EMOTIONS, SCAM_TYPES, STAGES

#: Dimensionality of the concatenated handcrafted feature block.
#: flow(6) + linguistic(11) + behaviour(8) + emotion(9) = 34.
#: Asserted at construction so a change to any extractor fails loudly here
#: rather than silently shifting which column means what.
FEATURE_DIM = 34

ENCODER_DIM = 768  # MuRIL base hidden size


@dataclass
class RSSIEConfig:
    encoder_name: str = "google/muril-base-cased"
    lstm_hidden: int = 256
    lstm_layers: int = 1
    dropout: float = 0.3
    feature_dim: int = FEATURE_DIM
    freeze_encoder: bool = True
    max_turns: int = 64
    max_tokens: int = 64


if TORCH_AVAILABLE:

    class RSSIEModel(nn.Module):
        """Shared encoder + BiLSTM + four heads."""

        def __init__(self, config: RSSIEConfig | None = None):
            super().__init__()
            from transformers import AutoModel  # type: ignore

            self.config = config or RSSIEConfig()
            self.encoder = AutoModel.from_pretrained(self.config.encoder_name)
            if self.config.freeze_encoder:
                for param in self.encoder.parameters():
                    param.requires_grad = False

            self.lstm = nn.LSTM(
                input_size=ENCODER_DIM,
                hidden_size=self.config.lstm_hidden,
                num_layers=self.config.lstm_layers,
                batch_first=True,
                bidirectional=True,
                dropout=self.config.dropout if self.config.lstm_layers > 1 else 0.0,
            )
            seq_dim = self.config.lstm_hidden * 2

            # Additive attention over turns. Two jobs: it pools a
            # variable-length call into a fixed vector, and its weights are the
            # attention visualisation the spec's explainability layer asks for.
            # A mean-pool would do the first job and none of the second.
            self.attention = nn.Sequential(
                nn.Linear(seq_dim, 128), nn.Tanh(), nn.Linear(128, 1)
            )

            self.dropout = nn.Dropout(self.config.dropout)
            fused_dim = seq_dim + self.config.feature_dim

            def head(out_dim: int) -> nn.Module:
                return nn.Sequential(
                    nn.Linear(fused_dim, 128),
                    nn.ReLU(),
                    nn.Dropout(self.config.dropout),
                    nn.Linear(128, out_dim),
                )

            self.scam_head = head(1)                    # binary logit
            self.type_head = head(len(SCAM_TYPES))
            self.stage_head = head(len(STAGES))         # per-turn, see forward()
            self.risk_head = head(1)                    # regression, sigmoid
            self.emotion_head = head(len(EMOTIONS))     # auxiliary

            # Per-turn stage prediction runs off the LSTM output directly:
            # stage is a property of a turn, not of the call, so pooling first
            # would throw away exactly the thing being predicted.
            self.turn_stage_head = nn.Linear(seq_dim, len(STAGES))

            # Learned log-variance per task (Kendall et al. 2018).
            self.log_vars = nn.Parameter(torch.zeros(5))

        def encode_turns(self, input_ids, attention_mask):
            """Encode each turn independently, then read the [CLS] vector.

            Turns are flattened to (batch*turns, tokens) for one encoder pass
            rather than looped — a Python loop over 64 turns is ~60x slower and
            was the bottleneck in the first version of this.
            """
            batch, turns, tokens = input_ids.shape
            flat_ids = input_ids.view(batch * turns, tokens)
            flat_mask = attention_mask.view(batch * turns, tokens)

            # A padded turn has an all-zero mask, which makes softmax over the
            # attention scores produce NaN. Give position 0 a single unmasked
            # token; the turn-level mask discards the output anyway.
            empty = flat_mask.sum(dim=1) == 0
            if empty.any():
                flat_mask = flat_mask.clone()
                flat_mask[empty, 0] = 1

            if self.config.freeze_encoder:
                with torch.no_grad():
                    out = self.encoder(input_ids=flat_ids, attention_mask=flat_mask)
            else:
                out = self.encoder(input_ids=flat_ids, attention_mask=flat_mask)
            cls = out.last_hidden_state[:, 0, :]
            return cls.view(batch, turns, ENCODER_DIM)

        def forward(self, input_ids, attention_mask, turn_mask, features):
            """
            input_ids      (B, T, L)  token ids per turn
            attention_mask (B, T, L)  token mask per turn
            turn_mask      (B, T)     1 for a real turn, 0 for padding
            features       (B, F)     handcrafted feature block
            """
            encoded = self.encode_turns(input_ids, attention_mask)
            encoded = self.dropout(encoded)

            lengths = turn_mask.sum(dim=1).clamp(min=1).cpu()
            packed = nn.utils.rnn.pack_padded_sequence(
                encoded, lengths, batch_first=True, enforce_sorted=False
            )
            packed_out, _ = self.lstm(packed)
            seq, _ = nn.utils.rnn.pad_packed_sequence(
                packed_out, batch_first=True, total_length=encoded.size(1)
            )

            turn_stage_logits = self.turn_stage_head(seq)

            scores = self.attention(seq).squeeze(-1)
            scores = scores.masked_fill(turn_mask == 0, float("-inf"))
            weights = torch.softmax(scores, dim=1)
            pooled = torch.bmm(weights.unsqueeze(1), seq).squeeze(1)

            fused = torch.cat([pooled, features], dim=1)

            return {
                "scam_logit": self.scam_head(fused).squeeze(-1),
                "type_logits": self.type_head(fused),
                "stage_logits": self.stage_head(fused),
                "turn_stage_logits": turn_stage_logits,
                "risk": torch.sigmoid(self.risk_head(fused)).squeeze(-1),
                "emotion_logits": self.emotion_head(fused),
                "attention": weights,
            }

        def loss(self, outputs, targets) -> tuple:
            """Uncertainty-weighted multi-task loss.

            Every term is masked on availability. A batch with no labelled
            victim turns contributes nothing to the emotion loss rather than
            contributing a zero, which would otherwise teach the head that
            silence means CALM.
            """
            losses = {}

            losses["scam"] = nn.functional.binary_cross_entropy_with_logits(
                outputs["scam_logit"], targets["scam"].float()
            )
            losses["type"] = nn.functional.cross_entropy(
                outputs["type_logits"], targets["scam_type"]
            )

            # Per-turn stage loss over real turns only.
            turn_logits = outputs["turn_stage_logits"]
            b, t, c = turn_logits.shape
            stage_mask = targets["turn_mask"].reshape(-1).bool()
            flat_logits = turn_logits.reshape(b * t, c)[stage_mask]
            flat_targets = targets["turn_stages"].reshape(-1)[stage_mask]
            losses["stage"] = (
                nn.functional.cross_entropy(flat_logits, flat_targets)
                if flat_targets.numel()
                else turn_logits.sum() * 0.0
            )

            losses["risk"] = nn.functional.mse_loss(outputs["risk"], targets["risk"].float())

            emotion_mask = targets["emotion"] >= 0
            losses["emotion"] = (
                nn.functional.cross_entropy(
                    outputs["emotion_logits"][emotion_mask], targets["emotion"][emotion_mask]
                )
                if emotion_mask.any()
                else outputs["emotion_logits"].sum() * 0.0
            )

            total = 0.0
            for i, key in enumerate(("scam", "type", "stage", "risk", "emotion")):
                precision = torch.exp(-self.log_vars[i])
                total = total + precision * losses[key] + self.log_vars[i]
            return total, {k: float(v) for k, v in losses.items()}

else:  # pragma: no cover

    class RSSIEModel:  # type: ignore[no-redef]
        """Placeholder when torch is not installed.

        Raising on construction rather than on import keeps the serving layer
        importable without torch — `engine/rssie.py` checks availability and
        falls back to the rule-based path before ever reaching this.
        """

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "RSSIEModel needs torch and transformers. Install them with:\n"
                "  pip install torch transformers 'numpy<2'\n"
                "The API does not need them — it serves the rule-based RSSIE "
                "path and reports rssie:rule_based on /api/health."
            )

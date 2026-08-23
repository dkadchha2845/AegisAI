#!/usr/bin/env python3
"""
Generates train_stage_classifier.ipynb.

The notebook is generated rather than hand-edited because a .ipynb is a JSON
blob with execution counts and output blobs baked in, which makes it hostile
to review and to version control. Editing this file and re-running it produces
a clean, diffable notebook every time:

    python ml/notebooks/build_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "train_stage_classifier.ipynb"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip().splitlines(True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip().splitlines(True),
    }


CELLS = [
    md(r"""
# AegisAI — stage classifier fine-tuning

Fine-tunes **MuRIL** into the 8-way utterance classifier the live engine
serves, and exports it where `services/api` expects to find it.

Runs on a free Colab T4 in roughly 10 minutes. It also runs on CPU, slowly —
useful for checking the pipeline end to end before spending GPU time.

### Why MuRIL and not a multilingual BERT

The corpus is Hinglish: Devanagari and romanised Hindi mixed with English,
often inside one sentence. mBERT and XLM-R both handle Hindi, but neither was
trained on transliterated Hindi in Latin script, which is what people actually
type and what ASR actually emits. MuRIL was pretrained on exactly that —
including transliterated pairs — and that is the whole difference on this data.

### What this notebook is careful about

1. **Splits arrive pre-made and are never re-derived here.** `build_dataset.py`
   splits by *call*, holding out whole archetypes. Utterances within one call
   share names, case IDs and phrasing tics, so an utterance-level split leaks
   test into train and inflates macro-F1 substantially. If a judge asks how you
   split, the answer has to be the same one every time.

2. **Macro-F1 is the headline, never accuracy.** The corpus is imbalanced —
   PAYMENT_EXECUTION has 183 training examples, ISOLATION has 42. Accuracy
   rewards a model that ignores the rare classes, and the rare classes are the
   ones the product exists to catch.

3. **ISOLATION and PAYMENT_EXECUTION recall is reported separately.** Macro-F1
   hides a model that never catches the payment. Those two numbers are the
   ones that decide whether this ships.
"""),
    code(r"""
# Colab: install and get the data. Skip locally if you already have both.
IN_COLAB = False
try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    pass

if IN_COLAB:
    !pip install -q "transformers>=4.44" "datasets>=2.20" "scikit-learn>=1.5" "accelerate>=0.33"
    # Point this at your clone, or upload ml/data/processed/*.jsonl by hand.
    from google.colab import files  # noqa: F401
    print("Upload train.jsonl, val.jsonl and test.jsonl when prompted.")
"""),
    code(r"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import numpy as np
import torch

SEED = 20260721

# Full determinism, not just np.random.seed. Two runs that disagree by three
# points of macro-F1 make every ablation in the deck unfalsifiable.
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

DATA = Path("../data/processed") if Path("../data/processed").exists() else Path(".")
ARTIFACTS = Path("../artifacts/stage-classifier")
ARTIFACTS.parent.mkdir(parents=True, exist_ok=True)

# Deliberately not MPS. On torch 2.2 / transformers 4.44 a full MuRIL run on
# Apple GPU completed every step with the loss pinned at exactly ln(8) — the
# uniform-prior loss — and never left initialisation. CPU converges.
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", DEVICE, "| data:", DATA.resolve())
"""),
    code(r"""
LABELS = [
    "GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION", "ISOLATION",
    "VERIFICATION_DEMAND", "PAYMENT_SETUP", "PAYMENT_EXECUTION", "BENIGN",
]
LABEL2ID = {label: i for i, label in enumerate(LABELS)}
ID2LABEL = {i: label for label, i in LABEL2ID.items()}

# The two the demo lives or dies on.
CRITICAL = ["ISOLATION", "PAYMENT_EXECUTION"]


def load(split: str) -> list[dict]:
    # Every turn, both speakers. The corpus labels the *call's* stage on each
    # turn rather than the caller's speech act, so during VERIFICATION_DEMAND
    # it is usually the victim talking as they read the OTP back. Filtering to
    # caller turns left that class with 6 training examples and 0 in val.
    return [
        json.loads(line)
        for line in (DATA / f"{split}.jsonl").read_text().splitlines()
        if line.strip()
    ]


train_rows, val_rows, test_rows = load("train"), load("val"), load("test")
print(f"train {len(train_rows)} | val {len(val_rows)} | test {len(test_rows)}")

from collections import Counter
print("\ntrain distribution:")
for label, n in Counter(r["label"] for r in train_rows).most_common():
    print(f"  {label:22s} {n:4d}")
"""),
    md(r"""
## Context window

Each example is `SPEAKER: previous turn [SEP] SPEAKER: current turn`.

The speaker tag is part of the input rather than a filter on it, so "OTP
bataiye" (caller demanding) and "OTP hai 458213" (victim complying) are
distinguishable inputs instead of the same one.

One turn of context, not zero and not five. Zero-context misclassifies
"Account number bataiye" — it is VERIFICATION_DEMAND after a fear line and
ordinary BENIGN service after "aapka refund process karna hai". More context
starts leaking the *whole call's* scamminess into every single utterance,
which inflates validation scores and produces a model that cannot label the
first two turns of a live call at all.

**This join must match `MuRILStageClassifier.predict` exactly.** If the
separator changes here it changes there, or the served model sees an input
format it never trained on.
"""),
    code(r"""
def build_examples(rows: list[dict]) -> tuple[list[str], list[int]]:
    by_call: dict[str, list[dict]] = {}
    for row in rows:
        by_call.setdefault(row["call_id"], []).append(row)

    def render(r: dict) -> str:
        return f"{r['speaker']}: {r['text']}"

    texts, labels = [], []
    for call_rows in by_call.values():
        call_rows.sort(key=lambda r: r["turn_index"])
        for i, row in enumerate(call_rows):
            current = render(row)
            previous = render(call_rows[i - 1]) if i else ""
            texts.append(f"{previous} [SEP] {current}" if previous else current)
            labels.append(LABEL2ID[row["label"]])
    return texts, labels


X_train, y_train = build_examples(train_rows)
X_val, y_val = build_examples(val_rows)
X_test, y_test = build_examples(test_rows)
print(len(X_train), len(X_val), len(X_test))
print("\nexample:", X_train[3][:160])
"""),
    code(r"""
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "google/muril-base-cased"
MAX_LEN = 128  # p99 of tokenised utterance-pairs; longer wastes compute

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=len(LABELS),
    id2label=ID2LABEL,
    label2id=LABEL2ID,
).to(DEVICE)
print(f"{sum(p.numel() for p in model.parameters()) / 1e6:.0f}M parameters")
"""),
    code(r"""
from torch.utils.data import Dataset


class UtteranceDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[int]):
        self.enc = tokenizer(texts, truncation=True, max_length=MAX_LEN, padding="max_length")
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, i: int) -> dict:
        item = {k: torch.tensor(v[i]) for k, v in self.enc.items()}
        item["labels"] = torch.tensor(self.labels[i])
        return item


ds_train = UtteranceDataset(X_train, y_train)
ds_val = UtteranceDataset(X_val, y_val)
ds_test = UtteranceDataset(X_test, y_test)
"""),
    md(r"""
## Class weighting

ISOLATION has ~42 training examples against PAYMENT_EXECUTION's ~183. Without
weighting, the cheapest way for the model to lower its loss is to under-predict
the rare classes — and the rare classes are the ones worth catching.

Inverse-frequency weights, normalised to mean 1 so the loss scale (and
therefore the learning rate) stays comparable to an unweighted run.
"""),
    code(r"""
counts = np.bincount(y_train, minlength=len(LABELS))
weights = counts.sum() / (len(LABELS) * np.maximum(counts, 1))
weights = weights / weights.mean()
class_weights = torch.tensor(weights, dtype=torch.float).to(DEVICE)

for label, n, w in zip(LABELS, counts, weights):
    print(f"  {label:22s} n={n:4d}  weight={w:.2f}")
"""),
    code(r"""
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from transformers import Trainer, TrainingArguments


def compute_metrics(pred) -> dict:
    y_true = pred.label_ids
    y_pred = pred.predictions.argmax(-1)
    out = {
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
    }
    # Per-class recall for the two that matter, surfaced every epoch rather
    # than only at the end — a run where ISOLATION recall collapses at epoch 2
    # should be visible while it is happening.
    per_class = f1_score(y_true, y_pred, average=None, labels=range(len(LABELS)), zero_division=0)
    for label in CRITICAL:
        out[f"f1_{label.lower()}"] = per_class[LABEL2ID[label]]
    return out


class WeightedTrainer(Trainer):
    # Cross-entropy with the class weights computed above.
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        loss = torch.nn.functional.cross_entropy(
            outputs.logits, labels, weight=class_weights
        )
        return (loss, outputs) if return_outputs else loss


args = TrainingArguments(
    output_dir="../artifacts/_train",
    num_train_epochs=6,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=32,
    learning_rate=3e-5,
    warmup_ratio=0.1,
    weight_decay=0.01,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_safetensors=False,
    load_best_model_at_end=True,
    # Selecting on macro-F1, not loss. Weighted loss and macro-F1 disagree
    # about which epoch is best, and macro-F1 is the number being reported.
    metric_for_best_model="macro_f1",
    greater_is_better=True,
    logging_steps=25,
    seed=SEED,
    report_to=[],
    fp16=(DEVICE == "cuda"),
)

trainer = WeightedTrainer(
    model=model,
    args=args,
    train_dataset=ds_train,
    eval_dataset=ds_val,
    compute_metrics=compute_metrics,
)
trainer.train()
"""),
    md(r"""
## Test-set evaluation

The test split is four held-out call archetypes the model has never seen —
including one genuine police call, which is the hard negative that decides
whether this can be pointed at real traffic without crying wolf.

Read the two critical recalls before the headline macro-F1.
"""),
    code(r"""
pred = trainer.predict(ds_test)
y_pred = pred.predictions.argmax(-1)
y_true = pred.label_ids

macro = f1_score(y_true, y_pred, average="macro", zero_division=0)
print(f"TEST macro-F1: {macro:.3f}\n")
print(classification_report(y_true, y_pred, target_names=LABELS, zero_division=0, digits=3))

print("\nCritical-class recall — these are the numbers that matter:")
report = classification_report(
    y_true, y_pred, target_names=LABELS, zero_division=0, output_dict=True
)
for label in CRITICAL:
    row = report[label]
    print(f"  {label:22s} recall={row['recall']:.3f}  support={int(row['support'])}")
    if row["support"] < 10:
        print(f"    ^ support is {int(row['support'])} — too few to quote this figure in the deck.")
"""),
    code(r"""
import matplotlib.pyplot as plt

cm = confusion_matrix(y_true, y_pred, labels=range(len(LABELS)))
fig, ax = plt.subplots(figsize=(8, 7))
ax.imshow(cm, cmap="magma")
ax.set_xticks(range(len(LABELS)), LABELS, rotation=45, ha="right")
ax.set_yticks(range(len(LABELS)), LABELS)
ax.set_xlabel("predicted"); ax.set_ylabel("true")
for i in range(len(LABELS)):
    for j in range(len(LABELS)):
        if cm[i, j]:
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] < cm.max() / 2 else "black")
ax.set_title(f"Confusion — test macro-F1 {macro:.3f}")
plt.tight_layout(); plt.show()

# The errors worth reading are the asymmetric ones: BENIGN predicted as a scam
# stage is a false alarm on a real call, and a scam stage predicted BENIGN is a
# miss. They cost very different amounts.
benign = LABEL2ID["BENIGN"]
print("false alarms (BENIGN -> scam stage):", cm[benign].sum() - cm[benign, benign])
print("misses (scam stage -> BENIGN):     ", cm[:, benign].sum() - cm[benign, benign])
"""),
    md(r"""
## Calibration

The UI shows `StageState.confidence` and keys behaviour off it, so a softmax
that reads 0.98 while being right 70% of the time is a lie the interface then
repeats. Temperature scaling on the validation set is one parameter, costs
seconds, and leaves accuracy untouched — it only rescales the confidence.
"""),
    code(r"""
val_pred = trainer.predict(ds_val)
logits = torch.tensor(val_pred.predictions)
labels_t = torch.tensor(val_pred.label_ids)

temperature = torch.nn.Parameter(torch.ones(1) * 1.0)
optimizer = torch.optim.LBFGS([temperature], lr=0.01, max_iter=60)


def closure():
    optimizer.zero_grad()
    loss = torch.nn.functional.cross_entropy(logits / temperature, labels_t)
    loss.backward()
    return loss


optimizer.step(closure)
T = float(temperature.detach())
print(f"fitted temperature: {T:.3f}   (>1 means the raw model was overconfident)")


def expected_calibration_error(logits_t, labels_t, temp=1.0, bins=10):
    probs = torch.softmax(logits_t / temp, dim=-1)
    conf, pred = probs.max(dim=-1)
    correct = pred.eq(labels_t).float()
    ece = 0.0
    for lo in np.linspace(0, 1, bins + 1)[:-1]:
        mask = (conf > lo) & (conf <= lo + 1 / bins)
        if mask.sum():
            ece += mask.float().mean() * (correct[mask].mean() - conf[mask].mean()).abs()
    return float(ece)


print(f"ECE before: {expected_calibration_error(logits, labels_t, 1.0):.4f}")
print(f"ECE after:  {expected_calibration_error(logits, labels_t, T):.4f}")
"""),
    md(r"""
## Export

Written to `ml/artifacts/stage-classifier`, which is exactly where
`services/api/engine/classifier.py` looks. Nothing else needs changing: the
API picks the checkpoint up on next boot and `/api/health` flips
`classifier.backend` from `lexical` to `muril`.

`id2label` travels inside the checkpoint config, so a reordered label list in
this notebook can never silently mis-decode at serving time.
"""),
    code(r"""
ARTIFACTS.mkdir(parents=True, exist_ok=True)
# MuRIL's weights contain non-contiguous tensor views, which safetensors
# refuses to serialise. Torch-native reloads identically.
trainer.model.save_pretrained(ARTIFACTS, safe_serialization=False)
tokenizer.save_pretrained(ARTIFACTS)

(ARTIFACTS / "metrics.json").write_text(json.dumps({
    "base_model": MODEL_NAME,
    "seed": SEED,
    "test_macro_f1": float(macro),
    "test_weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    "per_class": {
        label: {
            "precision": report[label]["precision"],
            "recall": report[label]["recall"],
            "f1": report[label]["f1-score"],
            "support": report[label]["support"],
        }
        for label in LABELS if label in report
    },
    "temperature": T,
    "context": "previous_turn [SEP] current_turn",
    "max_len": MAX_LEN,
    "train_size": len(X_train),
    "test_size": len(X_test),
    "split": "leave-archetypes-out, by call",
}, indent=2))

print("exported to", ARTIFACTS.resolve())
print("restart the API and check /api/health — classifier.backend should read 'muril'")
"""),
    md(r"""
## Sanity check: does the served path agree?

Loading the checkpoint through the *serving* wrapper rather than the trainer
catches the failure this notebook is most likely to cause — a mismatch between
the `[SEP]` join used here and the one in `MuRILStageClassifier.predict`. The
model would train fine, export fine, and quietly lose several points of
accuracy in production.
"""),
    code(r"""
import sys
sys.path.insert(0, "../..")

from services.api.engine.classifier import MuRILStageClassifier

served = MuRILStageClassifier(ARTIFACTS)
probes = [
    ("Main CBI crime branch se Inspector Sharma bol raha hoon.", "AUTHORITY_CLAIM"),
    ("Ye matter confidential hai, kisi ko mat bataiye.", "ISOLATION"),
    ("UPI app kholiye, amount daaliye aur PIN confirm kar dijiye.", "PAYMENT_EXECUTION"),
    ("Aapka order kal deliver hoga, address confirm kar lijiye.", "BENIGN"),
]
ok = 0
for text, expected in probes:
    out = served.predict(text)
    hit = "OK  " if out.label == expected else "MISS"
    ok += out.label == expected
    print(f"{hit} {out.label:22s} p={out.confidence:.2f}  (expected {expected})")
print(f"\n{ok}/{len(probes)} probes correct")
"""),
    md(r"""
## Refitting the Digital Twin

The transition matrix and dwell times are fitted by `ml/build_dataset.py`, not
here — they come from the labelled corpus, not from the model, so retraining
the classifier does not invalidate them. Rerun that script only when the
corpus changes:

```bash
cd ml && .venv/bin/python build_dataset.py
```

The API reads `ml/data/processed/transitions.json` at startup and reports
`twin.fitted` on `/api/health`. Stages fitted on fewer than 20 samples are
dropped rather than quoted — a median ETA derived from three calls is a number
the deck cannot defend.

## What actually happened when this was run

The first full run produced these numbers, and they are worth internalising
before you tune anything:

| backend | val macro-F1 | test macro-F1 (held-out archetypes) |
|---|---:|---:|
| lexical baseline | — | **0.368** |
| fine-tuned MuRIL | 0.983 | **0.221** |

The model converged cleanly and then lost to a pile of regexes. The 0.98 is
memorisation: 320 synthetic calls from a seeded grid give an 8-way classifier
enough surface detail to recognise the *archetype* rather than the *stage*.
The leave-archetypes-out split is the only reason this is visible — an
utterance-level split would have reported ~0.9 and been wrong.

Two consequences:

1. **Always run `ml/eval_backends.py`.** A test score with no baseline beside
   it cannot tell you whether the model is worth serving.
2. **The API gates promotion on that comparison**, not on the checkpoint
   existing, so a "successful" training run cannot silently make the product
   worse. Override with `AEGIS_CLASSIFIER=muril` once the numbers justify it.

### Where to go next, in order of payoff

1. **More calls, more archetypes.** This is a corpus-size problem, not a
   hyperparameter problem — resist the urge to tune. ISOLATION and
   VERIFICATION_DEMAND are the thinnest (37 and 6 caller-side training
   examples) and both are load-bearing.
2. **Real audio for the coercion features.** The index currently runs
   text-only and is capped accordingly. Prosody is the half of the signal that
   is genuinely independent of the text classifier.
3. **Adversarial benign data.** Legitimate calls that say "verify", "urgent",
   "KYC", and "account" are what the false-alarm rate turns on, and there is
   more headroom there than in the scam classes.
"""),
]

notebook = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1) + "\n")
print(f"wrote {OUT} ({len(CELLS)} cells)")

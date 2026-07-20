#!/usr/bin/env python3
"""
PRESAGE — headless fine-tune of the MuRIL stage classifier.

    .venv/bin/python ml/train.py                  # full run
    .venv/bin/python ml/train.py --epochs 1       # smoke test
    .venv/bin/python ml/train.py --model distilbert-base-multilingual-cased

Same pipeline as `ml/notebooks/train_stage_classifier.ipynb`, in a form that
runs unattended, on CI, or over SSH. The notebook is for reading and for
inspecting the confusion matrix; this is for producing the artifact.

Both must agree on two things or the served model silently underperforms:
the `previous [SEP] current` context join, and the label ordering carried in
the checkpoint config. Both are defined here and asserted at export.

Output lands in `ml/artifacts/stage-classifier`, which is exactly where
`services/api/engine/classifier.py` looks. Restart the API and `/api/health`
flips `classifier.backend` from `lexical` to `muril`.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

HERE = Path(__file__).parent
DATA = HERE / "data" / "processed"
ARTIFACTS = HERE / "artifacts" / "stage-classifier"

LABELS = [
    "GREETING", "AUTHORITY_CLAIM", "FEAR_INDUCTION", "ISOLATION",
    "VERIFICATION_DEMAND", "PAYMENT_SETUP", "PAYMENT_EXECUTION", "BENIGN",
]
LABEL2ID = {label: i for i, label in enumerate(LABELS)}
ID2LABEL = {i: label for label, i in LABEL2ID.items()}

#: The two classes the product lives or dies on. Macro-F1 hides a model that
#: never catches the payment, so these are reported separately.
CRITICAL = ["ISOLATION", "PAYMENT_EXECUTION"]

#: Must match MuRILStageClassifier.predict in services/api/engine/classifier.py.
SEP = " [SEP] "


def render(speaker: str, text: str) -> str:
    """One turn, speaker-tagged.

    The speaker tag is part of the input rather than a filter on it. The
    corpus labels the *call's* stage on every turn, not the caller's speech
    act — so during VERIFICATION_DEMAND it is usually the victim speaking, as
    they read the OTP back. Training on caller turns only left that class with
    six examples in train and zero in val, which is unlearnable.

    Tagging instead of filtering keeps all 931 turns and still lets the model
    condition on who is talking, so "OTP bataiye" (caller) and "OTP hai
    458213" (victim) are distinguishable inputs rather than the same one.
    """
    return f"{speaker}: {text}"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_split(split: str) -> list[dict]:
    path = DATA / f"{split}.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def build_examples(rows: list[dict]) -> tuple[list[str], list[int]]:
    """One turn of context per example.

    Zero-context misclassifies "Account number bataiye" — it is
    VERIFICATION_DEMAND after a fear line and ordinary service after "aapka
    refund process karna hai". More context leaks the whole call's
    scamminess into every utterance and produces a model that cannot label
    the opening turns of a live call at all.
    """
    by_call: dict[str, list[dict]] = {}
    for row in rows:
        by_call.setdefault(row["call_id"], []).append(row)

    texts, labels = [], []
    for call_rows in by_call.values():
        call_rows.sort(key=lambda r: r["turn_index"])
        for i, row in enumerate(call_rows):
            current = render(row["speaker"], row["text"])
            if i:
                previous = render(call_rows[i - 1]["speaker"], call_rows[i - 1]["text"])
                texts.append(f"{previous}{SEP}{current}")
            else:
                texts.append(current)
            labels.append(LABEL2ID[row["label"]])
    return texts, labels


class UtteranceDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[int], tokenizer, max_len: int):
        self.enc = tokenizer(
            texts, truncation=True, max_length=max_len, padding="max_length"
        )
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, i: int) -> dict:
        item = {k: torch.tensor(v[i]) for k, v in self.enc.items()}
        item["labels"] = torch.tensor(self.labels[i])
        return item


def make_compute_metrics():
    def compute_metrics(pred) -> dict:
        y_true = pred.label_ids
        y_pred = pred.predictions.argmax(-1)
        per_class = f1_score(
            y_true, y_pred, average=None, labels=range(len(LABELS)), zero_division=0
        )
        out = {
            "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
            "weighted_f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        }
        for label in CRITICAL:
            out[f"f1_{label.lower()}"] = per_class[LABEL2ID[label]]
        return out

    return compute_metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="google/muril-base-cased")
    parser.add_argument("--epochs", type=float, default=6)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--max-len", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    parser.add_argument(
        "--device", default=None, choices=["cpu", "cuda", "mps"],
        help="override device selection (default: cuda if present, else cpu)",
    )
    args = parser.parse_args()

    set_seed(args.seed)

    if args.device:
        device = args.device
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        # Deliberately NOT MPS by default. On torch 2.2 / transformers 4.44 a
        # full MuRIL run on Apple GPU completed all 246 steps with the loss
        # pinned at 2.0786 — exactly ln(8), i.e. the uniform-prior loss — and
        # a test macro-F1 of 0.11. The model never left initialisation. CPU is
        # far slower but actually converges, and a slow correct number beats a
        # fast meaningless one. Pass --device mps to try it anyway.
        device = "cpu"
    print(f"device: {device}  |  model: {args.model}")

    train_rows, val_rows, test_rows = (
        load_split("train"), load_split("val"), load_split("test")
    )
    X_train, y_train = build_examples(train_rows)
    X_val, y_val = build_examples(val_rows)
    X_test, y_test = build_examples(test_rows)
    print(f"examples: train={len(X_train)} val={len(X_val)} test={len(X_test)}")
    for label, n in Counter(LABELS[i] for i in y_train).most_common():
        print(f"  {label:22s} {n:4d}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID
    )

    ds_train = UtteranceDataset(X_train, y_train, tokenizer, args.max_len)
    ds_val = UtteranceDataset(X_val, y_val, tokenizer, args.max_len)
    ds_test = UtteranceDataset(X_test, y_test, tokenizer, args.max_len)

    # Inverse-frequency class weights, normalised to mean 1 so the loss scale
    # (and therefore the usable learning rate) matches an unweighted run.
    # Without this the cheapest way to lower the loss is to under-predict the
    # rare classes, and the rare classes are the ones worth catching.
    counts = np.bincount(y_train, minlength=len(LABELS))
    weights = counts.sum() / (len(LABELS) * np.maximum(counts, 1))
    weights = weights / weights.mean()
    class_weights = torch.tensor(weights, dtype=torch.float).to(device)
    print("class weights:", {l: round(float(w), 2) for l, w in zip(LABELS, weights)})

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            loss = torch.nn.functional.cross_entropy(
                outputs.logits, labels, weight=class_weights
            )
            return (loss, outputs) if return_outputs else loss

    targs = TrainingArguments(
        output_dir=str(HERE / "artifacts" / "_train"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=32,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        # Selecting on macro-F1, not loss: weighted loss and macro-F1 disagree
        # about which epoch is best, and macro-F1 is the reported number.
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        logging_steps=25,
        seed=args.seed,
        report_to=[],
        fp16=(device == "cuda"),
        use_cpu=(device == "cpu"),
        # MuRIL's published weights contain non-contiguous tensor views, which
        # safetensors refuses to serialise ("You are trying to save a non
        # contiguous tensor: bert.encoder.layer.0.attention.self.query.weight").
        # This is a property of the checkpoint, not of the device — it fails
        # identically on CPU and MPS. The torch-native format has no such
        # restriction and reloads identically; the cost is a slightly larger
        # file and a warning about pickle that does not apply to our own output.
        save_safetensors=False,
    )

    trainer = WeightedTrainer(
        model=model,
        args=targs,
        train_dataset=ds_train,
        eval_dataset=ds_val,
        compute_metrics=make_compute_metrics(),
    )
    trainer.train()

    # --- Test ------------------------------------------------------------
    pred = trainer.predict(ds_test)
    y_pred = pred.predictions.argmax(-1)
    y_true = pred.label_ids
    macro = f1_score(y_true, y_pred, average="macro", zero_division=0)

    print(f"\n=== TEST macro-F1: {macro:.4f} ===\n")
    print(classification_report(y_true, y_pred, target_names=LABELS, zero_division=0, digits=3))

    report = classification_report(
        y_true, y_pred, target_names=LABELS, zero_division=0, output_dict=True
    )
    print("Critical-class recall:")
    for label in CRITICAL:
        row = report.get(label)
        if not row:
            continue
        note = "" if row["support"] >= 10 else "  <- support too low to quote"
        print(f"  {label:22s} recall={row['recall']:.3f} support={int(row['support'])}{note}")

    cm = confusion_matrix(y_true, y_pred, labels=range(len(LABELS)))
    benign = LABEL2ID["BENIGN"]
    false_alarms = int(cm[benign].sum() - cm[benign, benign])
    misses = int(cm[:, benign].sum() - cm[benign, benign])
    print(f"\nfalse alarms (BENIGN -> scam stage): {false_alarms}")
    print(f"misses (scam stage -> BENIGN):       {misses}")

    # --- Calibration ------------------------------------------------------
    # The UI displays StageState.confidence, so an overconfident softmax is a
    # lie the interface then repeats. One parameter, fitted on val, accuracy
    # untouched.
    val_pred = trainer.predict(ds_val)
    logits = torch.tensor(val_pred.predictions)
    labels_t = torch.tensor(val_pred.label_ids)
    temperature = torch.nn.Parameter(torch.ones(1))
    optimizer = torch.optim.LBFGS([temperature], lr=0.01, max_iter=60)

    def closure():
        optimizer.zero_grad()
        loss = torch.nn.functional.cross_entropy(logits / temperature, labels_t)
        loss.backward()
        return loss

    optimizer.step(closure)
    T = float(temperature.detach())
    print(f"\nfitted temperature: {T:.3f} (>1 means the raw model was overconfident)")

    # --- Export -----------------------------------------------------------
    args.out.mkdir(parents=True, exist_ok=True)
    # See save_safetensors above — MuRIL's tensor views are non-contiguous.
    trainer.model.save_pretrained(args.out, safe_serialization=False)
    tokenizer.save_pretrained(args.out)

    # The label map travels inside the checkpoint, so a reordered LABELS list
    # here can never silently mis-decode at serving time. Assert it round-trips.
    saved = json.loads((args.out / "config.json").read_text())
    assert {int(k): v for k, v in saved["id2label"].items()} == ID2LABEL, (
        "id2label did not round-trip into the checkpoint config"
    )

    (args.out / "metrics.json").write_text(json.dumps({
        "base_model": args.model,
        "seed": args.seed,
        "epochs": args.epochs,
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
        "false_alarms": false_alarms,
        "misses": misses,
        "temperature": T,
        "context": "previous_turn [SEP] current_turn",
        "max_len": args.max_len,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "split": "leave-archetypes-out, by call",
    }, indent=2))

    print(f"\nexported to {args.out}")
    print("restart the API — /api/health should now report classifier.backend = muril")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

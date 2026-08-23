#!/usr/bin/env python3
"""
Train the RSSIE multi-head sequence classifier.

    python ml/training/rssie/train_rssie.py                     # full run
    python ml/training/rssie/train_rssie.py --epochs 2          # smoke test
    python ml/training/rssie/train_rssie.py --encoder distilbert-base-multilingual-cased
    python ml/training/rssie/train_rssie.py --unfreeze-encoder  # only with a big corpus

Exports to `ml/artifacts/rssie/`, which is where `services/api/engine/rssie.py`
looks. As with the stage classifier, the checkpoint is **not** promoted merely
for existing — `eval_rssie.py` writes a comparison against the rule-based
baseline and the serving layer gates on that.

What this run can and cannot tell you
-------------------------------------
The leave-archetypes-out split holds out whole scam types. Two of the five scam
types in the test set (COURIER_PARCEL, LOAN_APP_HARASSMENT) appear nowhere in
training, so the scam-type head's test accuracy is capped near 52% by
construction. That is not a bug and must not be "fixed" by reshuffling the
split — it is the split telling the truth about generalisation to unseen scam
families, which is precisely the capability the spec claims.

Report the binary scam head and the stage head as the headline numbers. The
type head is informative only on the types it has seen, and the risk head is a
deterministic function of the stage label (see labels.py) and is auxiliary.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

# The package moved from ml/rssie to ml/training/rssie, so it now sits two
# levels below ml/. Anchors are named and derived once rather than counted
# inline, so the next move is a one-line change instead of a silent bug.
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.training.rssie.dataset import CallExample, describe, load_calls  # noqa: E402
from ml.training.rssie.labels import EMOTIONS, SCAM_TYPES, STAGES  # noqa: E402
from ml.training.rssie.model import FEATURE_DIM, RSSIEConfig, RSSIEModel  # noqa: E402

ARTIFACTS = REPO_ROOT / "ml" / "artifacts" / "rssie"


def set_seed(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def collate(batch: list[CallExample], tokenizer, max_turns: int, max_tokens: int):
    """Pad a batch of variable-length calls into fixed tensors."""
    import torch

    size = len(batch)
    turns = min(max_turns, max(len(e.turns) for e in batch))

    input_ids = torch.zeros(size, turns, max_tokens, dtype=torch.long)
    attention = torch.zeros(size, turns, max_tokens, dtype=torch.long)
    turn_mask = torch.zeros(size, turns, dtype=torch.long)
    turn_stages = torch.zeros(size, turns, dtype=torch.long)

    for i, example in enumerate(batch):
        # Keep the LAST `max_turns` turns, not the first. A truncated call must
        # retain the payment end — that is where the decisive evidence is, and
        # dropping it to preserve the greeting would be exactly backwards.
        texts = example.texts[-turns:]
        stages = example.turn_stage_ids[-turns:]
        encoded = tokenizer(
            texts,
            truncation=True,
            max_length=max_tokens,
            padding="max_length",
            return_tensors="pt",
        )
        n = len(texts)
        input_ids[i, :n] = encoded["input_ids"]
        attention[i, :n] = encoded["attention_mask"]
        turn_mask[i, :n] = 1
        turn_stages[i, :n] = torch.tensor(stages, dtype=torch.long)

    return {
        "input_ids": input_ids,
        "attention_mask": attention,
        "turn_mask": turn_mask,
        "features": torch.tensor([e.features for e in batch], dtype=torch.float),
        "scam": torch.tensor([1 if e.is_scam else 0 for e in batch], dtype=torch.long),
        "scam_type": torch.tensor([e.scam_type_id for e in batch], dtype=torch.long),
        "turn_stages": turn_stages,
        "risk": torch.tensor([e.transfer_risk for e in batch], dtype=torch.float),
        "emotion": torch.tensor([e.emotion_id for e in batch], dtype=torch.long),
    }


def batches(examples: list[CallExample], size: int, shuffle: bool):
    order = list(range(len(examples)))
    if shuffle:
        random.shuffle(order)
    for i in range(0, len(order), size):
        yield [examples[j] for j in order[i : i + size]]


def evaluate(model, examples, tokenizer, args) -> dict:
    import torch
    from sklearn.metrics import f1_score

    model.eval()
    scam_true, scam_pred = [], []
    type_true, type_pred = [], []
    stage_true, stage_pred = [], []
    risk_err = []

    with torch.no_grad():
        for batch in batches(examples, args.batch_size, shuffle=False):
            tensors = collate(batch, tokenizer, args.max_turns, args.max_tokens)
            out = model(
                tensors["input_ids"], tensors["attention_mask"],
                tensors["turn_mask"], tensors["features"],
            )
            scam_pred += (torch.sigmoid(out["scam_logit"]) >= 0.5).long().tolist()
            scam_true += tensors["scam"].tolist()
            type_pred += out["type_logits"].argmax(-1).tolist()
            type_true += tensors["scam_type"].tolist()
            risk_err += (out["risk"] - tensors["risk"]).abs().tolist()

            mask = tensors["turn_mask"].bool()
            stage_pred += out["turn_stage_logits"].argmax(-1)[mask].tolist()
            stage_true += tensors["turn_stages"][mask].tolist()

    return {
        "scam_f1": float(f1_score(scam_true, scam_pred, average="binary", zero_division=0)),
        "scam_accuracy": float(np.mean(np.array(scam_true) == np.array(scam_pred))),
        "type_macro_f1": float(
            f1_score(type_true, type_pred, average="macro",
                     labels=list(range(len(SCAM_TYPES))), zero_division=0)
        ),
        "type_accuracy": float(np.mean(np.array(type_true) == np.array(type_pred))),
        "stage_macro_f1": float(
            f1_score(stage_true, stage_pred, average="macro",
                     labels=list(range(len(STAGES))), zero_division=0)
        ),
        "stage_accuracy": float(np.mean(np.array(stage_true) == np.array(stage_pred))),
        "risk_mae": float(np.mean(risk_err)) if risk_err else 0.0,
    }


def unseen_type_report(train: list[CallExample], test: list[CallExample]) -> dict:
    """Which scam types the test set contains that training never showed.

    Printed before the metrics so the type-head number is read in context
    rather than mistaken for a generalisation failure of the model.
    """
    seen = {SCAM_TYPES[e.scam_type_id] for e in train}
    test_counts = Counter(SCAM_TYPES[e.scam_type_id] for e in test)
    unseen = {t: n for t, n in test_counts.items() if t not in seen}
    return {
        "types_in_train": sorted(seen),
        "unseen_in_test": unseen,
        "unseen_fraction": round(sum(unseen.values()) / max(1, len(test)), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoder", default="google/muril-base-cased")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--encoder-lr", type=float, default=2e-5)
    parser.add_argument("--max-turns", type=int, default=48)
    parser.add_argument("--max-tokens", type=int, default=48)
    parser.add_argument("--lstm-hidden", type=int, default=192)
    parser.add_argument("--dropout", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--unfreeze-encoder", action="store_true")
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    args = parser.parse_args()

    try:
        import torch
        from transformers import AutoTokenizer
    except ImportError:
        print(
            "torch and transformers are required to train.\n"
            "  pip install torch transformers scikit-learn 'numpy<2'\n"
            "The API runs without them — it serves the rule-based RSSIE path.",
            file=sys.stderr,
        )
        return 1

    set_seed(args.seed)

    train = load_calls("train")
    val = load_calls("val")
    test = load_calls("test")
    print(f"calls: train={len(train)} val={len(val)} test={len(test)}")
    for name, split in (("train", train), ("val", val), ("test", test)):
        print(f"  {name}: {describe(split)}")

    unseen = unseen_type_report(train, test)
    print(
        f"\nleave-archetypes-out: {unseen['unseen_fraction']:.0%} of test calls are "
        f"scam types never seen in training {list(unseen['unseen_in_test'])}.\n"
        "The type head cannot score above that ceiling; this is the split "
        "working as intended, not a model failure.\n"
    )

    if args.unfreeze_encoder and len(train) < 1000:
        print(
            f"WARNING: --unfreeze-encoder with only {len(train)} training calls. "
            "This project has already produced one memorised model this way "
            "(val 0.98 / test 0.22). Expect the same unless the corpus grew.\n"
        )

    tokenizer = AutoTokenizer.from_pretrained(args.encoder)
    config = RSSIEConfig(
        encoder_name=args.encoder,
        lstm_hidden=args.lstm_hidden,
        dropout=args.dropout,
        feature_dim=FEATURE_DIM,
        freeze_encoder=not args.unfreeze_encoder,
        max_turns=args.max_turns,
        max_tokens=args.max_tokens,
    )
    model = RSSIEModel(config)

    trainable = [p for p in model.parameters() if p.requires_grad]
    total = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in trainable)
    print(f"parameters: {total/1e6:.1f}M total, {n_trainable/1e6:.2f}M trainable")

    head_params = [
        p for n, p in model.named_parameters() if p.requires_grad and not n.startswith("encoder.")
    ]
    encoder_params = [
        p for n, p in model.named_parameters() if p.requires_grad and n.startswith("encoder.")
    ]
    groups = [{"params": head_params, "lr": args.lr}]
    if encoder_params:
        # A much lower LR on the encoder — the heads are random at init and
        # need to move fast, the pretrained encoder does not and will be
        # destroyed if it moves at the same rate.
        groups.append({"params": encoder_params, "lr": args.encoder_lr})
    optimizer = torch.optim.AdamW(groups, weight_decay=0.01)

    best_score, best_state, best_epoch = -1.0, None, -1
    history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_losses = []
        for batch in batches(train, args.batch_size, shuffle=True):
            tensors = collate(batch, tokenizer, args.max_turns, args.max_tokens)
            out = model(
                tensors["input_ids"], tensors["attention_mask"],
                tensors["turn_mask"], tensors["features"],
            )
            loss, parts = model.loss(out, tensors)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            epoch_losses.append(float(loss))

        metrics = evaluate(model, val, tokenizer, args)
        # Selection on the mean of the two heads that carry real supervision.
        # Including the risk head would let a deterministic function of the
        # stage label inflate the selection criterion.
        score = (metrics["scam_f1"] + metrics["stage_macro_f1"]) / 2
        history.append({"epoch": epoch, "loss": float(np.mean(epoch_losses)), **metrics})
        print(
            f"epoch {epoch:2d}  loss {np.mean(epoch_losses):6.3f}  "
            f"val scam-F1 {metrics['scam_f1']:.3f}  "
            f"stage-F1 {metrics['stage_macro_f1']:.3f}  "
            f"type-F1 {metrics['type_macro_f1']:.3f}  "
            f"risk-MAE {metrics['risk_mae']:.3f}"
        )
        if score > best_score:
            best_score, best_epoch = score, epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)
        print(f"\nrestored best epoch {best_epoch} (val selection score {best_score:.3f})")

    test_metrics = evaluate(model, test, tokenizer, args)
    print("\n=== TEST (held-out archetypes) ===")
    for key, value in test_metrics.items():
        print(f"  {key:18s} {value:.4f}")

    args.out.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": config.__dict__,
            "labels": {"stages": STAGES, "scam_types": SCAM_TYPES, "emotions": EMOTIONS},
            "feature_dim": FEATURE_DIM,
        },
        args.out / "rssie.pt",
    )
    tokenizer.save_pretrained(args.out)
    (args.out / "metrics.json").write_text(
        json.dumps(
            {
                "encoder": args.encoder,
                "frozen_encoder": not args.unfreeze_encoder,
                "epochs": args.epochs,
                "best_epoch": best_epoch,
                "seed": args.seed,
                "train_calls": len(train),
                "val_calls": len(val),
                "test_calls": len(test),
                "test": test_metrics,
                "history": history,
                "split": "leave-archetypes-out, by call skeleton (reused from build_dataset.py)",
                "unseen_type_ceiling": unseen,
                "caveats": [
                    "transfer-risk head is a deterministic function of the stage "
                    "label (labels.py::transfer_risk_of_stage); it is auxiliary "
                    "regularisation, not an independent result.",
                    "emotion head cannot predict CURIOUS or TRUSTING — the corpus "
                    "has no such labels. Those two states are served by the "
                    "rule-based extractor.",
                    f"{unseen['unseen_fraction']:.0%} of test calls are scam types "
                    "absent from training, capping the type head by construction.",
                ],
            },
            indent=2,
        )
    )
    print(f"\nexported to {args.out}")
    print("run ml/training/rssie/eval_rssie.py to score it against the rule-based baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# aegis-core

The shared domain vocabulary for AegisAI. Imported by **both** the API
(`services/api`) and the dataset pipeline (`ml/`), which is why it lives here
rather than inside either one.

| Module | Holds |
|---|---|
| `taxonomy.py` | The 8 scam stages, threat weights, `LABELS`, `BY_LABEL` — **the single source of truth for stage labels** |
| `schema.py` | Victim states and corpus record shapes |
| `seeds.py` | Archetype seeds for corpus generation |
| `entities.py` | Deterministic, offline entity substitution (synthetic identifiers only) |
| `hinglish.py` | Hindi/Hinglish markers and density scoring |
| `llm.py` | Provider-abstracted generation backends (corpus building only) |

## Install

Editable, from the repo root — `services/api/requirements.txt` already does this:

```bash
pip install -e packages/aegis_core
```

## Why it is a package

`taxonomy.py` is the single source of truth for the stage labels. The API used
to reach it through `sys.path.insert(0, ml/)` with a `try/except ImportError`
that fell back to a hardcoded label list and an **empty** `BY_LABEL`. That
fallback exists for container builds without `ml/`, but it meant a broken path
degraded silently to stale labels with no threat weights — and no test caught
it, because the label list is the same eight strings. Installing the package
makes the import deterministic; the fallbacks remain as belt-and-braces.

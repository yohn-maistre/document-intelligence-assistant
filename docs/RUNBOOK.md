# RUNBOOK — running the LLM pipeline (from a network where the proxy is reachable)

> The Nemotron proxy (`llm-proxy.atlas-horizon.com`) and HuggingFace are **not**
> on the Claude-Code-web container's egress allowlist, so `synth gen` / `index` /
> `eval` / the connectivity proof must run on a machine that can reach them
> (your laptop, or the proot distro on your phone). Everything below is
> copy-paste. Paste the marked outputs back and the rest gets finalized.

## 0. Prereqs
```bash
git pull
# Phone / constrained device — torch-free lite base + the corpus generator:
uv sync --extra synth         # ~190 pkgs, no torch/ragas/phoenix
# (Laptop running the full local-embed path instead: uv sync --extra dev --extra full)
```
On a phone use `KLERK_EMBED_BACKEND=remote` (step 2) — there is no local model.

## 1. `.env` (gitignored — never commit)
Copy `.env.example` → `.env` and fill from the Nemotron bundle's `config.env`
plus your extras:
```ini
# from the bundle config.env (verbatim):
LITELLM_KEY=sk-...
CF_CLIENT_ID=...
CF_CLIENT_SECRET=...
PROXY_URL=https://llm-proxy.atlas-horizon.com
NEMOTRON_MODEL=nemotron-3-nano-omni
# Drive (service account JSON path + the folder you own & shared with the SA):
GOOGLE_APPLICATION_CREDENTIALS=.secrets/drive-sa.json
DRIVE_FOLDER_ID=<the folder id you create in step 6>
# Embedding backend — pick ONE (see step 2):
KLERK_EMBED_BACKEND=local
```

## 2. Embedding backend — pick the path that fits the machine
- **LOCAL (recommended for the submission eval — matches the graded Docker path):**
  ```bash
  uv sync --extra dev --extra local      # pulls torch + FlagEmbedding; downloads BAAI/bge-m3 (~2GB) on first use
  # KLERK_EMBED_BACKEND=local
  ```
- **REMOTE (lite / phone — no model download):** point at any OpenAI-compatible
  embeddings endpoint you can reach, e.g. a self-hosted BGE-M3 or a provider:
  ```ini
  KLERK_EMBED_BACKEND=remote
  KLERK_EMBED_REMOTE_URL=<https://.../v1>
  KLERK_EMBED_REMOTE_KEY=<key>
  KLERK_EMBED_REMOTE_MODEL=<e.g. BAAI/bge-m3>
  ```

## 3. Connectivity proof  ← PASTE THIS OUTPUT BACK (required for the submission line)
```bash
uv run klerk smoke
# or the bundle's: bash test-nemotron.sh
```
Expect a one-line Nemotron reply + a Phoenix URL.

## 4. Generate the corpus (Nemotron-backed, cached for free regen)
```bash
uv run klerk synth gen                 # → data/synth/fata_organa/ (~30 docs)
uv run klerk synth check               # ← PASTE: brief-constraint table (should be all ✓)
```

## 5. Build the index over the GENERATED corpus (note the --src!)
```bash
uv run klerk index build --src data/synth/fata_organa --rebuild
uv run klerk index stats               # ← PASTE: row/dim/fts stats
```

## 6. Run the eval over the 20-Q set  ← PASTE BOTH JSON FILES BACK
```bash
uv run klerk eval run                  # writes data/output/eval/rubric.json + ragas.json, prints a table
```
Paste `data/output/eval/rubric.json` and `data/output/eval/ragas.json` (or the
printed table). EVAL.md gets filled from these.

## 7. Drive upload + share (the corpus deliverable)
The service account has **no Drive quota of its own**, so upload into a folder
**you** own:
1. In your Google Drive, create a folder (e.g. `klerk-fata-organa-corpus`).
2. Share it with the service account **as Editor**:
   `fata-organa@project-3fcd8c76-2e2a-4287-abb.iam.gserviceaccount.com`
3. Put the folder id in `.env` as `DRIVE_FOLDER_ID`, then:
   ```bash
   uv run klerk drive upload data/synth/fata_organa --to "$DRIVE_FOLDER_ID" --dry-run   # preview
   uv run klerk drive upload data/synth/fata_organa --to "$DRIVE_FOLDER_ID"             # real
   ```
4. Finally, share that same folder with **`ydharmaw@fata-organa.com` (Editor)** for submission.

## 8. (optional) Full-system smoke
```bash
docker compose up --build       # FastAPI :8000  +  Studio (textual-serve) :8001
```

---
### What to paste back for finalization
- step 3 `klerk smoke` output (connectivity proof)
- step 4 `klerk synth check` table
- step 5 `klerk index stats`
- step 6 `rubric.json` + `ragas.json`
- any errors/latency notes

From those I fill **EVAL.md** (real numbers + honest failure analysis) and the
README results/hardware sections, then we submit.

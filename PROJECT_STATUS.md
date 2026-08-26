# Project Status — Local AI Companion

Last updated: 2026-08-24 (pausing for a break — see §12 for exactly where to resume)
Project location: `D:\milo\assistant`

> **How to use this file:** paste this whole document into a new chat/session
> as context before asking for further work. It should be enough for any LLM
> to understand what exists, how it works, and what's next — without you
> having to re-explain the project from scratch. Update it after each
> meaningful change.

---

## 1. What this project is

A local, privacy-first AI companion/assistant running on personal hardware
(RTX 3050 4GB). Long-term vision includes voice, memory, and safe system
actions — but development follows a **vertical-slice** philosophy: build
the smallest working end-to-end loop first, then extend it, rather than
completing entire "phases" of isolated modules before anything is usable.

Full architectural plan (phases, model stack, memory design, safety
philosophy) is a separate reference document — if it exists in your repo,
point a new session at it too. This file only tracks **current build
status**, not the whole vision.

---

## 2. Current state: it works

You can currently:
- Run `python main.py` and have a real conversation with Qwen2.5:3b
- Say `remember that X` and have it persist across restarts
- Ask about something you said earlier and have it recalled from memory,
  even after closing and reopening the app
- Say `open <whitelisted app>` and have it actually launch, with clean
  refusal for anything not on the whitelist
- Run `python main.py --voice` for push-to-talk voice conversation:
  Enter → speak → Enter → transcribed accurately → normal pipeline →
  response printed AND spoken aloud

This is the first real milestone — the assistant has **persistent
identity/memory**, not just a stateless chat window.

---

## 3. Model backend: Ollama (not llama-cpp)

Important deviation from the original plan: the model runs through
**Ollama**, not a raw GGUF file loaded via llama-cpp-python.

- `ollama serve` must be running in the background (usually already is)
- Config controls which backend is active — see `config/assistant.yaml`

✅ **Verified.** The Ollama backend (`OllamaBackend` in `mind/chat_engine.py`,
backend-switch logic in `main.py`, `ModelConfig` fields in `core/config.py`)
was confirmed working end-to-end during the §7 foundation verification pass.

⚠️ **Model swap decided, NOT yet confirmed applied.** Decision made to
switch from `qwen2.5:3b` to `qwen3.5:2b`. The only change needed is one
line in `config/assistant.yaml`:
```yaml
model:
  ollama_model: "qwen3.5:2b"   # was "qwen2.5:3b"
```
Plus `ollama pull qwen3.5:2b` first if not already pulled. **This has not
been confirmed as actually done** — check `config/assistant.yaml` and
`ollama list` when resuming, and update this note once verified. Also
note: `qwen3.5:2b` is shipped at Q8_0 quantization (2.7GB), so despite
being a smaller parameter count than the old 3B/Q4 model, VRAM footprint
is similar, not smaller — don't expect freed-up headroom from this swap.

---

## 4. Architecture — folders and what each one does

```
assistant/
├── main.py                    # entry point — wires everything together, the main loop
├── config/
│   └── assistant.yaml         # ALL tunables live here: model backend, generation params, persona choice
├── core/
│   ├── config.py               # loads + validates assistant.yaml into typed objects
│   ├── state.py                 # SessionState — in-memory turn history for the current run only
│   └── model_lifecycle.py       # enforces "only one model loaded at a time" (VRAM safety)
├── mind/
│   └── chat_engine.py           # LlamaCppBackend, OllamaBackend, MockBackend + prompt builder
├── memory/
│   └── store.py                 # MemoryStore — rolling journal + permanent long-term facts (see §5)
├── orchestrator/
│   └── router.py                # classify_intent() + extract_remember_fact() — simple string logic, no model calls
├── persona/
│   ├── persona.py               # loads persona .md file, builds system prompt
│   └── personas/default.md      # THE PERSONALITY — plain markdown, edit directly, no code changes needed
├── interface/
│   └── terminal.py               # stdin/stdout — the only interface that exists right now
└── memory_data/                 # where memory actually gets written (see §5) — NOT committed to git
    ├── journal/                  # daily .md files, auto-deleted after 7 days
    └── preferences/long_term.md  # permanent facts, never auto-deleted
```

---

## 5. Memory system — how it actually works

Two tiers, both plain markdown, both human-readable/editable:

### Rolling journal (`memory_data/journal/YYYY-MM-DD.md`)
- Every single turn (user + assistant) gets appended here automatically,
  no judgment calls, no filtering
- One file per day
- On startup, `memory.cleanup_old()` deletes any file older than 7 days
- When building a prompt, the last 7 days get concatenated and injected
  as context (capped at ~6000 characters, keeps the most recent part if
  it overflows)
- **Trade-off, chosen deliberately:** this gives strong context of "the
  last week" without needing a model to judge what's worth saving. The
  cost is it forgets everything after 7 days — that's what tier 2 is for.

### Long-term facts (`memory_data/preferences/long_term.md`)
- Only written when you say **"remember that X"** or **"remember X"**
  (exact phrase match, `extract_remember_fact()` in `router.py` — no
  model involved in deciding this, pure string logic)
- Never auto-deleted
- Always injected into every prompt in full (capped at ~2000 characters)
- This is what makes it remember your name/preferences permanently

### What's NOT built yet
- No semantic/embedding-based memory (can't do fuzzy "what did we discuss
  about X" retrieval — only exact recency + explicit facts)
- No memory of *people* as structured entities (no `memory_data/people/`
  usage yet, despite the folder existing)
- No summarization/compression of the journal — it's raw transcript

---

## 6. Known issues already fixed (don't re-fix these)

| Issue | Fix |
|---|---|
| `config/assistant.yaml` paths (`model.path`, `app.data_dir`) were resolving relative to `config/` instead of the project root | Changed to `../models/...` and `../memory_data` in the YAML |
| Running `python main .py` (typo, space) fails with file-not-found | Not a bug — just a typo, `python main.py` is correct |
| Duplicate facts — `remember that X` twice appended twice | `memory/store.py`: `remember_fact()` now checks (case-insensitive, whitespace-normalized) before appending, skips if already present. Existing duplicates from before the fix were left as-is. |
| Multi-line assistant replies broke the one-line-per-entry journal format | `memory/store.py`: `log_turn()` now flattens newlines to spaces before writing |
| Ctrl-C mid-generation killed the whole app | `main.py`: `KeyboardInterrupt` now caught specifically around the LLM streaming loop only — prints `(cancelled)`, returns to prompt. Ctrl-C at the input prompt itself still exits normally, unchanged. |
| Leftover debug line (`soundfile.write("debug_capture.wav", ...)`) in `voice/pipeline.py` from STT accuracy diagnosis | Removed, along with the now-unused `import soundfile as sf` |

All 4 confirmed by user testing 2026-08-24.

---

## 7. Checklist — verify before continuing work in a new session

**Status: ✅ VERIFIED (Ox Alpha foundation pass, 2026-08-22).** All items
below confirmed live, plus real reliability bugs found and fixed under
adversarial testing (killed Ollama mid-session, malformed config, fake
7+ day old journal files). See §7a for what was fixed.

- [x] `python main.py --mock` runs and completes a full exchange without
      errors
- [x] `ollama serve` running, `qwen2.5:3b` present
- [x] `python main.py` (no `--mock`) produces real streamed Qwen responses
      (~3s round trip)
- [x] `core/config.py` — `ModelConfig` has `backend`, `ollama_model`,
      `ollama_host`, correctly populated from YAML
- [x] `mind/chat_engine.py` — `OllamaBackend` exists and works
- [x] `main.py` → `build_engine()` branches correctly on `cfg.model.backend`
- [x] Memory persists across restart (`remember that X` → exit → restart →
      recalled correctly, confirmed via `build_memory_context()` reaching
      the actual prompt)
- [x] Journal files exist and are readable
- [x] Long-term facts file has content
- [x] **New:** 7-day expiry tested with fake-dated files — day 8/9 deleted,
      day-7 boundary preserved, non-date filenames skipped, idempotent

### 7a. Bugs found and fixed during verification (don't reintroduce these)

| # | Issue | Fix |
|---|---|---|
| 1 | Ollama going unreachable mid-session raised a raw traceback and killed the whole app | `main.py`: generation wrapped in try/except — that turn is lost, session survives |
| 2 | Malformed `assistant.yaml` raised a raw YAML traceback at startup | `core/config.py`: `yaml.YAMLError` caught and re-raised as clean `ConfigError` |
| 3 | `remember that X` inputs were never written to the journal — left a transcript gap | `main.py`: fact branch now logs the user turn + acknowledgment, same as the ACTION branch does |
| 4 | Setting `backend: banana` (typo/invalid) silently fell through to the llamacpp path with a misleading error | `core/config.py`: `_validate()` now rejects unknown backend values with a clear message |
| 5 | `requests` was used by `OllamaBackend` but never declared as a dependency — missing install gave an ugly raw `ImportError` | Declared in `requirements.txt`; import wrapped to raise a clear `RuntimeError` (mirrors `LlamaCppBackend`'s pattern) |
| 6 | Ollama HTTP call had no timeout — a stalled Ollama server hung the whole REPL forever | Added `timeout=(10, 120)` to the request |

### 7b. Known gaps — all fixed as of 2026-08-24

The 4 gaps previously tracked here (duplicate facts, multi-line journal
entries, Ctrl-C mid-generation, leftover debug line) are now closed — see
§6 for the fix summary.

---

## 8. What's next (not yet started)

In rough priority order, per the vertical-slice philosophy — pick ONE at
a time, get it fully working, don't start the next until the current one
is solid:

1. **Verify the Ollama backend integration** — ✅ **DONE**, see §7/§7a
2. **Test journal auto-expiry actually works** — ✅ **DONE**, see §7
3. **One real action** — ✅ **DONE**. "Open X" launches whitelisted apps
   via `orchestrator/actions.py` + `config/actions.yaml`; non-whitelisted
   apps refuse cleanly with a clear message ("can only open whitelisted
   apps") instead of crashing or attempting arbitrary execution.
4. **Close the three known gaps from §7b** — still open, cheap fixes:
   - Dedup check on `remember_fact()`
   - Fix journal format to handle multi-line assistant replies
   - Graceful Ctrl-C handling that doesn't kill the session mid-generation
   - **New cleanup item from voice work:** remove the temporary debug
     `soundfile.write("debug_capture.wav", ...)` line from
     `voice/pipeline.py` — see §11
5. **Persona tuning** — now that memory is real, `persona/personas/default.md`
   can be edited and tested with actual context behind it
6. **Voice V1 (push-to-talk)** — ✅ **DONE**. See §11 for full details,
   including a real accuracy issue found and fixed along the way.
7. **Voice V2+ (VAD auto-detection, wake word, barge-in)** — not started,
   deliberately deferred. V1 should be used daily for a while first.

## 9. Workflow note: using Ox Alpha for code generation

As of this update, code changes are drafted by Ox Alpha (an external
coding model reached via prompt), reviewed by the user, then manually
applied. Implications for any session picking this project back up:

- Prompts to Ox Alpha are scoped tight (one file/feature at a time) to
  respect its context budget and keep review manageable
- This file (`PROJECT_STATUS.md`) is the thing pasted into new Ox Alpha
  prompts for context — keep it trimmed to what's relevant per-task
  rather than dumping the whole thing every time
- Nothing Ox Alpha outputs is applied without review — if you're the one
  reviewing, check against §6 (already-fixed issues) so old bugs don't
  get silently reintroduced by a model that doesn't have that history

## 10. Voice pipeline — how it works, and a real bug that got fixed

### Stack
- **STT**: sherpa-onnx, Whisper `small.en` (CPU-only, offline)
- **TTS**: sherpa-onnx, `vits-piper-en_US-amy-medium` (CPU-only, offline)
- **Recording**: `sounddevice`, 16kHz mono float32, manual Enter-to-start/
  stop (no VAD in this slice — the user decides utterance boundaries)
- New files: `voice/stt.py`, `voice/tts.py`, `voice/recorder.py`,
  `voice/pipeline.py`
- `main.py --voice` flag: with it, push-to-talk replaces typed input and
  responses are spoken as well as printed; without it, behavior is 100%
  unchanged from text-only mode
- Model paths configured in `config/assistant.yaml` under a new `voice:`
  section (`enabled`, `stt_model_dir`, `tts_model_dir`)

### Real issue found and fixed: STT accuracy on Indian English accent

**Symptom:** voice input worked (recording, TTS playback all fine) but
transcribed text frequently didn't match what was actually said.

**Diagnosis process** (useful pattern for future audio bugs):
1. Ruled out capture bugs first — dumped recorded audio to a wav file and
   listened back; it was clean and correct
2. Ruled out environment/mic hardware — same phrases, same room/background
   noise, transcribed correctly every time by ChatGPT's voice input
3. Concluded: model accuracy, not a code bug

**Root cause:** the original model choice, `sherpa-onnx-zipformer-small-en`,
is a lightweight English-only model. Research confirmed Indian English
accents see a real, well-documented accuracy gap on models like this —
this was a genuine model-selection issue, not user error or a code bug.

**Fix:** switched to sherpa-onnx's official Whisper `small.en` model.
Whisper's much larger and more accent-diverse training data handles
Indian English meaningfully better. `small.en` (not base.en, not medium.en)
was chosen as the cheapest first test — it worked: word-perfect on real
speech in testing, ~3s to transcribe ~6.6s of audio (int8, CPU, 2 threads).
**If accuracy issues resurface with different speech patterns, `medium.en`
is the documented next step — bigger model swap, not new debugging.**

The old Zipformer model files were preserved (not deleted) at
`D:\milo\models\voice\stt-zipformer-en-2023-06-26\` in case you want to
A/B compare later.

### Known cleanup item
A temporary debug line (`soundfile.write("debug_capture.wav", ...)`) was
added to `voice/pipeline.py` during the accuracy diagnosis. **Should be
removed** — it's not part of the real pipeline and silently writes a wav
file to disk on every voice turn if left in.

## 11. What's explicitly NOT being built yet (don't suggest these)

Wake word, VAD-based auto-listening, barge-in/interrupt handling, emotion
modeling, proactive triggers, GUI/desktop app, multi-model orchestration
(gatekeeper/executor split), semantic embedding search. All later phases
— resist scope creep back toward them until the current slice is solid
and actually used daily.

## 12. IN PROGRESS: natural-language action recognition — resume here

**The problem:** `orchestrator/actions.py`'s `extract_action()` and
`orchestrator/router.py`'s `classify_intent()` require exact prefix
matches ("open notepad" works, "buddy, open notepad" or "can you open
notepad" don't — they fall through to normal conversation instead).

### What was tried and rejected: native Ollama tool calling as primary router

Built a rigorous standalone test (`poc_tool_routing_test.py`, NOT part of
main codebase, still sitting in the repo — see cleanup note below): 10
prompts × 10 runs = 100 trials against `qwen3.5:2b` via Ollama's
`/api/chat` with a fake `open_app` tool (nothing actually executed).

**Results:**
- Positive accuracy (correctly calls the tool for real requests): 100%
- Correct app-name extraction: 100%
- Valid tool-call JSON: 100%
- **False positive rate: 40%** (16/40 negative cases wrongly triggered
  a tool call) — **REJECTED, does not meet the 0% safety bar**

**The dangerous specific failure:** "I opened Notepad yesterday" (past
tense, describing something already done) triggered a tool call 6/10
times — i.e. this exact sentence would have randomly launched Notepad
mid-conversation about 60% of the time. "the store is open" (unrelated
use of the word "open") triggered 9/10 times, though with hallucinated
non-whitelisted app names that a whitelist check would have caught.

**Follow-up experiment:** hardened the system prompt to explicitly
forbid calling the tool for past-tense/questions/statements. Result:
false positives dropped to 0%, but positive accuracy collapsed to 3.3%
— the model swung to refusing genuine requests instead. **Conclusion:
at 2B parameters, this model cannot reliably hold both "reject clearly
non-command phrasing" and "accept genuine requests" at the same time via
prompt tuning alone** — tightening one broke the other. This is a real
finding about this model's capability ceiling for this task, not a
prompting skill issue.

### Current direction: deterministic pre-filter in front of the LLM

Insight: the LLM was being asked to discriminate command-vs-not on
*every* input, including ones trivially decidable by grammar alone (past
tense, question framing, "X is Y" state-description statements). A cheap
rule-based filter ahead of the LLM call should handle those obvious
cases deterministically (100% consistent, no per-run variance, unlike
the model), leaving the LLM only for genuinely ambiguous phrasing —
which is a fairer and narrower test of what it's actually good at.

**Prototype filter** (`command_filter.py`, built and tested in a
sandbox, NOT yet in the actual project) classifies input as:
- **Fast-accept** (clear imperative or polite-request form: "open X",
  "can/could/would you open X") → skip LLM entirely, extract app name,
  check whitelist, execute
- **Fast-reject** (past-tense verbs, question-starting words, "X is/are/
  was Y" statement patterns) → skip LLM entirely, treat as normal
  conversation
- **Ambiguous** (matches neither pattern) → fall back to LLM tool-calling

**Result so far:** tested against the exact 10 prompts from the PoC
report — **10/10 correctly classified, including both dangerous false
positives**, using pure regex, zero LLM calls, zero variance run-to-run.

**Two honest caveats, unresolved:**
1. This filter is tuned to the 10 known prompts. **Not yet tested
   against phrasing outside that set** — could be overfit, could miss
   real cases, could have false "fast-accept" cases not yet discovered.
2. Patterns were hand-written from English grammar reasoning, not
   derived from a larger test corpus.

### Next steps to resume with

1. Expand the test set significantly beyond the original 10 prompts —
   more phrasing variety, deliberately adversarial edge cases (other
   tenses, sarcasm, indirect requests, app names embedded in longer
   sentences)
2. Re-run `command_filter.py`'s classify() against the expanded set,
   fix/tighten patterns as gaps are found
3. Once the filter's fast-accept/fast-reject buckets are solid, build
   the combined pipeline: filter first, LLM only for the ambiguous
   bucket, re-run the full 100-trial-style harness end-to-end (filter +
   LLM together) to get final real numbers
4. Only then write the Ox Alpha prompt to actually integrate this into
   `orchestrator/router.py` / `orchestrator/actions.py` — nothing has
   touched the real codebase yet, everything above is still prototype/
   test code

### Cleanup pending (not urgent, do whenever)
- `poc_tool_routing_test.py` + its `.csv`/`.json` result files are still
  sitting in the repo from the rejected PoC — fine to keep for reference
  while this work continues, delete once the filter approach is settled
- The `command_filter.py` prototype exists outside the repo (sandbox) —
  needs to be brought into the actual project once validated further
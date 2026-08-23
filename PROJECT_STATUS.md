# Project Status — Local AI Companion

Last updated: 2026-08-22 (foundation verification pass by Ox Alpha — see §7b)
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

This is the first real milestone — the assistant has **persistent
identity/memory**, not just a stateless chat window.

---

## 3. Model backend: Ollama (not llama-cpp)

Important deviation from the original plan: the model runs through
**Ollama**, not a raw GGUF file loaded via llama-cpp-python. Ollama was
already installed with `qwen2.5:3b` pulled, so we adapted rather than
duplicating that setup.

- `ollama serve` must be running in the background (usually already is)
- Model name as Ollama sees it: `qwen2.5:3b`
- Config controls which backend is active — see `config/assistant.yaml`

⚠️ **Needs verification in a fresh session:** the Ollama backend code
(`OllamaBackend` class in `mind/chat_engine.py`, backend-switch logic in
`main.py`, and the extra `ModelConfig` fields in `core/config.py`) was
given as manual copy-paste instructions in chat, not applied by me
directly to a file I could re-verify. **Before doing further work,
confirm these three files actually contain the Ollama backend changes** —
see checklist in §7.

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

### 7b. Known gaps — deliberately not fixed yet, address before voice

These are small and cheap. Recommended as the *next* task — closing
these out solidifies the three existing pillars (chat/memory/actions)
before adding a fourth (voice), which is a much larger lift.

- **Duplicate facts:** saying `remember that X` twice appends it twice —
  no dedup check against existing long-term facts
- **Multi-line assistant replies break the journal format** — the journal
  assumes one turn = one line; a multi-line response breaks that
  structure, and this will compound as transcripts grow
- **Ctrl-C kills the whole app, even mid-generation** — acceptable for
  text-only, but voice will need proper interrupt-without-exit (barge-in)
  handling, and this is the first sign that piece doesn't exist yet

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
4. **Close the three known gaps from §7b** — recommended next, before
   voice or persona work. Cheap fixes, prevents them compounding:
   - Dedup check on `remember_fact()`
   - Fix journal format to handle multi-line assistant replies
   - Graceful Ctrl-C handling that doesn't kill the session mid-generation
5. **Persona tuning** — now that memory is real, `persona/personas/default.md`
   can be edited and tested with actual context behind it
6. **Voice** — explicitly NOT next. See §10. Requires wake word, VAD,
   STT, TTS, and barge-in/interrupt handling — a much larger lift than
   anything built so far, and the Ctrl-C issue in §7b is an early signal
   that interrupt handling isn't solved yet even for text.

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

## 10. What's explicitly NOT being built yet (don't suggest these)

Voice/wake-word, TTS, emotion modeling, proactive triggers, GUI/desktop
app, multi-model orchestration (gatekeeper/executor split), semantic
embedding search. All later phases — resist scope creep back toward them
until the current slice is solid and actually used daily.
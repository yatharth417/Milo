# Local AI Companion — Phase 0 Scaffold

This is the first end-to-end slice from the build plan: `main.py` →
terminal input → conversation state → persona prompt → Qwen → streamed
response. No memory, no tools, no voice yet — that's intentional.

## Structure

```
assistant/
├── main.py                    # entry point, wires everything together
├── requirements.txt
├── config/
│   └── assistant.yaml         # all tunables — model path, generation params, persona
├── core/
│   ├── config.py               # loads + validates assistant.yaml
│   ├── state.py                 # SessionState — in-memory turn history
│   └── model_lifecycle.py       # single-model-resident policy (see below)
├── mind/
│   └── chat_engine.py          # LlamaCppBackend (real) + MockBackend (no weights needed)
├── orchestrator/
│   └── router.py                # classify_intent() — conversation/memory/action
├── persona/
│   ├── persona.py               # loader + system prompt builder
│   └── personas/default.md      # edit this directly to change personality/tone
└── interface/
    └── terminal.py               # stdin/stdout I/O
```

## Run it

Without real model weights (verifies the whole pipeline is wired correctly):

```
pip install -r requirements.txt
cd assistant
python main.py --mock
```

With a real model:

1. Get Qwen2.5-3B-Instruct in GGUF Q4 format (e.g. from Hugging Face).
2. Put the path in `config/assistant.yaml` under `model.path`.
3. Install llama-cpp-python with GPU flags for your hardware, e.g.:
   ```
   CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python
   ```
4. `python main.py`

## Why model_lifecycle.py exists already

The build plan flagged VRAM pressure (RTX 3050 4GB) as a real risk once a
second model shows up (executor, TTS, etc.). Rather than bolt lifecycle
management on later, `ModelLifecycleManager` enforces "only one model
resident at a time" from day one. Right now there's only one model
registered (`chat`), so it's a no-op in practice — but the swap logic and
logging are already in place for when that changes.

## What's deliberately not here yet

Memory (structured/semantic/markdown), tool execution, voice, and
proactivity are all later phases per the plan. `orchestrator/router.py`
already classifies intent into conversation/memory/action buckets, but
only `conversation` is routed anywhere right now — that's the hook Phase 1
will plug into.

## Editing the persona

`persona/personas/default.md` is plain Markdown, read at startup. Change
tone, add rules, whatever — no code changes needed. Bump the `version:` in
the header comment when you make a real change.

# Milo — Local AI Companion

Milo is a local-first, privacy-focused AI companion designed to run on personal hardware. It currently combines conversational AI, persistent memory, safe application actions, and push-to-talk voice interaction into one small Python application.

> **Current version:** Voice V1 + natural command filter
>
> **Primary model:** Qwen3.5:2B via Ollama
>
> **Hardware target:** NVIDIA RTX 3050 4GB
>
> **Platform:** Windows
>
> **Language:** Python 3.12

---

## What Milo can do today

### 💬 Local conversation

Milo runs Qwen3.5:2B locally through Ollama and maintains recent conversation context during a session.

```text
User → Milo → Qwen3.5:2B → response
```

The Ollama integration uses the `/api/chat` endpoint and disables model thinking output for the normal assistant experience, so internal reasoning is not surfaced to the user.

### 🧠 Persistent memory

Milo currently uses two simple, human-readable memory layers:

**Rolling journal**

- Stores user and assistant turns in `memory_data/journal/`.
- One file is created per day.
- Entries older than 7 days are automatically removed.
- Recent journal context is injected into prompts with a character budget.

**Long-term facts**

- Explicit facts can be stored with commands such as:
  - `remember that I like coffee`
  - `remember my favorite color is blue`
- Facts are stored in `memory_data/preferences/long_term.md`.
- Long-term facts survive application restarts.
- New duplicate facts are prevented using case-insensitive, whitespace-normalized comparison.

### 🖥️ Safe application actions

Milo can open applications that are explicitly authorized in `config/actions.yaml`.

Examples:

```text
open notepad
buddy, open notepad
can you please open notepad?
please launch notepad
bring up notepad
```

The security model is intentionally restrictive:

```text
User request
    ↓
Intent / command understanding
    ↓
Whitelist lookup
    ↓
Exact predefined command
    ↓
subprocess.Popen(...)
```

User input is never treated as an arbitrary shell command, and unlisted applications are refused.

### 🎤 Voice V1 — push-to-talk

Milo supports local voice conversations with:

- **STT:** sherpa-onnx Whisper `small.en`
- **TTS:** sherpa-onnx Piper/VITS `en_US-amy-medium`
- **Recording/playback:** `sounddevice`
- **Execution:** CPU-only for STT/TTS, keeping the RTX 3050 available for Qwen through Ollama

Voice V1 intentionally uses push-to-talk:

```text
Press Enter
    ↓
Speak
    ↓
Press Enter
    ↓
Speech-to-text
    ↓
Existing Milo pipeline
    ↓
Qwen3.5:2B
    ↓
Text response + speech output
```

Because spoken input becomes normal text before routing, voice and text use the same memory and action behavior.

---

## Current architecture

```text
assistant/
├── main.py                       # entry point and main loop
├── config/
│   ├── assistant.yaml            # central configuration
│   └── actions.yaml              # whitelisted applications
├── core/
│   ├── config.py                 # typed configuration loading/validation
│   ├── state.py                  # in-memory session state
│   └── model_lifecycle.py        # one-model-at-a-time lifecycle policy
├── mind/
│   └── chat_engine.py            # chat engine + Ollama/llama.cpp/mock backends
├── orchestrator/
│   ├── router.py                 # deterministic intent/command routing
│   └── actions.py                # safe whitelist-based app execution
├── memory/
│   └── store.py                  # journal + long-term memory
├── persona/
│   ├── persona.py                # persona loading/system prompt creation
│   └── personas/default.md       # active personality definition
├── interface/
│   └── terminal.py               # terminal input/output helpers
├── voice/
│   ├── recorder.py                # push-to-talk microphone capture
│   ├── stt.py                     # sherpa-onnx Whisper STT
│   ├── tts.py                     # sherpa-onnx Piper/VITS TTS
│   └── pipeline.py                # voice orchestration
└── memory_data/
    ├── journal/                   # runtime daily journals
    └── preferences/long_term.md   # runtime persistent facts
```

### Request flow

For a normal chat turn:

```text
Input
  ↓
Deterministic command filter
  ↓
Intent routing
  ↓
Memory update/read
  ↓
Prompt construction
  ↓
Qwen3.5:2B via Ollama
  ↓
Streaming response
```

For an action request:

```text
Input
  ↓
Fast deterministic command filter
  ↓
Extract target application
  ↓
Whitelist check
  ↓
Approved command execution
```

For voice mode:

```text
Microphone
  ↓
Whisper small.en
  ↓
Normal Milo text pipeline
  ↓
Response text
  ↓
Piper TTS
  ↓
Speakers
```

---

## Natural command understanding

Milo currently uses a **deterministic tri-state command filter** before the normal LLM path.

The filter produces one of three outcomes:

- **Fast-accept:** clearly looks like an action request → handle deterministically.
- **Fast-reject:** clearly looks like a statement/question/negation → treat as normal conversation.
- **Ambiguous:** let the existing router decide.

This was chosen after testing native LLM-only tool calling with Qwen3.5:2B. In the local 100-trial proof-of-concept, Qwen3.5:2B produced correct action calls very well for positive requests, but generated false-positive tool calls for ordinary conversation in a significant number of negative cases. Milo therefore does not currently trust the model alone to decide whether a system action should happen.

The guiding principle is:

> **The model may help understand a request, but deterministic Milo code remains responsible for deciding what is allowed to execute.**

---

## Requirements

- Windows
- Python 3.12
- Ollama
- Qwen3.5:2B installed in Ollama
- A working microphone and speakers for voice mode
- NVIDIA RTX 3050 4GB is the current target hardware

Python packages used by the project include the existing runtime dependencies plus the voice stack used by Voice V1.

---

## Setup

### 1. Install and verify Ollama

Install Ollama and make sure the model is available:

```powershell
ollama list
```

You should see:

```text
qwen3.5:2B
```

You can also verify the model directly:

```powershell
ollama run qwen3.5:2B
```

### 2. Install Python dependencies

From the project environment:

```powershell
pip install -r requirements.txt
```

### 3. Configure Milo

Edit:

```text
config/assistant.yaml
```

The important model settings are:

```yaml
model:
  backend: "ollama"
  ollama_model: "qwen3.5:2B"
  ollama_host: "http://localhost:11434"
```

Voice settings are controlled from the same file.

### 4. Configure actions

Edit:

```text
config/actions.yaml
```

Only applications listed there can be launched.

---

## Running Milo

### Text mode

From the project directory:

```powershell
python main.py
```

### Voice mode

Enable `voice.enabled` in `config/assistant.yaml`, then run:

```powershell
python main.py --voice
```

Voice V1 is push-to-talk: press Enter to start recording and Enter again to stop.

### Mock mode

Use the mock backend for pipeline testing without loading a real model:

```powershell
python main.py --mock
```

---

## Voice models

Voice V1 uses local model files; they are not bundled with the project.

### Speech-to-text

**Model:** sherpa-onnx Whisper `small.en`

Place the extracted model under the configured STT directory.

### Text-to-speech

**Model:** sherpa-onnx Piper/VITS `en_US-amy-medium`

Place the extracted model under the configured TTS directory.

The exact paths are controlled by `config/assistant.yaml`.

---

## Safety model

Milo is intentionally conservative about computer actions.

### Current rules

- No arbitrary shell execution from user text.
- Application launches come only from `config/actions.yaml`.
- Unknown applications are refused.
- The LLM does not receive direct subprocess access.
- Voice input uses the same safety path as typed input.
- Action failures are returned as user-facing messages instead of crashing the application.

This architecture is designed so that natural-language understanding can become more capable later without removing deterministic execution controls.

---

## Reliability work already completed

The current foundation has been tested and hardened for several known failure modes:

- Ollama connection failures no longer kill the whole text session.
- Ollama requests have a timeout.
- Invalid backend configuration is rejected clearly.
- Missing Ollama dependencies produce clearer errors.
- Long-term facts avoid creating new duplicate entries.
- Multi-line assistant responses are flattened before journal storage so entries remain one physical line.
- Journal expiry has been tested at the 7-day boundary.
- Ctrl-C during model generation cancels the current generation instead of terminating the entire application.
- Voice initialization and voice processing failures are handled without silently corrupting the text pipeline.

---

## Current limitations

Milo is intentionally still small. The following are **not** implemented yet:

- Wake word / always-listening mode
- Automatic VAD-based turn detection
- Barge-in / interrupt while Milo is speaking
- Closing applications
- Arbitrary system commands
- General computer-use automation
- Web browsing
- Semantic/embedding-based memory search
- Structured people/topic memory
- GUI/desktop application
- Proactive behavior
- Multi-model gatekeeper/executor orchestration
- Native Qwen tool-calling as the primary router

---

## Development philosophy

Milo follows a **vertical-slice** approach:

> Build the smallest complete capability that works end-to-end, test it on the real machine, then extend it.

The project intentionally avoids implementing large future systems before the current slice is actually useful.

For new capabilities, the preferred pattern is:

```text
Natural-language input
        ↓
Interpretation
        ↓
Deterministic validation / permission check
        ↓
Capability execution
        ↓
Human-readable result
```

---

## Roadmap

### Near term

- Use and stress-test Voice V1 in real daily conversations.
- Improve natural command phrasing while preserving deterministic safety.
- Continue testing the command filter against false positives and edge cases.

### Later

- Voice V2: automatic turn detection / VAD
- Wake word
- Barge-in / interruption handling
- Additional safe commands such as closing applications or opening approved locations
- Stronger memory retrieval
- More advanced tool/capability orchestration

---


The current focus is **making Milo understand natural requests reliably without sacrificing the deterministic safety boundary**, then extending that capability gradually.

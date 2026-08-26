"""
main.py — Phase 0 entry point.

python main.py
    -> user message
    -> conversation state
    -> personality prompt
    -> Qwen
    -> streamed response

No memory retrieval, no tools, no voice yet. This is deliberately the
smallest end-to-end loop, per the build plan's "First Build Target" (§17).

Run with --mock to exercise the full pipeline without real model weights.
"""

from __future__ import annotations
from memory.store import MemoryStore

import argparse
import logging
from mind.chat_engine import ChatEngine, OllamaBackend
from core.config import Config, ConfigError, load_config
from core.model_lifecycle import ModelLifecycleManager
from core.state import Role, SessionState
from interface import terminal
from mind.chat_engine import (
    ChatEngine,
    GenerationParams,
    LlamaCppBackend,
    MockBackend,
    build_prompt,
)
from orchestrator.actions import execute_action, extract_action, load_action_whitelist
from orchestrator.router import Intent, classify_intent, extract_remember_fact
from persona.persona import build_system_prompt, load_persona

log = logging.getLogger("assistant")

EXIT_COMMANDS = {"/exit", "/quit"}
RESET_COMMANDS = {"/reset"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local AI companion — Phase 0 chat loop")
    parser.add_argument(
        "--config", default="config/assistant.yaml", help="Path to assistant.yaml"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the mock model backend instead of loading real weights",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Push-to-talk: Enter to record, Enter to stop; spoken replies via TTS",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def build_engine(cfg: Config, manager: ModelLifecycleManager, use_mock: bool) -> ChatEngine:
    def load_fn():
        if use_mock:
            return MockBackend()
        if cfg.model.backend == "ollama":
            return OllamaBackend(cfg.model.ollama_model, cfg.model.ollama_host)
        return LlamaCppBackend(
            model_path=cfg.model.path,
            context_length=cfg.model.context_length,
            gpu_layers=cfg.model.gpu_layers,
            threads=cfg.model.threads,
        )

    def unload_fn(backend):
        unload = getattr(backend, "unload", None)
        if unload:
            unload()

    manager.register("chat", load_fn=load_fn, unload_fn=unload_fn)
    backend = manager.acquire("chat")
    return ChatEngine(backend)


def render_conversation(state: SessionState, max_turns: int) -> str:
    """Turn recent SessionState turns into the ChatML-ish block build_prompt expects."""
    lines = []
    for turn in state.recent(max_turns):
        tag = "user" if turn.role == Role.USER else "assistant"
        lines.append(f"<|im_start|>{tag}\n{turn.text}<|im_end|>")
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> None:
    args = parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"Config error: {e}")
        raise SystemExit(1)

    setup_logging(cfg.app.log_level)
    log.info("Starting %s", cfg.app.name)

    persona = load_persona(cfg.persona.active, personas_dir="persona/personas")
    system_prompt = build_system_prompt(persona)

    manager = ModelLifecycleManager()
    try:
        engine = build_engine(cfg, manager, use_mock=args.mock)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"Model load failed: {e}")
        print("Tip: run with --mock to test the pipeline without real weights.")
        raise SystemExit(1)

    memory = MemoryStore(cfg.app.data_dir)
    memory.cleanup_old()

    action_whitelist = load_action_whitelist()

    state = SessionState()
    gen_params = GenerationParams(
        max_tokens=cfg.generation.max_tokens,
        temperature=cfg.generation.temperature,
        top_p=cfg.generation.top_p,
        repeat_penalty=cfg.generation.repeat_penalty,
        stream=cfg.generation.stream,
    )

    voice = None
    if args.voice:
        # Built up front so missing models/packages fail with one clear
        # message here instead of an exception mid-conversation.
        if not cfg.voice.enabled:
            print("Voice is disabled — set voice.enabled: true in config/assistant.yaml.")
            raise SystemExit(1)
        try:
            from voice.pipeline import VoiceInitError, VoicePipeline

            voice = VoicePipeline(cfg.voice)
        except VoiceInitError as e:
            print(f"Voice init failed: {e}")
            raise SystemExit(1)

    print(f"--- {cfg.app.name} (persona: {persona.name} v{persona.version}) ---")
    print("Type /exit to quit, /reset to clear session context.\n")

    try:
        while True:
            if voice is None:
                user_input = terminal.get_user_input()
            else:
                try:
                    user_input = voice.listen()
                    if user_input:
                        print(f"you (spoken): {user_input}")
                except EOFError:
                    break  # stdin closed
                except Exception as e:
                    # A dead mic or failed decode costs one turn, not the session.
                    print(f"(voice problem: {e} — type this turn instead)")
                    user_input = terminal.get_user_input()

            if user_input.strip() in EXIT_COMMANDS:
                break
            if user_input.strip() in RESET_COMMANDS:
                state.reset()
                print("(session reset)")
                continue
            if not user_input.strip():
                continue

            intent = classify_intent(user_input)
            fact = extract_remember_fact(user_input)
            if fact:
                memory.remember_fact(fact)
                response_text = f"(saved to long-term memory: {fact})"
                print(response_text)

                # Journal the request like any other turn so the transcript
                # shows what was asked, not just the fact that resulted.
                state.add_turn(Role.USER, user_input)
                memory.log_turn("user", user_input)
                state.add_turn(Role.ASSISTANT, response_text)
                memory.log_turn("assistant", response_text)
            elif intent == Intent.ACTION:
                # Actions answer directly — a launch confirmation doesn't
                # need an LLM turn.
                app_name = extract_action(user_input)
                if app_name is None:
                    response_text = "I couldn't tell which app you mean — try 'open <app name>'."
                else:
                    response_text = execute_action(app_name, action_whitelist)
                print(response_text)

                # Log the exchange like any other turn so the transcript stays complete.
                state.add_turn(Role.USER, user_input)
                memory.log_turn("user", user_input)
                state.add_turn(Role.ASSISTANT, response_text)
                memory.log_turn("assistant", response_text)
            else:
                state.add_turn(Role.USER, user_input)
                memory.log_turn("user", user_input)

                conversation_block = render_conversation(state, cfg.session.max_turns_in_context)
                memory_context = memory.build_memory_context()
                prompt = build_prompt(system_prompt, memory_context, conversation_block)

                terminal.show_typing_indicator()
                full_response = []
                try:
                    for chunk in engine.stream_response(prompt, gen_params):
                        terminal.stream_token(chunk)
                        full_response.append(chunk)
                except KeyboardInterrupt:
                    # Ctrl-C mid-generation ends this turn, not the session —
                    # the outer handler stays for Ctrl-C at the input prompt.
                    terminal.newline()
                    print("(cancelled)")
                    continue
                except Exception:
                    # A backend failure (Ollama down, mid-stream drop) should
                    # cost this turn, not the whole session.
                    log.exception("Generation failed")
                    terminal.newline()
                    print("(model error — check that Ollama is running, then try again)")
                    full_response = ["(model error — reply lost, please try again.)"]
                terminal.newline()

                response_text = "".join(full_response).strip()
                state.add_turn(Role.ASSISTANT, response_text)
                memory.log_turn("assistant", response_text)

            if voice is not None and response_text:
                voice.say(response_text)

    except KeyboardInterrupt:
        pass
    finally:
        engine.unload()
        manager.release_all()
        print("\n(session ended)")


if __name__ == "__main__":
    main()

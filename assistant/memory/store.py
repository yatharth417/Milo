"""
memory/store.py — Phase 1 memory: rolling window + explicit long-term facts.

Two tiers, deliberately simple:

- Episodic (journal/): every turn gets appended to a daily markdown file,
  auto-expires after RETENTION_DAYS. Gives "good context of the week"
  without any judgment calls about what's worth keeping — trades
  permanence for removing the hardest decision (what matters) from the
  critical path.
- Long-term (long_term.md): explicit "remember that ..." facts only, no
  expiry, no model judgment. This is what actually persists identity and
  preferences past a week — the rolling window alone would forget your
  name, which defeats the point.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

RETENTION_DAYS = 7
JOURNAL_CHAR_BUDGET = 6000   # rough cap so a week of chat doesn't blow the prompt
LONG_TERM_CHAR_BUDGET = 2000


class MemoryStore:
    def __init__(self, data_dir: Path):
        self.journal_dir = Path(data_dir) / "journal"
        self.long_term_path = Path(data_dir) / "preferences" / "long_term.md"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.long_term_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.long_term_path.exists():
            self.long_term_path.write_text("# Long-term facts\n\n", encoding="utf-8")

    # ---------- episodic (rolling window) ----------

    def _today_path(self) -> Path:
        return self.journal_dir / f"{date.today().isoformat()}.md"

    def log_turn(self, role: str, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        line = f"- **{timestamp} {role}:** {text}\n"
        with self._today_path().open("a", encoding="utf-8") as f:
            f.write(line)

    def recent_journal(
        self, days: int = RETENTION_DAYS, char_budget: int = JOURNAL_CHAR_BUDGET
    ) -> str:
        cutoff = date.today() - timedelta(days=days - 1)
        chunks = []
        for f in sorted(self.journal_dir.glob("*.md")):
            try:
                file_date = date.fromisoformat(f.stem)
            except ValueError:
                continue
            if file_date >= cutoff:
                chunks.append(f.read_text(encoding="utf-8"))
        combined = "\n".join(chunks)
        if len(combined) > char_budget:
            combined = combined[-char_budget:]  # keep the most recent part
        return combined

    def cleanup_old(self, days: int = RETENTION_DAYS) -> None:
        """Delete journal files older than the retention window. Call at startup."""
        cutoff = date.today() - timedelta(days=days)
        for f in self.journal_dir.glob("*.md"):
            try:
                file_date = date.fromisoformat(f.stem)
            except ValueError:
                continue
            if file_date < cutoff:
                log.info("Expiring journal file %s (older than %d days)", f.name, days)
                f.unlink()

    # ---------- long-term (explicit, permanent) ----------

    def remember_fact(self, text: str) -> None:
        timestamp = date.today().isoformat()
        with self.long_term_path.open("a", encoding="utf-8") as f:
            f.write(f"- ({timestamp}) {text}\n")
        log.info("Saved long-term fact: %s", text)

    def long_term_facts(self, char_budget: int = LONG_TERM_CHAR_BUDGET) -> str:
        text = self.long_term_path.read_text(encoding="utf-8")
        if len(text) > char_budget:
            text = text[-char_budget:]
        return text

    # ---------- combined context for prompt injection ----------

    def build_memory_context(self) -> str:
        facts = self.long_term_facts()
        journal = self.recent_journal()
        parts = []
        if facts.strip():
            parts.append(f"### Long-term facts\n{facts.strip()}")
        if journal.strip():
            parts.append(f"### This week's conversation log\n{journal.strip()}")
        return "\n\n".join(parts)
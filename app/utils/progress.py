from __future__ import annotations

import sys
import time


class ProgressReporter:
    def __init__(self, total_papers: int) -> None:
        self.total_papers = max(total_papers, 0)
        self.started_at = time.time()
        self._last_paper_line = ""

    def start(self, output_dir: str) -> None:
        self._write(f"[autopaper] output: {output_dir}")
        self._write(f"[autopaper] papers: {self.total_papers}")

    def paper_stage(self, index: int, arxiv_id: str, stage: str) -> None:
        line = f"{self._bar(index - 1, self.total_papers)} paper {index}/{self.total_papers} {arxiv_id} -> {stage}"
        if line != self._last_paper_line:
            self._write(line)
            self._last_paper_line = line

    def paper_done(self, index: int, arxiv_id: str, status: str) -> None:
        self._write(f"{self._bar(index, self.total_papers)} paper {index}/{self.total_papers} {arxiv_id} -> {status}")

    def graph_stage(self, stage: str) -> None:
        self._write(f"[graph] {stage}")

    def finish(self, status: str) -> None:
        elapsed = time.time() - self.started_at
        self._write(f"[autopaper] finished: {status} ({elapsed:.1f}s)")

    def _bar(self, current: int, total: int, width: int = 24) -> str:
        if total <= 0:
            return "[" + ("-" * width) + "]"
        filled = int(width * current / total)
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def _write(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

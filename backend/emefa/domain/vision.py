"""Vision provider contract for user-requested image analysis."""

from pathlib import Path
from typing import Protocol


class VisionAnalyzer(Protocol):
    async def analyze(self, image_path: Path, content_type: str, question: str) -> str: ...

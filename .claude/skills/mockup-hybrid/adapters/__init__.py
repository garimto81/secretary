"""
Mockup Hybrid Adapters 모듈

HTML, Stitch, Mermaid 백엔드 어댑터를 제공합니다.
"""

from .html_adapter import HTMLAdapter, HTMLGenerationResult
from .stitch_adapter import StitchAdapter, StitchGenerationResult
from .mermaid_adapter import MermaidAdapter, MermaidGenerationResult

__all__ = [
    "HTMLAdapter",
    "HTMLGenerationResult",
    "StitchAdapter",
    "StitchGenerationResult",
    "MermaidAdapter",
    "MermaidGenerationResult",
]

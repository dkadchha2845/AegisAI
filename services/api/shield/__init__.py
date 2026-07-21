"""
CFSRP — Citizen Fraud Shield & Response Platform (KAVACH Module 3).

The user-facing layer. It does not detect scams itself; it translates the
intelligence from Module 1 (RSSIE) and Module 2 (FIGAE) into immediate,
actionable citizen protection: real-time threat verification, stage-aware
guidance, an emergency-response engine, an evidence vault, and structured
cybercrime-complaint generation.

Detect → Connect → **Protect**.
"""

from .complaint import build_complaint
from .guidance import build_guidance
from .response import build_response
from .verify import verify

__all__ = ["verify", "build_guidance", "build_response", "build_complaint"]

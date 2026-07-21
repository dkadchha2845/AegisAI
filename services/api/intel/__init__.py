"""
FIGAE — Fraud Intelligence & Geospatial Analytics Engine (KAVACH Module 2).

Correlates individual Module 1 scam detections into large-scale cybercrime
intelligence: a fraud knowledge graph, community/campaign detection, geospatial
hotspots, dynamic risk scoring, and investigation-ready reports.

Public surface is `get_intel()` (the cached service) and the dataclasses the
routes serialise. Everything is offline and deterministic; Neo4j is a documented
production swap behind `graph.FraudGraph`, not a runtime requirement.
"""

from .service import get_intel

__all__ = ["get_intel"]

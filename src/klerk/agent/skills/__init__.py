"""agentskills.io manifests for klerk's 5 capabilities.

Five YAML files, one per capability:
  - escalation.yaml      (A)  draft a routing email on low confidence
  - action_items.yaml    (B)  extract structured action items
  - conflict_report.yaml (C)  LangGraph-orchestrated contradiction sweep
  - writer.yaml          (D)  adversarial multi-drafter proposal
  - drift.yaml           (E)  scheduled corpus drift detection

The manifests are portable: any agent runtime that consumes the
agentskills.io spec can mount these and call klerk's Python entrypoints
directly. They're declarative — runtime config (LLM provider, schedule,
observability span names) is data, not code.
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def list_manifests() -> list[Path]:
    """Return the absolute paths of every shipped YAML manifest."""
    return sorted(_SKILLS_DIR.glob("*.yaml"))


def manifests() -> list[dict]:
    """Load and return all manifests as dicts."""
    import yaml

    return [yaml.safe_load(p.read_text()) for p in list_manifests()]

"""Generate LangGraph state machine PNG diagram (architecture visualization)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.graph.builder import build_graph


def main() -> None:
    print("Compiling LangGraph StateGraph...")
    graph = build_graph()
    output_path = ROOT / "docs" / "architecture" / "langgraph_workflow.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Rendering Mermaid PNG...")
    png_bytes = graph.get_graph().draw_mermaid_png()
    with open(output_path, "wb") as f:
        f.write(png_bytes)

    print(f"Successfully generated LangGraph image at: {output_path} ({len(png_bytes):,} bytes)")


if __name__ == "__main__":
    main()

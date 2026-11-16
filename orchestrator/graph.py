"""
graph.py — LangGraph StateGraph for the AMP orchestrator.

Graph shape:
  START → csa → stage2 → da → END

  csa fires SWA as asyncio.create_task() (background, non-blocking).
  stage2 runs RRA/GPA/IAA concurrently via asyncio.gather internally.

Used by:
  - flow.py::run_amp_workflow()  (programmatic)
  - langgraph.json               (LangGraph Studio — langgraph dev)
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .nodes import csa_node, da_node, stage2_node
from .state import AmpGraphState


def build_graph(checkpointer=None) -> StateGraph:
    """Build and compile the AMP StateGraph."""
    g = StateGraph(AmpGraphState)

    g.add_node("csa",    csa_node)
    g.add_node("stage2", stage2_node)
    g.add_node("da",     da_node)

    g.set_entry_point("csa")
    g.add_edge("csa",    "stage2")
    g.add_edge("stage2", "da")
    g.add_edge("da",     END)

    return g.compile(checkpointer=checkpointer or MemorySaver())


# Lazy singleton — shared by flow.py and LangGraph Studio
_graph = None


def get_graph():
    """Return the compiled AMP graph (singleton)."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph

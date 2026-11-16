from .schemas import (
    EventLogEntry, ProcessState, ActionRecommendation,
    PredictedAction, IAAState, ProcessStep, TaskItem, WorkflowStep,
)
from .iaa import run_iaa, iaa_node, build_process_state
from .retriever import IAARetriever
from .chain import apply_overrides
from .case_store import CaseStore

# main.py is the ADK entry point and pulls in `google.adk`. ADK was removed
# from the active stack — FastAPI on port 8003 is the live interface — so this
# import is best-effort only. If ADK isn't installed, root_agent stays None
# and the FastAPI / orchestrator flow keeps working.
try:
    from .main import root_agent  # noqa: F401
except ImportError:
    root_agent = None  # type: ignore[assignment]

__all__ = [
    "EventLogEntry", "ProcessState", "ActionRecommendation",
    "PredictedAction", "IAAState", "ProcessStep", "TaskItem", "WorkflowStep",
    "run_iaa", "iaa_node", "build_process_state",
    "IAARetriever", "apply_overrides",
    "CaseStore",
    "root_agent",
]

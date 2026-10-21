"""POST /api/study (spec P2-04) — the HTTP surface over the case-study runner.

The body is a :class:`~ngdesign.study.CaseStudyRequest` (a ``CaseStudy`` without
``base``): the route fills ``base`` from the default project's current flowsheet
and runs :func:`ngdesign.study.run` synchronously — a small grid solves in
seconds; the queued job model (spec P3-02) is the async surface for long ones.

What stays here: the HTTP mapping. A missing thermo or unit plugin (the
registry's ``KeyError``) is 501; a structurally impossible study (ValueError,
e.g. an empty axis) is 422. A case whose units fail or recycles do not converge
is a 200 with its row in ``StudyResult.failed`` (spec P2-02): the table is the
answer, the failure is data in it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ngdesign import registry
from ngdesign.agent.tools import ProjectStore
from ngdesign.api.deps import default_project_store
from ngdesign.study import CaseStudy, CaseStudyRequest, StudyResult
from ngdesign.study import run as run_study

router = APIRouter()


@router.post("/api/study")
def study_case(
    body: CaseStudyRequest, store: Annotated[ProjectStore, Depends(default_project_store)]
) -> StudyResult:
    """Run the parameter grid against the current project's flowsheet."""
    project = store.get()
    study = CaseStudy(
        id=body.id,
        inputs=body.inputs,
        outputs=body.outputs,
        base=project.flowsheet,
    )
    try:
        thermo = registry.create("thermo", project.flowsheet.thermo)
        return run_study(study, thermo)
    except KeyError as exc:
        # The registry names the plugin nobody registered: a missing kind, 501.
        raise HTTPException(status_code=501, detail=str(exc.args[0] if exc.args else exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router", "study_case"]

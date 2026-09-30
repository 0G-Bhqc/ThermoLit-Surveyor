"""
api.py — 最小 FastAPI 服务(可选依赖 server:pip install 'thermolit-surveyor[server]')。

  POST /survey      提交调研任务(后台线程执行)→ {job_id}
  GET  /jobs/{id}   查询任务状态与产物(报告/审计/假说/方案/指标)
  GET  /health      存活探针

启动:uvicorn thermolit.api:app --port 8000
"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from thermolit import __version__
except ImportError:  # pragma: no cover
    __version__ = "0.0.0"

app = FastAPI(title="ThermoLit-Surveyor", version=__version__,
              description="缺口驱动、物理约束的研究闭环智能体")

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class SurveyRequest(BaseModel):
    query: str = Field(min_length=3, description="初始检索查询")
    profile: str = "thermoelectric"
    top_k: Optional[int] = None
    followup: Optional[int] = None
    check_dois: bool = True


def _run_job(job_id: str, req: SurveyRequest) -> None:
    from thermolit.graph import run_agent
    from thermolit.profiles import THERMOELECTRIC_PROFILE

    try:
        state = run_agent(req.query, profile=THERMOELECTRIC_PROFILE,
                          top_k=req.top_k, num_followup=req.followup,
                          check_dois=req.check_dois)
        result = {
            "status": "done",
            "material_system": state.get("material_system"),
            "report": state.get("deep_gap_report", ""),
            "audit_table_md": state.get("audit_table_md", ""),
            "hypotheses": state.get("hypotheses", []),
            "experiment_plan": state.get("experiment_plan", {}),
            "doi_check": state.get("doi_check", {}),
            "metrics": state.get("metrics", {}),
        }
    except Exception as e:  # 后台任务兜底:任何异常都落到 job 状态,不炸线程
        result = {"status": "error", "error": str(e)}
    with _jobs_lock:
        _jobs[job_id].update(result)


@app.post("/survey")
def submit_survey(req: SurveyRequest) -> Dict[str, str]:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}
    threading.Thread(target=_run_job, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id, "status": "running"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": __version__}

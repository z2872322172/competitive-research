from app.db import SessionLocal
from app.workflows.research_graph import run_research_workflow
from app.workflows.research_graph import latest_success_checkpoint
from app.workers.celery_app import celery_app


@celery_app.task(name="research.run", autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def run_research_task(run_id: int, resume: bool = False) -> int:
    db = SessionLocal()
    try:
        effective_resume = resume or latest_success_checkpoint(db, run_id) is not None
        run_research_workflow(db, run_id, delay_seconds=0.2, resume=effective_resume)
        return run_id
    finally:
        db.close()

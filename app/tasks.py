import csv
import io
import logging

from celery import shared_task
from django.db import IntegrityError

from app.dependencies import container

logger = logging.getLogger(__name__)


@shared_task(
  bind=True,
  autoretry_for=(Exception,),
  retry_backoff=True,
  retry_kwargs={"max_retries": 3},
  acks_late=True,
)
def process_enrollment_task(self, enrollment_id: str) -> dict:
  service = container.enrollment_service

  try:
    result = service.validate_and_finalize(enrollment_id)
    return {
      "enrollment_id": result.id,
      "status": result.status.value,
      "error_message": result.error_message,
    }
  except Exception as exc:
    logger.exception("Failed to process enrollment %s", enrollment_id)
    try:
      result = service.finalize_enrollment(
        enrollment_id,
        success=False,
        error_message=str(exc),
      )
      return {
        "enrollment_id": result.id,
        "status": result.status.value,
        "error_message": result.error_message,
      }
    except Exception:
      raise self.retry(exc=exc)


@shared_task(bind=True)
def process_enrollment_batch_task(self, enrollment_ids: list[str]) -> dict:
  processed = 0
  failed = 0

  for enrollment_id in enrollment_ids:
    try:
      result = process_enrollment_task(enrollment_id)
      if result["status"] == "processed":
        processed += 1
      else:
        failed += 1
    except Exception:
      failed += 1
      logger.exception("Batch item failed: %s", enrollment_id)

  return {"processed": processed, "failed": failed, "total": len(enrollment_ids)}

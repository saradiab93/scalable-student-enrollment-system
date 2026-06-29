import logging

from celery import group, shared_task
from django.db import OperationalError

from app.dependencies import container

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
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

    except OperationalError:
        raise

    except Exception as exc:
        logger.exception("Failed to process enrollment %s", enrollment_id)

        result = service.finalize_enrollment(
            enrollment_id=enrollment_id,
            success=False,
            error_message=str(exc),
        )

        return {
            "enrollment_id": result.id,
            "status": result.status.value,
            "error_message": result.error_message,
        }


@shared_task
def process_enrollment_batch_task(enrollment_ids: list[str]) -> str:
    job = group(
        process_enrollment_task.s(enrollment_id)
        for enrollment_id in enrollment_ids
    ).apply_async()

    return job.id
from datetime import datetime
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from app.application.dtos import EnrollmentCreateDTO, EnrollmentDTO, EnrollmentReportDTO
from app.application.interfaces.aggregate_repository import AggregateRepository
from app.application.interfaces.enrollment_repository import EnrollmentRepository
from app.domain.enums import EnrollmentStatus
from app.domain.exceptions import EnrollmentNotFoundError
from app.infrastructure.models import EnrollmentAggregate, EnrollmentRecord


class DjangoEnrollmentRepository(EnrollmentRepository):
  def _to_dto(self, record: EnrollmentRecord) -> EnrollmentDTO:
    return EnrollmentDTO(
      id=str(record.id),
      student_id=record.student_id,
      region=record.region,
      grade=record.grade,
      name=record.name,
      status=EnrollmentStatus(record.status),
      error_message=record.error_message,
      created_at=record.created_at,
      processed_at=record.processed_at,
    )

  def create_pending(self, data: EnrollmentCreateDTO) -> EnrollmentDTO:
    record = EnrollmentRecord.objects.create(
      student_id=data.student_id,
      name=data.name,
      region=data.region,
      grade=data.grade,
      status=EnrollmentStatus.PENDING.value,
    )
    return self._to_dto(record)

  def get_by_id(self, enrollment_id: str) -> Optional[EnrollmentDTO]:
    try:
      record = EnrollmentRecord.objects.get(id=enrollment_id)
    except EnrollmentRecord.DoesNotExist:
      return None
    return self._to_dto(record)

  def update_status(
    self,
    enrollment_id: str,
    status: EnrollmentStatus,
    error_message: str = "",
  ) -> EnrollmentDTO:
    with transaction.atomic():
      try:
        record = EnrollmentRecord.objects.select_for_update().get(id=enrollment_id)
      except EnrollmentRecord.DoesNotExist:
        raise EnrollmentNotFoundError(f"Enrollment {enrollment_id} not found")

      record.status = status.value
      record.error_message = error_message
      if status in (EnrollmentStatus.PROCESSED, EnrollmentStatus.FAILED):
        record.processed_at = timezone.now()
      try:
        record.save(
          update_fields=["status", "error_message", "processed_at"],
        )
      except IntegrityError:
        raise
    return self._to_dto(record)

  def exists_processed(self, student_id: str) -> bool:
    return EnrollmentRecord.objects.filter(
      student_id=student_id,
      status=EnrollmentStatus.PROCESSED.value,
    ).exists()


class DjangoAggregateRepository(AggregateRepository):
  def increment(self, region: str, grade: int) -> None:
    with transaction.atomic():
      aggregate, _ = EnrollmentAggregate.objects.select_for_update().get_or_create(
        region=region,
        grade=grade,
        defaults={"count": 0},
      )
      aggregate.count = F("count") + 1
      aggregate.save(update_fields=["count"])

  def get_report(
    self,
    region: Optional[str] = None,
    grade: Optional[int] = None,
  ) -> list[EnrollmentReportDTO]:
    queryset = EnrollmentAggregate.objects.all()

    if region is not None:
      queryset = queryset.filter(region=region)
    if grade is not None:
      queryset = queryset.filter(grade=grade)

    return [
      EnrollmentReportDTO(
        region=row.region,
        grade=row.grade,
        count=row.count,
      )
      for row in queryset.order_by("region", "grade")
    ]

  def rebuild_from_processed_records(self) -> int:
    """Rebuild aggregate table from processed enrollment records."""
    from django.db.models import Count

    with transaction.atomic():
      EnrollmentAggregate.objects.all().delete()
      aggregates = (
        EnrollmentRecord.objects.filter(
          status=EnrollmentStatus.PROCESSED.value,
        )
        .values("region", "grade")
        .annotate(count=Count("id"))
      )
      created = EnrollmentAggregate.objects.bulk_create(
        [
          EnrollmentAggregate(
            region=row["region"],
            grade=row["grade"],
            count=row["count"],
          )
          for row in aggregates
        ],
      )
    return len(created)

from typing import Optional

from django.db import IntegrityError

from app.application.dtos import (
  EnrollmentCreateDTO,
  EnrollmentDTO,
  EnrollmentReportDTO,
  IngestionResultDTO,
)
from app.application.interfaces.aggregate_repository import AggregateRepository
from app.application.interfaces.enrollment_repository import EnrollmentRepository
from app.domain.enums import EnrollmentStatus
from app.domain.exceptions import (
  EnrollmentNotFoundError,
  InvalidEnrollmentDataError,
)


class EnrollmentService:
  VALID_GRADES = range(1, 13)

  def __init__(
    self,
    enrollment_repo: EnrollmentRepository,
    aggregate_repo: AggregateRepository,
  ) -> None:
    self._enrollment_repo = enrollment_repo
    self._aggregate_repo = aggregate_repo

  def validate_enrollment_data(self, data: EnrollmentCreateDTO) -> None:
    if not data.student_id or not data.student_id.strip():
      raise InvalidEnrollmentDataError("student_id is required")
    if not data.region or not data.region.strip():
      raise InvalidEnrollmentDataError("region is required")
    if data.grade not in self.VALID_GRADES:
      raise InvalidEnrollmentDataError(
        f"grade must be between 1 and 12, got {data.grade}",
      )

  def ingest_enrollments(
    self,
    enrollments: list[EnrollmentCreateDTO],
  ) -> IngestionResultDTO:
    enrollment_ids: list[str] = []

    for enrollment_data in enrollments:
      dto = self._enrollment_repo.create_pending(enrollment_data)
      enrollment_ids.append(dto.id)

    return IngestionResultDTO(
      accepted=len(enrollment_ids),
      enrollment_ids=enrollment_ids,
    )

  def finalize_enrollment(
    self,
    enrollment_id: str,
    success: bool,
    error_message: str = "",
  ) -> EnrollmentDTO:
    enrollment = self._enrollment_repo.get_by_id(enrollment_id)
    if enrollment is None:
      raise EnrollmentNotFoundError(f"Enrollment {enrollment_id} not found")

    if enrollment.status != EnrollmentStatus.PENDING:
      return enrollment

    if success:
      try:
        if self._enrollment_repo.exists_processed(enrollment.student_id):
          return self._enrollment_repo.update_status(
            enrollment_id,
            EnrollmentStatus.FAILED,
            error_message="Student already enrolled",
          )
        updated = self._enrollment_repo.update_status(
          enrollment_id,
          EnrollmentStatus.PROCESSED,
        )
      except IntegrityError:
        return self._enrollment_repo.update_status(
          enrollment_id,
          EnrollmentStatus.FAILED,
          error_message="Student already enrolled",
        )

      self._aggregate_repo.increment(updated.region, updated.grade)
      return updated

    return self._enrollment_repo.update_status(
      enrollment_id,
      EnrollmentStatus.FAILED,
      error_message=error_message,
    )

  def validate_and_finalize(self, enrollment_id: str) -> EnrollmentDTO:
    enrollment = self._enrollment_repo.get_by_id(enrollment_id)
    if enrollment is None:
      raise EnrollmentNotFoundError(f"Enrollment {enrollment_id} not found")

    if enrollment.status != EnrollmentStatus.PENDING:
      return enrollment

    try:
      self.validate_enrollment_data(
        EnrollmentCreateDTO(
          student_id=enrollment.student_id,
          region=enrollment.region,
          grade=enrollment.grade,
          name=enrollment.name,
        ),
      )
    except InvalidEnrollmentDataError as exc:
      return self.finalize_enrollment(enrollment_id, success=False, error_message=str(exc))

    if self._enrollment_repo.exists_processed(enrollment.student_id):
      return self.finalize_enrollment(
        enrollment_id,
        success=False,
        error_message="Student already enrolled",
      )

    return self.finalize_enrollment(enrollment_id, success=True)

  def get_enrollment(self, enrollment_id: str) -> EnrollmentDTO:
    enrollment = self._enrollment_repo.get_by_id(enrollment_id)
    if enrollment is None:
      raise EnrollmentNotFoundError(f"Enrollment {enrollment_id} not found")
    return enrollment


class ReportingService:
  def __init__(self, aggregate_repo: AggregateRepository) -> None:
    self._aggregate_repo = aggregate_repo

  def get_enrollment_report(
    self,
    region: Optional[str] = None,
    grade: Optional[int] = None,
  ) -> list[EnrollmentReportDTO]:
    return self._aggregate_repo.get_report(region=region, grade=grade)

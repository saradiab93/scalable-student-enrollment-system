from app.application.interfaces.aggregate_repository import AggregateRepository
from app.application.interfaces.enrollment_repository import EnrollmentRepository
from app.application.services.enrollment_service import EnrollmentService, ReportingService
from app.infrastructure.repositories.django_repositories import (
  DjangoAggregateRepository,
  DjangoEnrollmentRepository,
)


class Container:
  """Simple dependency injection container."""

  def __init__(self) -> None:
    self._enrollment_repo: EnrollmentRepository | None = None
    self._aggregate_repo: AggregateRepository | None = None
    self._enrollment_service: EnrollmentService | None = None
    self._reporting_service: ReportingService | None = None

  @property
  def enrollment_repository(self) -> EnrollmentRepository:
    if self._enrollment_repo is None:
      self._enrollment_repo = DjangoEnrollmentRepository()
    return self._enrollment_repo

  @property
  def aggregate_repository(self) -> AggregateRepository:
    if self._aggregate_repo is None:
      self._aggregate_repo = DjangoAggregateRepository()
    return self._aggregate_repo

  @property
  def enrollment_service(self) -> EnrollmentService:
    if self._enrollment_service is None:
      self._enrollment_service = EnrollmentService(
        enrollment_repo=self.enrollment_repository,
        aggregate_repo=self.aggregate_repository,
      )
    return self._enrollment_service

  @property
  def reporting_service(self) -> ReportingService:
    if self._reporting_service is None:
      self._reporting_service = ReportingService(
        aggregate_repo=self.aggregate_repository,
      )
    return self._reporting_service


container = Container()

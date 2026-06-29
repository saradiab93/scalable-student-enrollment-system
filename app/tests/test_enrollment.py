import csv
import io
import threading
from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from app.application.dtos import EnrollmentCreateDTO
from app.application.services.enrollment_service import EnrollmentService
from app.dependencies import container
from app.domain.enums import EnrollmentStatus
from app.infrastructure.models import EnrollmentAggregate, EnrollmentRecord
from app.infrastructure.repositories.django_repositories import (
  DjangoAggregateRepository,
  DjangoEnrollmentRepository,
)
from app.tasks import process_enrollment_task


class EnrollmentIngestionAPITest(APITestCase):
  def test_json_ingestion_returns_202_and_creates_pending_records(self):
    payload = {
      "enrollments": [
        {
          "student_id": "STU001",
          "region": "North",
          "grade": 5,
          "name": "Sara",
        },
        {
          "student_id": "STU002",
          "region": "South",
          "grade": 7,
          "name": "Omar",
        },
      ],
    }

    with patch("app.interfaces.api.views.process_enrollment_task.delay") as mock_delay:
      response = self.client.post(
        reverse("enrollment-ingest"),
        payload,
        format="json",
      )

    self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
    self.assertEqual(response.data["accepted"], 2)
    self.assertEqual(mock_delay.call_count, 2)

    records = EnrollmentRecord.objects.all()
    self.assertEqual(records.count(), 2)
    self.assertTrue(all(r.status == EnrollmentStatus.PENDING.value for r in records))

  def test_csv_ingestion(self):
    csv_content = "student_id,region,grade,name\nSTU003,East,3,Charlie\n"
    csv_file = io.BytesIO(csv_content.encode("utf-8"))
    csv_file.name = "enrollments.csv"

    with patch("app.interfaces.api.views.process_enrollment_task.delay"):
      response = self.client.post(
        reverse("enrollment-ingest"),
        {"file": csv_file},
        format="multipart",
      )

    self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
    record = EnrollmentRecord.objects.get(student_id="STU003")
    self.assertEqual(record.region, "East")
    self.assertEqual(record.grade, 3)


class EnrollmentProcessingTest(APITestCase):
  def setUp(self):
    self.service = EnrollmentService(
      enrollment_repo=DjangoEnrollmentRepository(),
      aggregate_repo=DjangoAggregateRepository(),
    )

  def test_successful_processing_updates_aggregate(self):
    result = self.service.ingest_enrollments(
      [EnrollmentCreateDTO(student_id="STU100", region="West", grade=10)],
    )
    enrollment_id = result.enrollment_ids[0]

    processed = self.service.validate_and_finalize(enrollment_id)

    self.assertEqual(processed.status, EnrollmentStatus.PROCESSED)
    aggregate = EnrollmentAggregate.objects.get(region="West", grade=10)
    self.assertEqual(aggregate.count, 1)

  def test_invalid_grade_marks_failed(self):
    record = EnrollmentRecord.objects.create(
      student_id="STU101",
      region="West",
      grade=99,
      status=EnrollmentStatus.PENDING.value,
    )

    result = self.service.validate_and_finalize(str(record.id))

    self.assertEqual(result.status, EnrollmentStatus.FAILED)
    self.assertIn("grade", result.error_message.lower())

  def test_duplicate_student_marks_second_as_failed(self):
    first = self.service.ingest_enrollments(
      [EnrollmentCreateDTO(student_id="STU200", region="North", grade=5)],
    )
    self.service.validate_and_finalize(first.enrollment_ids[0])

    second = self.service.ingest_enrollments(
      [EnrollmentCreateDTO(student_id="STU200", region="North", grade=5)],
    )
    result = self.service.validate_and_finalize(second.enrollment_ids[0])

    self.assertEqual(result.status, EnrollmentStatus.FAILED)
    self.assertIn("already enrolled", result.error_message.lower())


class FailedBackgroundTaskTest(APITestCase):
  def test_task_marks_enrollment_failed_on_processing_error(self):
    record = EnrollmentRecord.objects.create(
      student_id="STU300",
      region="East",
      grade=4,
      status=EnrollmentStatus.PENDING.value,
    )

    with patch.object(
      EnrollmentService,
      "validate_and_finalize",
      side_effect=RuntimeError("Simulated worker crash"),
    ):
      process_enrollment_task(str(record.id))

    record.refresh_from_db()
    self.assertEqual(record.status, EnrollmentStatus.FAILED.value)
    self.assertIn("Simulated worker crash", record.error_message)


class ConcurrentEnrollmentRaceConditionTest(TransactionTestCase):
  """
  Demonstrates handling of concurrent duplicate enrollment attempts.
  Only one enrollment should succeed; the other must fail safely.
  """

  def test_concurrent_duplicate_enrollment_race_condition(self):
    service = EnrollmentService(
      enrollment_repo=DjangoEnrollmentRepository(),
      aggregate_repo=DjangoAggregateRepository(),
    )

    first = service.ingest_enrollments(
      [EnrollmentCreateDTO(student_id="STU500", region="Central", grade=8)],
    )
    second = service.ingest_enrollments(
      [EnrollmentCreateDTO(student_id="STU500", region="Central", grade=8)],
    )

    results: list[str] = []
    errors: list[Exception] = []

    def process(enrollment_id: str):
      from django.db import connection

      connection.close()
      try:
        result = service.validate_and_finalize(enrollment_id)
        results.append(result.status.value)
      except Exception as exc:
        errors.append(exc)

    threads = [
      threading.Thread(target=process, args=(first.enrollment_ids[0],)),
      threading.Thread(target=process, args=(second.enrollment_ids[0],)),
    ]
    for thread in threads:
      thread.start()
    for thread in threads:
      thread.join()

    processed_count = EnrollmentRecord.objects.filter(
      student_id="STU500",
      status=EnrollmentStatus.PROCESSED.value,
    ).count()
    failed_count = EnrollmentRecord.objects.filter(
      student_id="STU500",
      status=EnrollmentStatus.FAILED.value,
    ).count()

    self.assertEqual(processed_count, 1)
    self.assertEqual(failed_count, 1)

    aggregate = EnrollmentAggregate.objects.get(region="Central", grade=8)
    self.assertEqual(aggregate.count, 1)


class ReportingAPITest(APITestCase):
  def setUp(self):
    repo = DjangoAggregateRepository()
    repo.increment("North", 5)
    repo.increment("North", 5)
    repo.increment("South", 7)

  def test_report_by_region(self):
    response = self.client.get(
      reverse("enrollment-report"),
      {"region": "North"},
    )

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data["total_students"], 2)
    self.assertEqual(len(response.data["results"]), 1)
    self.assertEqual(response.data["results"][0]["count"], 2)

  def test_report_all_regions(self):
    response = self.client.get(reverse("enrollment-report"))

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data["total_students"], 3)


class ReportingPerformanceTest(APITestCase):
  def test_report_query_count_is_bounded(self):
    repo = DjangoAggregateRepository()
    for region in ("A", "B", "C"):
      for grade in range(1, 5):
        for _ in range(3):
          repo.increment(region, grade)

    connection.queries_log.clear()
    with self.assertNumQueries(1):
      container.reporting_service.get_enrollment_report()

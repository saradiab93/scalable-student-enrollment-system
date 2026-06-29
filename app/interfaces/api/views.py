import csv
import io
import logging

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from app.application.dtos import EnrollmentCreateDTO
from app.dependencies import container
from app.domain.exceptions import EnrollmentNotFoundError
from app.interfaces.api.serializers import (
  EnrollmentBatchSerializer,
  EnrollmentResponseSerializer,
  IngestionResponseSerializer,
  ReportResponseSerializer,
)
from app.tasks import process_enrollment_batch_task, process_enrollment_task

logger = logging.getLogger(__name__)


class EnrollmentIngestionView(APIView):
  parser_classes = [JSONParser, MultiPartParser, FormParser]

  def post(self, request: Request) -> Response:
    enrollments = self._parse_request(request)
    if not enrollments:
      return Response(
        {"detail": "No enrollment data provided"},
        status=status.HTTP_400_BAD_REQUEST,
      )

    serializer = EnrollmentBatchSerializer(data={"enrollments": enrollments})
    serializer.is_valid(raise_exception=True)

    enrollment_dtos = [
      EnrollmentCreateDTO(
        student_id=item["student_id"],
        region=item["region"],
        grade=item["grade"],
        name=item.get("name", ""),
      )
      for item in serializer.validated_data["enrollments"]
    ]

    result = container.enrollment_service.ingest_enrollments(enrollment_dtos)

    for enrollment_id in result.enrollment_ids:
      process_enrollment_task.delay(enrollment_id)

    response_data = {
      "accepted": result.accepted,
      "enrollment_ids": result.enrollment_ids,
      "message": "Enrollments queued for background processing",
    }
    return Response(
      IngestionResponseSerializer(response_data).data,
      status=status.HTTP_202_ACCEPTED,
    )

  def _parse_request(self, request: Request) -> list[dict]:
    content_type = request.content_type or ""

    if "multipart/form-data" in content_type or "text/csv" in content_type:
      return self._parse_csv(request)
    if "application/json" in content_type or isinstance(request.data, dict):
      return self._parse_json(request)
    return self._parse_json(request)

  def _parse_json(self, request: Request) -> list[dict]:
    data = request.data
    if isinstance(data, list):
      return data
    if isinstance(data, dict) and "enrollments" in data:
      return data["enrollments"]
    if isinstance(data, dict) and "student_id" in data:
      return [data]
    return []

  def _parse_csv(self, request: Request) -> list[dict]:
    csv_file = request.FILES.get("file")
    if csv_file:
      content = csv_file.read().decode("utf-8")
    else:
      content = request.data.get("csv", "")
      if hasattr(content, "read"):
        content = content.read().decode("utf-8")

    if not content:
      return []

    reader = csv.DictReader(io.StringIO(content))
    enrollments = []
    for row in reader:
      enrollments.append(
        {
          "student_id": row.get("student_id", "").strip(),
          "region": row.get("region", "").strip(),
          "grade": int(row.get("grade", 0)),
          "name": row.get("name", "").strip(),
        },
      )
    return enrollments


class EnrollmentDetailView(APIView):
  def get(self, request: Request, enrollment_id: str) -> Response:
    try:
      enrollment = container.enrollment_service.get_enrollment(enrollment_id)
    except EnrollmentNotFoundError:
      return Response(
        {"detail": "Enrollment not found"},
        status=status.HTTP_404_NOT_FOUND,
      )

    data = EnrollmentResponseSerializer(
      {
        "id": enrollment.id,
        "student_id": enrollment.student_id,
        "region": enrollment.region,
        "grade": enrollment.grade,
        "name": enrollment.name,
        "status": enrollment.status.value,
        "error_message": enrollment.error_message,
        "created_at": enrollment.created_at,
        "processed_at": enrollment.processed_at,
      },
    ).data
    return Response(data)


class EnrollmentReportView(APIView):
  def get(self, request: Request) -> Response:
    region = request.query_params.get("region")
    grade_param = request.query_params.get("grade")

    grade = None
    if grade_param is not None:
      try:
        grade = int(grade_param)
      except ValueError:
        return Response(
          {"detail": "grade must be an integer"},
          status=status.HTTP_400_BAD_REQUEST,
        )

    results = container.reporting_service.get_enrollment_report(
      region=region,
      grade=grade,
    )

    total = sum(item.count for item in results)
    response_data = {
      "results": [
        {"region": item.region, "grade": item.grade, "count": item.count}
        for item in results
      ],
      "total_students": total,
    }
    return Response(ReportResponseSerializer(response_data).data)

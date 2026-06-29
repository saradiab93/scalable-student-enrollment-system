from django.urls import path

from app.interfaces.api.views import (
  EnrollmentDetailView,
  EnrollmentIngestionView,
  EnrollmentReportView,
)

urlpatterns = [
  path("enrollments/", EnrollmentIngestionView.as_view(), name="enrollment-ingest"),
  path("enrollments/<str:enrollment_id>/", EnrollmentDetailView.as_view(), name="enrollment-detail"),
  path("reports/enrollments/", EnrollmentReportView.as_view(), name="enrollment-report"),
]

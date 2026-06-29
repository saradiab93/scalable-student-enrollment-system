import uuid

from django.db import models

from app.domain.enums import EnrollmentStatus


class EnrollmentRecord(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  student_id = models.CharField(max_length=64, db_index=True)
  name = models.CharField(max_length=255, blank=True, default="")
  region = models.CharField(max_length=128, db_index=True)
  grade = models.PositiveSmallIntegerField(db_index=True)
  status = models.CharField(
    max_length=16,
    choices=EnrollmentStatus.choices(),
    default=EnrollmentStatus.PENDING.value,
    db_index=True,
  )
  error_message = models.TextField(blank=True, default="")
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  processed_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    indexes = [
      models.Index(fields=["region", "grade"], name="idx_enrollment_region_grade"),
      models.Index(fields=["status", "created_at"], name="idx_enrollment_status_created"),
    ]
    constraints = [
      models.UniqueConstraint(
        fields=["student_id"],
        condition=models.Q(status=EnrollmentStatus.PROCESSED.value),
        name="unique_processed_student",
      ),
    ]

  def __str__(self) -> str:
    return f"{self.student_id} ({self.status})"


class EnrollmentAggregate(models.Model):
  """
  Pre-aggregated counts for fast reporting at scale.
  Updated atomically when enrollments are processed.
  """

  region = models.CharField(max_length=128)
  grade = models.PositiveSmallIntegerField()
  count = models.PositiveIntegerField(default=0)

  class Meta:
    constraints = [
      models.UniqueConstraint(
        fields=["region", "grade"],
        name="unique_region_grade_aggregate",
      ),
    ]
    indexes = [
      models.Index(fields=["region"], name="idx_aggregate_region"),
      models.Index(fields=["grade"], name="idx_aggregate_grade"),
      models.Index(fields=["region", "grade"], name="idx_aggregate_region_grade"),
    ]

  def __str__(self) -> str:
    return f"{self.region}/grade-{self.grade}: {self.count}"

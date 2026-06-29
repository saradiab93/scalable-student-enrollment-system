from rest_framework import serializers


class EnrollmentInputSerializer(serializers.Serializer):
  student_id = serializers.CharField(max_length=64)
  region = serializers.CharField(max_length=128)
  grade = serializers.IntegerField(min_value=1, max_value=12)
  name = serializers.CharField(max_length=255, required=False, default="", allow_blank=True)


class EnrollmentBatchSerializer(serializers.Serializer):
  enrollments = EnrollmentInputSerializer(many=True)


class EnrollmentResponseSerializer(serializers.Serializer):
  id = serializers.CharField()
  student_id = serializers.CharField()
  region = serializers.CharField()
  grade = serializers.IntegerField()
  name = serializers.CharField()
  status = serializers.CharField()
  error_message = serializers.CharField()
  created_at = serializers.DateTimeField()
  processed_at = serializers.DateTimeField(allow_null=True)


class IngestionResponseSerializer(serializers.Serializer):
  accepted = serializers.IntegerField()
  enrollment_ids = serializers.ListField(child=serializers.CharField())
  message = serializers.CharField()


class ReportItemSerializer(serializers.Serializer):
  region = serializers.CharField()
  grade = serializers.IntegerField()
  count = serializers.IntegerField()


class ReportResponseSerializer(serializers.Serializer):
  results = ReportItemSerializer(many=True)
  total_students = serializers.IntegerField()

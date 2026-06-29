from django.contrib import admin

from app.infrastructure.models import EnrollmentAggregate, EnrollmentRecord

admin.site.register(EnrollmentRecord)
admin.site.register(EnrollmentAggregate)

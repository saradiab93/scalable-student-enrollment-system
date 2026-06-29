from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.domain.enums import EnrollmentStatus


@dataclass(frozen=True)
class EnrollmentCreateDTO:
    student_id: str
    region: str
    grade: int
    name: str = ""


@dataclass(frozen=True)
class EnrollmentDTO:
    id: str
    student_id: str
    region: str
    grade: int
    name: str
    status: EnrollmentStatus
    error_message: str
    created_at: datetime
    processed_at: Optional[datetime]


@dataclass(frozen=True)
class EnrollmentReportDTO:
    region: str
    grade: int
    count: int


@dataclass(frozen=True)
class IngestionResultDTO:
    accepted: int
    enrollment_ids: list[str]

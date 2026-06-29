from enum import Enum


class EnrollmentStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.name) for member in cls]

from abc import ABC, abstractmethod
from typing import Optional

from app.application.dtos import EnrollmentReportDTO


class AggregateRepository(ABC):
    @abstractmethod
    def increment(self, region: str, grade: int) -> None:
        ...

    @abstractmethod
    def get_report(
        self,
        region: Optional[str] = None,
        grade: Optional[int] = None,
    ) -> list[EnrollmentReportDTO]:
        ...

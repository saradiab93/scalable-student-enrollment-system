from abc import ABC, abstractmethod
from typing import Optional

from app.application.dtos import EnrollmentCreateDTO, EnrollmentDTO
from app.domain.enums import EnrollmentStatus


class EnrollmentRepository(ABC):
    @abstractmethod
    def create_pending(self, data: EnrollmentCreateDTO) -> EnrollmentDTO:
        ...

    @abstractmethod
    def get_by_id(self, enrollment_id: str) -> Optional[EnrollmentDTO]:
        ...

    @abstractmethod
    def update_status(
        self,
        enrollment_id: str,
        status: EnrollmentStatus,
        error_message: str = "",
    ) -> EnrollmentDTO:
        ...

    @abstractmethod
    def exists_processed(self, student_id: str) -> bool:
        ...

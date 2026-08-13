"""Application repository backed by SQLite and SQLAlchemy."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from internship_agent.domain.generated_content import GeneratedApplicationContent
from internship_agent.domain.review import ReviewDecision
from internship_agent.domain.vacancy import ApplicationStatus, Vacancy
from internship_agent.domain.validation import ValidationReport
from internship_agent.exceptions import (
    ApprovalBlockedError,
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    RepositoryError,
)
from internship_agent.persistence.models import (
    ApplicationDocumentRecord,
    ApplicationRecord,
    ApprovalEventRecord,
    AuditLogRecord,
    Base,
    StatusEventRecord,
    ValidationFindingRecord,
)


class ApplicationRepository:
    """Repository for application package records."""

    def __init__(self, database_url: str) -> None:
        """Create a repository for the provided SQLAlchemy database URL."""

        _ensure_sqlite_parent(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self._engine = create_engine(database_url, connect_args=connect_args)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    def create_schema(self) -> None:
        """Create database tables when they do not already exist."""

        Base.metadata.create_all(self._engine)
        self._upgrade_sqlite_schema()

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a managed SQLAlchemy session."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def add_application(
        self,
        *,
        candidate_email: str,
        vacancy: Vacancy,
        status: ApplicationStatus,
        match_score: float,
        recommendation: str,
        follow_up_date: date | None = None,
    ) -> ApplicationRecord:
        """Add an application record and audit log, rejecting duplicates."""

        fingerprint = vacancy_fingerprint(vacancy)
        record = ApplicationRecord(
            candidate_email=candidate_email,
            company_name=vacancy.company_name,
            role_title=vacancy.role_title,
            vacancy_fingerprint=fingerprint,
            vacancy_source=vacancy.source_text,
            vacancy_url=str(vacancy.application_url) if vacancy.application_url else None,
            recommendation=recommendation,
            status=status.value,
            match_score=match_score,
            follow_up_date=follow_up_date,
        )

        try:
            with self.session() as session:
                session.add(record)
                session.flush()
                detail = f"{record.company_name} - {record.role_title} saved as {record.status}."
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="application_created",
                        detail=detail,
                    )
                )
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="status_changed",
                        detail=f"Initial status set to {record.status}.",
                    )
                )
        except IntegrityError as exc:
            raise DuplicateApplicationError(
                "An application for this candidate, company and role already exists."
            ) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not save the application record.") from exc

        return record

    def record_review_decision(
        self,
        *,
        candidate_email: str,
        vacancy: Vacancy,
        content: GeneratedApplicationContent,
        validation_report: ValidationReport,
        decision: ReviewDecision,
        match_score: float,
        recommendation: str,
        notes: str = "",
        follow_up_date: date | None = None,
    ) -> ApplicationRecord:
        """Persist a human approval or rejection decision for a generated package."""

        if decision == ReviewDecision.APPROVE and validation_report.has_blocking_findings:
            raise ApprovalBlockedError(
                "Application packages with blocking validation findings cannot be approved."
            )

        status = (
            ApplicationStatus.APPROVED
            if decision == ReviewDecision.APPROVE
            else ApplicationStatus.REJECTED
        )
        validation_status = _validation_status(validation_report)
        record = ApplicationRecord(
            candidate_email=candidate_email,
            company_name=vacancy.company_name,
            role_title=vacancy.role_title,
            vacancy_fingerprint=vacancy_fingerprint(vacancy),
            vacancy_source=vacancy.source_text,
            vacancy_url=str(vacancy.application_url) if vacancy.application_url else None,
            recommendation=recommendation,
            status=status.value,
            match_score=match_score,
            follow_up_date=follow_up_date,
            cover_letter_text=content.cover_letter,
            application_recipient_email=(
                str(vacancy.application_email) if vacancy.application_email else None
            ),
            application_email_subject=content.email_subject,
            application_email_body=content.email_body,
            generated_content_json=content.model_dump_json(),
            validation_status=validation_status,
            notes=notes,
        )

        try:
            with self.session() as session:
                session.add(record)
                session.flush()
                for finding in validation_report.findings:
                    session.add(
                        ValidationFindingRecord(
                            application_id=record.id,
                            severity=finding.severity.value,
                            code=finding.code,
                            message=finding.message,
                        )
                    )
                session.add(
                    ApprovalEventRecord(
                        application_id=record.id,
                        decision=decision.value,
                        notes=notes,
                    )
                )
                session.add(
                    StatusEventRecord(
                        application_id=record.id,
                        from_status=None,
                        to_status=status.value,
                        notes=f"Human review decision: {decision.value}.",
                    )
                )
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="review_decision_recorded",
                        detail=(
                            f"{decision.value} recorded for "
                            f"{record.company_name} - {record.role_title}."
                        ),
                    )
                )
        except IntegrityError as exc:
            raise DuplicateApplicationError(
                "An application for this candidate, company and role already exists."
            ) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not record the review decision.") from exc

        return record

    def update_status(
        self,
        application_id: int,
        new_status: ApplicationStatus,
        *,
        explicit_submission_confirmation: bool = False,
    ) -> ApplicationRecord:
        """Update application status while preventing unsafe submission transitions."""

        try:
            with self.session() as session:
                record = session.get(ApplicationRecord, application_id)
                if record is None:
                    raise RepositoryError("Application record does not exist.")

                current_status = ApplicationStatus(record.status)
                if (
                    current_status == ApplicationStatus.DISCOVERED
                    and new_status == ApplicationStatus.SUBMITTED
                ):
                    raise InvalidStatusTransitionError(
                        "Applications cannot transition directly from discovered to submitted."
                    )

                if (
                    new_status == ApplicationStatus.SUBMITTED
                    and not explicit_submission_confirmation
                ):
                    raise InvalidStatusTransitionError(
                        "Submission status requires explicit user confirmation."
                    )

                record.status = new_status.value
                record.updated_at = datetime.now(UTC)
                if new_status == ApplicationStatus.SUBMITTED:
                    record.applied_at = datetime.now(UTC)
                session.add(
                    StatusEventRecord(
                        application_id=record.id,
                        from_status=current_status.value,
                        to_status=new_status.value,
                        notes="Status updated by human reviewer.",
                    )
                )
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="status_changed",
                        detail=f"{current_status.value} -> {new_status.value}",
                    )
                )
                return record
        except InvalidStatusTransitionError:
            raise
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not update the application status.") from exc

    def update_follow_up_date(
        self,
        application_id: int,
        follow_up_date: date | None,
    ) -> ApplicationRecord:
        """Update the follow-up date and add an audit log entry."""

        try:
            with self.session() as session:
                record = session.get(ApplicationRecord, application_id)
                if record is None:
                    raise RepositoryError("Application record does not exist.")
                record.follow_up_date = follow_up_date
                record.updated_at = datetime.now(UTC)
                detail = (
                    "Follow-up date cleared."
                    if follow_up_date is None
                    else f"Follow-up date set to {follow_up_date.isoformat()}."
                )
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="follow_up_date_changed",
                        detail=detail,
                    )
                )
                return record
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not update the follow-up date.") from exc

    def record_generated_documents(
        self,
        application_id: int,
        *,
        docx_path: Path,
        pdf_path: Path,
    ) -> ApplicationRecord:
        """Store generated document paths for an approved application."""

        try:
            with self.session() as session:
                record = session.get(ApplicationRecord, application_id)
                if record is None:
                    raise RepositoryError("Application record does not exist.")
                record.cover_letter_path = str(docx_path)
                record.updated_at = datetime.now(UTC)
                session.add(
                    ApplicationDocumentRecord(
                        application_id=record.id,
                        document_type="cover_letter_docx",
                        path=str(docx_path),
                    )
                )
                session.add(
                    ApplicationDocumentRecord(
                        application_id=record.id,
                        document_type="cover_letter_pdf",
                        path=str(pdf_path),
                    )
                )
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="documents_generated",
                        detail="Generated DOCX and PDF cover letter documents.",
                    )
                )
                return record
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not record generated documents.") from exc

    def record_gmail_draft(
        self,
        application_id: int,
        *,
        recipient_email: str,
        draft_id: str,
        draft_url: str | None = None,
    ) -> ApplicationRecord:
        """Store Gmail draft metadata after a human-approved draft creation."""

        try:
            with self.session() as session:
                record = session.get(ApplicationRecord, application_id)
                if record is None:
                    raise RepositoryError("Application record does not exist.")
                record.application_recipient_email = recipient_email
                record.gmail_draft_id = draft_id
                record.gmail_draft_url = draft_url
                record.updated_at = datetime.now(UTC)
                session.add(
                    AuditLogRecord(
                        application_id=record.id,
                        action="gmail_draft_created",
                        detail=f"Gmail draft created for {recipient_email}.",
                    )
                )
                return record
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not record Gmail draft metadata.") from exc

    def get_application(self, application_id: int) -> ApplicationRecord | None:
        """Retrieve one application by ID."""

        try:
            with self.session() as session:
                return session.get(ApplicationRecord, application_id)
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not retrieve the application record.") from exc

    def list_applications(self) -> list[ApplicationRecord]:
        """List applications ordered newest first."""

        try:
            with self.session() as session:
                statement = select(ApplicationRecord).order_by(ApplicationRecord.created_at.desc())
                return list(session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not list application records.") from exc

    def list_audit_logs(self) -> list[AuditLogRecord]:
        """List audit log records ordered oldest first."""

        try:
            with self.session() as session:
                statement = select(AuditLogRecord).order_by(AuditLogRecord.created_at.asc())
                return list(session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not list audit log records.") from exc

    def list_validation_findings(self, application_id: int) -> list[ValidationFindingRecord]:
        """List validation findings for an application."""

        try:
            with self.session() as session:
                statement = (
                    select(ValidationFindingRecord)
                    .where(ValidationFindingRecord.application_id == application_id)
                    .order_by(ValidationFindingRecord.id.asc())
                )
                return list(session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not list validation findings.") from exc

    def list_approval_events(self, application_id: int) -> list[ApprovalEventRecord]:
        """List approval events for an application."""

        try:
            with self.session() as session:
                statement = (
                    select(ApprovalEventRecord)
                    .where(ApprovalEventRecord.application_id == application_id)
                    .order_by(ApprovalEventRecord.created_at.asc())
                )
                return list(session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not list approval events.") from exc

    def list_document_records(self, application_id: int) -> list[ApplicationDocumentRecord]:
        """List generated document records for an application."""

        try:
            with self.session() as session:
                statement = (
                    select(ApplicationDocumentRecord)
                    .where(ApplicationDocumentRecord.application_id == application_id)
                    .order_by(ApplicationDocumentRecord.created_at.asc())
                )
                return list(session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not list generated document records.") from exc

    def list_status_events(self, application_id: int) -> list[StatusEventRecord]:
        """List status events for an application."""

        try:
            with self.session() as session:
                statement = (
                    select(StatusEventRecord)
                    .where(StatusEventRecord.application_id == application_id)
                    .order_by(StatusEventRecord.created_at.asc())
                )
                return list(session.scalars(statement))
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not list status events.") from exc

    def _upgrade_sqlite_schema(self) -> None:
        if self._engine.url.get_backend_name() != "sqlite":
            return
        additive_columns = {
            "applications": {
                "cover_letter_text": "TEXT",
                "application_recipient_email": "VARCHAR(320)",
                "gmail_draft_id": "VARCHAR(255)",
                "gmail_draft_url": "VARCHAR(2048)",
                "generated_content_json": "TEXT",
            },
            "validation_findings": {
                "code": "VARCHAR(120) NOT NULL DEFAULT 'legacy_finding'",
            },
        }
        try:
            with self._engine.begin() as connection:
                for table_name, columns in additive_columns.items():
                    existing_columns = {
                        row[1]
                        for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
                    }
                    for column_name, column_sql in columns.items():
                        if column_name not in existing_columns:
                            connection.execute(
                                text(
                                    f"ALTER TABLE {table_name} "
                                    f"ADD COLUMN {column_name} {column_sql}"
                                )
                            )
        except SQLAlchemyError as exc:
            raise RepositoryError("Could not upgrade the SQLite schema.") from exc


def vacancy_fingerprint(vacancy: Vacancy) -> str:
    """Return a stable fingerprint for duplicate vacancy detection."""

    payload = "\n".join(
        [
            vacancy.company_name.strip().casefold(),
            vacancy.role_title.strip().casefold(),
            vacancy.source_text.strip(),
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _validation_status(validation_report: ValidationReport) -> str:
    if validation_report.has_blocking_findings:
        return "failed"
    if validation_report.findings:
        return "warnings"
    return "passed"


def _ensure_sqlite_parent(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)

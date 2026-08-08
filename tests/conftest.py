"""Shared test fixtures."""

from collections.abc import Iterator

import pytest

from internship_agent.domain.candidate import CandidateProfile


@pytest.fixture()
def candidate_profile() -> CandidateProfile:
    """Return a verified test candidate."""

    return CandidateProfile(
        schema_version=1,
        personal={
            "full_name": "Test Student",
            "email": "test@example.edu",
            "phone": "+60123456789",
            "location": "Shah Alam, Selangor, Malaysia",
            "nationality": None,
            "work_authorisation": "Malaysia",
        },
        education={
            "institution": "Example University",
            "programme": "Bachelor of Computer Science",
            "cgpa": 3.7,
            "cgpa_scale": 4.0,
            "academic_highlights": ["Dean's List"],
            "graduation_year": 2027,
        },
        internship={
            "start_date": "2026-09-22",
            "end_date": "2026-12-26",
            "duration_weeks": 14,
            "availability_notes": "Available for internship.",
        },
        preferences={
            "target_roles": ["Software Engineering Intern"],
            "preferred_locations": ["Shah Alam"],
            "industries": [],
            "minimum_match_score": 70,
        },
        skills={
            "programming": ["Python", "SQL"],
            "ai_and_data": ["Machine Learning"],
            "tools": ["Streamlit"],
        },
        documents={
            "master_resume_docx": "documents/master_resume.docx",
            "master_resume_pdf": "documents/master_resume.pdf",
            "academic_transcript": "documents/academic_transcript.pdf",
            "university_letter": "documents/university_internship_letter.pdf",
            "project_evidence": "documents/project_evidence.md",
        },
        approval={
            "required_before_email": True,
            "required_before_submission": True,
            "allow_automatic_submission": False,
        },
        evidence_files=[
            {
                "evidence_id": "python-course",
                "path": "evidence/python.pdf",
                "description": "Python coursework.",
                "approved": True,
            }
        ],
        experiences=[
            {
                "organization": "Example University",
                "title": "Course Project",
                "start_date": "2025-01-01",
                "end_date": "2025-05-01",
                "summary": "Built data tools.",
                "skills": ["Python", "SQL"],
                "evidence_ids": ["python-course"],
            }
        ],
    )


@pytest.fixture()
def sqlite_url(tmp_path: pytest.TempPathFactory) -> Iterator[str]:
    """Return a temporary SQLite database URL."""

    db_path = tmp_path / "test.db"
    yield f"sqlite:///{db_path}"

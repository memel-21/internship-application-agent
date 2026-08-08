"""Tests for candidate profile loading."""

import json
from pathlib import Path

import pytest

from internship_agent.exceptions import CandidateProfileError
from internship_agent.services.profile_loader import load_candidate_profile


def test_load_candidate_profile_valid(tmp_path: pytest.TempPathFactory) -> None:
    """Valid local JSON loads into a candidate profile."""

    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "personal": {
                    "full_name": "Test Student",
                    "email": "test@example.edu",
                    "phone": "+60123456789",
                    "location": "Shah Alam, Selangor, Malaysia",
                    "nationality": None,
                    "work_authorisation": "Malaysia",
                },
                "education": {
                    "institution": "Example University",
                    "programme": "Bachelor of Computer Science",
                    "cgpa": 3.7,
                    "cgpa_scale": 4.0,
                    "academic_highlights": ["Dean's List"],
                    "graduation_year": 2027,
                },
                "internship": {
                    "start_date": "2026-09-22",
                    "end_date": "2026-12-26",
                    "duration_weeks": 14,
                    "availability_notes": "Available for internship.",
                },
                "preferences": {
                    "target_roles": ["Software Engineering Intern"],
                    "preferred_locations": ["Shah Alam"],
                    "industries": [],
                    "minimum_match_score": 70,
                },
                "skills": {
                    "programming": ["Python", "SQL"],
                    "ai_and_data": ["Machine Learning"],
                    "tools": ["Streamlit"],
                },
                "documents": {
                    "master_resume_docx": "documents/master_resume.docx",
                    "master_resume_pdf": "documents/master_resume.pdf",
                    "academic_transcript": "documents/academic_transcript.pdf",
                    "university_letter": "documents/university_internship_letter.pdf",
                    "project_evidence": "documents/project_evidence.md",
                },
                "approval": {
                    "required_before_email": True,
                    "required_before_submission": True,
                    "allow_automatic_submission": False,
                },
            }
        ),
        encoding="utf-8",
    )

    profile = load_candidate_profile(path)

    assert profile.full_name == "Test Student"
    assert profile.verified is True


def test_load_candidate_profile_invalid_json_has_useful_error(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Invalid JSON returns an actionable loader error."""

    path = tmp_path / "candidate.json"
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(CandidateProfileError, match="not valid JSON"):
        load_candidate_profile(path)


def test_load_candidate_profile_invalid_schema_has_useful_error(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Invalid candidate schema includes the failing field."""

    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({"full_name": ""}), encoding="utf-8")

    with pytest.raises(CandidateProfileError, match="schema_version"):
        load_candidate_profile(path)


def test_example_candidate_profile_loads() -> None:
    """The committed example candidate profile config loads."""

    profile = load_candidate_profile(Path("config/candidate_profile.example.json"))

    assert profile.full_name == "Example Student"
    assert profile.email == "student@example.edu"
    assert profile.personal.work_authorisation is None
    assert "Python" in profile.flattened_skills()

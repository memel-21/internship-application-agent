"""Candidate profile loading and validation."""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from internship_agent.domain.candidate import CandidateProfile
from internship_agent.exceptions import CandidateProfileError


def load_candidate_profile(path: Path) -> CandidateProfile:
    """Load and validate a candidate profile from a local JSON file."""

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CandidateProfileError(f"Could not read candidate profile at {path}.") from exc

    try:
        payload: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CandidateProfileError(f"Candidate profile is not valid JSON: {exc.msg}.") from exc

    try:
        return CandidateProfile.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {"loc": ["profile"], "msg": "invalid"}
        location = ".".join(str(part) for part in first_error["loc"])
        raise CandidateProfileError(
            f"Candidate profile failed validation at '{location}': {first_error['msg']}."
        ) from exc

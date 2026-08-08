# Repository Architecture

Milestone 1 uses a small `src` layout that separates UI, domain models, deterministic services, and persistence.

```text
src/internship_agent/
  app.py                    Streamlit entry point for the local MVP UI.
  settings.py               Environment-backed runtime settings.
  exceptions.py             Domain-specific recoverable exceptions.
  domain/
    candidate.py            Verified candidate profile Pydantic models.
    vacancy.py              Vacancy and application status Pydantic models.
  services/
    profile_loader.py       Local JSON loading and validation boundary.
    eligibility.py          Deterministic hard eligibility checks.
    scoring.py              Deterministic match scoring.
  persistence/
    models.py               SQLAlchemy database tables.
    repository.py           Application repository and audit logging.
tests/                      Unit tests for deterministic logic and persistence.
data/demo_candidate_profile.json
                            Non-private demo profile for local app startup.
```

Later milestones should add AI extraction and generation behind isolated adapter interfaces, keeping OpenAI Responses API calls outside `domain`, `services`, and `persistence` business rules.


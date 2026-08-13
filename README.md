# Internship Application Agent

Local human-in-the-loop assistant for preparing and tracking internship
applications. The MVP keeps deterministic checks in Python and isolates AI
calls behind services.

## Current Milestones

- Milestone 1: project foundation, candidate profile loading, vacancy schemas,
  deterministic eligibility/scoring, SQLite repository, and minimal Streamlit UI.
- Milestone 2: structured vacancy extraction with a deterministic demo extractor
  and an OpenAI Responses API adapter.
- Milestone 3: approved evidence loading, deterministic evidence selection, and
  grounded application draft generation with internal source references.
- Milestone 4: deterministic content validation with blocking, warning, and
  information findings before approval.
- Milestone 5: human review decision persistence for approved and rejected
  generated packages in SQLite.
- Milestone 6: DOCX and PDF cover letter generation for approved packages.
- Milestone 7: application tracking dashboard for statuses, follow-up dates,
  documents, validation findings, and audit history.
- Milestone 8: final MVP hardening with additive SQLite schema upgrades,
  overwrite protection, and full local verification.

## Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` for local settings. Keep demo mode enabled unless
you intend to call the OpenAI API.

```dotenv
INTERNSHIP_AGENT_DEMO_MODE=true
OPENAI_API_KEY=
OPENAI_MODEL=
```

## Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Verify

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest
```

## Safety

- The app must not submit applications or send emails automatically.
- Generated claims must be grounded in the verified candidate profile or
  approved local evidence.
- Private profile data and personal documents are ignored by Git.
- Tests do not require network access.

## Vacancy Extraction

Demo mode uses deterministic local extraction and never calls OpenAI. Real mode
uses the OpenAI Responses API through `OpenAIVacancyExtractor`, requesting a
JSON-schema structured response and validating it with Pydantic before use.

## Grounded Generation

Application drafts are generated from selected approved evidence only. Internal
claim source references are validated before content is shown for review, and
unsupported requirements remain visible as gaps instead of fabricated strengths.

## Content Validation

Generated cover letters and emails are checked deterministically for exact
company and role names, candidate identity, date and CGPA consistency,
unsupported technologies, prohibited claims, placeholders, duplicate
applications, attachment references, and email/cover-letter consistency.
Blocking findings must be resolved before any future approval action.

## Human Review Persistence

Approved and rejected application packages are saved only after an explicit
human decision. Approval is blocked when validation has blocking findings, while
rejections can still be stored with findings and notes for audit history. The
MVP does not send emails or submit applications automatically.

## Document Generation

Approved cover letters can be exported to DOCX and PDF under the configured
output directory. Filenames are sanitized, existing files are not overwritten
unless the user explicitly enables overwrite, and generated document paths are
recorded in SQLite.

## Application Tracking

The Streamlit tracker lists saved applications, shows review artifacts and audit
history, updates follow-up dates, and changes statuses. Submission status still
requires explicit manual confirmation from the user.

## Gmail Draft Preparation

The app validates a draft package for approved applications before any outreach.
The required attachments are the generated cover letter PDF, resume PDF,
academic transcript PDF, and university internship letter PDF. Missing files,
invalid recipient emails, unsupported attachment types, and unapproved
applications block draft preparation. The MVP prepares and records Gmail draft
metadata only; it does not send emails automatically.

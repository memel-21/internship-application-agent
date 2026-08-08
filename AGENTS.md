# AGENTS.md

## Project

Internship Application Agent is a human-in-the-loop system for analysing,
preparing and tracking internship applications.

## Commands

Install:

```bash
pip install -e ".[dev]"
```

Run:

```bash
streamlit run app.py
```

Test:

```bash
pytest
```

Lint:

```bash
ruff check .
ruff format --check .
```

Type check:

```bash
mypy src
```

Full verification:

```bash
ruff check . &&
ruff format --check . &&
mypy src &&
pytest
```

## Architecture rules

* Domain models belong in `src/internship_agent/domain`.
* Database access belongs in repositories or persistence modules.
* AI calls belong in dedicated services.
* Streamlit pages must not contain core business logic.
* Deterministic checks must not be delegated to an AI model.
* Structured Pydantic output is required for model extraction.
* User approval is required before consequential actions.
* Every generated claim must be grounded in approved evidence.
* Never log secrets or complete personal documents.

## Testing rules

* Add tests with every business-logic change.
* Mock OpenAI calls.
* Do not require network access during tests.
* Include success, failure and boundary cases.
* Run the full verification command before marking work complete.

## Security rules

* API keys must come from environment variables.
* Never commit `.env`.
* Never place candidate documents in Git.
* Sanitize generated filenames.
* Prevent path traversal.
* Never render untrusted HTML.
* Store only required personal information.

## Product rules

* Never fabricate candidate details.
* Never automatically submit applications.
* Never automatically send email in the MVP.
* Never alter source documents.
* Never conceal validation warnings.
* Hard eligibility failures override numerical scores.

## Milestone rules

* Implement milestones incrementally. Do not begin later milestones until explicitly instructed.
* Keep all generated claims traceable to verified candidate data or approved evidence.
* Use structured schemas for model-boundary data whenever possible.
* Do not use LangChain or LangGraph in the MVP.

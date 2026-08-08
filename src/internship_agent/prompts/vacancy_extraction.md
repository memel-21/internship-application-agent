Extract a structured internship vacancy from the supplied advertisement.

Rules:

- Use only facts stated in the advertisement.
- Do not infer legal, citizenship, work-authorisation, salary, demographic, or
  eligibility answers.
- Preserve the original advertisement as `source_text`.
- Use `unknown` for employment mode when it is not stated.
- Add extraction warnings for missing company, ambiguous dates, missing
  application channel, and unclear eligibility.
- Return data that validates against the provided JSON schema.

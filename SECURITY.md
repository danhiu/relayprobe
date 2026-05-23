# Security Policy

## Reporting a vulnerability

If you find a security issue in RelayProbe — credential leakage, log redaction bypass, prompt injection in the audit reports, or anything that could harm a user running the audit service — please **do not** open a public issue.

Email **danhiu@users.noreply.github.com** with:

- A description of the issue
- Steps to reproduce
- Affected versions
- Any suggested fixes

You will get an acknowledgement within 72 hours and a fix or status update within 14 days.

## What's in scope

- API key leakage through logs, error messages, or response bodies
- Prompt injection that lets an upstream alter the audit verdict
- Container escape from the official Docker image
- Dependency CVEs that affect a default deployment

## What's not in scope

- Issues requiring physical or local network access to the host
- Vulnerabilities in upstream relays themselves (those are by definition what RelayProbe exists to detect)
- Findings on third-party services we do not control

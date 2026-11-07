# Security Policy

## Reporting a Vulnerability

Report vulnerabilities through GitHub private vulnerability reporting only: [report a vulnerability](https://github.com/MarcusJellinghaus/agent-workspace/security/advisories/new) (or, in this repository, **Security → Report a vulnerability**).

Do not open public issues for security problems.

## Response

Reports are handled on a best-effort basis. There is no fixed response time.

## Supported Versions

Only the latest commit on `main` receives security fixes.

## Scope

In scope are bypasses of intended restrictions, such as:

- permission checks (using an operation, data source, schema or table above the user's level)
- tool exposure (the model reaching a tool the user may not use)
- workspace confinement (reading or writing outside the configured project folder)
- SQL injection through tool parameters, or running unapproved queries
- credential handling (credentials leaking into logs, tool output, prompts or error messages)
- audit logging (a tool call that leaves no log entry)

## Threat Model

User prompts, model output, tool arguments and data content (e.g. table comments, file contents) are untrusted input. agent-workspace must enforce its permissions and confinement on the server side regardless of what the model requests.

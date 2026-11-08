# Security Policy

## Reporting a Vulnerability

Report vulnerabilities through GitHub private vulnerability reporting only: [report a vulnerability](https://github.com/MarcusJellinghaus/agent-workbench/security/advisories/new) (or, in this repository, **Security → Report a vulnerability**).

Do not open public issues for security problems.

## Response

Reports are handled on a best-effort basis. There is no fixed response time.

## Supported Versions

Only the latest commit on `main` receives security fixes.

## Scope

In scope are bypasses of intended restrictions, such as:

- tool permissions (the model calling a `deny` tool, or an `ask` tool without confirmation)
- tool exposure (the model seeing a tool whose mode is `deny`)
- workspace confinement (reading or writing outside the configured project folder)
- SQL injection through tool parameters, or running unapproved queries
- credential handling (credentials leaking into logs, tool output, prompts or error messages)
- tool-call logging (a tool call that leaves no log entry)

## Security Design

Trust boundaries, controls, threat model and residual risks: [`docs/security/security_design.md`](docs/security/security_design.md).

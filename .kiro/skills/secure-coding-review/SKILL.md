---
name: secure-coding-review
description: Use when writing or reviewing code that handles multi-tenant data, external input, secrets, database queries, or network-exposed endpoints. Provides a concrete checklist to catch tenant-isolation gaps, injection, secret leakage, and missing authorization before code ships.
---

# Secure Coding & Review

Security review is a pass over a diff with specific questions, not a vibe. Run this checklist on
any change that touches data access, input handling, auth, secrets, or endpoints.

## Tenant isolation (highest priority here)

- Does every org-scoped **read** filter by `organization_id` (not trust an id from the body)?
- Does every **write of a foreign key** to another org-scoped resource validate that the
  referenced row belongs to the caller's org (fetch-with-org, 404 if not)?
- Does every **list** filter by `organization_id` at the query level, not in Python after?
- For handlers without an org in scope (webhooks/callbacks): is the org derived from the payload
  and that derivation explicitly validated?

## Input & injection

- Untrusted input (request bodies, tool results, webhook payloads, external API responses) is
  validated at the boundary with a schema before use.
- SQL uses parameterized queries / the ORM — no string interpolation of untrusted values.
- Shell/command construction (if any) uses argument arrays or proper escaping, not string concat.
- Path/file operations validate against traversal; URLs are validated before fetching.

## Secrets

- No hardcoded credentials, keys, or tokens; read from env/config or the credentials service.
- Secret values are never logged — reference them by key name. Sensitive integration fields are
  registered so masking applies.

## Authorization & exposure

- Network-exposed endpoints have auth/authorization; any intentionally public/unauthenticated
  route is called out explicitly and justified.
- The change grants the least privilege needed (task/tool carries only the org/run context required).

## Destructive & irreversible actions

- Bulk deletes, data-dropping migrations, production config, and auth/permission changes are
  flagged: what it does, blast radius, reversibility — and confirmed before running.

## How to respond to a finding

State the risk, the concrete fix, and whether it blocks merge. Prefer the smallest change that
closes the gap. Re-check the same class of issue elsewhere in the diff.

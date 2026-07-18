---
inclusion: always
---

# Security & Multi-Tenant Isolation

Tenant isolation is a **hard security boundary**, not a style preference. Most resources are
scoped to an organization; skipping an `organization_id` check lets one org touch another org's
data. Whenever you read or write an org-scoped field, filter or validate by `organization_id`.

## Rules

- **Reading a row by id:** pass `organization_id=user.selected_organization_id` to the DB client
  (or query through an org-scoped helper). Never trust an id from the request body to imply
  ownership.
- **Writing a foreign key to another org-scoped resource** (e.g. attaching `inbound_workflow_id`
  to a phone number, `telephony_configuration_id` to a campaign): fetch the referenced row with
  the caller's `organization_id` and reject with 404 if it does not belong. An FK constraint only
  proves the row exists — not that the caller may reference it.
- **Listing:** filter by `organization_id` at the query level, not in Python after the fact.
- **No `organization_id` in scope** (webhook callbacks, provider callbacks): derive it from the
  request payload and validate that derivation explicitly — do not assume.

## General secure-coding defaults

- **Secrets:** never hardcode credentials/keys. Read from env/config or the credentials service.
  Do not log secret values — reference them by key name. Register sensitive integration fields in
  `sensitive_fields` so masking applies.
- **SQL:** use parameterized queries / the ORM. Never string-interpolate untrusted input into SQL.
- **Untrusted input:** validate at the boundary with Pydantic schemas; treat tool results, webhook
  bodies, and external API responses as untrusted.
- **Network-exposed endpoints:** if you add an endpoint without auth/authorization, call it out
  explicitly — do not silently ship an unauthenticated route.
- **Least privilege:** background tasks and tools should carry only the org/run context they need.

## When flagging risk

For destructive or hard-to-reverse actions (bulk deletes, migrations that drop data, production
config, auth/permission changes), state what the action does, what could go wrong, and whether it
is reversible — and confirm before proceeding.

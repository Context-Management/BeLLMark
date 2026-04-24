# BeLLMark v1 Trust Contract

## Product Boundary
BeLLMark is a self-hosted, single-user benchmarking studio for periodic
evaluation and pre-procurement selection, producing auditable decision
artifacts. BeLLMark is NOT an LLM observability platform and is NOT a
CI/CD evaluation harness.

## Security Boundary
v1 ships with no built-in user accounts and no RBAC. Secure access using
your infrastructure (VPN, reverse proxy, firewall, private subnet).

## Data/Telemetry Boundary
BeLLMark does not phone home and does not send telemetry. Outbound network
calls are limited to the configured LLM provider endpoints.

## Reproducibility Boundary
Run configuration is stored and exportable for audit and re-run. LLM outputs
are inherently non-deterministic; reruns are comparable, not identical.

## Support Boundary
Best-effort, async-only. Issues require MRB bundle; otherwise closed as
non-actionable.

## Commercial Boundary
€799 buys commercial permission for a single legal entity, plus procurement-
proof artifacts (receipt + certificate) and a clear refund policy.

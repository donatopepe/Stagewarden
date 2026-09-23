---
description: Decide node autonomy and escalation
argument-hint: "<node-decision>"
---
# Node autonomy policy

A node may act autonomously only inside its approved work packet, file scope, tool permissions, context budget and provider/model policy.

- low impact, local, reversible: act and emit event;
- medium impact or scope clarification: pause and report to parent;
- architecture, security, data, compatibility, cost, provider/model, permission or fundamental test decision: escalate to user;
- missing evidence, unknown context limit or packet mismatch: block;
- no fallback or parallelism without explicit policy.

Every decision records cause, impact, options, recommendation, decision owner, reversibility and next event.

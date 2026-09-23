# Model metadata

Model metadata is input to capability and limit discovery. It is not a routing decision and never contains credentials.

In v3, model metadata must be attached to a provider/model identity with source, timestamp, freshness, exact ID, alias distinction, context/input/output limits, tokenizer/measurement method, and supported parameters.

The user owns provider, model, account, credentials, cost, quota and fallback choices. A catalog can inform or validate a node work packet; it cannot silently select a service.

See:

- [`providers/README.md`](providers/README.md)
- [`../docs/specs/stagewarden-v3.md`](../docs/specs/stagewarden-v3.md)
- [`../TODO.md`](../TODO.md)

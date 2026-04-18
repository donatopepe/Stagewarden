# Stagewarden

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Autore: Donato Pepe
Licenza: MIT

Stagewarden is a production-grade CLI coding agent for controlled software delivery, with Codex-style agent loops, multi-model routing, PRINCE2-aligned governance, structured traces, and safe file/shell execution.

Caratteristiche principali:

- iterative agent loop
- planner and executor split
- model routing and escalation
- `RUN_MODEL:` handoff execution
- shell, file, and git tools
- local stub support for smoke tests

Install locally:

```bash
python3 -m pip install -e .
```

Run:

```bash
stagewarden "create a file named hello.txt"
```

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import Agent
from .config import AgentConfig
from .ljson import LJSONOptions, benchmark_sizes, decode, dump_file, encode, load_file
from .textcodec import dumps_ascii, loads_text, read_text_utf8, write_text_utf8


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stagewarden", description="Stagewarden: production-grade CLI coding agent.")
    parser.add_argument("task", nargs="?", default="", help='Task to execute, for example: stagewarden "fix the failing tests"')
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum agent loop iterations.")
    parser.add_argument("--verbose", action="store_true", help="Print step-by-step logs.")
    parser.add_argument("--strict-ascii-output", dest="strict_ascii_output", action="store_true", default=True, help="Escape ambiguous non-ASCII characters in structured and generated text output.")
    parser.add_argument("--allow-unicode-output", dest="strict_ascii_output", action="store_false", help="Disable ASCII-safe escaping for generic file output.")
    parser.add_argument("--caveman", nargs="?", const="full", choices=["lite", "full", "ultra", "wenyan-lite", "wenyan", "wenyan-ultra"], help="Activate caveman mode at the selected level.")
    parser.add_argument("--caveman-commit", action="store_true", help="Generate a caveman-style commit message from the current diff.")
    parser.add_argument("--caveman-review", action="store_true", help="Generate one-line caveman review findings for the current diff.")
    parser.add_argument("--caveman-help", action="store_true", help="Show caveman commands and usage.")
    parser.add_argument("--caveman-compress", metavar="PATH", help="Compress a natural-language memory file and write a .original backup.")
    parser.add_argument("--ljson-encode", metavar="JSON_PATH", help="Encode a JSON array file to LJSON.")
    parser.add_argument("--ljson-decode", metavar="LJSON_PATH", help="Decode an LJSON file to JSON array.")
    parser.add_argument("--ljson-output", metavar="OUT_PATH", help="Output path for --ljson-encode/--ljson-decode.")
    parser.add_argument("--ljson-numeric", action="store_true", help="Use numeric-key LJSON representation when encoding.")
    parser.add_argument("--ljson-gzip", action="store_true", help="Write gzipped LJSON when encoding.")
    parser.add_argument("--ljson-benchmark", metavar="JSON_PATH", help="Benchmark standard JSON vs LJSON for a JSON array file.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = AgentConfig(
        workspace_root=Path.cwd(),
        max_steps=args.max_steps,
        verbose=args.verbose,
        strict_ascii_output=args.strict_ascii_output,
    )

    if args.ljson_encode:
        records = loads_text(read_text_utf8(Path(args.ljson_encode)))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-encode must be a JSON array.")
        target = Path(args.ljson_output) if args.ljson_output else Path(args.ljson_encode).with_suffix(".ljson")
        dump_file(
            target,
            records,
            options=LJSONOptions(numeric_keys=args.ljson_numeric),
            gzip_enabled=args.ljson_gzip,
        )
        print(str(target))
        return 0

    if args.ljson_decode:
        records = load_file(args.ljson_decode, gzipped=args.ljson_gzip or str(args.ljson_decode).endswith(".gz"))
        target = Path(args.ljson_output) if args.ljson_output else Path(args.ljson_decode).with_suffix(".json")
        write_text_utf8(target, dumps_ascii(records, indent=2))
        print(str(target))
        return 0

    if args.ljson_benchmark:
        records = loads_text(read_text_utf8(Path(args.ljson_benchmark)))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-benchmark must be a JSON array.")
        print(dumps_ascii(
            {
                "standard": benchmark_sizes(records),
                "numeric": benchmark_sizes(records, numeric_keys=True),
                "standard_gzip": benchmark_sizes(records, gzip_enabled=True),
                "numeric_gzip": benchmark_sizes(records, numeric_keys=True, gzip_enabled=True),
            },
            indent=2,
        ))
        return 0

    agent = Agent(config)
    task = args.task
    if args.caveman_help:
        task = "/caveman help"
    elif args.caveman_commit:
        task = "/caveman commit"
    elif args.caveman_review:
        task = "/caveman review"
    elif args.caveman_compress:
        task = f"/caveman compress {args.caveman_compress}"
    elif args.caveman:
        task = f"/caveman {args.caveman} {args.task}".strip()
    elif not task:
        build_parser().error("task is required unless a caveman command flag is used")

    result = agent.run(task)
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""te-agent — the Team Engine matching-algorithm harness.

    te-agent doctor        pre-flight checks; run before every phase
    te-agent spec          Phase 1: draft the matching-algorithm documents
    te-agent verify-docs   check Phase 1 output (quotes, conventions, freeze)
    te-agent impl          Phase 2: implement the APPROVED spec in flightcrew-be
    te-agent verify-code   check Phase 2 output
"""

from __future__ import annotations

import argparse
import asyncio
import sys

DEFAULT_MODEL = "opus[1m]"


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"default: {DEFAULT_MODEL}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="te-agent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="pre-flight checks")
    _add_common(doctor)

    spec = sub.add_parser("spec", help="Phase 1 — draft the spec documents")
    _add_common(spec)
    spec.add_argument("--resume", metavar="SESSION_ID", help="continue a previous spec run")
    spec.add_argument(
        "--fork",
        action="store_true",
        help="with --resume, branch instead of extending (keeps the original for audit)",
    )
    spec.add_argument(
        "--dry-run",
        action="store_true",
        help="permission_mode=default with everything write-shaped denied: watch what "
        "the agent would do without a byte changing",
    )

    sub.add_parser("verify-docs", help="check Phase 1 output")

    impl = sub.add_parser("impl", help="Phase 2 — implement the approved spec")
    _add_common(impl)
    impl.add_argument("--resume", metavar="SESSION_ID")
    impl.add_argument("--fork", action="store_true")

    sub.add_parser("verify-code", help="check Phase 2 output")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "doctor":
        from .doctor import run_doctor

        return asyncio.run(run_doctor(model=args.model))

    if args.command == "spec":
        from .phase1_spec import run_spec

        return asyncio.run(
            run_spec(
                model=args.model,
                resume=args.resume,
                fork=args.fork,
                dry_run=args.dry_run,
            )
        )

    if args.command == "verify-docs":
        from .checks import verify_docs

        return verify_docs()

    if args.command == "impl":
        from .phase2_impl import run_impl

        return asyncio.run(run_impl(model=args.model, resume=args.resume, fork=args.fork))

    if args.command == "verify-code":
        from .checks import verify_code

        return verify_code()

    return 2


if __name__ == "__main__":
    sys.exit(main())

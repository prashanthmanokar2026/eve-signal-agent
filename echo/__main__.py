import argparse
import json
from .config import load
from .runner import Mission


def main():
    parser = argparse.ArgumentParser(description="ECHO — Finding EVE")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a headless mission and export evidence")
    run.add_argument("mission")
    run.add_argument("--output", default="results/run")
    run.add_argument("--baseline", action="store_true")
    evaluate = commands.add_parser("evaluate", help="Run paired generated missions")
    evaluate.add_argument("--count", type=int, default=30)
    evaluate.add_argument("--seed", type=int, default=100)
    evaluate.add_argument("--output", default="results/benchmark")
    serve = commands.add_parser("serve", help="Open the local mission console")
    serve.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        if args.command == "run":
            mission = Mission(load(args.mission), args.baseline)
            report = mission.run()
            mission.export(args.output)
            print(json.dumps({k: v for k, v in report.items() if k not in ["evidence", "key_decisions"]}, indent=2))
        elif args.command == "evaluate":
            from .evaluate import evaluate
            if not 1 <= args.count <= 1000:
                parser.error("count must be between 1 and 1000")
            print(json.dumps(evaluate(args.count, args.output, args.seed), indent=2))
        else:
            from .server import serve
            serve(args.port)
    except (ValueError, OSError) as exc:
        parser.exit(2, "Error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()

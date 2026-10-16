import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.db import init_db
from src.trace import tracer


def main():
    parser = argparse.ArgumentParser(description="Flower Catalog AI CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    subparsers.add_parser("init", help="Initialize the database")

    # Collect
    parser_collect = subparsers.add_parser("collect", help="Collect semantic data via API")
    parser_collect.add_argument("--category", required=True, help="Category name")
    parser_collect.add_argument("--region", required=True, help="Region ID")

    # Import CSV
    parser_import = subparsers.add_parser("import-wordstat", help="Import CSV data")
    parser_import.add_argument("--file", required=True, help="CSV file path")
    parser_import.add_argument("--category", required=True, help="Category name")

    # Cluster
    parser_cluster = subparsers.add_parser("cluster", help="Cluster semantic data")
    parser_cluster.add_argument("--category", required=True, help="Category name")

    # Queue
    parser_queue = subparsers.add_parser("queue", help="Queue processing")
    parser_queue.add_argument("--category", required=True, help="Category name")

    # Process
    parser_process = subparsers.add_parser("process", help="Process photos")
    parser_process.add_argument("--category", required=True, help="Category name")
    parser_process.add_argument(
        "--approved-only", action="store_true", help="Process only approved"
    )

    # Export
    parser_export = subparsers.add_parser("export-to-disk", help="Export to local disk")
    parser_export.add_argument("--category", required=True, help="Category name")

    try:
        args = parser.parse_args()
    except SystemExit:
        # Avoid sys.exit from traceback in span if help is requested
        sys.exit(0)

    with tracer.span("main", command=args.command):
        if args.command == "init":
            init_db()
        else:
            with tracer.span(f"cmd.{args.command}"):
                pass


if __name__ == "__main__":
    main()

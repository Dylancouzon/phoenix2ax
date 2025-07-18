#!/usr/bin/env python3
"""
Phoenix Export Tool

This script exports data from Phoenix (datasets, traces, prompts, annotations, evaluations)
for import into Arize.

Usage:
  cd export
  python export_all_projects.py [--all] [--datasets] [--traces] [--prompts] \
                                 [--annotations] [--evaluations] [--projects]

Environment Variables:
  PHOENIX_ENDPOINT: Base URL of the Phoenix server.
                    For self-hosted, e.g., http://localhost:6006
                    For Phoenix Cloud, e.g., https://app.phoenix.arize.com
  PHOENIX_API_KEY: API key for Phoenix Cloud authentication (if required).
  PHOENIX_EXPORT_DIR: Directory to save exported data (default: "phoenix_export").
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Import exporters
from exporters import (
    export_annotations,
    export_datasets,
    export_evaluations,
    export_prompts,
    export_traces,
)
from utils import create_client_with_retry, parse_export_args

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Ensure results directory exists
RESULTS_DIR = Path("./results")
RESULTS_DIR.mkdir(exist_ok=True)


def main() -> None:
    """Main entry point for the script."""
    args = parse_export_args()

    # Check for required arguments
    if not args.base_url:
        logger.error(
            "No Phoenix Endpoint URL provided. Set the PHOENIX_ENDPOINT environment variable "
            "(e.g., https://app.phoenix.arize.com for Cloud, "
            "http://localhost:6006 for self-hosted) or use --base-url."
        )
        return

    # Set up logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not os.path.isabs(args.export_dir):
        base_export_dir = args.export_dir
    else:
        base_export_dir = args.export_dir

    logger.info(f"Connecting to Phoenix server at {args.base_url}")
    logger.info(f"Exporting data to: {os.path.abspath(base_export_dir)}")

    # Create HTTPX client with retry capabilities
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if args.api_key:
        headers["api_key"] = args.api_key

    client = create_client_with_retry(
        base_url=args.base_url.rstrip("/"),
        headers=headers,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        initial_backoff=args.initial_backoff,
        max_backoff=args.max_backoff,
        backoff_factor=args.backoff_factor,
    )

    # Keep track of successful exports
    successful_exports = []
    failed_exports = []

    # Check if any export type is selected
    if not (
        args.all
        or args.datasets
        or args.prompts
        or args.projects
        or args.traces
        or args.annotations
        or args.evaluations
    ):
        logger.error("No export type selected. Use --help to see available options.")
        return

    # Create the projects directory (needs to exist for annotations even if not exporting traces)
    projects_dir = os.path.join(base_export_dir, "projects")
    os.makedirs(projects_dir, exist_ok=True)

    # Export datasets (step 1)
    if args.all or args.datasets:
        logger.info("Step 1: Exporting datasets...")
        datasets_dir = os.path.join(base_export_dir, "datasets")
        results_file = os.path.join(RESULTS_DIR, "dataset_export_results.json")

        try:
            results = export_datasets.export_datasets(
                client=client,
                output_dir=datasets_dir,
                verbose=args.verbose,
                results_file=results_file,
            )

            if results:
                export_count = sum(d.get("status") == "exported" for d in results)
                logger.info(f"Successfully exported {export_count} datasets")
                successful_exports.append("datasets")
            else:
                logger.error("Failed to export datasets")
                failed_exports.append("datasets")
        except Exception as e:
            logger.error(f"Error exporting datasets: {e}")
            failed_exports.append("datasets")

    # Export prompts (step 2)
    if args.all or args.prompts:
        logger.info("Step 2: Exporting prompts...")
        prompts_dir = os.path.join(base_export_dir, "prompts")
        results_file = os.path.join(RESULTS_DIR, "prompt_export_results.json")

        try:
            results = export_prompts.export_prompts(
                client=client,
                output_dir=prompts_dir,
                verbose=args.verbose,
                results_file=results_file,
            )

            if results:
                export_count = sum(p.get("status") == "exported" for p in results)
                logger.info(f"Successfully exported {export_count} prompts")
                successful_exports.append("prompts")
            else:
                logger.error("Failed to export prompts")
                failed_exports.append("prompts")
        except Exception as e:
            logger.error(f"Error exporting prompts: {e}")
            failed_exports.append("prompts")

    # Export traces (step 3)
    if args.all or args.traces or args.projects:
        logger.info("Step 3: Exporting traces and project metadata...")
        results_file = os.path.join(RESULTS_DIR, "trace_export_results.json")

        try:
            results = export_traces.export_traces(
                client=client,
                output_dir=projects_dir,
                project_names=args.project,
                verbose=args.verbose,
                results_file=results_file,
            )

            if results:
                success_count = sum(
                    1 for status in results.values() if status.get("status") == "exported"
                )
                total_traces = sum(p.get("trace_count", 0) for p in results.values())

                logger.info(
                    f"Successfully exported {total_traces} traces from {success_count} projects"
                )
                successful_exports.append("traces")
            else:
                logger.error("Failed to export traces")
                failed_exports.append("traces")
        except Exception as e:
            logger.error(f"Error exporting traces: {e}")
            failed_exports.append("traces")

    # Export annotations (step 4)
    if args.all or args.annotations:
        logger.info("Step 4: Exporting annotations...")
        results_file = os.path.join(RESULTS_DIR, "annotation_export_results.json")

        try:
            results = export_annotations.export_annotations(
                client=client,
                output_dir=projects_dir,
                project_names=args.project,
                verbose=args.verbose,
                results_file=results_file,
            )

            if results:
                success_count = sum(
                    1 for status in results.values() if status.get("status") == "exported"
                )
                total_annotations = sum(p.get("annotation_count", 0) for p in results.values())

                logger.info(
                    f"Successfully exported {total_annotations} annotations "
                    f"from {success_count} projects"
                )
                successful_exports.append("annotations")
            else:
                logger.error("No annotations were exported")
                failed_exports.append("annotations")
        except Exception as e:
            logger.error(f"Error exporting annotations: {e}")
            failed_exports.append("annotations")

    # Export evaluations (step 5)
    if args.all or args.evaluations:
        logger.info("Step 5: Exporting evaluations...")
        results_file = os.path.join(RESULTS_DIR, "evaluation_export_results.json")

        try:
            results = export_evaluations.export_evaluations(
                client=client,
                output_dir=projects_dir,
                project_names=args.project,
                verbose=args.verbose,
                results_file=results_file,
            )

            if results:
                success_count = sum(
                    1 for status in results.values() if status.get("status") == "exported"
                )
                total_evaluations = sum(p.get("evaluation_count", 0) for p in results.values())

                logger.info(
                    f"Successfully exported {total_evaluations} evaluations "
                    f"from {success_count} projects"
                )
                successful_exports.append("evaluations")
            else:
                logger.error("Failed to export evaluations")
                failed_exports.append("evaluations")
        except Exception as e:
            logger.error(f"Error exporting evaluations: {e}")
            failed_exports.append("evaluations")

    # Print summary
    print("\n=== Export Summary ===")
    if successful_exports:
        logger.info(f"Successfully exported: {', '.join(successful_exports)}")

    if failed_exports:
        logger.error(f"Failed to export: {', '.join(failed_exports)}")

    # Display results file locations
    print("\n=== Export Results Files ===")
    for result_type in ["dataset", "trace", "prompt", "annotation", "evaluation"]:
        result_file = RESULTS_DIR / f"{result_type}_export_results.json"
        if result_file.exists():
            print(f"- {result_type.capitalize()} results: {result_file}")

    if failed_exports:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Recompute the publication reports from pinned proofs and saved timing observations."""
import argparse
from pathlib import Path
import shutil
import tempfile

from . import comparison, formal_reports, game, proof_timing, scaling

OBSERVATIONS = (scaling.ENVIRONMENT, scaling.RAW, "formal_proof_timing_repetitions.csv")


def reproduce(destination):
    source = comparison.OUTPUT
    for name in OBSERVATIONS:
        shutil.copyfile(source / name, destination / name)
    comparison.baselines(destination)
    comparison.costs(destination)
    formal_reports.generate(destination)
    game.report(game.EVIDENCE, destination / "adaptive_game.json")
    scaling.report(destination)
    proof_timing.summarize(destination / "formal_proof_timing_repetitions.csv",
                           destination / "formal_proof_timing_v2.json")
    expected = {p.name for p in source.iterdir() if p.is_file()}
    actual = {p.name for p in destination.iterdir() if p.is_file()}
    if expected != actual:
        raise ValueError(f"Different file inventory: {sorted(expected ^ actual)}")
    for name in sorted(actual):
        if (destination / name).read_bytes() != (source / name).read_bytes():
            raise ValueError(f"Different report content: {name}")
    print(f"{len(actual) - len(OBSERVATIONS)} generated reports match. "
          f"{len(OBSERVATIONS)} captured inputs include the machine manifest and raw timing series.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="retain the reports in an empty directory")
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        if any(args.output.iterdir()):
            parser.error("Use an empty directory to preserve existing files")
        reproduce(args.output)
    else:
        with tempfile.TemporaryDirectory() as work:
            reproduce(Path(work))


if __name__ == "__main__":
    main()

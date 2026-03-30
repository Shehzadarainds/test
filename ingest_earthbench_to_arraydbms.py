#!/usr/bin/env python3
"""
Earth-Bench → Array (Tensor) DBMS Ingestion Script
====================================================
Downloads the Earth-Bench dataset from HuggingFace and ingests every
GeoTIFF file into the Array (Tensor) DBMS using the ChronosDB-style
hierarchical Dataset Namespace:

    EarthBench.<QuestionN>.<Filename_without_extension>

Example dataset names registered:
    EarthBench.Question1.Xinjiang_2019-01-01_LST
    EarthBench.Question1.Xinjiang_2019-01-01_NDVI
    EarthBench.Question10.Germany_2021-07-29_b4
    EarthBench.Question101.Aracaju_precipitation_2025-01-01

Usage:
    py -3 ingest_earthbench_to_arraydbms.py
    py -3 ingest_earthbench_to_arraydbms.py --skip-download
    py -3 ingest_earthbench_to_arraydbms.py --question question1
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path(__file__).parent
BENCHMARK_DIR = PROJECT_ROOT / "benchmark" / "data"
ARRAY_DB_DIR  = PROJECT_ROOT / "agent" / "tools" / "tmp" / "array_dbms"
REGISTRY_FILE = ARRAY_DB_DIR / "registry.json"

ARRAY_DB_DIR.mkdir(parents=True, exist_ok=True)


# ── Registry helpers (mirrors ArrayDBMS.py) ────────────────────────────────

def load_registry() -> dict:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return {}


def save_registry(reg: dict):
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def dataset_storage_path(dataset_name: str) -> Path:
    """'EarthBench.Question1.Band4' → ARRAY_DB_DIR/EarthBench/Question1/Band4.npy"""
    parts = dataset_name.split(".")
    return ARRAY_DB_DIR.joinpath(*parts).with_suffix(".npy")


# ── Core ingestion (in-situ, no format conversion — ChronosDB §3.1.2) ─────

def ingest_tif(tif_path: Path, dataset_name: str, registry: dict) -> dict:
    """
    Ingest a single GeoTIFF into the Array DBMS.
    Stores data as (bands, height, width) NumPy array.
    Updates the registry with schema metadata.
    """
    import rasterio

    with rasterio.open(str(tif_path)) as src:
        data      = src.read()                        # (bands, H, W)
        crs       = str(src.crs) if src.crs else "undefined"
        transform = list(src.transform)
        nodata    = src.nodata
        meta = {
            "dataset_name": dataset_name,
            "source_path":  str(tif_path),
            "crs":          crs,
            "transform":    transform,
            "nodata":       nodata,
            "bands":        int(src.count),
            "height":       int(src.height),
            "width":        int(src.width),
            "dtype":        str(data.dtype),
            "shape":        list(data.shape),
        }

    out_path = dataset_storage_path(dataset_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(out_path), data)

    registry[dataset_name] = meta
    return meta


# ── Download step ──────────────────────────────────────────────────────────

def download_earthbench():
    """Download the full Earth-Bench dataset from HuggingFace."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("  [ERROR] huggingface_hub not installed. Run: pip install huggingface-hub")
        sys.exit(1)

    print("\n[1/2] Downloading Earth-Bench from HuggingFace...")
    print(f"      Target: {BENCHMARK_DIR}")
    BENCHMARK_DIR.parent.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id="Sssunset/Earth-Bench",
        repo_type="dataset",
        local_dir=str(BENCHMARK_DIR),
        resume_download=True,
    )
    print("      Download complete.\n")


# ── Ingestion step ─────────────────────────────────────────────────────────

def ingest_all(question_filter: str = None):
    """
    Walk the benchmark/data directory and ingest every .tif file
    into the Array (Tensor) DBMS.

    Dataset naming:
        EarthBench.<QuestionDir>.<FilenameStem>
        (spaces in filenames are replaced with underscores)
    """
    if not BENCHMARK_DIR.exists():
        print("[ERROR] benchmark/data/ not found. Run without --skip-download first.")
        sys.exit(1)

    # Collect all question directories
    q_dirs = sorted(
        [d for d in BENCHMARK_DIR.iterdir()
         if d.is_dir() and d.name.startswith("question")],
        key=lambda d: int(d.name.replace("question", ""))
    )

    if question_filter:
        q_dirs = [d for d in q_dirs if d.name == question_filter]
        if not q_dirs:
            print(f"[ERROR] No directory named '{question_filter}' found.")
            sys.exit(1)

    registry = load_registry()
    total_ingested  = 0
    total_skipped   = 0
    total_errors    = 0
    ingested_names  = []

    print(f"\n[2/2] Ingesting into Array (Tensor) DBMS")
    print(f"      Storage root : {ARRAY_DB_DIR}")
    print(f"      Dataset namespace: EarthBench.<Question>.<File>")
    print(f"      Questions to process: {len(q_dirs)}\n")

    for q_dir in q_dirs:
        tif_files = sorted(
            list(q_dir.glob("*.tif")) + list(q_dir.glob("*.TIF"))
        )
        if not tif_files:
            continue

        # Hierarchical collection name: EarthBench.Question1
        q_label = "Question" + q_dir.name.replace("question", "").capitalize()
        print(f"  [{q_dir.name}]  {len(tif_files)} files")

        for tif in tif_files:
            # Replace spaces with underscores for valid namespace keys
            file_stem   = tif.stem.replace(" ", "_")
            dataset_name = f"EarthBench.{q_label}.{file_stem}"

            # Skip already-ingested datasets
            if dataset_name in registry:
                total_skipped += 1
                continue

            try:
                meta = ingest_tif(tif, dataset_name, registry)
                total_ingested += 1
                ingested_names.append(dataset_name)
                print(f"    + {dataset_name}  shape={meta['shape']}  dtype={meta['dtype']}")
            except Exception as e:
                total_errors += 1
                print(f"    ! SKIPPED {tif.name}: {e}")

        # Save registry after each question (checkpoint)
        save_registry(registry)

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("Array (Tensor) DBMS — Ingestion Summary")
    print("=" * 70)
    print(f"  Ingested  : {total_ingested} datasets")
    print(f"  Skipped   : {total_skipped}  (already in DBMS)")
    print(f"  Errors    : {total_errors}")
    print(f"  Total in DBMS: {len(registry)} datasets")
    print(f"  Registry  : {REGISTRY_FILE}")
    print("=" * 70)

    # Print a few example dataset names
    if ingested_names:
        print("\nExample registered datasets:")
        for name in ingested_names[:8]:
            print(f"  {name}")
        if len(ingested_names) > 8:
            print(f"  ... and {len(ingested_names) - 8} more")

    print("\nYou can now query these datasets using the ArrayDBMS MCP tools:")
    print("  get_schema('EarthBench.Question1.Xinjiang_2019-01-01_LST')")
    print("  hyperslab('EarthBench.Question1.Xinjiang_2019-01-01_NDVI', 0, 256, 0, 256)")
    print("  aggregate('EarthBench.Question1.Xinjiang_2019-01-01_LST', 'mean', axis=0)")


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest Earth-Bench dataset into Array (Tensor) DBMS"
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip HuggingFace download (use already-downloaded data)"
    )
    parser.add_argument(
        "--question", type=str, default=None,
        help="Ingest only one question dir, e.g. --question question1"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Earth-Bench -> Array (Tensor) DBMS Ingestion")
    print("ChronosDB-style in-situ ingestion | Hierarchical Dataset Namespace")
    print("=" * 70)

    if not args.skip_download:
        download_earthbench()
    else:
        print("\n[1/2] Skipping download (--skip-download)")

    ingest_all(question_filter=args.question)


if __name__ == "__main__":
    main()

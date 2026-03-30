"""
Array (Tensor) DBMS Tool for Earth-Agent
=========================================
Implements core Array (Tensor) DBMS concepts based on the theoretical
foundations of ChronosDB (Rodriges Zalipynis, HSE University, 2024).

Key concepts implemented:
  - Multilevel data model: hierarchical Dataset Namespace (logical array)
    backed by in-situ GeoTIFF/NumPy subarrays at the system level.
  - In-situ ingestion: no format conversion, files registered as-is.
  - Core Array DBMS operations:
      * get_schema       — inspect array schema (dimensions, dtype, CRS)
      * hyperslab        — spatial window query (index-range selection)
      * chunk_array      — rechunk / retile an array along any dimension
      * array_join       — element-wise join of two arrays (e.g. NDVI)
      * aggregate        — reduce an array along a dimension (mean/sum/min/max)
      * compute_expr     — evaluate an algebraic expression over registered arrays

References: ChronosDB (VLDB 2018), BitFun (SIGMOD), dissertation arXiv 2024.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastmcp import FastMCP
import numpy as np

mcp = FastMCP()
parser = argparse.ArgumentParser()
parser.add_argument('--temp_dir', type=str)
parser.add_argument('--array_db_dir', type=str, default='array_dbms')
args, unknown = parser.parse_known_args()

TEMP_DIR = Path(args.temp_dir)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Root of the Array DBMS storage — mirrors ChronosDB's dataset namespace
ARRAY_DB_DIR = Path(args.array_db_dir)
ARRAY_DB_DIR.mkdir(parents=True, exist_ok=True)

# Dataset registry: maps hierarchical name → metadata dict
REGISTRY_FILE = ARRAY_DB_DIR / "registry.json"


# ─────────────────────────────────────────────────────────────────────────────
# Registry helpers  (Dataset Namespace, ChronosDB §3.1.2)
# ─────────────────────────────────────────────────────────────────────────────

def _load_registry() -> dict:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return {}


def _save_registry(reg: dict):
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def _dataset_path(dataset_name: str) -> Path:
    """Hierarchical name 'A.B.C' maps to ARRAY_DB_DIR/A/B/C.npy"""
    parts = dataset_name.split(".")
    return ARRAY_DB_DIR.joinpath(*parts).with_suffix(".npy")


def _load_array(dataset_name: str) -> np.ndarray:
    path = _dataset_path(dataset_name)
    if not path.exists():
        raise FileNotFoundError(f"Dataset '{dataset_name}' not found.")
    return np.load(str(path))


def _save_array(dataset_name: str, data: np.ndarray):
    path = _dataset_path(dataset_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(path), data)


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 1 — ingest_dataset
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Registers (ingests) a raster/GeoTIFF file into the Array (Tensor) DBMS
using the ChronosDB in-situ approach: no format conversion takes place.
The file is read once, stored as a system-level subarray, and registered
under a hierarchical Dataset Namespace name.

Dataset naming follows the ChronosDB convention:
    Collection.Subcollection.DatasetName
    e.g. "Landsat8.SurfaceReflectance.Band4"
         "EarthBench.Question1.NIR"

Parameters
    • source_path  (str): Absolute path to the GeoTIFF / raster source file.
    • dataset_name (str): Hierarchical dot-separated name for the dataset.
                          e.g. "EarthBench.Question1.NIR_2022"

Returns
    • dict with: dataset_name, shape [bands, height, width], dtype,
                 crs, subarray_size, source_path, message.
''')
def ingest_dataset(source_path: str, dataset_name: str) -> dict:
    """
    In-situ ingestion of a raster file into the Array (Tensor) DBMS.
    Implements ChronosDB Dataset Ingestion (§3.1.2).

    Parameters:
        source_path  (str): Path to GeoTIFF or raster file.
        dataset_name (str): Hierarchical name, e.g. "Landsat8.Band4".

    Returns:
        dict: Ingestion result with schema information.
    """
    import rasterio

    with rasterio.open(source_path) as src:
        data = src.read()                    # (bands, height, width)
        crs  = str(src.crs) if src.crs else "undefined"
        transform = list(src.transform)
        nodata    = src.nodata
        meta = {
            "dataset_name": dataset_name,
            "source_path":  str(source_path),
            "crs":          crs,
            "transform":    transform,
            "nodata":       nodata,
            "bands":        int(src.count),
            "height":       int(src.height),
            "width":        int(src.width),
            "dtype":        str(data.dtype),
            "shape":        list(data.shape),
        }

    _save_array(dataset_name, data)

    reg = _load_registry()
    reg[dataset_name] = meta
    _save_registry(reg)

    return {
        "dataset_name":  dataset_name,
        "shape":         list(data.shape),
        "dtype":         str(data.dtype),
        "crs":           crs,
        "subarray_size": f"{data.shape[1]}x{data.shape[2]}",
        "source_path":   str(source_path),
        "message":       (
            f"Dataset '{dataset_name}' ingested into Array DBMS (in-situ). "
            f"Shape: {list(data.shape)}, dtype: {data.dtype}."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 2 — get_schema
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Returns the schema of a registered Array (Tensor) DBMS dataset.
Mirrors ChronosDB's gdalinfo-style schema output (§3.1.2):
dimensions, data type, CRS, geotransform, nodata, and subarray size.

Parameters
    • dataset_name (str): Hierarchical name of the dataset.

Returns
    • dict: Full schema — shape, bands, height, width, dtype, CRS,
            geotransform, nodata, source path.
''')
def get_schema(dataset_name: str) -> dict:
    """
    Inspect the schema of a registered array (tensor).
    Implements ChronosDB schema output (§3.1.2).

    Parameters:
        dataset_name (str): Hierarchical dataset name.

    Returns:
        dict: Array schema.
    """
    reg = _load_registry()
    if dataset_name not in reg:
        return {"error": f"Dataset '{dataset_name}' not registered in Array DBMS."}

    meta = reg[dataset_name]
    shape = meta["shape"]

    return {
        "dataset_name":  dataset_name,
        "dimensions":    {"bands": shape[0], "height": shape[1], "width": shape[2]},
        "dtype":         meta["dtype"],
        "crs":           meta.get("crs", "undefined"),
        "geotransform":  meta.get("transform", []),
        "nodata":        meta.get("nodata"),
        "subarray_size": f"{shape[1]}x{shape[2]}",
        "source_path":   meta.get("source_path", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 3 — hyperslab  (spatial window query, §2.2.3 / §4.1.1)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Performs a hyperslab (spatial window) query on a registered array —
the core Array DBMS index-range selection operation (§2.2.3, §4.1.1).
Only the requested sub-region is read; the full array is not loaded.

Parameters
    • dataset_name (str): Hierarchical name of the dataset.
    • band_start   (int): First band index, 0-based (inclusive).
    • band_end     (int): Last band index, 0-based (exclusive). Use -1 for all.
    • row_start    (int): First row index (inclusive).
    • row_end      (int): Last row index (exclusive).
    • col_start    (int): First column index (inclusive).
    • col_end      (int): Last column index (exclusive).

Returns
    • dict: shape, dtype, and values of the extracted subarray.
''')
def hyperslab(
    dataset_name: str,
    row_start: int,
    row_end:   int,
    col_start: int,
    col_end:   int,
    band_start: int = 0,
    band_end:   int = -1,
) -> dict:
    """
    Hyperslab (index-range) query — core Array DBMS operation.
    Implements ChronosDB hyperslabbing (§2.2.3, benchmarked in §4.1.1).

    Parameters:
        dataset_name            : Hierarchical dataset name.
        row_start / row_end     : Row range (exclusive end).
        col_start / col_end     : Column range (exclusive end).
        band_start / band_end   : Band range (exclusive end; -1 = all bands).

    Returns:
        dict: Sliced subarray with shape, dtype, values.
    """
    try:
        data = _load_array(dataset_name)   # (bands, H, W)
    except FileNotFoundError as e:
        return {"error": str(e)}

    b_end = band_end if band_end != -1 else data.shape[0]
    sliced = data[band_start:b_end, row_start:row_end, col_start:col_end]

    return {
        "dataset_name": dataset_name,
        "hyperslab": {
            "bands":   [band_start, b_end],
            "rows":    [row_start,  row_end],
            "columns": [col_start,  col_end],
        },
        "shape":  list(sliced.shape),
        "dtype":  str(sliced.dtype),
        "values": sliced.tolist(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 4 — chunk_array  (N-d retiling / chunking, §2.2.1 / §4.1.1)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Rechunks (retiles) a registered array along the spatial dimensions —
the Array DBMS N-d retiling operation (§2.2.1, §4.1.1).
Produces chunk statistics: number of chunks, chunk shape, total size.

Parameters
    • dataset_name (str): Hierarchical name of the dataset.
    • chunk_height  (int): Tile height in pixels (default 256).
    • chunk_width   (int): Tile width in pixels (default 256).

Returns
    • dict: Number of chunks, chunk shape, array shape, chunk statistics.
''')
def chunk_array(
    dataset_name: str,
    chunk_height: int = 256,
    chunk_width:  int = 256,
) -> dict:
    """
    Rechunk (retile) an array — implements N-d Retiling (§2.2.1).

    Parameters:
        dataset_name  : Hierarchical dataset name.
        chunk_height  : Tile height.
        chunk_width   : Tile width.

    Returns:
        dict: Chunking statistics.
    """
    try:
        data = _load_array(dataset_name)
    except FileNotFoundError as e:
        return {"error": str(e)}

    bands, H, W = data.shape
    n_row_chunks = int(np.ceil(H / chunk_height))
    n_col_chunks = int(np.ceil(W / chunk_width))
    total_chunks = bands * n_row_chunks * n_col_chunks

    chunks_info = []
    for b in range(bands):
        for r in range(n_row_chunks):
            for c in range(n_col_chunks):
                r0, r1 = r * chunk_height, min((r + 1) * chunk_height, H)
                c0, c1 = c * chunk_width,  min((c + 1) * chunk_width,  W)
                chunk = data[b, r0:r1, c0:c1]
                chunks_info.append({
                    "band": b, "row_chunk": r, "col_chunk": c,
                    "row_range": [r0, r1], "col_range": [c0, c1],
                    "shape": list(chunk.shape),
                    "mean":  float(np.nanmean(chunk)),
                })

    return {
        "dataset_name":  dataset_name,
        "array_shape":   list(data.shape),
        "chunk_shape":   [1, chunk_height, chunk_width],
        "n_row_chunks":  n_row_chunks,
        "n_col_chunks":  n_col_chunks,
        "total_chunks":  total_chunks,
        "chunks":        chunks_info,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 5 — array_join  (K-Way Array Join, §2.2.2)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Performs an element-wise join of two registered arrays and optionally
evaluates an algebraic expression over the joined arrays.
Implements the Distributed K-Way Array (Tensor) Join (§2.2.2).

Typical use: compute NDVI by joining NIR and Red band arrays:
    expression = "(A - B) / (A + B + 1e-6)"

Parameters
    • dataset_a    (str): Name of the first dataset (variable "A").
    • dataset_b    (str): Name of the second dataset (variable "B").
    • expression   (str): NumPy-compatible expression over A and B.
                          e.g. "(A - B) / (A + B + 1e-6)"  for NDVI.
    • output_name  (str): Name to register the result in the Array DBMS.
    • band_a       (int): Band index of dataset A (0-based, default 0).
    • band_b       (int): Band index of dataset B (0-based, default 0).

Returns
    • dict: Result shape, dtype, statistics (min/max/mean), output name.
''')
def array_join(
    dataset_a:   str,
    dataset_b:   str,
    expression:  str,
    output_name: str,
    band_a:      int = 0,
    band_b:      int = 0,
) -> dict:
    """
    K-Way Array (Tensor) Join with expression evaluation (§2.2.2).
    Used for NDVI, SAVI, and other multi-array computations.

    Parameters:
        dataset_a / dataset_b : Input dataset names.
        expression            : Expression over variables A and B.
        output_name           : Name to store the result.
        band_a / band_b       : Which band to use from each dataset.

    Returns:
        dict: Join result statistics.
    """
    try:
        A = _load_array(dataset_a)[band_a].astype(np.float32)
        B = _load_array(dataset_b)[band_b].astype(np.float32)
    except FileNotFoundError as e:
        return {"error": str(e)}

    if A.shape != B.shape:
        return {
            "error": (
                f"Shape mismatch: {dataset_a} band {band_a} has shape {A.shape}, "
                f"but {dataset_b} band {band_b} has shape {B.shape}. "
                "Arrays must have the same spatial dimensions for a join."
            )
        }

    try:
        result = eval(expression, {"__builtins__": {}}, {"A": A, "B": B, "np": np})
    except Exception as e:
        return {"error": f"Expression evaluation failed: {e}"}

    result = np.array(result, dtype=np.float32)
    _save_array(output_name, result[np.newaxis, :, :])   # store as (1, H, W)

    reg = _load_registry()
    reg[output_name] = {
        "dataset_name": output_name,
        "source_path":  f"join({dataset_a}, {dataset_b})",
        "expression":   expression,
        "dtype":        str(result.dtype),
        "shape":        [1, result.shape[0], result.shape[1]],
        "bands": 1, "height": result.shape[0], "width": result.shape[1],
    }
    _save_registry(reg)

    valid = result[~np.isnan(result)]
    return {
        "output_name": output_name,
        "input_a":     f"{dataset_a}[band={band_a}]",
        "input_b":     f"{dataset_b}[band={band_b}]",
        "expression":  expression,
        "shape":       list(result.shape),
        "dtype":       str(result.dtype),
        "statistics": {
            "min":  float(np.nanmin(valid))  if valid.size else None,
            "max":  float(np.nanmax(valid))  if valid.size else None,
            "mean": float(np.nanmean(valid)) if valid.size else None,
        },
        "message": f"Join result registered as '{output_name}' in Array DBMS.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 6 — aggregate  (Aggregation, §2.2.3)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Aggregates a registered array along a specified dimension.
Implements the Array DBMS Aggregation operation (§2.2.3).

Parameters
    • dataset_name (str): Hierarchical name of the dataset.
    • operation    (str): Aggregation function — "mean", "sum", "min", "max",
                          "std", "count_valid".
    • axis         (int): Dimension to aggregate over:
                            0 = bands, 1 = rows (latitude), 2 = columns (longitude).

Returns
    • dict: Result shape, dtype, and aggregated values.
''')
def aggregate(
    dataset_name: str,
    operation:    str = "mean",
    axis:         int = 0,
) -> dict:
    """
    Array (Tensor) DBMS aggregation along a dimension (§2.2.3).

    Parameters:
        dataset_name : Hierarchical dataset name.
        operation    : One of mean / sum / min / max / std / count_valid.
        axis         : Axis to reduce (0=bands, 1=rows, 2=cols).

    Returns:
        dict: Aggregated array with statistics.
    """
    try:
        data = _load_array(dataset_name).astype(np.float32)
    except FileNotFoundError as e:
        return {"error": str(e)}

    ops = {
        "mean":        lambda x, ax: np.nanmean(x, axis=ax),
        "sum":         lambda x, ax: np.nansum(x, axis=ax),
        "min":         lambda x, ax: np.nanmin(x, axis=ax),
        "max":         lambda x, ax: np.nanmax(x, axis=ax),
        "std":         lambda x, ax: np.nanstd(x, axis=ax),
        "count_valid": lambda x, ax: np.sum(~np.isnan(x), axis=ax),
    }
    if operation not in ops:
        return {"error": f"Unknown operation '{operation}'. Choose from: {list(ops)}."}

    result = ops[operation](data, axis)
    axis_names = {0: "bands", 1: "rows (latitude)", 2: "columns (longitude)"}

    return {
        "dataset_name":  dataset_name,
        "operation":     operation,
        "aggregated_over": axis_names.get(axis, str(axis)),
        "input_shape":   list(data.shape),
        "output_shape":  list(result.shape),
        "dtype":         str(result.dtype),
        "values":        result.tolist(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 7 — compute_expr  (Tunable / algebraic computation, §2.3 / §4.2)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Evaluates an algebraic expression over one registered array and registers
the result as a new dataset. Inspired by ChronosDB tunable queries and
BitFun's fast re-computing (§2.3, §4.2).

Useful for indices like NDVI, SAVI (with tunable parameter L), water masks,
and any cell-wise transformation.

Available variables in the expression:
    • X  — the loaded array (shape: bands × H × W)
    • np — NumPy

Parameters
    • dataset_name (str): Input dataset name.
    • expression   (str): NumPy expression over variable X.
                          e.g. "(X[0] - X[1]) / (X[0] + X[1] + 1e-6)"
    • output_name  (str): Name to register the result.
    • band         (int or null): If provided, loads only this band as X (2-D).
                                  If null, X is the full 3-D array.

Returns
    • dict: Result statistics and registered output name.
''')
def compute_expr(
    dataset_name: str,
    expression:   str,
    output_name:  str,
    band:         int = None,
) -> dict:
    """
    Evaluate a tunable algebraic expression over a registered array (§2.3).

    Parameters:
        dataset_name : Source dataset.
        expression   : NumPy expression with variable X (and optionally np).
        output_name  : Name to store result in Array DBMS.
        band         : Load a single band (2-D) instead of full 3-D array.

    Returns:
        dict: Computation result and statistics.
    """
    try:
        data = _load_array(dataset_name).astype(np.float32)
    except FileNotFoundError as e:
        return {"error": str(e)}

    X = data[band] if band is not None else data

    try:
        result = eval(expression, {"__builtins__": {}}, {"X": X, "np": np})
    except Exception as e:
        return {"error": f"Expression evaluation failed: {e}"}

    result = np.array(result, dtype=np.float32)
    out = result[np.newaxis] if result.ndim == 2 else result
    _save_array(output_name, out)

    reg = _load_registry()
    reg[output_name] = {
        "dataset_name": output_name,
        "source_path":  f"expr({dataset_name})",
        "expression":   expression,
        "dtype":        str(result.dtype),
        "shape":        list(out.shape),
        "bands":        out.shape[0],
        "height":       out.shape[-2],
        "width":        out.shape[-1],
    }
    _save_registry(reg)

    valid = result.ravel()
    valid = valid[~np.isnan(valid)]
    return {
        "output_name": output_name,
        "expression":  expression,
        "input":       f"{dataset_name}" + (f"[band={band}]" if band is not None else ""),
        "output_shape": list(result.shape),
        "dtype":        str(result.dtype),
        "statistics": {
            "min":  float(np.min(valid))  if valid.size else None,
            "max":  float(np.max(valid))  if valid.size else None,
            "mean": float(np.mean(valid)) if valid.size else None,
        },
        "message": f"Result registered as '{output_name}' in Array DBMS.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 8 — list_datasets
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(description='''
Description

Lists all datasets registered in the Array (Tensor) DBMS, showing
the hierarchical Dataset Namespace (ChronosDB §3.1.2).

Returns
    • dict: All registered dataset names with shape, dtype, and source.
''')
def list_datasets() -> dict:
    """
    List all registered arrays in the Array (Tensor) DBMS.
    Mirrors ChronosDB's Dataset Namespace listing (§3.1.2).

    Returns:
        dict: Registry of all datasets.
    """
    reg = _load_registry()
    datasets = []
    for name, meta in reg.items():
        datasets.append({
            "dataset_name": name,
            "shape":        meta.get("shape", []),
            "dtype":        meta.get("dtype", "unknown"),
            "source_path":  meta.get("source_path", ""),
        })
    return {
        "total":    len(datasets),
        "datasets": datasets,
    }


if __name__ == "__main__":
    mcp.run()

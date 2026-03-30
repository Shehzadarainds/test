"""
Array DBMS Interactive Console
================================
Run this file to query the satellite data DBMS directly.

Usage:
    py -3 dbms_console.py
"""

import json
import numpy as np
from pathlib import Path

# ── Connect to the DBMS ────────────────────────────────────────────────────
ARRAY_DB_DIR  = Path('agent/tools/tmp/array_dbms')
REGISTRY_FILE = ARRAY_DB_DIR / 'registry.json'

if not REGISTRY_FILE.exists():
    print("[ERROR] DBMS not found. Run ingest_earthbench_to_arraydbms.py first.")
    exit(1)

_registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
print(f"Connected to Array DBMS  ({len(_registry)} datasets)")
print("=" * 60)


# ── Core helpers ───────────────────────────────────────────────────────────

def _load(name: str) -> np.ndarray:
    path = ARRAY_DB_DIR.joinpath(*name.split('.')).with_suffix('.npy')
    if not path.exists():
        raise FileNotFoundError(f"Dataset '{name}' not found in DBMS.")
    return np.load(str(path))


# ══════════════════════════════════════════════════════════════════════════
# QUERY FUNCTIONS  (same as MCP tools the LLM calls)
# ══════════════════════════════════════════════════════════════════════════

def list_datasets(filter_prefix: str = None):
    """
    List all datasets in the DBMS.
    Optionally filter by prefix, e.g. 'EarthBench.Question1'
    """
    results = {
        k: v for k, v in _registry.items()
        if (filter_prefix is None or k.startswith(filter_prefix))
    }
    print(f"\n[list_datasets]  filter='{filter_prefix}'")
    print(f"  Found {len(results)} datasets")
    for name, meta in list(results.items())[:20]:
        print(f"  {name}")
        print(f"    shape={meta['shape']}  dtype={meta['dtype']}  crs={meta.get('crs','?')}")
    if len(results) > 20:
        print(f"  ... and {len(results)-20} more")
    return results


def get_schema(dataset_name: str):
    """
    Get full schema/metadata for a dataset.
    """
    if dataset_name not in _registry:
        print(f"[ERROR] Dataset '{dataset_name}' not registered.")
        return None
    meta  = _registry[dataset_name]
    shape = meta['shape']
    result = {
        "dataset_name" : dataset_name,
        "dimensions"   : {"bands": shape[0], "height": shape[1], "width": shape[2]},
        "dtype"        : meta['dtype'],
        "crs"          : meta.get('crs', 'undefined'),
        "geotransform" : meta.get('transform', []),
        "nodata"       : meta.get('nodata'),
        "source_path"  : meta.get('source_path', ''),
    }
    print(f"\n[get_schema]  '{dataset_name}'")
    for k, v in result.items():
        print(f"  {k:<15}: {v}")
    return result


def hyperslab(dataset_name: str,
              row_start: int, row_end: int,
              col_start: int, col_end: int,
              band_start: int = 0, band_end: int = -1):
    """
    Spatial window query — extracts a sub-region of the array.
    Only the requested pixels are loaded (efficient).
    """
    data  = _load(dataset_name)
    b_end = band_end if band_end != -1 else data.shape[0]
    sliced = data[band_start:b_end, row_start:row_end, col_start:col_end]

    print(f"\n[hyperslab]  '{dataset_name}'")
    print(f"  Window : rows={row_start}:{row_end}  cols={col_start}:{col_end}  bands={band_start}:{b_end}")
    print(f"  Shape  : {sliced.shape}")
    print(f"  Values :")
    for band_idx in range(sliced.shape[0]):
        print(f"    Band {band_start + band_idx}:")
        for row in sliced[band_idx]:
            print("     ", list(row))
    return sliced


def aggregate(dataset_name: str, operation: str = 'mean', axis: int = 0):
    """
    Reduce array along a dimension.
    axis: 0=bands, 1=rows(latitude), 2=cols(longitude)
    operation: mean / sum / min / max / std / count_valid
    """
    data = _load(dataset_name).astype(np.float32)
    nodata = _registry[dataset_name].get('nodata')
    if nodata is not None:
        data[data == nodata] = np.nan

    ops = {
        'mean'        : lambda x, ax: np.nanmean(x, axis=ax),
        'sum'         : lambda x, ax: np.nansum(x,  axis=ax),
        'min'         : lambda x, ax: np.nanmin(x,  axis=ax),
        'max'         : lambda x, ax: np.nanmax(x,  axis=ax),
        'std'         : lambda x, ax: np.nanstd(x,  axis=ax),
        'count_valid' : lambda x, ax: np.sum(~np.isnan(x), axis=ax),
    }
    if operation not in ops:
        print(f"[ERROR] Unknown operation '{operation}'. Choose: {list(ops)}")
        return None

    result = ops[operation](data, axis)
    axis_name = {0: 'bands', 1: 'rows (latitude)', 2: 'cols (longitude)'}.get(axis, str(axis))

    print(f"\n[aggregate]  '{dataset_name}'")
    print(f"  Operation  : {operation}")
    print(f"  Axis       : {axis}  ({axis_name})")
    print(f"  Input shape: {data.shape}  ->  Output shape: {result.shape}")
    print(f"  Result stats:")
    print(f"    min  = {np.nanmin(result):.4f}")
    print(f"    max  = {np.nanmax(result):.4f}")
    print(f"    mean = {np.nanmean(result):.4f}")
    return result


def array_join(dataset_a: str, dataset_b: str,
               expression: str, output_name: str,
               band_a: int = 0, band_b: int = 0):
    """
    Element-wise join of two arrays with a custom expression.
    Variables A and B refer to dataset_a and dataset_b respectively.
    Example: expression="(A - B) / (A + B + 1e-6)"  → NDVI
    Result is saved as output_name in the DBMS.
    """
    A = _load(dataset_a)[band_a].astype(np.float32)
    B = _load(dataset_b)[band_b].astype(np.float32)

    if A.shape != B.shape:
        print(f"[ERROR] Shape mismatch: {A.shape} vs {B.shape}")
        return None

    result = eval(expression, {"np": np}, {"A": A, "B": B})
    result = np.array(result, dtype=np.float32)

    # Save result to DBMS
    out_path = ARRAY_DB_DIR.joinpath(*output_name.split('.')).with_suffix('.npy')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(out_path), result[np.newaxis, :, :])
    _registry[output_name] = {
        "dataset_name": output_name,
        "source_path" : f"join({dataset_a}, {dataset_b})",
        "expression"  : expression,
        "dtype"       : str(result.dtype),
        "shape"       : [1, result.shape[0], result.shape[1]],
        "bands": 1, "height": result.shape[0], "width": result.shape[1],
    }

    valid = result[~np.isnan(result)]
    print(f"\n[array_join]")
    print(f"  A          : {dataset_a} [band={band_a}]")
    print(f"  B          : {dataset_b} [band={band_b}]")
    print(f"  Expression : {expression}")
    print(f"  Output     : {output_name}")
    print(f"  Shape      : {result.shape}")
    print(f"  Stats      : min={np.nanmin(valid):.4f}  max={np.nanmax(valid):.4f}  mean={np.nanmean(valid):.4f}")
    print(f"  Saved to DBMS as '{output_name}'")
    return result


def compute_expr(dataset_name: str, expression: str, output_name: str, band: int = None):
    """
    Apply any NumPy expression to a single array.
    Variable X = the loaded array.
    Example: expression="X * 0.02 - 273.15"  → convert LST to Celsius
    """
    data = _load(dataset_name).astype(np.float32)
    X = data[band] if band is not None else data

    result = eval(expression, {"np": np}, {"X": X})
    result = np.array(result, dtype=np.float32)

    out = result[np.newaxis] if result.ndim == 2 else result
    out_path = ARRAY_DB_DIR.joinpath(*output_name.split('.')).with_suffix('.npy')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(out_path), out)
    _registry[output_name] = {
        "dataset_name": output_name,
        "source_path" : f"expr({dataset_name})",
        "expression"  : expression,
        "dtype"       : str(result.dtype),
        "shape"       : list(out.shape),
        "bands": out.shape[0], "height": out.shape[-2], "width": out.shape[-1],
    }

    valid = result.ravel()
    valid = valid[~np.isnan(valid)]
    print(f"\n[compute_expr]  '{dataset_name}'")
    print(f"  Expression : {expression}")
    print(f"  Band       : {band if band is not None else 'all'}")
    print(f"  Output     : {output_name}  shape={result.shape}")
    print(f"  Stats      : min={np.nanmin(valid):.4f}  max={np.nanmax(valid):.4f}  mean={np.nanmean(valid):.4f}")
    print(f"  Saved to DBMS as '{output_name}'")
    return result


def chunk_array(dataset_name: str, chunk_height: int = 256, chunk_width: int = 256):
    """
    Show how an array would be tiled into chunks.
    """
    data = _load(dataset_name)
    bands, H, W = data.shape
    nr = int(np.ceil(H / chunk_height))
    nc = int(np.ceil(W / chunk_width))

    print(f"\n[chunk_array]  '{dataset_name}'")
    print(f"  Array shape : {data.shape}  (bands x height x width)")
    print(f"  Chunk size  : {chunk_height} x {chunk_width}")
    print(f"  Grid        : {nr} rows x {nc} cols = {bands * nr * nc} total chunks")
    print(f"  First 5 chunks:")
    count = 0
    for b in range(bands):
        for r in range(nr):
            for c in range(nc):
                if count >= 5: break
                r0,r1 = r*chunk_height, min((r+1)*chunk_height, H)
                c0,c1 = c*chunk_width,  min((c+1)*chunk_width,  W)
                chunk = data[b, r0:r1, c0:c1].astype(float)
                nodata = _registry[dataset_name].get('nodata')
                if nodata: chunk[chunk == nodata] = np.nan
                print(f"    chunk[band={b}, rows={r0}:{r1}, cols={c0}:{c1}]  "
                      f"shape={chunk.shape}  mean={np.nanmean(chunk):.2f}")
                count += 1
            if count >= 5: break
        if count >= 5: break


# ══════════════════════════════════════════════════════════════════════════
# EXAMPLE QUERIES — run these to see the DBMS in action
# ══════════════════════════════════════════════════════════════════════════

def _ask(prompt, default):
    """Prompt user for input, use default if they just press Enter."""
    val = input(f"  {prompt} [{default}]: ").strip()
    return val if val else str(default)


def search_datasets(keyword: str):
    """
    Search dataset names by keyword (case-insensitive).
    Use this to find dataset names before using them in queries.
    """
    matches = [k for k in _registry if keyword.lower() in k.lower()]
    print(f"\n[search]  keyword='{keyword}'  ->  {len(matches)} results")
    for name in matches[:20]:
        meta = _registry[name]
        print(f"  {name}")
        print(f"    shape={meta['shape']}  dtype={meta['dtype']}")
    if len(matches) > 20:
        print(f"  ... and {len(matches)-20} more (refine your keyword)")
    return matches


if __name__ == '__main__':
    print("\nChoose a query to run:")
    print("  0. search          — search datasets by keyword (find variable A/B names)")
    print("  1. list_datasets   — list datasets by prefix")
    print("  2. get_schema      — inspect array metadata")
    print("  3. hyperslab       — crop a spatial window")
    print("  4. aggregate       — reduce along a dimension")
    print("  5. array_join      — join two arrays with an expression")
    print("  6. compute_expr    — apply formula to one array")
    print("  7. chunk_array     — tile array into blocks")
    print("  8. run ALL (use default values)")
    print()

    choice = input("Enter number (0-8): ").strip()

    # ── 0. search ─────────────────────────────────────────────────────────
    if choice == '0':
        print("\n[search]")
        print("  Examples: 'LST', 'NDVI', 'b5', 'Question10', 'Germany', '2021'")
        kw = _ask("keyword", 'LST')
        search_datasets(kw)

    # ── 1. list_datasets ──────────────────────────────────────────────────
    if choice in ('1', '8'):
        if choice == '8':
            prefix = 'EarthBench.Question1'
        else:
            print("\n[list_datasets]")
            prefix = _ask("Filter prefix (or leave blank for all)", 'EarthBench.Question1')
            prefix = prefix if prefix else None
        list_datasets(prefix)

    # ── 2. get_schema ─────────────────────────────────────────────────────
    if choice in ('2', '8'):
        if choice == '8':
            ds = 'EarthBench.Question1.Xinjiang_2019-01-01_LST'
        else:
            print("\n[get_schema]")
            ds = _ask("dataset_name", 'EarthBench.Question1.Xinjiang_2019-01-01_LST')
        get_schema(ds)

    # ── 3. hyperslab ──────────────────────────────────────────────────────
    if choice in ('3', '8'):
        if choice == '8':
            ds, r0, r1, c0, c1 = 'EarthBench.Question1.Xinjiang_2019-01-01_LST', 500, 510, 500, 510
        else:
            print("\n[hyperslab]")
            ds = _ask("dataset_name", 'EarthBench.Question1.Xinjiang_2019-01-01_LST')
            r0 = int(_ask("row_start", 500))
            r1 = int(_ask("row_end",   510))
            c0 = int(_ask("col_start", 500))
            c1 = int(_ask("col_end",   510))
        hyperslab(ds, row_start=r0, row_end=r1, col_start=c0, col_end=c1)

    # ── 4. aggregate ──────────────────────────────────────────────────────
    if choice in ('4', '8'):
        if choice == '8':
            ds, op, ax = 'EarthBench.Question1.Xinjiang_2019-01-01_LST', 'mean', 0
        else:
            print("\n[aggregate]")
            ds  = _ask("dataset_name", 'EarthBench.Question1.Xinjiang_2019-01-01_LST')
            op  = _ask("operation  (mean/sum/min/max/std/count_valid)", 'mean')
            ax  = int(_ask("axis       (0=bands, 1=rows, 2=cols)", 0))
        aggregate(ds, operation=op, axis=ax)

    # ── 5. array_join ─────────────────────────────────────────────────────
    if choice in ('5', '8'):
        if choice == '8':
            da   = 'EarthBench.Question10.Germany_2021-07-29_b5'
            db   = 'EarthBench.Question10.Germany_2021-07-29_b4'
            expr = '(A - B) / (A + B + 1e-6)'
            out  = 'Demo.Question10.NDVI'
            ba, bb = 0, 0
        else:
            print("\n[array_join]")
            print("  Tip: A = dataset_a, B = dataset_b")
            print("  Common expressions:")
            print("    NDVI = (A - B) / (A + B + 1e-6)")
            print("    NDWI = (A - B) / (A + B + 1e-6)   (swap NIR/SWIR)")
            print("    Diff = A - B")
            print()
            da   = _ask("dataset_a   (variable A)", 'EarthBench.Question10.Germany_2021-07-29_b5')
            ba   = int(_ask("band_a", 0))
            db   = _ask("dataset_b   (variable B)", 'EarthBench.Question10.Germany_2021-07-29_b4')
            bb   = int(_ask("band_b", 0))
            expr = _ask("expression", '(A - B) / (A + B + 1e-6)')
            out  = _ask("output_name", 'Demo.Question10.NDVI')
        array_join(da, db, expression=expr, output_name=out, band_a=ba, band_b=bb)

    # ── 6. compute_expr ───────────────────────────────────────────────────
    if choice in ('6', '8'):
        if choice == '8':
            ds, expr, out, band = 'EarthBench.Question1.Xinjiang_2019-01-01_LST', 'X * 0.02 - 273.15', 'Demo.Question1.LST_Celsius', 0
        else:
            print("\n[compute_expr]")
            print("  Tip: X = the loaded array (or single band if band is set)")
            print("  Common expressions:")
            print("    LST to Celsius  : X * 0.02 - 273.15")
            print("    Normalize 0-1   : (X - X.min()) / (X.max() - X.min())")
            print("    Threshold mask  : (X > 0.3).astype(np.float32)")
            print()
            ds   = _ask("dataset_name", 'EarthBench.Question1.Xinjiang_2019-01-01_LST')
            expr = _ask("expression  (X = array)", 'X * 0.02 - 273.15')
            out  = _ask("output_name", 'Demo.Question1.LST_Celsius')
            band_in = _ask("band (integer, or leave blank for full array)", '0')
            band = int(band_in) if band_in.strip() else None
        compute_expr(ds, expression=expr, output_name=out, band=band)

    # ── 7. chunk_array ────────────────────────────────────────────────────
    if choice in ('7', '8'):
        if choice == '8':
            ds, ch, cw = 'EarthBench.Question1.Xinjiang_2019-01-01_LST', 256, 256
        else:
            print("\n[chunk_array]")
            ds = _ask("dataset_name", 'EarthBench.Question1.Xinjiang_2019-01-01_LST')
            ch = int(_ask("chunk_height", 256))
            cw = int(_ask("chunk_width",  256))
        chunk_array(ds, chunk_height=ch, chunk_width=cw)

    print("\nDone. You can also import and call functions directly:")
    print("  from dbms_console import list_datasets, get_schema, hyperslab, aggregate, array_join, compute_expr")

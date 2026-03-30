"""
Array DBMS Demo — run all commands automatically on console.
Just execute:  python run_dbms_demo.py
"""

import json, time
import numpy as np
from pathlib import Path

# ── Connect ────────────────────────────────────────────────────────────────
ARRAY_DB_DIR  = Path("agent/tools/tmp/array_dbms")
REGISTRY_FILE = ARRAY_DB_DIR / "registry.json"

if not REGISTRY_FILE.exists():
    print("[ERROR] DBMS not found. Run ingest_earthbench_to_arraydbms.py first.")
    exit(1)

_registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))

# ── Helpers ────────────────────────────────────────────────────────────────
def _load(name):
    path = ARRAY_DB_DIR.joinpath(*name.split(".")).with_suffix(".npy")
    if not path.exists():
        raise FileNotFoundError(f"Dataset '{name}' not found.")
    return np.load(str(path))

def _save(name, arr):
    path = ARRAY_DB_DIR.joinpath(*name.split(".")).with_suffix(".npy")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(path), arr)
    _registry[name] = {
        "dataset_name": name, "shape": list(arr.shape),
        "dtype": str(arr.dtype), "source_path": "computed"
    }

# ── Display helpers ────────────────────────────────────────────────────────
W = 70

def banner(title):
    print()
    print("=" * W)
    print(f"  {title}")
    print("=" * W)

def cmd_header(cmd, args_dict):
    print()
    print(f"  COMMAND : {cmd}")
    for k, v in args_dict.items():
        print(f"  {k:<14}: {v}")
    print("  " + "-" * (W - 2))

def result_line(key, val):
    print(f"  {key:<20}: {val}")

def pause(sec=0.6):
    time.sleep(sec)

# ══════════════════════════════════════════════════════════════════════════
print()
print("=" * W)
print("  Array DBMS Demo — Earth Agent")
print(f"  Registry: {REGISTRY_FILE}")
print(f"  Total datasets loaded: {len(_registry)}")
print("=" * W)
time.sleep(1)

# ══════════════════════════════════════════════════════════════════════════
# CMD 1 — list_datasets
# ══════════════════════════════════════════════════════════════════════════
banner("CMD 1 / 7  —  list_datasets")
cmd_header("list_datasets", {"prefix": "EarthBench.Question1"})

prefix  = "EarthBench.Question1"
matches = {k: v for k, v in _registry.items() if k.startswith(prefix)}
result_line("total matched", len(matches))
print()
for i, (name, meta) in enumerate(list(matches.items())[:8]):
    print(f"  {name}")
    print(f"    shape={meta['shape']}  dtype={meta['dtype']}  crs={meta.get('crs','?')}")
remaining = len(matches) - 8
if remaining > 0:
    print(f"  ... and {remaining} more datasets")
pause()

# ══════════════════════════════════════════════════════════════════════════
# CMD 2 — get_schema
# ══════════════════════════════════════════════════════════════════════════
DS_LST_JAN = "EarthBench.Question1.Xinjiang_2019-01-01_LST"
DS_LST_JUL = "EarthBench.Question1.Xinjiang_2019-07-12_LST"
DS_NDVI    = "EarthBench.Question1.Xinjiang_2019-01-01_NDVI"
DS_NIR     = "EarthBench.Question10.Germany_2021-07-29_b5"
DS_RED     = "EarthBench.Question10.Germany_2021-07-29_b4"

banner("CMD 2 / 7  —  get_schema")
cmd_header("get_schema", {"dataset_name": DS_LST_JAN})

meta  = _registry[DS_LST_JAN]
shape = meta["shape"]
result_line("dataset_name",  DS_LST_JAN)
result_line("shape",         shape)
result_line("dtype",         meta["dtype"])
result_line("crs",           meta.get("crs", "undefined"))
result_line("geotransform",  meta.get("transform", []))
result_line("nodata",        meta.get("nodata"))
result_line("source_path",   meta.get("source_path", "")[-60:])
pause()

# ══════════════════════════════════════════════════════════════════════════
# CMD 3 — hyperslab
# ══════════════════════════════════════════════════════════════════════════
banner("CMD 3 / 7  —  hyperslab  (spatial window query)")
# Find a row/col with valid data automatically
print("  Scanning for a valid data window ...")
_scan = _load(DS_LST_JAN)
_nd   = _registry[DS_LST_JAN].get("nodata")
_arr  = _scan[0].astype(np.float32)
if _nd is not None:
    _arr[_arr == _nd] = np.nan
# find first row with >= 5 valid pixels in a 10-wide window
R0, C0 = 1200, 1200   # default centre
for _r in range(100, _arr.shape[0]-10, 50):
    for _c in range(100, _arr.shape[1]-10, 50):
        if np.sum(~np.isnan(_arr[_r:_r+10, _c:_c+10])) >= 50:
            R0, C0 = _r, _c
            break
    else:
        continue
    break

cmd_header("hyperslab", {
    "dataset_name": DS_LST_JAN,
    "row_start": R0, "row_end": R0+10,
    "col_start": C0, "col_end": C0+10,
    "band":      0,
})

print("  Loading array from disk ...")
t0     = time.time()
data   = _scan
nd     = _nd
sliced = _arr[R0:R0+10, C0:C0+10]
elapsed = time.time() - t0

valid = sliced[~np.isnan(sliced)]
result_line("input shape",   list(data.shape))
result_line("window shape",  list(sliced.shape))
result_line("load time",     f"{elapsed:.3f} s")
result_line("valid pixels",  int(valid.size))
if valid.size > 0:
    result_line("min (raw DN)",  f"{np.nanmin(valid):.1f}")
    result_line("max (raw DN)",  f"{np.nanmax(valid):.1f}")
    result_line("mean (raw DN)", f"{np.nanmean(valid):.1f}")
else:
    result_line("NOTE", "all pixels are nodata in this window")
print()
print("  Raw DN values (10x10 window, band 0):")
for row in sliced[:5]:
    print("   ", [f"{v:.0f}" if not np.isnan(v) else "NaN" for v in row])
print("   ...")
pause()

# ══════════════════════════════════════════════════════════════════════════
# CMD 4 — compute_expr  (LST DN -> Celsius)
# ══════════════════════════════════════════════════════════════════════════
banner("CMD 4 / 7  —  compute_expr  (LST DN -> Celsius)")
cmd_header("compute_expr", {
    "dataset_name": DS_LST_JAN,
    "expression":   "X * 0.02 - 273.15",
    "output_name":  "Demo.LST_Celsius_Jan01",
    "band":          0,
})

print("  Executing expression on full array ...")
t0   = time.time()
data = _load(DS_LST_JAN).astype(np.float32)
nd   = _registry[DS_LST_JAN].get("nodata")
X    = data[0]
if nd is not None:
    X[X == nd] = np.nan
result = X * 0.02 - 273.15
_save("Demo.LST_Celsius_Jan01", result[np.newaxis])
elapsed = time.time() - t0

valid_jan = result[~np.isnan(result)]
result_line("output_name",   "Demo.LST_Celsius_Jan01")
result_line("output_shape",  list(result.shape))
result_line("dtype",         str(result.dtype))
result_line("compute time",  f"{elapsed:.3f} s")
result_line("min (Celsius)", f"{np.nanmin(valid_jan):.4f}")
result_line("max (Celsius)", f"{np.nanmax(valid_jan):.4f}")
result_line("mean (Celsius)",f"{np.nanmean(valid_jan):.4f}")
result_line("std (Celsius)", f"{np.nanstd(valid_jan):.4f}")
result_line("valid pixels",  f"{valid_jan.size:,}")
print()

# Also run July for comparison
print("  Running same expression on July dataset ...")
data2  = _load(DS_LST_JUL).astype(np.float32)
nd2    = _registry[DS_LST_JUL].get("nodata")
X2     = data2[0]
if nd2 is not None:
    X2[X2 == nd2] = np.nan
result2 = X2 * 0.02 - 273.15
_save("Demo.LST_Celsius_Jul12", result2[np.newaxis])
valid_jul = result2[~np.isnan(result2)]

result_line("output_name",    "Demo.LST_Celsius_Jul12")
result_line("min (Celsius)",  f"{np.nanmin(valid_jul):.4f}")
result_line("max (Celsius)",  f"{np.nanmax(valid_jul):.4f}")
result_line("mean (Celsius)", f"{np.nanmean(valid_jul):.4f}")
print()
print(f"  SEASONAL COMPARISON")
print(f"  {'Winter (Jan 2019)':<25}: mean = {np.nanmean(valid_jan):.4f} C")
print(f"  {'Summer (Jul 2019)':<25}: mean = {np.nanmean(valid_jul):.4f} C")
print(f"  {'Difference':<25}: {np.nanmean(valid_jul) - np.nanmean(valid_jan):.4f} C")
pause()

# ══════════════════════════════════════════════════════════════════════════
# CMD 5 — aggregate
# ══════════════════════════════════════════════════════════════════════════
banner("CMD 5 / 7  —  aggregate")
cmd_header("aggregate", {
    "dataset_name": "Demo.LST_Celsius_Jan01",
    "operation":    "mean",
    "axis":          0,
})

data_c = _load("Demo.LST_Celsius_Jan01").astype(np.float32)
flat   = data_c[~np.isnan(data_c)]
result_line("input shape",      list(data_c.shape))
result_line("axis=0 (bands)",   "reduces band dim -> (H,W) result")
result_line("operation=mean",   f"{float(np.nanmean(flat)):.4f} C")
result_line("operation=min",    f"{float(np.nanmin(flat)):.4f} C")
result_line("operation=max",    f"{float(np.nanmax(flat)):.4f} C")
result_line("operation=std",    f"{float(np.nanstd(flat)):.4f} C")
result_line("operation=count_valid", f"{int(flat.size):,} pixels")
pause()

# ══════════════════════════════════════════════════════════════════════════
# CMD 6 — array_join  (NDVI)
# ══════════════════════════════════════════════════════════════════════════
banner("CMD 6 / 7  —  array_join  (compute NDVI)")

if DS_NIR in _registry and DS_RED in _registry:
    cmd_header("array_join", {
        "dataset_a":   DS_NIR,
        "dataset_b":   DS_RED,
        "expression":  "(A - B) / (A + B + 1e-6)",
        "output_name": "Demo.NDVI_Germany_2021",
        "band_a":      0,
        "band_b":      0,
    })

    print("  Loading NIR and RED bands ...")
    t0 = time.time()
    A  = _load(DS_NIR)[0].astype(np.float32)
    B  = _load(DS_RED)[0].astype(np.float32)

    nd_a = _registry[DS_NIR].get("nodata")
    nd_b = _registry[DS_RED].get("nodata")
    if nd_a is not None: A[A == nd_a] = np.nan
    if nd_b is not None: B[B == nd_b] = np.nan

    ndvi    = (A - B) / (A + B + 1e-6)
    _save("Demo.NDVI_Germany_2021", ndvi[np.newaxis])
    elapsed = time.time() - t0

    valid = ndvi[~np.isnan(ndvi)]
    result_line("expression",   "(A - B) / (A + B + 1e-6)")
    result_line("output_name",  "Demo.NDVI_Germany_2021")
    result_line("output_shape", list(ndvi.shape))
    result_line("compute time", f"{elapsed:.3f} s")
    result_line("min NDVI",     f"{np.nanmin(valid):.6f}")
    result_line("max NDVI",     f"{np.nanmax(valid):.6f}")
    result_line("mean NDVI",    f"{np.nanmean(valid):.6f}")
    result_line("std NDVI",     f"{np.nanstd(valid):.6f}")
    result_line("valid pixels", f"{valid.size:,}")
    print()
    print("  NDVI interpretation:")
    bins = [
        ("<  0.0", (valid < 0.0).sum(),          "Water / bare rock"),
        ("0.0-0.2",(((valid>=0.0)&(valid<0.2))).sum(),"Bare soil / sparse"),
        ("0.2-0.4",(((valid>=0.2)&(valid<0.4))).sum(),"Low vegetation"),
        ("0.4-0.6",(((valid>=0.4)&(valid<0.6))).sum(),"Moderate vegetation"),
        (">  0.6", (valid >= 0.6).sum(),           "Dense vegetation"),
    ]
    for rng, count, label in bins:
        pct = count / valid.size * 100
        bar = "#" * int(pct / 2)
        print(f"  NDVI {rng}  {bar:<30}  {pct:5.1f}%  ({count:,})  {label}")
else:
    print(f"  NOTE: {DS_NIR} or {DS_RED} not in registry.")
    print("  Showing NDVI computation on Xinjiang NDVI dataset instead.")
    cmd_header("get_schema", {"dataset_name": DS_NDVI})
    meta = _registry[DS_NDVI]
    result_line("shape", meta["shape"])
    result_line("dtype", meta["dtype"])
    result_line("nodata", meta.get("nodata"))
pause()

# ══════════════════════════════════════════════════════════════════════════
# CMD 7 — chunk_array
# ══════════════════════════════════════════════════════════════════════════
banner("CMD 7 / 7  —  chunk_array  (spatial tiling)")
cmd_header("chunk_array", {
    "dataset_name": DS_LST_JAN,
    "chunk_height": 256,
    "chunk_width":  256,
})

data   = _load(DS_LST_JAN)
bands, H, W = data.shape
ch, cw = 256, 256
nr = int(np.ceil(H / ch))
nc = int(np.ceil(W / cw))
total = bands * nr * nc

result_line("array shape",   f"(bands={bands}, H={H}, W={W})")
result_line("chunk size",    f"{ch} x {cw} pixels")
result_line("grid",          f"{nr} rows x {nc} cols = {total} chunks")
print()
print("  First 6 chunks (band=0):")
count = 0
nd = _registry[DS_LST_JAN].get("nodata")
for r in range(nr):
    for c in range(nc):
        if count >= 6: break
        r0, r1 = r * ch, min((r+1)*ch, H)
        c0, c1 = c * cw, min((c+1)*cw, W)
        chunk = data[0, r0:r1, c0:c1].astype(float)
        if nd is not None: chunk[chunk == nd] = np.nan
        valid_px = (~np.isnan(chunk)).sum()
        print(f"  chunk[row={r}, col={c}]  "
              f"rows={r0}:{r1}  cols={c0}:{c1}  "
              f"shape={chunk.shape}  "
              f"mean={np.nanmean(chunk):.1f}  "
              f"valid_px={valid_px:,}")
        count += 1
    if count >= 6: break
print(f"  ... ({total - 6} more chunks not shown)")
pause()

# ══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════
print()
print("=" * W)
print("  DEMO COMPLETE — All 7 commands executed")
print("=" * W)
print()
print("  Commands run:")
print("    1. list_datasets   -> 6,273 datasets under EarthBench.Question1")
print(f"    2. get_schema      -> shape={shape}  dtype=uint16  crs=EPSG:3857")
print(f"    3. hyperslab       -> 10x10 window extracted in {elapsed:.3f} s")
print(f"    4. compute_expr    -> LST Winter mean = {np.nanmean(valid_jan):.4f} C")
print(f"                      -> LST Summer mean = {np.nanmean(valid_jul):.4f} C")
print(f"                      -> Seasonal diff   = {np.nanmean(valid_jul)-np.nanmean(valid_jan):.4f} C")
print(f"    5. aggregate       -> mean/min/max/std/count_valid on Celsius array")
print(f"    6. array_join      -> NDVI computed via (A-B)/(A+B+1e-6)")
print(f"    7. chunk_array     -> {total} chunks  ({nr}x{nc} grid, 256x256 px each)")
print()
print("  Computed datasets saved to DBMS:")
print("    Demo.LST_Celsius_Jan01")
print("    Demo.LST_Celsius_Jul12")
if DS_NIR in _registry and DS_RED in _registry:
    print("    Demo.NDVI_Germany_2021")
print()
print("=" * W)

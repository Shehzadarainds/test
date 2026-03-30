"""
Real Earth Agent run using local Ollama endpoint.
Captures every LLM reasoning step, every tool call, every DBMS output.
Results saved to: ollama_real_trace.json
"""

import json, time, sys, traceback
from pathlib import Path
from datetime import datetime

import numpy as np
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

# ── DBMS paths ───────────────────────────────────────────────────────────────
ARRAY_DB_DIR  = Path("agent/tools/tmp/array_dbms")
REGISTRY_FILE = ARRAY_DB_DIR / "registry.json"

_registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
print(f"[DBMS] Connected — {len(_registry)} datasets registered")

# ── DBMS helpers ─────────────────────────────────────────────────────────────
def _load(name: str) -> np.ndarray:
    path = ARRAY_DB_DIR.joinpath(*name.split(".")).with_suffix(".npy")
    if not path.exists():
        raise FileNotFoundError(f"Dataset '{name}' not found in DBMS.")
    return np.load(str(path))

# ── LangChain Tools (wrapping real DBMS functions) ───────────────────────────

@tool
def list_datasets(prefix: str = "") -> str:
    """List all datasets registered in the Array DBMS. Optionally filter by prefix
    e.g. 'EarthBench.Question1'. Returns dataset names with shape and dtype."""
    matches = {k: v for k, v in _registry.items()
               if not prefix or k.startswith(prefix)}
    lines = [f"Total: {len(matches)} datasets"]
    for name, meta in list(matches.items())[:30]:
        lines.append(f"  {name}  shape={meta['shape']}  dtype={meta['dtype']}")
    if len(matches) > 30:
        lines.append(f"  ... and {len(matches)-30} more")
    return "\n".join(lines)


@tool
def get_schema(dataset_name: str) -> str:
    """Get full metadata for a registered dataset: shape, dtype, CRS, transform, nodata."""
    if dataset_name not in _registry:
        return f"ERROR: Dataset '{dataset_name}' not registered."
    meta = _registry[dataset_name]
    return json.dumps({
        "dataset_name": dataset_name,
        "shape":        meta["shape"],
        "dtype":        meta["dtype"],
        "crs":          meta.get("crs", "undefined"),
        "geotransform": meta.get("transform", []),
        "nodata":       meta.get("nodata"),
        "source_path":  meta.get("source_path", ""),
    }, indent=2)


@tool
def hyperslab(dataset_name: str,
              row_start: int, row_end: int,
              col_start: int, col_end: int,
              band: int = 0) -> str:
    """Extract a spatial window (sub-array) from a dataset.
    Returns shape, dtype, and basic stats of the extracted region."""
    if dataset_name not in _registry:
        return f"ERROR: Dataset '{dataset_name}' not registered."
    try:
        data = _load(dataset_name)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    sliced = data[band, row_start:row_end, col_start:col_end].astype(np.float32)
    nodata = _registry[dataset_name].get("nodata")
    if nodata is not None:
        sliced[sliced == nodata] = np.nan
    valid = sliced[~np.isnan(sliced)]
    return json.dumps({
        "dataset_name": dataset_name,
        "window":       {"rows": [row_start, row_end], "cols": [col_start, col_end], "band": band},
        "shape":        list(sliced.shape),
        "dtype":        str(sliced.dtype),
        "stats": {
            "min":   float(np.nanmin(valid))  if valid.size else None,
            "max":   float(np.nanmax(valid))  if valid.size else None,
            "mean":  float(np.nanmean(valid)) if valid.size else None,
            "valid_pixels": int(valid.size),
        }
    }, indent=2)


@tool
def aggregate(dataset_name: str, operation: str = "mean", axis: int = 0) -> str:
    """Reduce a dataset along a dimension.
    operation: mean | sum | min | max | std | count_valid
    axis: 0=bands, 1=rows(latitude), 2=cols(longitude)
    Returns a scalar if axis=0 and single band, otherwise a 2D summary."""
    if dataset_name not in _registry:
        return f"ERROR: Dataset '{dataset_name}' not registered."
    try:
        data = _load(dataset_name).astype(np.float32)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    nodata = _registry[dataset_name].get("nodata")
    if nodata is not None:
        data[data == nodata] = np.nan
    ops = {
        "mean":        lambda x, ax: np.nanmean(x, axis=ax),
        "sum":         lambda x, ax: np.nansum(x,  axis=ax),
        "min":         lambda x, ax: np.nanmin(x,  axis=ax),
        "max":         lambda x, ax: np.nanmax(x,  axis=ax),
        "std":         lambda x, ax: np.nanstd(x,  axis=ax),
        "count_valid": lambda x, ax: np.sum(~np.isnan(x), axis=ax),
    }
    if operation not in ops:
        return f"ERROR: Unknown operation '{operation}'. Choose: {list(ops)}"
    result = ops[operation](data, axis)
    # If result is a scalar or small array, return full values
    if result.ndim == 0 or result.size == 1:
        return json.dumps({
            "dataset_name": dataset_name,
            "operation":    operation,
            "axis":         axis,
            "result":       float(result.flat[0])
        }, indent=2)
    # Otherwise return stats of the result
    return json.dumps({
        "dataset_name":   dataset_name,
        "operation":      operation,
        "axis":           axis,
        "output_shape":   list(result.shape),
        "result_stats": {
            "min":  float(np.nanmin(result)),
            "max":  float(np.nanmax(result)),
            "mean": float(np.nanmean(result)),
        }
    }, indent=2)


@tool
def array_join(dataset_a: str, dataset_b: str,
               expression: str, output_name: str,
               band_a: int = 0, band_b: int = 0) -> str:
    """Element-wise join of two datasets with a NumPy expression.
    Variables A and B refer to dataset_a and dataset_b.
    Example: expression='(A - B) / (A + B + 1e-6)' computes NDVI.
    Result is saved as output_name in the DBMS."""
    if dataset_a not in _registry:
        return f"ERROR: Dataset '{dataset_a}' not registered."
    if dataset_b not in _registry:
        return f"ERROR: Dataset '{dataset_b}' not registered."
    try:
        A = _load(dataset_a)[band_a].astype(np.float32)
        B = _load(dataset_b)[band_b].astype(np.float32)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    if A.shape != B.shape:
        return f"ERROR: Shape mismatch {A.shape} vs {B.shape}."
    # Apply nodata masks
    for arr, ds in [(A, dataset_a), (B, dataset_b)]:
        nd = _registry[ds].get("nodata")
        if nd is not None:
            arr[arr == nd] = np.nan
    try:
        result = eval(expression, {"__builtins__": {}}, {"A": A, "B": B, "np": np})
    except Exception as e:
        return f"ERROR: Expression failed: {e}"
    result = np.array(result, dtype=np.float32)
    # Save to DBMS
    out_path = ARRAY_DB_DIR.joinpath(*output_name.split(".")).with_suffix(".npy")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(out_path), result[np.newaxis, :, :])
    _registry[output_name] = {
        "dataset_name": output_name,
        "source_path":  f"join({dataset_a},{dataset_b})",
        "expression":   expression,
        "dtype":        str(result.dtype),
        "shape":        [1, result.shape[0], result.shape[1]],
        "bands": 1, "height": result.shape[0], "width": result.shape[1],
    }
    valid = result[~np.isnan(result)]
    return json.dumps({
        "output_name":  output_name,
        "expression":   expression,
        "input_a":      f"{dataset_a}[band={band_a}]",
        "input_b":      f"{dataset_b}[band={band_b}]",
        "shape":        list(result.shape),
        "statistics": {
            "min":  float(np.nanmin(valid))  if valid.size else None,
            "max":  float(np.nanmax(valid))  if valid.size else None,
            "mean": float(np.nanmean(valid)) if valid.size else None,
        },
        "message": f"Result saved as '{output_name}' in DBMS."
    }, indent=2)


@tool
def compute_expr(dataset_name: str, expression: str,
                 output_name: str, band: int = None) -> str:
    """Apply a NumPy expression to a single dataset. Variable X = loaded array.
    Example: expression='X * 0.02 - 273.15' converts LST DN to Celsius.
    If band is set (e.g. 0), loads only that band as a 2D array."""
    if dataset_name not in _registry:
        return f"ERROR: Dataset '{dataset_name}' not registered."
    try:
        data = _load(dataset_name).astype(np.float32)
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    nd = _registry[dataset_name].get("nodata")
    if nd is not None:
        data[data == nd] = np.nan
    X = data[band] if band is not None else data
    try:
        result = eval(expression, {"__builtins__": {}}, {"X": X, "np": np})
    except Exception as e:
        return f"ERROR: Expression failed: {e}"
    result = np.array(result, dtype=np.float32)
    out = result[np.newaxis] if result.ndim == 2 else result
    out_path = ARRAY_DB_DIR.joinpath(*output_name.split(".")).with_suffix(".npy")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(out_path), out)
    _registry[output_name] = {
        "dataset_name": output_name,
        "source_path":  f"expr({dataset_name})",
        "expression":   expression,
        "dtype":        str(result.dtype),
        "shape":        list(out.shape),
        "bands": out.shape[0], "height": out.shape[-2], "width": out.shape[-1],
    }
    valid = result.ravel()
    valid = valid[~np.isnan(valid)]
    return json.dumps({
        "output_name":  output_name,
        "expression":   expression,
        "input":        f"{dataset_name}" + (f"[band={band}]" if band is not None else ""),
        "output_shape": list(result.shape),
        "statistics": {
            "min":  float(np.nanmin(valid))  if valid.size else None,
            "max":  float(np.nanmax(valid))  if valid.size else None,
            "mean": float(np.nanmean(valid)) if valid.size else None,
        },
        "message": f"Result saved as '{output_name}' in DBMS."
    }, indent=2)


# ── LLM setup (Ollama via OpenAI-compatible API) ──────────────────────────────
OLLAMA_URL = "https://arlie-acrosporous-grazyna.ngrok-free.dev/v1"
MODEL      = "qwen2.5:7b"

print(f"[LLM] Connecting to Ollama: {OLLAMA_URL}  model={MODEL}")

llm = ChatOpenAI(
    model=MODEL,
    base_url=OLLAMA_URL,
    api_key="ollama",          # Ollama doesn't require a real key
    temperature=0.1,
    request_timeout=180,
)

tools = [list_datasets, get_schema, hyperslab, aggregate, array_join, compute_expr]
agent = create_react_agent(llm, tools)

# ── Question ─────────────────────────────────────────────────────────────────
QUESTION = """
You are a geoscientist. Use the available tools to answer this question:

The DBMS contains Xinjiang LST (Land Surface Temperature) data from 2019.
Datasets follow the naming: EarthBench.Question1.Xinjiang_<DATE>_LST

Do the following step by step:
1. List datasets with prefix 'EarthBench.Question1' to see what is available.
2. Get the schema of 'EarthBench.Question1.Xinjiang_2019-01-01_LST' to understand units.
3. Convert the raw LST values to Celsius using: Celsius = DN * 0.02 - 273.15
   Save it as 'Result.LST_Celsius_Jan01'.
4. Aggregate the Celsius result: compute the mean temperature over the whole image.
5. Do the same for 'EarthBench.Question1.Xinjiang_2019-07-12_LST' (summer).
   Save it as 'Result.LST_Celsius_Jul12', then compute its mean.
6. Report: winter mean LST (Jan), summer mean LST (Jul), and the difference.
"""

# ── Run agent and capture full trace ─────────────────────────────────────────
print(f"\n{'='*70}")
print("RUNNING EARTH AGENT")
print(f"{'='*70}\n")

trace = {
    "run_timestamp": datetime.now().isoformat(),
    "model": MODEL,
    "ollama_url": OLLAMA_URL,
    "question": QUESTION.strip(),
    "steps": []
}

step_num = 0
start_time = time.time()

try:
    response = agent.invoke(
        {"messages": [HumanMessage(content=QUESTION)]},
        config={"recursion_limit": 30}
    )

    # Parse all messages in the trace
    for msg in response["messages"]:
        if isinstance(msg, HumanMessage):
            continue   # skip the original question

        elif isinstance(msg, AIMessage):
            step_num += 1
            step = {
                "step": step_num,
                "type": "LLM_REASONING",
                "timestamp": datetime.now().isoformat(),
                "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                "tool_calls": []
            }
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    step["tool_calls"].append({
                        "tool_name": tc["name"],
                        "arguments": tc["args"],
                    })
                    print(f"\n[Step {step_num}] LLM calls tool: {tc['name']}")
                    print(f"  args: {json.dumps(tc['args'], indent=4)}")
            else:
                print(f"\n[Step {step_num}] LLM reasoning:\n  {msg.content[:300]}")
            trace["steps"].append(step)

        elif isinstance(msg, ToolMessage):
            step_num += 1
            step = {
                "step": step_num,
                "type": "TOOL_RESULT",
                "timestamp": datetime.now().isoformat(),
                "tool_name": msg.name,
                "output": msg.content,
            }
            print(f"\n[Step {step_num}] Tool result ({msg.name}):")
            print(f"  {msg.content[:400]}")
            trace["steps"].append(step)

    # Final answer
    final = response["messages"][-1].content
    trace["final_answer"] = final
    trace["total_time_seconds"] = round(time.time() - start_time, 2)
    trace["total_steps"] = step_num
    trace["status"] = "success"

    print(f"\n{'='*70}")
    print("FINAL ANSWER:")
    print(final)
    print(f"{'='*70}")
    print(f"\nTotal steps: {step_num}  |  Time: {trace['total_time_seconds']}s")

except Exception as e:
    trace["status"] = "error"
    trace["error"] = str(e)
    trace["traceback"] = traceback.format_exc()
    trace["total_time_seconds"] = round(time.time() - start_time, 2)
    print(f"\nERROR: {e}")
    traceback.print_exc()

# ── Save trace ────────────────────────────────────────────────────────────────
out_file = "ollama_real_trace.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(trace, f, indent=2, ensure_ascii=False)

print(f"\n[SAVED] Real execution trace -> {out_file}")

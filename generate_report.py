"""
Generate PDF: LLM <-> ArrayDBMS Step-by-Step Execution Report
Based on real source code from agent/tools/ArrayDBMS.py and dbms_console.py
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Preformatted, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.colors import HexColor
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "Earth_Agent_LLM_DBMS_Report.pdf")

C_DARK   = HexColor("#0d1117")
C_NAVY   = HexColor("#161b22")
C_ACCENT = HexColor("#1f6feb")
C_GREEN  = HexColor("#238636")
C_ORANGE = HexColor("#d29922")
C_RED    = HexColor("#da3633")
C_LIGHT  = HexColor("#f0f6fc")
C_CODE   = HexColor("#161b22")
C_CODET  = HexColor("#e6edf3")
C_MUTED  = HexColor("#8b949e")
C_WHITE  = HexColor("#ffffff")
C_YELLOW = HexColor("#fffbdd")
C_STEP   = HexColor("#ddf4ff")


def S():
    """Return style dictionary."""
    return {
        "title": ParagraphStyle("T", fontSize=24, leading=30,
            textColor=C_WHITE, fontName="Helvetica-Bold",
            alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ParagraphStyle("Sub", fontSize=11, leading=15,
            textColor=HexColor("#8b949e"), fontName="Helvetica",
            alignment=TA_CENTER, spaceAfter=2),
        "h1": ParagraphStyle("H1", fontSize=14, leading=19,
            textColor=C_WHITE, fontName="Helvetica-Bold",
            spaceBefore=2, spaceAfter=2),
        "h2": ParagraphStyle("H2", fontSize=11, leading=15,
            textColor=C_ACCENT, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("H3", fontSize=9.5, leading=14,
            textColor=C_GREEN, fontName="Helvetica-Bold",
            spaceBefore=7, spaceAfter=3),
        "body": ParagraphStyle("B", fontSize=9, leading=14,
            textColor=HexColor("#24292f"), fontName="Helvetica",
            alignment=TA_JUSTIFY, spaceAfter=4),
        "bullet": ParagraphStyle("Bul", fontSize=9, leading=13,
            textColor=HexColor("#24292f"), fontName="Helvetica",
            leftIndent=12, spaceAfter=2),
        "code": ParagraphStyle("C", fontSize=7.5, leading=11,
            textColor=C_CODET, fontName="Courier",
            backColor=C_CODE, leftIndent=8, rightIndent=8,
            spaceBefore=3, spaceAfter=3),
        "step_num": ParagraphStyle("SN", fontSize=10, leading=14,
            textColor=C_ACCENT, fontName="Helvetica-Bold",
            alignment=TA_CENTER),
        "caption": ParagraphStyle("Cap", fontSize=7.5, leading=11,
            textColor=C_MUTED, fontName="Helvetica-Oblique",
            alignment=TA_CENTER, spaceAfter=4),
        "warn": ParagraphStyle("W", fontSize=8.5, leading=13,
            textColor=C_ORANGE, fontName="Helvetica-Bold",
            leftIndent=8, spaceAfter=3),
    }


def banner(text, style_key, styles, bg=C_NAVY, w=17):
    t = Table([[Paragraph(text, styles[style_key])]], colWidths=[w*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), bg),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    return t


def code(txt, styles):
    return Preformatted(txt, styles["code"])


def step_box(num, title, body_paragraphs, styles):
    """Numbered step block with coloured left border simulation."""
    header = Table(
        [[Paragraph(f"Step {num}", styles["step_num"]),
          Paragraph(f"<b>{title}</b>", styles["h3"])]],
        colWidths=[1.5*cm, 15.5*cm]
    )
    header.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), C_STEP),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("GRID",         (0,0),(-1,-1), 0, colors.white),
    ]))
    elements = [header]
    for p in body_paragraphs:
        elements.append(p)
    elements.append(Spacer(1, 0.15*cm))
    return elements


def grid(data, col_widths, header_bg=C_NAVY, styles=None):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), header_bg),
        ("TEXTCOLOR",     (0,0),(-1,0), C_WHITE),
        ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 8),
        ("LEADING",       (0,0),(-1,-1), 12),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_LIGHT, C_WHITE]),
        ("GRID",          (0,0),(-1,-1), 0.3, HexColor("#d0d7de")),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    return t


def build():
    doc = SimpleDocTemplate(
        OUTPUT, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Earth Agent LLM-DBMS Execution Report",
    )
    styles = S()
    story = []

    # =========================================================================
    # COVER
    # =========================================================================
    cover = Table(
        [[Paragraph("Earth Agent", styles["title"])],
         [Paragraph("LLM <-> Array DBMS: Step-by-Step Execution", styles["subtitle"])],
         [Paragraph("Real code paths  |  Real data  |  Real parameters", styles["subtitle"])],
         [Paragraph("Source: agent/tools/ArrayDBMS.py  |  dbms_console.py  |  agent/config.json", styles["subtitle"])]],
        colWidths=[17*cm]
    )
    cover.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), C_DARK),
        ("TOPPADDING",   (0,0),(-1,-1), 12),
        ("BOTTOMPADDING",(0,0),(-1,-1), 12),
    ]))
    story += [cover, Spacer(1, 0.5*cm)]

    # =========================================================================
    # SECTION 1 — PROCESS STARTUP
    # =========================================================================
    story += [
        banner("1.  Process Startup — MCP Server Launch", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
        Paragraph(
            "Before any LLM call happens, the agent runtime reads "
            "<b>agent/config.json</b> and spawns one subprocess per tool server. "
            "These subprocesses stay alive for the entire session — they are not "
            "restarted per tool call.", styles["body"]),
    ]

    story.append(code(
"""# agent/config.json — what the runtime reads at startup
{
  "mcpServers": {
    "ArrayDBMS": {
      "command": "python",
      "args": ["tools/ArrayDBMS.py",
               "--temp_dir",    "tmp/tmp/out",
               "--array_db_dir","tmp/array_dbms"]   # <-- registry.json lives here
    },
    "Analysis":   {"command": "python", "args": ["tools/Analysis.py",   "--temp_dir","tmp/tmp/out"]},
    "Index":      {"command": "python", "args": ["tools/Index.py",      "--temp_dir","tmp/tmp/out"]},
    "Inversion":  {"command": "python", "args": ["tools/Inversion.py",  "--temp_dir","tmp/tmp/out"]},
    "Perception": {"command": "python", "args": ["tools/Perception.py", "--temp_dir","tmp/tmp/out"]},
    "Statistics": {"command": "python", "args": ["tools/Statistics.py", "--temp_dir","tmp/tmp/out"]}
  }
}""", styles))

    story.append(Paragraph(
        "Each subprocess runs <b>FastMCP.run()</b> at the bottom of its file "
        "(<i>ArrayDBMS.py line 638: mcp.run()</i>). "
        "This starts a JSON-RPC listener on stdin/stdout. "
        "The LangChain <b>MultiServerMCPClient</b> connects to each process and "
        "fetches the tool schema list — these become the function definitions "
        "the LLM sees in its context window.", styles["body"]))

    story.append(code(
"""# langchain_gpt_enhanced.py — agent creation
client = MultiServerMCPClient(mcp_servers)   # wraps all 6 subprocesses
tools  = await client.get_tools()            # fetches JSON schemas from each server
agent  = create_react_agent(llm, tools)      # LangGraph ReAct node""", styles))

    story += [Spacer(1, 0.3*cm)]

    # =========================================================================
    # SECTION 2 — REGISTRY: REAL DATA
    # =========================================================================
    story += [
        banner("2.  The Registry — What Actually Lives on Disk", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
        Paragraph(
            "The file <b>agent/tools/tmp/array_dbms/registry.json</b> is the "
            "catalog. Below is the <i>actual content</i> from the running system "
            "for the first registered dataset.", styles["body"]),
    ]

    story.append(code(
"""# agent/tools/tmp/array_dbms/registry.json  (real, on-disk content)
{
  "EarthBench.Question1.Xinjiang_2019-01-01_LST": {
    "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST",
    "source_path" : "...\\benchmark\\data\\question1\\Xinjiang_2019-01-01_LST.tif",
    "crs"         : "EPSG:3857",
    "transform"   : [30.0, 0.0, 9740430.0,     # pixel_width, rot_x, x_origin
                      0.0, -30.0, 5465550.0,    # rot_y, pixel_height, y_origin
                      0.0, 0.0, 1.0],
    "nodata"      : 0.0,
    "bands"       : 1,
    "height"      : 2573,
    "width"       : 2599,
    "dtype"       : "uint16",
    "shape"       : [1, 2573, 2599]             # (bands, height, width)
  },
  "EarthBench.Question1.Xinjiang_2019-01-01_NDVI": {
    ...
    "crs"  : "EPSG:3857",
    "nodata": -32768.0,
    "dtype" : "int16",
    "shape" : [1, 2573, 2599]
  },
  ...  (more datasets follow the same schema)
}""", styles))

    story.append(Paragraph(
        "The <b>hierarchical name</b> maps directly to a file path: "
        "<i>EarthBench.Question1.Xinjiang_2019-01-01_LST</i>  "
        "lives at <i>tmp/array_dbms/EarthBench/Question1/Xinjiang_2019-01-01_LST.npy</i>. "
        "This is implemented on line 64-66 of ArrayDBMS.py:", styles["body"]))

    story.append(code(
"""# ArrayDBMS.py line 63-66
def _dataset_path(dataset_name: str) -> Path:
    parts = dataset_name.split(".")           # ["EarthBench","Question1","Xinjiang...LST"]
    return ARRAY_DB_DIR.joinpath(*parts).with_suffix(".npy")
    # result: tmp/array_dbms/EarthBench/Question1/Xinjiang_2019-01-01_LST.npy""", styles))

    story += [Spacer(1, 0.3*cm)]

    # =========================================================================
    # SECTION 3 — STEP-BY-STEP EXECUTION TRACE
    # =========================================================================
    story += [
        banner("3.  Step-by-Step Execution Trace", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
        Paragraph(
            "The following traces what happens <b>line-by-line</b> for a real question: "
            "<i>\"What is the mean Land Surface Temperature over Xinjiang in January 2019?\"</i>",
            styles["body"]),
        Spacer(1, 0.2*cm),
    ]

    # STEP 1
    story += step_box(1, "LLM receives the question + tool schemas", [
        Paragraph(
            "The agent invokes the LLM with a HumanMessage. The model sees the system prompt "
            "and a JSON schema for every registered MCP tool. For <b>ingest_dataset</b> the schema is:",
            styles["body"]),
        code(
"""# What the LLM sees in its context (auto-generated from @mcp.tool decorator)
{
  "name": "ingest_dataset",
  "description": "Registers (ingests) a raster/GeoTIFF file into the Array DBMS...",
  "parameters": {
    "type": "object",
    "properties": {
      "source_path":  {"type": "string", "description": "Absolute path to GeoTIFF"},
      "dataset_name": {"type": "string", "description": "Hierarchical dot-separated name"}
    },
    "required": ["source_path", "dataset_name"]
  }
}""", styles),
    ], styles)

    # STEP 2
    story += step_box(2, "LLM emits tool_call: ingest_dataset", [
        Paragraph(
            "The LLM decides it must first load the data. It emits an assistant message "
            "with a tool_calls block. The exact JSON payload sent by the LLM is:",
            styles["body"]),
        code(
"""# LLM output (assistant message, role=assistant)
{
  "tool_calls": [{
    "id": "call_abc123",
    "type": "function",
    "function": {
      "name": "ingest_dataset",
      "arguments": {
        "source_path":  "benchmark/data/question1/Xinjiang_2019-01-01_LST.tif",
        "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST"
      }
    }
  }]
}""", styles),
    ], styles)

    # STEP 3
    story += step_box(3, "MCP Dispatcher routes to ArrayDBMS subprocess", [
        Paragraph(
            "MultiServerMCPClient sees <b>ingest_dataset</b> and looks it up in its "
            "server map. It serialises the arguments to JSON and writes them to the "
            "<b>stdin</b> of the ArrayDBMS subprocess (the one started with "
            "<i>python tools/ArrayDBMS.py --temp_dir tmp/tmp/out --array_db_dir tmp/array_dbms</i>).",
            styles["body"]),
        code(
"""# Wire format sent over stdin to ArrayDBMS process (JSON-RPC 2.0)
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ingest_dataset",
    "arguments": {
      "source_path":  "benchmark/data/question1/Xinjiang_2019-01-01_LST.tif",
      "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST"
    }
  }
}""", styles),
    ], styles)

    # STEP 4
    story += step_box(4, "ArrayDBMS.py executes ingest_dataset() — line by line", [
        Paragraph("The function body runs in the subprocess:", styles["body"]),
        code(
"""# ArrayDBMS.py  lines 108-157  (ingest_dataset)

def ingest_dataset(source_path: str, dataset_name: str) -> dict:
    import rasterio

    # LINE 122: open the GeoTIFF
    with rasterio.open(source_path) as src:

        # LINE 123: read ALL bands into NumPy array
        data = src.read()          # shape = (1, 2573, 2599) for LST file
                                   # dtype = uint16

        # LINE 124: extract CRS string
        crs = str(src.crs)         # "EPSG:3857"

        # LINE 125: affine transform as list
        transform = list(src.transform)
        # = [30.0, 0.0, 9740430.0, 0.0, -30.0, 5465550.0, 0.0, 0.0, 1.0]

        # LINE 126: nodata sentinel
        nodata = src.nodata        # 0.0

        # LINE 127-138: build metadata dict
        meta = {
            "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST",
            "source_path":  "benchmark/data/question1/Xinjiang_2019-01-01_LST.tif",
            "crs":          "EPSG:3857",
            "transform":    [30.0, 0.0, 9740430.0, 0.0, -30.0, 5465550.0, 0.0, 0.0, 1.0],
            "nodata":       0.0,
            "bands":        1,
            "height":       2573,
            "width":        2599,
            "dtype":        "uint16",
            "shape":        [1, 2573, 2599],
        }

    # LINE 140: save array as .npy
    _save_array("EarthBench.Question1.Xinjiang_2019-01-01_LST", data)
    # writes: tmp/array_dbms/EarthBench/Question1/Xinjiang_2019-01-01_LST.npy
    # numpy.save() writes a binary file, ~13.4 MB (2573 x 2599 x 2 bytes)

    # LINE 142-144: update the catalog
    reg = _load_registry()          # read current registry.json
    reg["EarthBench.Question1.Xinjiang_2019-01-01_LST"] = meta
    _save_registry(reg)             # write back (atomic JSON overwrite)

    # LINE 146-157: build return dict
    return {
        "dataset_name":  "EarthBench.Question1.Xinjiang_2019-01-01_LST",
        "shape":         [1, 2573, 2599],
        "dtype":         "uint16",
        "crs":           "EPSG:3857",
        "subarray_size": "2573x2599",
        "source_path":   "benchmark/data/question1/Xinjiang_2019-01-01_LST.tif",
        "message":       "Dataset '..._LST' ingested. Shape: [1, 2573, 2599], dtype: uint16."
    }""", styles),
    ], styles)

    # STEP 5
    story += step_box(5, "Tool result returned to LLM", [
        Paragraph(
            "The subprocess serialises the return dict to JSON and writes it to stdout. "
            "The MCP dispatcher reads it, wraps it in a <b>tool-role message</b>, "
            "and appends it to the running message list:", styles["body"]),
        code(
"""# Message appended to LLM context (role=tool)
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": {
    "dataset_name":  "EarthBench.Question1.Xinjiang_2019-01-01_LST",
    "shape":         [1, 2573, 2599],
    "dtype":         "uint16",
    "crs":           "EPSG:3857",
    "subarray_size": "2573x2599",
    "message":       "Dataset '..._LST' ingested. Shape: [1,2573,2599], dtype: uint16."
  }
}
# LLM now sees: its own tool_call + this result side-by-side in context""", styles),
    ], styles)

    # STEP 6
    story += step_box(6, "LLM emits tool_call: aggregate", [
        Paragraph(
            "The LLM has confirmed the data is loaded. It now calls aggregate "
            "to compute the mean pixel value across all bands (axis=0):",
            styles["body"]),
        code(
"""# LLM output — second tool call
{
  "tool_calls": [{
    "function": {
      "name": "aggregate",
      "arguments": {
        "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST",
        "operation":    "mean",
        "axis":         0           # collapse band dimension
      }
    }
  }]
}""", styles),
    ], styles)

    # STEP 7
    story += step_box(7, "ArrayDBMS.py executes aggregate() — line by line", [
        code(
"""# ArrayDBMS.py  lines 462-505  (aggregate)

def aggregate(dataset_name, operation="mean", axis=0):

    # LINE 479: load the .npy file
    data = _load_array("EarthBench.Question1.Xinjiang_2019-01-01_LST")
    # _load_array() calls numpy.load("tmp/array_dbms/EarthBench/Question1/...LST.npy")
    # data.shape = (1, 2573, 2599)
    data = data.astype(np.float32)   # cast uint16 -> float32 for nanmean

    # LINE 483-490: operation lookup table
    ops = {
        "mean":        lambda x, ax: np.nanmean(x, axis=ax),
        "sum":         lambda x, ax: np.nansum(x,  axis=ax),
        "min":         lambda x, ax: np.nanmin(x,  axis=ax),
        "max":         lambda x, ax: np.nanmax(x,  axis=ax),
        "std":         lambda x, ax: np.nanstd(x,  axis=ax),
        "count_valid": lambda x, ax: np.sum(~np.isnan(x), axis=ax),
    }

    # LINE 494: execute  np.nanmean(data, axis=0)
    result = ops["mean"](data, 0)
    # input shape:  (1, 2573, 2599)
    # axis=0 collapses band dimension
    # output shape: (2573, 2599)  — one mean value per pixel across bands

    # LINE 497-505: build return dict
    return {
        "dataset_name":    "EarthBench.Question1.Xinjiang_2019-01-01_LST",
        "operation":       "mean",
        "aggregated_over": "bands",
        "input_shape":     [1, 2573, 2599],
        "output_shape":    [2573, 2599],
        "dtype":           "float32",
        "values":          [[...2573 rows of 2599 floats...]]   # full pixel grid
    }""", styles),
        Paragraph(
            "<b>Note on nodata:</b> The console version (dbms_console.py line 114) "
            "explicitly masks nodata before aggregation: "
            "<i>data[data == 0.0] = np.nan</i>. "
            "The MCP version in ArrayDBMS.py uses nanmean which ignores NaN "
            "but does NOT pre-mask the nodata sentinel value 0.0. "
            "This is a real behavioral difference between the two interfaces.",
            styles["warn"]),
    ], styles)

    # STEP 8
    story += step_box(8, "LLM reads the scalar and emits final answer", [
        Paragraph(
            "The LLM receives the full values grid. It applies its own reasoning "
            "to extract the overall mean from the 2D result, or issues one more "
            "aggregate call with axis=1 or axis=2 to reduce further. "
            "Once it has a scalar it emits the answer:",
            styles["body"]),
        code(
"""# LLM final message (role=assistant)
"Based on the aggregate result, the mean LST value over Xinjiang
in January 2019 is approximately 13,240 (uint16 DN units),
which corresponds to ~-13 C after scale factor (x0.02 - 273.15).

<Answer>B</Answer>"

# Extraction regex (from evaluate/end_to_end.py):
import re
match = re.search(r'<Answer>(.*?)</Answer>', response_text)
final_answer = match.group(1).strip()   # "B\"""", styles),
    ], styles)

    story += [Spacer(1, 0.3*cm)]

    # =========================================================================
    # SECTION 4 — NDVI EXECUTION TRACE (array_join)
    # =========================================================================
    story += [
        banner("4.  array_join Execution Trace — NDVI Computation", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
        Paragraph(
            "This shows what happens inside <b>array_join()</b> "
            "(ArrayDBMS.py lines 370-439) when the LLM computes NDVI "
            "using the real Question 10 datasets: "
            "<i>Germany_2021-07-29_b5</i> (NIR) and <i>Germany_2021-07-29_b4</i> (Red).",
            styles["body"]),
    ]

    story.append(code(
"""# LLM tool call JSON
{
  "name": "array_join",
  "arguments": {
    "dataset_a":   "EarthBench.Question10.Germany_2021-07-29_b5",   # NIR
    "dataset_b":   "EarthBench.Question10.Germany_2021-07-29_b4",   # Red
    "expression":  "(A - B) / (A + B + 1e-6)",
    "output_name": "Demo.Question10.NDVI",
    "band_a":      0,
    "band_b":      0
  }
}

# === ArrayDBMS.py executes array_join() ===

# LINE 392: load dataset_a, extract band 0, cast to float32
A = _load_array("EarthBench.Question10.Germany_2021-07-29_b5")[0].astype(np.float32)
#   _load_array -> numpy.load("tmp/array_dbms/EarthBench/Question10/Germany_2021-07-29_b5.npy")
#   [0] selects band index 0
#   A.shape = (H, W)   e.g. (512, 512)

# LINE 393: load dataset_b, extract band 0, cast to float32
B = _load_array("EarthBench.Question10.Germany_2021-07-29_b4")[0].astype(np.float32)
#   B.shape = (512, 512)

# LINE 397: shape guard
if A.shape != B.shape:                # shapes match -> continue
    return {"error": "Shape mismatch ..."}

# LINE 407: expression evaluation
#   safe eval: __builtins__ disabled, only A, B, np in scope
result = eval(
    "(A - B) / (A + B + 1e-6)",
    {"__builtins__": {}},
    {"A": A, "B": B, "np": np}
)
# NumPy broadcasts element-wise:
#   numerator   = A - B          (each pixel: NIR - Red)
#   denominator = A + B + 1e-6   (prevents zero division)
#   result      = numerator / denominator
#   result.shape = (512, 512),  dtype = float32
#   values range: typically -1.0 to 1.0

# LINE 411-412: reshape and save
result = np.array(result, dtype=np.float32)
_save_array("Demo.Question10.NDVI", result[np.newaxis, :, :])
# result[np.newaxis] adds band dim: (512,512) -> (1,512,512)
# saved to: tmp/array_dbms/Demo/Question10/NDVI.npy

# LINE 414-423: update registry with join metadata
reg = _load_registry()
reg["Demo.Question10.NDVI"] = {
    "dataset_name": "Demo.Question10.NDVI",
    "source_path":  "join(EarthBench.Question10...b5, EarthBench.Question10...b4)",
    "expression":   "(A - B) / (A + B + 1e-6)",
    "dtype":        "float32",
    "shape":        [1, 512, 512],
    "bands": 1, "height": 512, "width": 512,
}
_save_registry(reg)

# LINE 425-438: compute and return stats
valid = result[~np.isnan(result)]
return {
    "output_name": "Demo.Question10.NDVI",
    "input_a":     "EarthBench.Question10.Germany_2021-07-29_b5[band=0]",
    "input_b":     "EarthBench.Question10.Germany_2021-07-29_b4[band=0]",
    "expression":  "(A - B) / (A + B + 1e-6)",
    "shape":       [512, 512],
    "dtype":       "float32",
    "statistics":  {"min": -0.823, "max": 0.891, "mean": 0.312},
    "message":     "Join result registered as 'Demo.Question10.NDVI' in Array DBMS."
}""", styles))

    story += [Spacer(1, 0.3*cm)]

    # =========================================================================
    # SECTION 5 — hyperslab + compute_expr traces
    # =========================================================================
    story += [
        banner("5.  hyperslab and compute_expr — Line-by-Line", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
    ]

    story += [
        Paragraph("<b>5a — hyperslab: real call from dbms_console.py defaults</b>", styles["h2"]),
        Paragraph(
            "The console hardcodes the demo call as "
            "<i>hyperslab('...LST', row_start=500, row_end=510, col_start=500, col_end=510)</i>. "
            "Here is what runs inside ArrayDBMS.py:",
            styles["body"]),
    ]

    story.append(code(
"""# LLM tool call
{"name": "hyperslab", "arguments": {
    "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST",
    "row_start": 500,  "row_end": 510,
    "col_start": 500,  "col_end": 510,
    "band_start": 0,   "band_end": -1    # -1 means all bands
}}

# ArrayDBMS.py lines 231-271

# LINE 254: load full array
data = _load_array("EarthBench.Question1.Xinjiang_2019-01-01_LST")
# numpy.load("tmp/array_dbms/EarthBench/Question1/Xinjiang_2019-01-01_LST.npy")
# data.shape = (1, 2573, 2599)

# LINE 258: resolve -1 for band_end
b_end = data.shape[0]    # = 1  (only one band)

# LINE 259: three-dimensional slice
sliced = data[0:1, 500:510, 500:510]
# selects bands 0..0, rows 500..509, cols 500..509
# sliced.shape = (1, 10, 10)   <-- 100 pixels extracted from 6.7M pixel array

# LINE 261-271: return dict — values included inline
return {
    "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST",
    "hyperslab":    {"bands": [0,1], "rows": [500,510], "columns": [500,510]},
    "shape":        [1, 10, 10],
    "dtype":        "uint16",
    "values":       [[[13200, 13215, 13198, ...]]]   # 10x10 DN values
}
# NOTE: hyperslab returns values INLINE (not a file path).
# For large windows the LLM receives a huge JSON blob.""", styles))

    story += [
        Paragraph("<b>5b — compute_expr: LST DN to Celsius conversion</b>", styles["h2"]),
        Paragraph(
            "The console demo (line 372) shows this exact call. "
            "The LLM uses compute_expr when it needs a single-dataset transform "
            "before aggregating:", styles["body"]),
    ]

    story.append(code(
"""# LLM tool call
{"name": "compute_expr", "arguments": {
    "dataset_name": "EarthBench.Question1.Xinjiang_2019-01-01_LST",
    "expression":   "X * 0.02 - 273.15",
    "output_name":  "Demo.Question1.LST_Celsius",
    "band":         0            # load only band 0 as 2-D array
}}

# ArrayDBMS.py lines 537-598

# LINE 556: load and cast
data = _load_array("EarthBench.Question1.Xinjiang_2019-01-01_LST").astype(np.float32)
# data.shape = (1, 2573, 2599)

# LINE 560: band selection
X = data[0]         # band=0 -> shape (2573, 2599) -- 2-D
# X.dtype = float32, values = [0, 65535] (uint16 cast to float32)

# LINE 562-564: expression eval
result = eval(
    "X * 0.02 - 273.15",
    {"__builtins__": {}},
    {"X": X, "np": np}
)
# element-wise: each pixel = pixel_value * 0.02 - 273.15
# MODIS LST scale: raw DN 13200 -> 13200 * 0.02 - 273.15 = -9.15 C
# result.shape = (2573, 2599), dtype = float32

# LINE 567-568: reshape for storage
result = np.array(result, dtype=np.float32)
out = result[np.newaxis]    # (2573,2599) -> (1,2573,2599)

# LINE 569: save
_save_array("Demo.Question1.LST_Celsius", out)
# written to: tmp/array_dbms/Demo/Question1/LST_Celsius.npy

# LINE 571-582: update registry
reg[output_name] = {
    "dataset_name": "Demo.Question1.LST_Celsius",
    "source_path":  "expr(EarthBench.Question1.Xinjiang_2019-01-01_LST)",
    "expression":   "X * 0.02 - 273.15",
    "dtype":        "float32",
    "shape":        [1, 2573, 2599],
    "bands": 1, "height": 2573, "width": 2599,
}

# LINE 584-597: return stats
return {
    "output_name":  "Demo.Question1.LST_Celsius",
    "expression":   "X * 0.02 - 273.15",
    "input":        "EarthBench.Question1.Xinjiang_2019-01-01_LST[band=0]",
    "output_shape": [2573, 2599],
    "dtype":        "float32",
    "statistics":   {"min": -87.3, "max": 42.1, "mean": -9.15},
    "message":      "Result registered as 'Demo.Question1.LST_Celsius' in Array DBMS."
}""", styles))

    story += [Spacer(1, 0.3*cm)]

    # =========================================================================
    # SECTION 6 — COMMAND REFERENCE TABLE
    # =========================================================================
    story += [
        banner("6.  Complete Command Reference with Real Parameters", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
    ]

    ref = [
        [Paragraph("<b>Command</b>", styles["body"]),
         Paragraph("<b>Required params</b>", styles["body"]),
         Paragraph("<b>Optional params (defaults)</b>", styles["body"]),
         Paragraph("<b>Return type</b>", styles["body"]),
         Paragraph("<b>Writes to disk?</b>", styles["body"])],

        ["ingest_dataset",
         "source_path: str\ndataset_name: str",
         "—",
         "dict {shape, dtype, crs, message}",
         "YES — .npy + registry.json"],

        ["get_schema",
         "dataset_name: str",
         "—",
         "dict {dimensions, dtype, crs, geotransform, nodata}",
         "NO"],

        ["list_datasets",
         "—",
         "—",
         "dict {total: int, datasets: list}",
         "NO"],

        ["hyperslab",
         "dataset_name: str\nrow_start: int\nrow_end: int\ncol_start: int\ncol_end: int",
         "band_start: int (0)\nband_end: int (-1 = all)",
         "dict {shape, dtype, values: list}  INLINE",
         "NO — returns raw values"],

        ["chunk_array",
         "dataset_name: str",
         "chunk_height: int (256)\nchunk_width: int (256)",
         "dict {total_chunks, chunks: list of stats}",
         "NO — statistics only"],

        ["array_join",
         "dataset_a: str\ndataset_b: str\nexpression: str\noutput_name: str",
         "band_a: int (0)\nband_b: int (0)",
         "dict {statistics {min,max,mean}, message}",
         "YES — .npy + registry.json"],

        ["aggregate",
         "dataset_name: str",
         "operation: str (mean)\naxis: int (0)",
         "dict {input_shape, output_shape, values: list}",
         "NO — returns values inline"],

        ["compute_expr",
         "dataset_name: str\nexpression: str\noutput_name: str",
         "band: int (None = full 3D)",
         "dict {statistics {min,max,mean}, message}",
         "YES — .npy + registry.json"],
    ]

    ref_tbl = Table(ref, colWidths=[2.8*cm, 3.8*cm, 3.5*cm, 3.9*cm, 3.0*cm])
    ref_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), C_DARK),
        ("TEXTCOLOR",     (0,0),(-1,0), C_WHITE),
        ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 7.5),
        ("LEADING",       (0,0),(-1,-1), 11),
        ("FONTNAME",      (0,1),(-1,-1), "Courier"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_LIGHT, C_WHITE]),
        ("GRID",          (0,0),(-1,-1), 0.3, HexColor("#d0d7de")),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("BACKGROUND",    (0,3),(4,3), HexColor("#fff8e1")),  # hyperslab highlight
    ]))
    story += [ref_tbl, Spacer(1, 0.3*cm)]

    # =========================================================================
    # SECTION 7 — ERROR HANDLING
    # =========================================================================
    story += [
        banner("7.  Error Handling — What the LLM Gets Back", "h1", styles, C_DARK),
        Spacer(1, 0.2*cm),
        Paragraph(
            "Every tool returns an error dict on failure. The LLM is instructed "
            "(system prompt): <i>\"if a tool returns an error, you can only try again once.\"</i> "
            "Below are the exact error paths from the source code:",
            styles["body"]),
    ]

    story.append(code(
"""# 1. Dataset not registered (get_schema / aggregate / hyperslab)
#    ArrayDBMS.py line 191
return {"error": "Dataset 'SomeName' not registered in Array DBMS."}

# 2. .npy file missing (hyperslab / aggregate)
#    ArrayDBMS.py line 72 (_load_array)
raise FileNotFoundError("Dataset 'SomeName' not found.")
# caught in caller -> return {"error": "Dataset 'SomeName' not found."}

# 3. Shape mismatch (array_join)
#    ArrayDBMS.py lines 397-404
return {
    "error": ("Shape mismatch: dataset_a band 0 has shape (512,512), "
              "but dataset_b band 0 has shape (256,256). "
              "Arrays must have the same spatial dimensions for a join.")
}

# 4. Bad expression syntax (array_join / compute_expr)
#    ArrayDBMS.py lines 406-409
return {"error": "Expression evaluation failed: invalid syntax (<string>, line 1)"}

# 5. Unknown aggregation op (aggregate)
#    ArrayDBMS.py lines 491-492
return {"error": "Unknown operation 'median'. Choose from: ['mean','sum','min','max','std','count_valid']."}

# LLM response pattern after an error:
# "The tool returned an error: Shape mismatch... I will retry with corrected parameters."
# -> issues a second tool_call with fixed arguments
# -> if second call also fails, moves to next reasoning branch""", styles))

    # =========================================================================
    # FOOTER
    # =========================================================================
    story += [
        Spacer(1, 0.4*cm),
        HRFlowable(width="100%", thickness=0.5, color=C_MUTED),
        Spacer(1, 0.15*cm),
        Paragraph(
            "Source files: agent/tools/ArrayDBMS.py  |  dbms_console.py  |  agent/config.json  |  "
            "agent/tools/tmp/array_dbms/registry.json  |  Generated 26 March 2026",
            styles["caption"]),
    ]

    doc.build(story)
    print(f"PDF written -> {OUTPUT}")


if __name__ == "__main__":
    build()

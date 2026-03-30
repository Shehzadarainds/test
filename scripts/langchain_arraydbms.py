"""
Earth-Agent with Array (Tensor) DBMS Integration
=================================================
This script runs the Earth-Agent evaluation with the Array (Tensor) DBMS
as the primary data source. Instead of reading raw GeoTIFF files from disk,
the agent uses DBMS query operations (hyperslab, aggregate, array_join, etc.)
to retrieve and manipulate data from the Array DBMS.

Goal 3 implementation:
  "The data should be inside the DBMS, the agent must manipulate
   the data using its query language."

Usage:
    cd scripts
    py -3 langchain_arraydbms.py --model gemini2.5 --config ../agent/config_gemini2_5.json
    py -3 langchain_arraydbms.py --model deepseek  --config ../agent/config_deepseek.json
"""

import os
import sys
os.environ["GTIFF_SRS_SOURCE"] = "EPSG"

import json
import logging
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Use the current Python interpreter for spawning MCP subprocesses
PYTHON_EXE = sys.executable

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from tqdm import tqdm

# ── Change to scripts/ directory ───────────────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Parse CLI arguments ────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--model',  type=str, default='arraydbms_model',
                    help='Model name used for output folder naming')
parser.add_argument('--config', type=str, default='../agent/config_gemini2_5.json',
                    help='Path to model config JSON')
parser.add_argument('--questions', type=int, default=188,
                    help='Number of questions to evaluate (default: 188)')
parser.add_argument('--autoplan', action='store_true',
                    help='Use Autonomous Planning mode instead of Instruction Following')
parser.add_argument('--dbms-only', action='store_true',
                    help='Load ONLY ArrayDBMS tools (skip Analysis/Index/etc.) — recommended for local/slow models')
cli_args = parser.parse_args()

# ── Global vars ────────────────────────────────────────────────────────────
logger       = None
temp_dir_path = None
model_name   = cli_args.model
autoplanning = cli_args.autoplan

# ── Array DBMS storage root (must match ingest_earthbench_to_arraydbms.py) ─
ARRAY_DB_DIR = Path('../agent/tools/tmp/array_dbms').resolve()

# ── System prompt — instructs agent to use ArrayDBMS tools ────────────────
SYSTEM_PROMPT = '''
You are a geoscientist. Answer multiple-choice questions about Earth observation
data analysis using the available tools.

IMPORTANT — DATA ACCESS RULES:
You are connected to an Array (Tensor) DBMS that stores all satellite data.
You MUST retrieve data from the DBMS using its query operations:

  1. list_datasets()
       → List all datasets in the DBMS to discover available data.

  2. get_schema(dataset_name)
       → Get dimensions, dtype, CRS for a dataset before querying it.

  3. hyperslab(dataset_name, row_start, row_end, col_start, col_end)
       → Spatial window query — retrieves a sub-region of an array.
         Use this instead of reading full images.

  4. aggregate(dataset_name, operation, axis)
       → Compute mean/sum/min/max/std over a dimension.

  5. array_join(dataset_a, dataset_b, expression, output_name)
       → Join two arrays and compute an expression (e.g. NDVI).
         Example: expression="(A - B) / (A + B + 1e-6)"

  6. compute_expr(dataset_name, expression, output_name)
       → Apply a formula to a single array.

DATASET NAMING:
  Datasets follow the ChronosDB hierarchical namespace:
    EarthBench.QuestionN.<filename_without_extension>
  Example: "EarthBench.Question1.Xinjiang_2019-01-01_LST"

WORKFLOW:
  Step 1: Call list_datasets() to find datasets for the current question.
  Step 2: Call get_schema() to understand the data dimensions.
  Step 3: Use hyperslab / aggregate / array_join to retrieve/compute data.
  Step 4: Pass results to analysis tools (Index, Statistics, etc.) if needed.
  Step 5: Answer with the correct choice.

RULES:
- Always use DBMS tools first to get data. Do NOT reference raw file paths.
- If a tool returns an error, try once more with adjusted parameters.
- Your final answer format MUST be: <Answer>Your choice</Answer>
'''


# ── Map raw data path to ArrayDBMS namespace ───────────────────────────────

def data_path_to_dbms_namespace(data_path: str) -> str:
    """
    Convert 'benchmark/data/question1' -> 'EarthBench.Question1'
    This is the ArrayDBMS namespace prefix for the question's datasets.
    """
    if not data_path:
        return ""
    # Extract question number from path like 'benchmark/data/question1'
    q_dir = Path(data_path).name  # e.g. 'question1'
    q_num = q_dir.replace('question', '').capitalize()
    return f"EarthBench.Question{q_num}"


def build_dbms_query(question: dict) -> str:
    """
    Build the query string that tells the agent:
    - Which ArrayDBMS namespace to look in
    - The actual question text
    """
    data_path = question.get('data', '')
    namespace = data_path_to_dbms_namespace(data_path)

    q_text = question['auto'] if autoplanning else question['instruct']

    dbms_hint = ""
    if namespace:
        dbms_hint = (
            f"\n\n[Array DBMS] The data for this question is in namespace: "
            f"'{namespace}'\n"
            f"Use list_datasets() and filter by '{namespace}' to find "
            f"all available datasets, then query them using hyperslab / "
            f"aggregate / array_join as needed.\n"
        )

    query = q_text + dbms_hint

    if question.get('choices'):
        query += '\n' + '\n'.join([
            '{}.{}'.format(chr(ord('A') + i), choice)
            for i, choice in enumerate(question['choices'])
        ])

    return query


# ── Logging ────────────────────────────────────────────────────────────────

def init_global_params():
    global temp_dir_path, logger

    mode = 'AP' if autoplanning else 'IF'
    temp_dir_path = Path('../evaluate_langchain/{}_{}_arraydbms_{}'.format(
        model_name, mode,
        datetime.now().strftime('%y-%m-%d_%H-%M')
    )).resolve()
    temp_dir_path.mkdir(parents=True, exist_ok=True)

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({
                "question_index": record.args[0] if record.args else "unknown",
                "timestamp": self.formatTime(record, self.datefmt),
                "conversations": record.args[1] if len(record.args) > 1 else [],
                "final_answer": record.args[2] if len(record.args) > 2 else None
            }, ensure_ascii=False, indent=4)

    logger = logging.getLogger("arraydbms_logger")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        temp_dir_path / "{}_{}_arraydbms.log".format(model_name, mode)
    )
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    return temp_dir_path, logger


# ── MCP config — includes ArrayDBMS server ────────────────────────────────

def load_config_with_arraydbms(config_path: str):
    """
    Load model config and inject the ArrayDBMS MCP server.
    This ensures the agent has access to DBMS query tools.
    """
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    model_config = config['models'][0]
    base_url = model_config['client_args']['base_url']
    # Local Ollama is slow with many tools — use longer timeout
    is_local = 'localhost' in base_url or '127.0.0.1' in base_url
    timeout = 600 if is_local else 120
    llm = ChatOpenAI(
        model=model_config['model_name'],
        api_key=model_config.get('api_key', 'placeholder'),
        base_url=base_url,
        temperature=0.1,
        request_timeout=timeout,
    )

    # Build MCP servers — start with ArrayDBMS, then add existing tools
    mcp_servers = {}

    # 1. ArrayDBMS — the primary data access tool
    mcp_servers['ArrayDBMS'] = {
        "command": PYTHON_EXE,
        "args": [
            str(Path('../agent/tools/ArrayDBMS.py').resolve()),
            "--temp_dir",   str(temp_dir_path / 'out'),
            "--array_db_dir", str(ARRAY_DB_DIR),
        ],
        "transport": "stdio"
    }

    # 2. Existing Earth-Agent tools (Analysis, Index, etc.)
    # Skip if --dbms-only flag is set (recommended for local/slow models)
    if not cli_args.dbms_only:
        for server_name, server_config in config.get('mcpServers', {}).items():
            updated_args = []
            for arg in server_config['args']:
                if 'tmp/tmp/out' in arg:
                    updated_args.append(str(temp_dir_path / 'out'))
                elif arg.startswith('tools/'):
                    updated_args.append(str(Path('../agent/' + arg).resolve()))
                else:
                    updated_args.append(arg)
            mcp_servers[server_name] = {
                "command": PYTHON_EXE,
                "args":    updated_args,
                "transport": "stdio"
            }

    return llm, mcp_servers


# ── Agent creation ─────────────────────────────────────────────────────────

async def create_agent(llm, mcp_servers):
    client = MultiServerMCPClient(mcp_servers)
    tools  = await client.get_tools()

    # Show which tools are loaded — highlight ArrayDBMS tools
    dbms_tools  = [t.name for t in tools if any(
        k in t.name for k in ['dataset', 'hyperslab', 'chunk', 'array_join',
                               'aggregate', 'compute_expr', 'schema'])]
    other_tools = [t.name for t in tools if t.name not in dbms_tools]

    print(f"\nLoaded {len(tools)} tools:")
    print(f"  ArrayDBMS tools : {dbms_tools}")
    print(f"  Other tools     : {other_tools[:8]}{'...' if len(other_tools)>8 else ''}")

    agent = create_react_agent(llm, tools)
    return agent, client


# ── Question loading ───────────────────────────────────────────────────────

def load_questions(path='../benchmark/question.json'):
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)

    out = []
    for qid, qinfo in raw.items():
        AP_IDX = 0 if qinfo['evaluation'][0]['type'] == 'autonomous planning' else 1
        data = qinfo['evaluation'][AP_IDX].get('data') or \
               qinfo['evaluation'][1 - AP_IDX].get('data')
        if data is None:
            continue
        out.append({
            "question_id": qid,
            "auto":     qinfo['evaluation'][AP_IDX]['question'],
            "instruct": qinfo['evaluation'][1 - AP_IDX]['question'],
            "data":     data,
            "choices":  qinfo.get('choices'),
        })
    return out


# ── Answer extraction ──────────────────────────────────────────────────────

def extract_answer(response):
    for msg in reversed(response.get("messages", [])):
        if hasattr(msg, 'type') and msg.type == 'ai':
            content = msg.content
            if '<Answer>' in content:
                start = content.find('<Answer>') + len('<Answer>')
                end   = content.find('</Answer>')
                return content[start:end].strip() if end != -1 else content[start:].strip()
            return content
    return "No answer found"


# ── Single question handler ────────────────────────────────────────────────

async def handle_question(agent, question):
    try:
        query = SYSTEM_PROMPT + "\n\nQuestion: " + build_dbms_query(question)

        print(f"\n[{question['question_id']}] Querying Array DBMS namespace: "
              f"{data_path_to_dbms_namespace(question.get('data',''))}")

        response = await agent.ainvoke(
            {"messages": [HumanMessage(content=query)]},
            config={"recursion_limit": 50, "max_execution_time": 300}
        )

        answer = extract_answer(response)

        # Build conversation log
        conv_log = []
        for msg in response.get("messages", []):
            if not hasattr(msg, 'type'):
                continue
            if msg.type == 'human':
                conv_log.append({"role": "user", "content": msg.content})
            elif msg.type == 'ai':
                content = []
                if msg.content:
                    content.append({"type": "text", "content": msg.content})
                if hasattr(msg, 'additional_kwargs'):
                    for tc in msg.additional_kwargs.get('tool_calls', []):
                        try:
                            args = json.loads(tc['function']['arguments'])
                        except Exception:
                            args = tc['function']['arguments']
                        content.append({"name": tc['function']['name'], "input": args})
                if content:
                    conv_log.append({"role": "assistant", "content": content})
            elif msg.type == 'tool':
                conv_log.append({
                    "role": "tool",
                    "name": msg.name,
                    "content": str(msg.content)[:500]
                })

        logger.info("Chat", question['question_id'], conv_log, answer)
        print(f"  Answer: {answer}")
        return answer

    except Exception as e:
        err = f"Error: {e}"
        logger.info(question['question_id'], [], err)
        print(f"  {err}")
        return err


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    print("=" * 65)
    print("Earth-Agent + Array (Tensor) DBMS")
    print("Data access via DBMS query language (hyperslab/aggregate/join)")
    print("=" * 65)

    init_global_params()

    # Verify Array DBMS has data
    registry_file = ARRAY_DB_DIR / "registry.json"
    if not registry_file.exists():
        print("[ERROR] Array DBMS registry not found.")
        print("        Run: py -3 ingest_earthbench_to_arraydbms.py --skip-download")
        return

    registry = json.loads(registry_file.read_text(encoding='utf-8'))
    print(f"Array DBMS: {len(registry)} datasets ready")

    llm, mcp_servers = load_config_with_arraydbms(cli_args.config)
    agent, client    = await create_agent(llm, mcp_servers)

    try:
        questions = load_questions()[:cli_args.questions]
        print(f"Questions : {len(questions)}")
        print(f"Mode      : {'AutoPlan' if autoplanning else 'Instruction Following'}")
        print(f"Output    : {temp_dir_path}\n")

        results = []
        for question in tqdm(questions, desc="Processing"):
            answer = await handle_question(agent, question)
            results.append({"question_id": question['question_id'], "answer": answer})
            await asyncio.sleep(1)

        results_path = temp_dir_path / "results_summary.json"
        results_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=4),
            encoding='utf-8'
        )

        print(f"\nDone! Results: {results_path}")

    finally:
        if hasattr(client, 'close'):
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Run Earth Agent evaluation on available questions (those with downloaded data)
"""
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# Change to scripts directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import the langchain mistralai module functions
import sys
sys.path.insert(0, '.')
from langchain_mistralai import (
    init_global_params,
    init_chat_logger,
    load_langchain_config,
    create_langchain_agent,
    load_questions,
    handle_question,
    temp_dir_path
)


def find_available_questions():
    """Find which questions have downloaded data"""
    benchmark_dir = Path('../benchmark/data')
    available_questions = {}
    
    # Get all question directories
    for qdir in sorted(benchmark_dir.glob('question*')):
        if not qdir.is_dir():
            continue
        
        question_num = qdir.name.replace('question', '')
        try:
            question_num = int(question_num)
        except ValueError:
            continue
        
        # Count files in this directory
        files = list(qdir.glob('*'))
        file_count = len(files)
        
        if file_count > 0:
            available_questions[question_num] = {
                'path': qdir,
                'file_count': file_count
            }
    
    return available_questions


async def main():
    """Main evaluation function for available questions only"""
    print("=" * 80)
    print("Earth Agent - Mistral Evaluation (Available Data Only)")
    print("=" * 80)
    
    # Check available data
    available = find_available_questions()
    
    if not available:
        print("\n✗ No question data directories found!")
        print("Please ensure the dataset is downloaded to benchmark/data/")
        return
    
    print(f"\n✓ Found {len(available)} questions with downloaded data:")
    for qnum in sorted(available.keys()):
        files = available[qnum]['file_count']
        print(f"  - question{qnum}: {files} files")
    
    # Initialize global parameters
    print("\nInitializing LangChain-based Earth Science Agent...")
    init_global_params()
    
    # Initialize chat logger
    chat_log_path = init_chat_logger()
    print(f"Chat log will be saved to: {chat_log_path}")
    
    # Load configuration and create agent
    print("\nLoading model configuration...")
    llm, mcp_servers = load_langchain_config()
    
    print("Creating agent with MCP tools...")
    agent, client = await create_langchain_agent(llm, mcp_servers)
    
    try:
        # Load all questions
        print("\nLoading benchmark questions...")
        all_questions = load_questions()
        
        # Filter to only available questions
        available_question_nums = set(available.keys())
        questions_to_process = [
            q for q in all_questions 
            if int(q['question_id']) in available_question_nums
        ]
        
        print(f"Processing {len(questions_to_process)} available questions out of {len(all_questions)} total")
        
        # Process questions
        results = []
        failed = []
        
        for question in tqdm(questions_to_process, desc="Processing questions"):
            try:
                answer = await handle_question(agent, question, chat_log_path)
                results.append({
                    "question_id": question['question_id'],
                    "answer": answer,
                    "status": "success"
                })
            except Exception as e:
                print(f"\n✗ Error on question {question['question_id']}: {e}")
                failed.append({
                    "question_id": question['question_id'],
                    "error": str(e)
                })
                results.append({
                    "question_id": question['question_id'],
                    "status": "failed",
                    "error": str(e)
                })
            
            # Optional: Add delay between questions to avoid rate limiting
            await asyncio.sleep(1)
        
        # Save results summary
        from langchain_mistralai import temp_dir_path
        results_path = Path(temp_dir_path) / "results_summary.json"
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        
        # Print summary
        print("\n" + "=" * 80)
        print("EVALUATION COMPLETED")
        print("=" * 80)
        print(f"✓ Successfully processed: {len([r for r in results if r['status'] == 'success'])} questions")
        if failed:
            print(f"✗ Failed: {len(failed)} questions")
        print(f"\nResults saved to: {results_path}")
        print(f"Chat history saved to: {chat_log_path}")
        print(f"Detailed logs available at: {temp_dir_path}")
        
    except Exception as e:
        print(f"Error in evaluation: {e}")
        raise
    
    finally:
        # Clean up
        if hasattr(client, 'close'):
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())

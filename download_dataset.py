#!/usr/bin/env python3
"""
Download Earth-Bench dataset from Hugging Face
"""
import os
from pathlib import Path
from huggingface_hub import snapshot_download

def main():
    """Download the Earth-Bench dataset"""
    
    # Set up paths
    project_root = Path(__file__).parent
    data_dir = project_root / "benchmark" / "data"
    
    print("=" * 80)
    print("Earth-Bench Dataset Download")
    print("=" * 80)
    print(f"\nDownloading to: {data_dir}")
    print(f"Repository: Sssunset/Earth-Bench")
    print("\nThis may take a while depending on your internet speed...")
    print("The dataset contains satellite imagery for 188 benchmark questions.\n")
    
    try:
        # Create parent directory if it doesn't exist
        data_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Download the dataset with resume capability
        print("Starting download...")
        local_dir = snapshot_download(
            repo_id="Sssunset/Earth-Bench",
            repo_type="dataset",
            local_dir=str(data_dir),
            token=None,  # Set to your token if you have private repo access
            resume_download=True  # Resume if interrupted
        )
        
        print("\n" + "=" * 80)
        print("✓ Download completed successfully!")
        print("=" * 80)
        print(f"Dataset location: {local_dir}")
        
        # Verify dataset structure
        if data_dir.exists():
            question_dirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith('question')]
            print(f"Found {len(question_dirs)} question directories")
            
            # Show sample of first few directories
            for qdir in sorted(question_dirs)[:5]:
                files = list(qdir.glob('*.tif')) + list(qdir.glob('*.TIF'))
                print(f"  - {qdir.name}: {len(files)} files")
            
            if len(question_dirs) > 5:
                print(f"  ... and {len(question_dirs) - 5} more")
        
        print("\n✓ Dataset is ready to use!")
        print("You can now run the evaluation script:")
        print("  cd scripts")
        print("  python langchain_mistralai.py")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"✗ Download error: {e}")
        print("=" * 80)
        print("\nPartially downloaded files are preserved.")
        print("You can retry the download - it will resume from where it left off.\n")
        print("To retry, simply run:")
        print("  python download_dataset.py\n")
        print("Or download manually from:")
        print("  https://huggingface.co/datasets/Sssunset/Earth-Bench")

if __name__ == "__main__":
    main()


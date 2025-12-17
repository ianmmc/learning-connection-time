#!/usr/bin/env python3
"""
Make all Python scripts executable

Run this after cloning the repository to set correct permissions.
"""

from pathlib import Path
import os
import stat

def make_executable(file_path):
    """Make a file executable"""
    current = file_path.stat().st_mode
    file_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"✓ {file_path.relative_to(Path.cwd())}")

def main():
    root = Path(__file__).parent.parent
    
    # Find all Python scripts
    scripts = []
    
    for directory in ['infrastructure', 'pipelines']:
        dir_path = root / directory
        if dir_path.exists():
            scripts.extend(dir_path.rglob("*.py"))
    
    print(f"Making {len(scripts)} scripts executable...")
    
    for script in scripts:
        try:
            make_executable(script)
        except Exception as e:
            print(f"✗ Failed: {script}: {e}")
    
    print(f"\n✅ Complete!")

if __name__ == "__main__":
    main()

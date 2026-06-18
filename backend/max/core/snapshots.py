import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path("C:/Users/drash/.gemini/antigravity/snapshots")

IGNORE_DIRS = {".git", ".venv", "__pycache__", ".snapshots", ".gemini", ".idx", "snapshots"}

def get_workspace_root() -> Path:
    # This file is in backend/max/core/snapshots.py
    # Parent of backend is the workspace root
    return Path(__file__).resolve().parent.parent.parent.parent

def take_snapshot(thread_id: str, checkpoint_id: str):
    if not checkpoint_id:
        return
    workspace = get_workspace_root()
    target_dir = SNAPSHOT_DIR / thread_id / checkpoint_id
    if target_dir.exists():
        # Snapshot already exists
        return
    
    logger.info(f"[Snapshots] Taking snapshot for thread {thread_id}, checkpoint {checkpoint_id}")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    for root, dirs, files in os.walk(workspace):
        # Filter out ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        
        for file in files:
            src_file = Path(root) / file
            # Ignore database files and temporary SQLite files
            if src_file.suffix in {".db", ".db-journal", ".db-wal", ".db-shm"}:
                continue
            
            # Ignore very large files
            try:
                if src_file.stat().st_size > 10 * 1024 * 1024: # 10MB
                    continue
            except Exception:
                continue
                
            rel_path = src_file.relative_to(workspace)
            dest_file = target_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src_file, dest_file)
            except Exception as e:
                logger.warning(f"[Snapshots] Failed to copy {src_file}: {e}")

def restore_snapshot(thread_id: str, checkpoint_id: str):
    if not checkpoint_id:
        return
    workspace = get_workspace_root()
    src_dir = SNAPSHOT_DIR / thread_id / checkpoint_id
    if not src_dir.exists():
        logger.warning(f"[Snapshots] No snapshot found for checkpoint {checkpoint_id}")
        return
        
    logger.info(f"[Snapshots] Restoring snapshot for thread {thread_id}, checkpoint {checkpoint_id}")
    
    # 1. Delete files in workspace that are NOT in the snapshot
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for file in files:
            dest_file = Path(root) / file
            if dest_file.suffix in {".db", ".db-journal", ".db-wal", ".db-shm"}:
                continue
            rel_path = dest_file.relative_to(workspace)
            src_file = src_dir / rel_path
            
            if not src_file.exists():
                try:
                    dest_file.unlink()
                except Exception as e:
                    logger.warning(f"[Snapshots] Failed to delete {dest_file}: {e}")
                    
    # 2. Copy files from snapshot to workspace
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            src_file = Path(root) / file
            rel_path = src_file.relative_to(src_dir)
            dest_file = workspace / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src_file, dest_file)
            except Exception as e:
                logger.warning(f"[Snapshots] Failed to restore {dest_file}: {e}")

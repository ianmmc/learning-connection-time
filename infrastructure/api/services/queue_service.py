"""
Acquisition Queue Service

File-based queue for serial processing of district acquisitions.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

QUEUE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "acquisition_queue"


class AcquisitionQueue:
    """Manages acquisition queue with file-based persistence."""

    def __init__(self):
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        self.queue_file = QUEUE_DIR / "queue.json"
        self.current_file = QUEUE_DIR / "current.json"
        self.history_dir = QUEUE_DIR / "history"
        self.history_dir.mkdir(exist_ok=True)

    def add(self, district: Dict) -> int:
        """Add district to queue, return position."""
        queue = self._read_queue()
        queue["pending"].append(district)
        self._write_queue(queue)
        return len(queue["pending"])

    def add_batch(self, districts: List[Dict]) -> int:
        """Add multiple districts to queue, return new queue length."""
        queue = self._read_queue()
        queue["pending"].extend(districts)
        self._write_queue(queue)
        return len(queue["pending"])

    def get_next(self) -> Optional[Dict]:
        """Get and remove next district from queue."""
        queue = self._read_queue()
        if not queue["pending"]:
            return None
        district = queue["pending"].pop(0)
        self._write_queue(queue)
        return district

    def peek_next(self) -> Optional[Dict]:
        """Peek at next district without removing it."""
        queue = self._read_queue()
        if not queue["pending"]:
            return None
        return queue["pending"][0]

    def set_current(self, district: Dict, pid: int = None):
        """Mark district as currently processing."""
        data = {
            **district,
            "pid": pid or os.getpid(),
            "started_at": datetime.utcnow().isoformat(),
            "step": "starting",
        }
        with open(self.current_file, "w") as f:
            json.dump(data, f, indent=2)

    def update_current_step(self, step: str):
        """Update the current step of running acquisition."""
        if not self.current_file.exists():
            return
        with open(self.current_file) as f:
            data = json.load(f)
        data["step"] = step
        data["step_started_at"] = datetime.utcnow().isoformat()
        with open(self.current_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_current(self) -> Optional[Dict]:
        """Get currently running acquisition."""
        if not self.current_file.exists():
            return None
        with open(self.current_file) as f:
            return json.load(f)

    def clear_current(self):
        """Clear current processing marker."""
        self.current_file.unlink(missing_ok=True)

    def move_to_history(self, district_id: str, status: str, error: str = None):
        """Move completed acquisition to history."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        history_file = self.history_dir / f"{timestamp}_{district_id}.json"

        current = self.get_current()
        if current:
            current["completed_at"] = datetime.utcnow().isoformat()
            current["final_status"] = status
            if error:
                current["error"] = error
            with open(history_file, "w") as f:
                json.dump(current, f, indent=2)

    def get_status(self) -> Dict:
        """Get full queue status."""
        queue = self._read_queue()
        current = self.get_current()
        return {
            "pending": queue["pending"],
            "pending_count": len(queue["pending"]),
            "current": current,
            "updated_at": queue.get("updated_at"),
        }

    def remove(self, district_id: str) -> bool:
        """Remove district from pending queue."""
        queue = self._read_queue()
        original_len = len(queue["pending"])
        queue["pending"] = [
            d for d in queue["pending"]
            if d.get("district_id") != district_id
        ]
        if len(queue["pending"]) < original_len:
            self._write_queue(queue)
            return True
        return False

    def clear_all(self):
        """Clear all pending items from queue."""
        queue = {"pending": [], "updated_at": datetime.utcnow().isoformat()}
        self._write_queue(queue)

    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get recent acquisition history."""
        history_files = sorted(self.history_dir.glob("*.json"), reverse=True)
        history = []
        for f in history_files[:limit]:
            with open(f) as fp:
                history.append(json.load(fp))
        return history

    def _read_queue(self) -> Dict:
        """Read queue from file."""
        if self.queue_file.exists():
            with open(self.queue_file) as f:
                return json.load(f)
        return {"pending": [], "updated_at": None}

    def _write_queue(self, queue: Dict):
        """Write queue to file."""
        queue["updated_at"] = datetime.utcnow().isoformat()
        with open(self.queue_file, "w") as f:
            json.dump(queue, f, indent=2)


# Singleton instance
acquisition_queue = AcquisitionQueue()

"""
ollama_launcher.py - Utility to ensure Ollama is running at low priority

PURPOSE:
    Checks if Ollama server is running, and starts it via the low-priority
    wrapper script if not. This ensures all pipeline components (scoring,
    triage, extraction) use a low-priority Ollama instance.

USAGE:
    from infrastructure.api.services.ollama_launcher import ensure_ollama_running

    # Call before any Ollama operation
    if not ensure_ollama_running():
        raise RuntimeError("Could not start Ollama")

WRAPPER SCRIPT:
    ~/.local/bin/ollama-serve-lowpri
    - Starts Ollama at nice +10 (configurable in script)
    - Created by Phase 9 implementation
"""

import logging
import os
import subprocess
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Ollama API endpoint
OLLAMA_API_URL = "http://localhost:11434"
OLLAMA_HEALTH_ENDPOINT = f"{OLLAMA_API_URL}/api/tags"

# Wrapper script location
WRAPPER_SCRIPT = Path.home() / ".local" / "bin" / "ollama-serve-lowpri"

# Startup configuration
MAX_STARTUP_WAIT = 30  # seconds to wait for Ollama to start
STARTUP_CHECK_INTERVAL = 1  # seconds between health checks


def is_ollama_running() -> bool:
    """Check if Ollama server is responding."""
    try:
        response = requests.get(OLLAMA_HEALTH_ENDPOINT, timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def start_ollama_lowpri() -> bool:
    """
    Start Ollama using the low-priority wrapper script.

    Returns:
        True if Ollama started successfully, False otherwise
    """
    if not WRAPPER_SCRIPT.exists():
        logger.error(f"Ollama wrapper script not found: {WRAPPER_SCRIPT}")
        logger.error("Create it with: claude code or manually")
        return False

    logger.info(f"Starting Ollama via wrapper: {WRAPPER_SCRIPT}")

    try:
        # Start Ollama in background, detached from this process
        # Use nohup to ensure it survives if parent terminates
        subprocess.Popen(
            ["nohup", str(WRAPPER_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process group
        )

        # Wait for Ollama to become responsive
        logger.info(f"Waiting up to {MAX_STARTUP_WAIT}s for Ollama to start...")

        for i in range(MAX_STARTUP_WAIT):
            time.sleep(STARTUP_CHECK_INTERVAL)
            if is_ollama_running():
                logger.info(f"Ollama started successfully (took {i + 1}s)")
                return True

        logger.error(f"Ollama did not start within {MAX_STARTUP_WAIT}s")
        return False

    except Exception as e:
        logger.error(f"Failed to start Ollama: {e}")
        return False


def ensure_ollama_running() -> bool:
    """
    Ensure Ollama is running, starting it if necessary.

    This is the main entry point - call this before any Ollama operation.

    Returns:
        True if Ollama is running (was already running or started successfully)
        False if Ollama could not be started
    """
    if is_ollama_running():
        logger.debug("Ollama is already running")
        return True

    logger.info("Ollama is not running, attempting to start...")
    return start_ollama_lowpri()


def get_ollama_nice_value() -> int | None:
    """
    Get the current nice value of the Ollama process.

    Returns:
        Nice value (0-19) or None if Ollama is not running
    """
    try:
        # Find Ollama PID
        result = subprocess.run(
            ["pgrep", "-f", "ollama serve"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return None

        pid = result.stdout.strip().split()[0]

        # Get nice value
        result = subprocess.run(
            ["ps", "-o", "ni=", "-p", pid],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return int(result.stdout.strip())

    except Exception:
        pass

    return None

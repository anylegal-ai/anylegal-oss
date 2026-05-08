"""Memory monitoring + cleanup helpers for long-lived backend workers."""

import gc
import logging
import psutil
import os
from typing import Dict

logger = logging.getLogger(__name__)

def get_memory_usage() -> Dict[str, float]:
    """Get current memory usage statistics."""
    try:
        process = psutil.Process()
        memory_info = process.memory_info()

        return {
            "rss_mb": memory_info.rss / 1024 / 1024,                     
            "vms_mb": memory_info.vms / 1024 / 1024,                       
            "percent": process.memory_percent(),
            "available_mb": psutil.virtual_memory().available / 1024 / 1024
        }
    except Exception as e:
        logger.error(f"Failed to get memory usage: {e}")
        return {}

def log_memory_usage(context: str = ""):
    """Log current memory usage with context."""
    try:
        stats = get_memory_usage()
        if stats:
            logger.info(f"🧠 MEMORY {context}: RSS={stats['rss_mb']:.1f}MB, "
                       f"VMS={stats['vms_mb']:.1f}MB, "
                       f"Usage={stats['percent']:.1f}%, "
                       f"Available={stats['available_mb']:.1f}MB")
    except Exception as e:
        logger.error(f"Failed to log memory usage: {e}")

def force_garbage_collection():
    """Force garbage collection and log results."""
    try:

        before_objects = len(gc.get_objects())
        before_memory = get_memory_usage()

        collected = gc.collect()

        after_objects = len(gc.get_objects())
        after_memory = get_memory_usage()

        objects_freed = before_objects - after_objects
        memory_freed = before_memory.get('rss_mb', 0) - after_memory.get('rss_mb', 0)

        if logger:
            logger.info(f"🧹 GARBAGE COLLECTION: Freed {objects_freed} objects, "
                       f"{memory_freed:.1f}MB memory, "
                       f"collected {collected} cycles")

        return {
            "objects_freed": objects_freed,
            "memory_freed_mb": memory_freed,
            "cycles_collected": collected
        }

    except Exception as e:
        logger.error(f"Garbage collection failed: {e}")
        return {}

def check_memory_pressure() -> bool:
    """Check if system is under memory pressure."""
    try:
        stats = get_memory_usage()

        return (
            stats.get('percent', 0) > 80 or 
            stats.get('available_mb', 1000) < 500
        )
    except Exception:
        return False

def optimize_memory_if_needed(context: str = ""):
    """Perform memory optimization if under pressure."""
    try:
        if check_memory_pressure():
            if logger:
                logger.warning(f"🚨 MEMORY PRESSURE detected during {context}")

            cleanup_stats = force_garbage_collection()

            if cleanup_stats:
                logger.info(f"🔧 MEMORY OPTIMIZATION completed: "
                           f"freed {cleanup_stats['memory_freed_mb']:.1f}MB")

            return True
        return False
    except Exception as e:
        logger.error(f"Memory optimization failed: {e}")
        return False


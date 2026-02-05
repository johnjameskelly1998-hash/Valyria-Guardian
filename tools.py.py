"""
Valyria Tool System - Phase 6 + Image Generation
Gives Valyria ability to read/write files, execute commands, and generate images
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# Import image generation
try:
    from .image_generator import generate_image
    IMAGE_GEN_AVAILABLE = True
except ImportError:
    IMAGE_GEN_AVAILABLE = False
    logging.warning("Image generation not available - install replicate: pip install replicate --break-system-packages")

logger = logging.getLogger(__name__)

# Safety boundaries
VALYRIA_ROOT = Path(__file__).parent.parent.absolute()  # Desktop/Valyria/
ALLOWED_DIRECTORIES = [
    VALYRIA_ROOT / "valyria_core",
    VALYRIA_ROOT / "data",
    VALYRIA_ROOT,  # Root folder only for reading
]

FORBIDDEN_EXTENSIONS = [
    ".exe", ".dll", ".so", ".dylib",  # Executables
    ".bat", ".sh", ".ps1",  # Scripts (except python)
]

FORBIDDEN_COMMANDS = [
    "rm ", "del ", "format", "shutdown", "reboot",
    "dd ", "mkfs", ">", ">>",  # Destructive or redirect
]


class ToolError(Exception):
    """Raised when a tool operation fails or is not allowed."""
    pass


def is_path_allowed(path: Path, write: bool = False) -> bool:
    """
    Check if a path is within allowed boundaries.
    
    Args:
        path: Path to check
        write: If True, check write permissions; if False, check read permissions
    
    Returns:
        True if path is allowed, False otherwise
    """
    try:
        path = path.resolve()
        
        # Check if path is within Valyria root
        if not str(path).startswith(str(VALYRIA_ROOT)):
            logger.warning(f"Path outside Valyria root: {path}")
            return False
        
        # For writes, must be in allowed directories
        if write:
            for allowed_dir in ALLOWED_DIRECTORIES:
                if str(path).startswith(str(allowed_dir.resolve())):
                    # Check file extension
                    if path.suffix.lower() in FORBIDDEN_EXTENSIONS:
                        logger.warning(f"Forbidden extension: {path.suffix}")
                        return False
                    return True
            logger.warning(f"Write not allowed in: {path}")
            return False
        
        # Reads allowed anywhere in Valyria root
        return True
        
    except Exception as e:
        logger.error(f"Error checking path: {e}")
        return False


# ============================================================================
# TOOL FUNCTIONS
# ============================================================================

def read_file(path: str) -> Dict[str, Any]:
    """
    Read contents of a file.
    
    Args:
        path: Relative or absolute path to file
    
    Returns:
        Dict with 'success', 'content', and 'error' fields
    """
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = VALYRIA_ROOT / file_path
        
        if not is_path_allowed(file_path, write=False):
            raise ToolError(f"Access denied: {path}")
        
        if not file_path.exists():
            raise ToolError(f"File not found: {path}")
        
        if not file_path.is_file():
            raise ToolError(f"Not a file: {path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"✅ Read file: {file_path} ({len(content)} chars)")
        
        return {
            "success": True,
            "path": str(file_path),
            "content": content,
            "size": len(content),
            "error": None
        }
        
    except Exception as e:
        logger.error(f"❌ Read file failed: {e}")
        return {
            "success": False,
            "path": path,
            "content": None,
            "error": str(e)
        }


def write_file(path: str, content: str, mode: str = "w") -> Dict[str, Any]:
    """
    Write content to a file.
    
    Args:
        path: Relative or absolute path to file
        content: Content to write
        mode: Write mode ('w' for overwrite, 'a' for append)
    
    Returns:
        Dict with 'success', 'path', and 'error' fields
    """
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = VALYRIA_ROOT / file_path
        
        if not is_path_allowed(file_path, write=True):
            raise ToolError(f"Write access denied: {path}")
        
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(file_path, mode, encoding='utf-8') as f:
            f.write(content)
        
        action = "Appended to" if mode == "a" else "Wrote"
        logger.info(f"✅ {action} file: {file_path} ({len(content)} chars)")
        
        return {
            "success": True,
            "path": str(file_path),
            "size": len(content),
            "mode": mode,
            "error": None
        }
        
    except Exception as e:
        logger.error(f"❌ Write file failed: {e}")
        return {
            "success": False,
            "path": path,
            "error": str(e)
        }


def list_files(directory: str = ".", pattern: str = "*") -> Dict[str, Any]:
    """
    List files in a directory.
    
    Args:
        directory: Directory path (relative or absolute)
        pattern: Glob pattern (e.g., "*.py", "data/*.json")
    
    Returns:
        Dict with 'success', 'files', and 'error' fields
    """
    try:
        dir_path = Path(directory)
        if not dir_path.is_absolute():
            dir_path = VALYRIA_ROOT / dir_path
        
        if not is_path_allowed(dir_path, write=False):
            raise ToolError(f"Access denied: {directory}")
        
        if not dir_path.exists():
            raise ToolError(f"Directory not found: {directory}")
        
        if not dir_path.is_dir():
            raise ToolError(f"Not a directory: {directory}")
        
        # List files matching pattern
        files = []
        for item in dir_path.glob(pattern):
            if item.is_file():
                files.append({
                    "name": item.name,
                    "path": str(item.relative_to(VALYRIA_ROOT)),
                    "size": item.stat().st_size,
                    "extension": item.suffix
                })
        
        logger.info(f"✅ Listed {len(files)} files in: {dir_path}")
        
        return {
            "success": True,
            "directory": str(dir_path),
            "pattern": pattern,
            "files": files,
            "count": len(files),
            "error": None
        }
        
    except Exception as e:
        logger.error(f"❌ List files failed: {e}")
        return {
            "success": False,
            "directory": directory,
            "files": [],
            "error": str(e)
        }


def run_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Execute a shell command (with restrictions).
    
    Args:
        command: Command to execute
        timeout: Timeout in seconds
    
    Returns:
        Dict with 'success', 'output', 'error', and 'return_code' fields
    """
    try:
        # Safety check - block dangerous commands
        command_lower = command.lower()
        for forbidden in FORBIDDEN_COMMANDS:
            if forbidden in command_lower:
                raise ToolError(f"Forbidden command: {forbidden}")
        
        # Only allow safe commands
        safe_prefixes = ["python ", "py ", "pip ", "pytest ", "ls", "dir", "cat", "type"]
        if not any(command.startswith(prefix) for prefix in safe_prefixes):
            raise ToolError(f"Command not in whitelist. Allowed: {safe_prefixes}")
        
        # Execute command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(VALYRIA_ROOT)
        )
        
        logger.info(f"✅ Executed command: {command} (exit code: {result.returncode})")
        
        return {
            "success": result.returncode == 0,
            "command": command,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
            "return_code": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        logger.error(f"❌ Command timeout: {command}")
        return {
            "success": False,
            "command": command,
            "output": None,
            "error": f"Command timed out after {timeout}s",
            "return_code": -1
        }
    except Exception as e:
        logger.error(f"❌ Command failed: {e}")
        return {
            "success": False,
            "command": command,
            "output": None,
            "error": str(e),
            "return_code": -1
        }


def delete_file(path: str) -> Dict[str, Any]:
    """
    Delete a file (requires confirmation).
    
    Args:
        path: Path to file to delete
    
    Returns:
        Dict with 'success' and 'error' fields
    """
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = VALYRIA_ROOT / file_path
        
        if not is_path_allowed(file_path, write=True):
            raise ToolError(f"Delete access denied: {path}")
        
        if not file_path.exists():
            raise ToolError(f"File not found: {path}")
        
        # Delete file
        file_path.unlink()
        
        logger.warning(f"🗑️ Deleted file: {file_path}")
        
        return {
            "success": True,
            "path": str(file_path),
            "error": None
        }
        
    except Exception as e:
        logger.error(f"❌ Delete failed: {e}")
        return {
            "success": False,
            "path": path,
            "error": str(e)
        }


# ============================================================================
# TOOL REGISTRY
# ============================================================================

AVAILABLE_TOOLS = {
    "read_file": {
        "function": read_file,
        "description": "Read contents of a file",
        "parameters": {
            "path": "Path to file (relative to Valyria root)"
        }
    },
    "write_file": {
        "function": write_file,
        "description": "Write or append content to a file",
        "parameters": {
            "path": "Path to file",
            "content": "Content to write",
            "mode": "Write mode: 'w' (overwrite) or 'a' (append)"
        }
    },
    "list_files": {
        "function": list_files,
        "description": "List files in a directory",
        "parameters": {
            "directory": "Directory path (default: current)",
            "pattern": "File pattern (default: '*')"
        }
    },
    "run_command": {
        "function": run_command,
        "description": "Execute a safe shell command",
        "parameters": {
            "command": "Command to execute",
            "timeout": "Timeout in seconds (default: 30)"
        }
    },
    "delete_file": {
        "function": delete_file,
        "description": "Delete a file (use with caution)",
        "parameters": {
            "path": "Path to file to delete"
        }
    }
}

# Add image generation if available
if IMAGE_GEN_AVAILABLE:
    AVAILABLE_TOOLS["generate_image"] = {
        "function": generate_image,
        "description": "Generate artistic images using Stable Diffusion AI",
        "parameters": {
            "prompt": "Detailed description of image to generate",
            "negative_prompt": "What to avoid in the image (optional)",
            "width": "Image width in pixels (default: 1024)",
            "height": "Image height in pixels (default: 1024)",
            "style": "Style preset: artistic, photorealistic, minimalist, fantasy, literary (default: artistic)"
        }
    }
    logger.info("✅ Image generation tool loaded")
else:
    logger.warning("⚠️ Image generation tool NOT loaded - install replicate")


def execute_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Execute a tool by name with given parameters.
    
    Args:
        tool_name: Name of tool to execute
        **kwargs: Tool parameters
    
    Returns:
        Tool execution result
    """
    if tool_name not in AVAILABLE_TOOLS:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}. Available: {list(AVAILABLE_TOOLS.keys())}"
        }
    
    tool = AVAILABLE_TOOLS[tool_name]
    try:
        result = tool["function"](**kwargs)
        return result
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return {
            "success": False,
            "error": f"Tool execution failed: {str(e)}"
        }

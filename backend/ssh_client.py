"""
SSH Client — Remote worker management for local GPU execution.

Usage:
    from backend.ssh_client import SSHWorkerClient
    
    with SSHWorkerClient(host="100.122.63.105", port=22, user="ise") as client:
        client.sync_scripts()
        result = client.execute_job("remote_train.py", {...})

Environment:
    Uses SSH key-based authentication. User must have SSH key set up:
    ssh-copy-id -i ~/.ssh/id_ed25519.pub user@host
"""

import json
import os
import stat
import hashlib
from pathlib import Path
from typing import Optional

import paramiko


class SSHWorkerClient:
    """SSH client for remote GPU worker management.
    
    Handles:
    - Script synchronization (local -> remote)
    - Environment variable sync
    - Job execution with JSON I/O
    - Connection pooling with keepalive
    """
    
    # Remote paths on the GPU machine
    REMOTE_TYTO_HOME = ".tyto"
    REMOTE_SCRIPTS_DIR = ".tyto/scripts"
    REMOTE_ENV_FILE = ".tyto/.env"
    REMOTE_VENV_PYTHON = ".tyto/venv/bin/python"
    
    # Local scripts directory (relative to project root)
    LOCAL_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts" / "remote_workers"
    
    # Local core modules directory (shared pure-logic utilities)
    LOCAL_CORE_DIR = Path(__file__).parent / "core"
    
    # Remote paths for core modules
    REMOTE_CORE_DIR = ".tyto/backend/core"
    
    def __init__(
        self,
        host: str,
        port: int = 22,
        user: str = "ise",
        key_path: Optional[str] = None,
        connect_timeout: int = 10,
        keepalive_interval: int = 30,
    ):
        """Initialize SSH connection parameters.
        
        Args:
            host: IP or hostname of remote machine
            port: SSH port (default 22)
            user: SSH username
            key_path: Path to private key (default: use SSH agent / default keys)
            connect_timeout: Connection timeout in seconds
            keepalive_interval: Send keepalive every N seconds
        """
        self.host = host
        self.port = port
        self.user = user
        self.key_path = key_path
        self.connect_timeout = connect_timeout
        self.keepalive_interval = keepalive_interval
        
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
    
    def __enter__(self):
        """Connect and return self for context manager."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close connection."""
        self.close()
    
    def connect(self):
        """Establish SSH connection with key-based auth."""
        if self._client is not None:
            return  # Already connected
        
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Find available SSH keys
        key_files = self._find_ssh_keys()
        
        # Prepare connection kwargs
        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.user,
            "timeout": self.connect_timeout,
            "allow_agent": True,
            "look_for_keys": False,  # We'll provide keys explicitly
        }
        
        # Use explicit key_path if provided, otherwise use discovered keys
        if self.key_path:
            connect_kwargs["key_filename"] = os.path.expanduser(self.key_path)
        elif key_files:
            connect_kwargs["key_filename"] = key_files
        
        try:
            self._client.connect(**connect_kwargs)
        except paramiko.ssh_exception.SSHException as e:
            self._client = None
            if "No authentication methods available" in str(e) or not key_files:
                raise paramiko.ssh_exception.SSHException(
                    f"SSH authentication failed for {self.user}@{self.host}.\n"
                    f"No valid SSH keys found. Please set up SSH key authentication:\n"
                    f"  1. Generate a key: ssh-keygen -t ed25519\n"
                    f"  2. Copy to remote: ssh-copy-id -i ~/.ssh/id_ed25519.pub {self.user}@{self.host}\n"
                    f"  3. Test with: ssh {self.user}@{self.host} 'echo ok'\n"
                    f"\nDiscovered keys: {key_files or 'None'}"
                ) from e
            raise
        
        # Set keepalive
        transport = self._client.get_transport()
        if transport:
            transport.set_keepalive(self.keepalive_interval)
        
        print(f"[SSH] Connected to {self.user}@{self.host}:{self.port}")
    
    def _find_ssh_keys(self) -> list[str]:
        """Find available SSH private keys in ~/.ssh/."""
        ssh_dir = Path.home() / ".ssh"
        if not ssh_dir.exists():
            return []
        
        keys = []
        # Standard key names first
        standard_names = ["id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"]
        for name in standard_names:
            key_path = ssh_dir / name
            if key_path.exists() and not key_path.name.endswith(".pub"):
                keys.append(str(key_path))
        
        # Look for any other private keys (files without .pub extension that aren't known non-keys)
        skip_files = {"known_hosts", "known_hosts.old", "config", "authorized_keys", ".DS_Store"}
        for file in ssh_dir.iterdir():
            if file.is_file() and not file.name.endswith(".pub") and file.name not in skip_files:
                if str(file) not in keys:
                    # Check if it looks like a private key
                    try:
                        content = file.read_text(errors="ignore")[:50]
                        if "PRIVATE KEY" in content or "OPENSSH PRIVATE KEY" in content:
                            keys.append(str(file))
                    except Exception:
                        pass
        
        return keys
    
    def close(self):
        """Close SSH connection."""
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._client:
            self._client.close()
            self._client = None
            print(f"[SSH] Disconnected from {self.host}")
    
    @property
    def sftp(self) -> paramiko.SFTPClient:
        """Get or create SFTP client."""
        if self._sftp is None:
            if self._client is None:
                self.connect()
            self._sftp = self._client.open_sftp()
        return self._sftp
    
    def _exec(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """Execute a command and return (exit_code, stdout, stderr).
        
        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (exit_code, stdout_text, stderr_text)
        """
        if self._client is None:
            self.connect()
        
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        
        return exit_code, stdout.read().decode(), stderr.read().decode()
    
    def _ensure_remote_dir(self, remote_path: str):
        """Ensure a remote directory exists."""
        # Use mkdir -p via shell for simplicity
        self._exec(f"mkdir -p ~/{remote_path}")
    
    def _get_file_hash(self, content: bytes) -> str:
        """Get MD5 hash of file content for change detection."""
        return hashlib.md5(content).hexdigest()
    
    def _get_remote_file_hash(self, remote_path: str) -> Optional[str]:
        """Get MD5 hash of remote file, or None if doesn't exist."""
        exit_code, stdout, _ = self._exec(f"md5sum ~/{remote_path} 2>/dev/null | cut -d' ' -f1")
        if exit_code == 0 and stdout.strip():
            return stdout.strip()
        return None
    
    def sync_core_modules(self, force: bool = False) -> dict:
        """Sync backend/core/ modules to remote ~/.tyto/backend/core/.
        
        These are shared pure-logic utilities used by remote workers.
        
        Args:
            force: If True, upload all files regardless of hash
            
        Returns:
            {"uploaded": [...], "skipped": [...], "errors": [...]}
        """
        result = {"uploaded": [], "skipped": [], "errors": []}
        
        # Ensure remote directory structure exists
        self._ensure_remote_dir(self.REMOTE_CORE_DIR)
        
        # Also ensure backend/__init__.py exists for proper module resolution
        self._ensure_remote_dir(".tyto/backend")
        
        if not self.LOCAL_CORE_DIR.exists():
            print(f"[SSH] Warning: Local core directory not found: {self.LOCAL_CORE_DIR}")
            return result
        
        # Sync all Python files from core directory
        core_files = list(self.LOCAL_CORE_DIR.glob("*.py"))
        
        # Also need backend/__init__.py for imports to work
        backend_init = self.LOCAL_CORE_DIR.parent / "__init__.py"
        files_to_sync = [(f, self.REMOTE_CORE_DIR) for f in core_files]
        if backend_init.exists():
            files_to_sync.append((backend_init, ".tyto/backend"))
        
        print(f"[SSH] Syncing {len(files_to_sync)} core module files...")
        
        for local_path, remote_dir in files_to_sync:
            filename = local_path.name
            remote_path = f"{remote_dir}/{filename}"
            
            try:
                local_content = local_path.read_bytes()
                local_hash = self._get_file_hash(local_content)
                
                if not force:
                    remote_hash = self._get_remote_file_hash(remote_path)
                    if remote_hash == local_hash:
                        result["skipped"].append(filename)
                        continue
                
                remote_full_path = f"/home/{self.user}/{remote_path}"
                self.sftp.putfo(
                    fl=__import__("io").BytesIO(local_content),
                    remotepath=remote_full_path,
                )
                
                result["uploaded"].append(filename)
                print(f"  ✓ {filename}")
                
            except Exception as e:
                result["errors"].append(f"{filename}: {e}")
                print(f"  ✗ {filename}: {e}")
        
        print(f"[SSH] Core sync complete: {len(result['uploaded'])} uploaded, {len(result['skipped'])} skipped")
        return result
    
    def sync_scripts(self, force: bool = False) -> dict:
        """Sync worker scripts to remote ~/.tyto/scripts/.
        
        Also syncs backend/core/ modules for shared utilities.
        
        Args:
            force: If True, upload all files regardless of hash
            
        Returns:
            {"uploaded": [...], "skipped": [...], "errors": [...]}
        """
        result = {"uploaded": [], "skipped": [], "errors": []}
        
        # First sync core modules (required by worker scripts)
        core_result = self.sync_core_modules(force=force)
        
        # Ensure remote scripts directory exists
        self._ensure_remote_dir(self.REMOTE_SCRIPTS_DIR)
        
        # Get list of local scripts to sync
        if not self.LOCAL_SCRIPTS_DIR.exists():
            print(f"[SSH] Warning: Local scripts directory not found: {self.LOCAL_SCRIPTS_DIR}")
            return result
        
        scripts = list(self.LOCAL_SCRIPTS_DIR.glob("*.py"))
        scripts += list(self.LOCAL_SCRIPTS_DIR.glob("*.sh"))
        scripts += list(self.LOCAL_SCRIPTS_DIR.glob("*.txt"))  # requirements.txt
        
        print(f"[SSH] Syncing {len(scripts)} files to remote...")
        
        for local_path in scripts:
            filename = local_path.name
            remote_path = f"{self.REMOTE_SCRIPTS_DIR}/{filename}"
            
            try:
                # Read local file
                local_content = local_path.read_bytes()
                local_hash = self._get_file_hash(local_content)
                
                # Check if remote file exists and matches
                if not force:
                    remote_hash = self._get_remote_file_hash(remote_path)
                    if remote_hash == local_hash:
                        result["skipped"].append(filename)
                        continue
                
                # Upload file
                remote_full_path = f"/home/{self.user}/{remote_path}"
                self.sftp.putfo(
                    fl=__import__("io").BytesIO(local_content),
                    remotepath=remote_full_path,
                )
                
                # Make Python scripts executable
                if filename.endswith(".py") or filename.endswith(".sh"):
                    self.sftp.chmod(remote_full_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
                
                result["uploaded"].append(filename)
                print(f"  ✓ {filename}")
                
            except Exception as e:
                result["errors"].append(f"{filename}: {e}")
                print(f"  ✗ {filename}: {e}")
        
        # Merge core results
        result["uploaded"] = core_result["uploaded"] + result["uploaded"]
        result["skipped"] = core_result["skipped"] + result["skipped"]
        result["errors"] = core_result["errors"] + result["errors"]
        
        print(f"[SSH] Sync complete: {len(result['uploaded'])} uploaded, {len(result['skipped'])} skipped")
        return result
    
    def sync_env(self, env_vars: dict) -> bool:
        """Update remote ~/.tyto/.env with credentials.
        
        Merges with existing env file (updates existing keys, adds new ones).
        
        Args:
            env_vars: Dict of key-value pairs to set
            
        Returns:
            True on success
        """
        try:
            # Ensure .tyto directory exists
            self._ensure_remote_dir(self.REMOTE_TYTO_HOME)
            
            # Read existing env file if it exists
            existing_env = {}
            remote_env_path = f"/home/{self.user}/{self.REMOTE_ENV_FILE}"
            
            try:
                with self.sftp.open(remote_env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, _, value = line.partition("=")
                            existing_env[key.strip()] = value.strip()
            except FileNotFoundError:
                pass  # File doesn't exist yet
            
            # Merge with new vars (new vars take precedence)
            merged_env = {**existing_env, **env_vars}
            
            # Write back
            env_content = "\n".join(f"{k}={v}" for k, v in sorted(merged_env.items()))
            env_content += "\n"
            
            with self.sftp.open(remote_env_path, "w") as f:
                f.write(env_content)
            
            # Set restrictive permissions (600)
            self.sftp.chmod(remote_env_path, stat.S_IRUSR | stat.S_IWUSR)
            
            print(f"[SSH] Updated {len(env_vars)} env vars in {self.REMOTE_ENV_FILE}")
            return True
            
        except Exception as e:
            print(f"[SSH] Error syncing env: {e}")
            return False
    
    def execute_job(
        self,
        script_name: str,
        params: dict,
        timeout: int = 3600,
    ) -> dict:
        """Execute a worker script on remote machine.
        
        Args:
            script_name: Name of script in ~/.tyto/scripts/ (e.g., "remote_train.py")
            params: JSON-serializable params to pass via stdin
            timeout: Max execution time in seconds
            
        Returns:
            JSON-parsed output from script's stdout
            
        Raises:
            RuntimeError: If script execution fails
        """
        # Build command
        # Activate venv and run script with JSON from stdin
        params_json = json.dumps(params)
        
        # Escape single quotes in JSON for shell
        params_json_escaped = params_json.replace("'", "'\"'\"'")
        
        command = (
            f"cd ~/{self.REMOTE_TYTO_HOME} && "
            f"source venv/bin/activate && "
            f"export TYTO_ROOT=$HOME/{self.REMOTE_TYTO_HOME} && "
            f"echo '{params_json_escaped}' | python scripts/{script_name}"
        )
        
        print(f"[SSH] Executing {script_name}...")
        exit_code, stdout, stderr = self._exec(command, timeout=timeout)
        
        if exit_code != 0:
            raise RuntimeError(
                f"Job {script_name} failed with exit code {exit_code}.\n"
                f"Stderr: {stderr}\n"
                f"Stdout: {stdout}"
            )
        
        # Parse JSON output — look for last JSON object in stdout
        # (Script may print logs before the final JSON result)
        try:
            # Try to find the last line that looks like JSON
            for line in reversed(stdout.strip().split("\n")):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    return json.loads(line)
            
            # If no JSON found, try parsing entire stdout
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to parse job output as JSON: {e}\n"
                f"Output: {stdout}"
            )
    
    def execute_async(self, script_name: str, params: dict) -> str:
        """Start a job in background, return process ID for status polling.
        
        Args:
            script_name: Name of script in ~/.tyto/scripts/
            params: JSON-serializable params
            
        Returns:
            Job identifier (PID + log file path)
        """
        import uuid
        
        job_id = str(uuid.uuid4())[:8]
        log_file = f".tyto/logs/{job_id}.log"
        params_file = f".tyto/jobs/{job_id}_params.json"
        
        params_json = json.dumps(params)
        
        # Create directories
        self._ensure_remote_dir(".tyto/logs")
        self._ensure_remote_dir(".tyto/jobs")
        
        # Write params to temp file on remote (avoids shell argument length limits)
        sftp = self._client.open_sftp()
        try:
            remote_params_path = f"/home/{self.user}/{params_file}"
            with sftp.file(remote_params_path, "w") as f:
                f.write(params_json)
        finally:
            sftp.close()
        
        # Run in background with nohup, using absolute venv python path
        # Avoids slow 'source activate' step that can cause SSH timeouts
        command = (
            f"TYTO_ROOT=/home/{self.user}/{self.REMOTE_TYTO_HOME} "
            f"nohup /home/{self.user}/{self.REMOTE_TYTO_HOME}/venv/bin/python "
            f"/home/{self.user}/{self.REMOTE_SCRIPTS_DIR}/{script_name} "
            f"< /home/{self.user}/{params_file} "
            f"> /home/{self.user}/{log_file} 2>&1 & echo $!"
        )
        
        exit_code, stdout, stderr = self._exec(command, timeout=10)
        
        if exit_code != 0:
            raise RuntimeError(f"Failed to start async job: {stderr}")
        
        pid = stdout.strip()
        print(f"[SSH] Started async job {script_name} (PID: {pid}, log: {log_file})")
        
        return f"{pid}:{log_file}"
    
    def check_async_job(self, job_ref: str) -> dict:
        """Check status of an async job.
        
        Args:
            job_ref: Job reference from execute_async (format: "pid:log_file")
            
        Returns:
            {
                "running": bool,
                "output": str or None,
                "progress": dict or None,  # Last PROGRESS: line parsed
                "result": dict or None,    # Final JSON result (when complete)
            }
        """
        pid, log_file = job_ref.split(":", 1)
        
        # Check if process is still running
        exit_code, _, _ = self._exec(f"kill -0 {pid} 2>/dev/null")
        running = exit_code == 0
        
        # Read last 200 lines of log file (avoids reading huge logs)
        exit_code, stdout, _ = self._exec(f"tail -200 ~/{log_file} 2>/dev/null")
        output = stdout if exit_code == 0 else None
        
        # Parse last PROGRESS: line for current status
        progress = None
        if output:
            for line in reversed(output.strip().split("\n")):
                line = line.strip()
                if line.startswith("PROGRESS:"):
                    try:
                        progress = json.loads(line[len("PROGRESS:"):])
                        break
                    except json.JSONDecodeError:
                        pass
        
        # When job is done, extract the final JSON result from stdout
        # The last JSON line in the output is the result
        result = None
        if not running and output:
            for line in reversed(output.strip().split("\n")):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        result = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
        
        return {"running": running, "output": output, "progress": progress, "result": result}
    
    def check_connection(self) -> dict:
        """Test connection and return GPU info.
        
        Returns:
            {"success": bool, "message": str, "gpu_info": str or None}
        """
        try:
            exit_code, stdout, stderr = self._exec(
                "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader",
                timeout=10
            )
            
            if exit_code == 0:
                return {
                    "success": True,
                    "message": "Connection successful",
                    "gpu_info": stdout.strip(),
                }
            else:
                return {
                    "success": False,
                    "message": f"nvidia-smi failed: {stderr}",
                    "gpu_info": None,
                }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "gpu_info": None,
            }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_ssh_client_for_machine(user_id: str, machine_name: str) -> Optional[SSHWorkerClient]:
    """Get an SSHWorkerClient for a specific machine by name.
    
    Used for action-level compute target selection.
    
    Args:
        user_id: User UUID
        machine_name: Name of the local machine
        
    Returns:
        Configured SSHWorkerClient or None if machine not found
    """
    from backend.supabase_client import get_user_local_machines
    
    if not user_id or not machine_name:
        return None
    
    machines = get_user_local_machines(user_id)
    machine = next((m for m in machines if m.get("name") == machine_name), None)
    
    if not machine:
        print(f"[SSH] Machine '{machine_name}' not found in user's local machines")
        return None
    
    return SSHWorkerClient(
        host=machine.get("host"),
        port=machine.get("port", 22),
        user=machine.get("user", "ise"),
    )


def deploy_to_local_gpu(user_id: str, machine_name: str) -> dict:
    """Deploy worker scripts and core modules to a local GPU machine.
    
    This is the SSH equivalent of `modal deploy` — run once after code changes,
    then all subsequent inference/training calls skip sync entirely.
    
    Args:
        user_id: User UUID
        machine_name: Name of the local machine
        
    Returns:
        Sync result dict with uploaded/skipped/errors lists
        
    Raises:
        RuntimeError: If machine not found or connection fails
    """
    client = get_ssh_client_for_machine(user_id, machine_name)
    if not client:
        raise RuntimeError(f"Machine '{machine_name}' not found for user {user_id}")
    
    print(f"\n🚀 Deploying to {machine_name} ({client.host})...")
    
    with client:
        result = client.sync_scripts(force=True)
    
    # Print summary
    uploaded = len(result.get("uploaded", []))
    errors = result.get("errors", [])
    
    if errors:
        print(f"\n⚠️  Deploy completed with {len(errors)} errors:")
        for err in errors:
            print(f"  ✗ {err}")
    else:
        print(f"\n✅ Deploy complete: {uploaded} files uploaded to {machine_name}")
    
    return result

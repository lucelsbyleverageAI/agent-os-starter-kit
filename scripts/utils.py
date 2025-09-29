#!/usr/bin/env python3
import os
import re
import subprocess
import time
import signal
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import requests


def get_project_name() -> str:
    """Get the project name based on the current directory (repository name)."""
    return Path.cwd().name


def run_command(cmd: List[str], cwd: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, cwd=cwd, check=check)


def run_command_silent(cmd: List[str], cwd: Optional[str] = None) -> bool:
    """Run a command silently and return True if successful."""
    try:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def clean_env_value(value: str) -> str:
    """Clean environment variable value by removing inline comments."""
    if '#' in value:
        clean_val = value.split('#')[0].strip()
        return clean_val.strip('"').strip("'")
    return value.strip('"').strip("'")


def expand_env_variables(value: str) -> str:
    """Expand shell-style environment variables in a string."""
    # Pattern to match ${VAR:-default} or ${VAR}
    pattern = r'\$\{([^}]+)\}'
    
    def replace_var(match):
        var_expr = match.group(1)
        if ':-' in var_expr:
            # Handle ${VAR:-default} syntax
            var_name, default_value = var_expr.split(':-', 1)
            return os.environ.get(var_name, default_value)
        else:
            # Handle ${VAR} syntax
            return os.environ.get(var_expr, '')
    
    return re.sub(pattern, replace_var, value)


def load_env_file(env_file_path: str = ".env.local") -> bool:
    """Load environment variables from file."""
    env_file = Path(env_file_path)
    if not env_file.exists():
        print(f"❌ {env_file_path} file not found. Please create it based on .env.example")
        return False
    
    print(f"📋 Loading environment from {env_file_path}...")
    
    # First pass: Load simple variables (no expansion)
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                clean_value = clean_env_value(value)
                # Only set if it doesn't contain variable references
                if not ('${' in clean_value):
                    os.environ[key] = clean_value
    
    # Second pass: Expand variables that reference other variables
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                clean_value = clean_env_value(value)
                # Expand any variable references
                expanded_value = expand_env_variables(clean_value)
                os.environ[key] = expanded_value
                
                # Show expansion for debugging
                if clean_value != expanded_value:
                    print(f"   Expanded {key}: {clean_value} → {expanded_value}")
    
    return True


def check_dependencies() -> bool:
    """Check that required dependencies are installed."""
    dependencies = [
        ("docker", "Docker"),
        ("docker-compose", "Docker Compose"), 
        ("poetry", "Poetry (for LangGraph)"),
        ("yarn", "Yarn (for web frontend)")
    ]
    
    for cmd, name in dependencies:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True)
            print(f"✅ {name} is installed")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"❌ {name} is not installed or not in PATH")
            return False
    
    return True


def check_docker_running() -> bool:
    """Check if Docker is running."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        print("✅ Docker is running")
        return True
    except subprocess.CalledProcessError:
        print("❌ Docker is not running. Please start Docker Desktop.")
        return False


def get_docker_compose_cmd(project_name: str, compose_file: str = "docker-compose.local.dev.yml") -> List[str]:
    """Get the base docker compose command with project name and file."""
    return ["docker", "compose", "--env-file", ".env.local", "-p", project_name, "-f", compose_file]


def stop_docker_services(project_name: str, remove_volumes: bool = False) -> bool:
    """Stop all Docker services for the project."""
    print("🛑 Stopping Docker services...")
    
    compose_files = ["docker-compose.local.dev.yml", "docker-compose.local.yml"]
    
    for compose_file in compose_files:
        if os.path.exists(compose_file):
            print(f"📦 Stopping services from {compose_file}...")
            cmd = get_docker_compose_cmd(project_name, compose_file)
            if remove_volumes:
                cmd.extend(["down", "--volumes"])
            else:
                cmd.extend(["down"])
            
            run_command_silent(cmd)
    
    # Also stop any standalone Supabase services
    if os.path.exists("supabase/docker/docker-compose.yml"):
        print("🗄️  Stopping Supabase services...")
        cmd = ["docker", "compose", "-p", project_name, "-f", "supabase/docker/docker-compose.yml"]
        if remove_volumes:
            cmd.extend(["down", "--volumes"])
        else:
            cmd.extend(["down"])
        
        run_command_silent(cmd)
    
    # Final cleanup
    print("🧹 Performing final Docker cleanup...")
    final_cmd = ["docker", "compose", "-p", project_name, "down"]
    if remove_volumes:
        final_cmd.append("--volumes")
    run_command_silent(final_cmd)
    
    return True


def start_docker_services(project_name: str) -> bool:
    """Start all Docker services using the consolidated compose file."""
    print("🏗️  Starting all Docker services...")
    
    env = os.environ.copy()
    cmd = get_docker_compose_cmd(project_name)
    cmd.extend(["up", "-d", "--build"])
    
    print("Running:", " ".join(cmd))
    print("Environment variables loaded:", len([k for k in env.keys() if not k.startswith('_')]))
    
    try:
        result = subprocess.run(cmd, env=env, check=True, capture_output=False, text=True)
        print("✅ Docker services started successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Docker services failed to start: {e}")
        return False


def wait_for_service_health(service_name: str, url: str, timeout: int = 30) -> bool:
    """Wait for a single service to be healthy."""
    print(f"⏳ Waiting for {service_name}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code in [200, 301, 302]:
                print(f"✅ {service_name} is responding")
                return True
        except (requests.RequestException, requests.ConnectionError):
            pass
        
        time.sleep(2)
    
    print(f"⚠️  {service_name} not yet ready (may still be starting)")
    return False


def wait_for_services_health() -> None:
    """Wait for all services to be healthy."""
    print("⏳ Waiting for services to start...")
    
    # Get platform configuration
    platform_domain = os.environ.get('PLATFORM_DOMAIN', 'localhost')
    platform_protocol = os.environ.get('PLATFORM_PROTOCOL', 'http')
    
    services = [
        ("Supabase (Kong Gateway)", f"{platform_protocol}://{platform_domain}:8000", 60),
        ("n8n", f"{platform_protocol}://{platform_domain}:5678", 30),
        ("LangConnect", f"{platform_protocol}://{platform_domain}:8080/health", 45),
        ("MCP Server", f"{platform_protocol}://{platform_domain}:8002/health", 30),
        ("Windmill Server", f"{platform_protocol}://{platform_domain}:9000/health", 45)
    ]
    
    for service_name, url, timeout in services:
        wait_for_service_health(service_name, url, timeout)


def find_processes_by_pattern(patterns: List[str], description: str) -> List[Tuple[int, str]]:
    """Find processes matching the given patterns using ps command."""
    print(f"🔍 Looking for {description} processes...")
    
    found_pids = []
    
    try:
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        for line in result.stdout.split('\n'):
            for pattern in patterns:
                if pattern in line and 'grep' not in line:  # Exclude grep itself
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            command = ' '.join(parts[10:])  # Command starts at column 10
                            found_pids.append((pid, command))
                            print(f"🔪 Found {description}: PID {pid} - {command[:80]}...")
                        except (ValueError, IndexError):
                            continue
                    break
                    
    except subprocess.CalledProcessError:
        print(f"❌ Error finding {description} processes")
        return []
    
    return found_pids


def kill_processes(process_list: List[Tuple[int, str]], description: str) -> bool:
    """Kill a list of processes gracefully, then forcefully if needed."""
    if not process_list:
        print(f"✅ No {description} processes found")
        return False
    
    killed_count = 0
    
    for pid, command in process_list:
        try:
            # Try graceful termination first (SIGTERM)
            print(f"🔪 Gracefully terminating PID {pid}...")
            os.kill(pid, signal.SIGTERM)
            
            # Wait a bit for graceful shutdown
            time.sleep(2)
            
            # Check if process is still running
            try:
                os.kill(pid, 0)  # Signal 0 checks if process exists
                # Still running, force kill
                print(f"🔨 Force killing PID {pid}...")
                os.kill(pid, signal.SIGKILL)
            except OSError:
                # Process already terminated
                pass
                
            print(f"✅ Stopped PID {pid}")
            killed_count += 1
            
        except OSError as e:
            if e.errno == 3:  # No such process
                print(f"⚠️  Process {pid} already terminated")
            elif e.errno == 1:  # Operation not permitted
                print(f"❌ Permission denied to kill process {pid}")
            else:
                print(f"❌ Error killing process {pid}: {e}")
    
    print(f"✅ Stopped {killed_count} {description} process(es)")
    return killed_count > 0


def stop_background_processes() -> bool:
    """Stop LangGraph and web frontend background processes."""
    print("🛑 Stopping background development processes...")
    
    # Patterns to identify processes
    langgraph_patterns = [
        "poetry run langgraph dev",
        "langgraph dev --allow-blocking",
        "langgraph dev"
    ]
    
    web_patterns = [
        "yarn dev",
        "next dev",
        "DOTENV_CONFIG_PATH=.env.local yarn dev"
    ]
    
    # Find and stop processes
    langgraph_processes = find_processes_by_pattern(langgraph_patterns, "LangGraph")
    langgraph_stopped = kill_processes(langgraph_processes, "LangGraph")
    
    web_processes = find_processes_by_pattern(web_patterns, "web frontend")
    web_stopped = kill_processes(web_processes, "web frontend")
    
    return langgraph_stopped or web_stopped


def print_service_urls() -> None:
    """Print the URLs for all services."""
    platform_domain = os.environ.get('PLATFORM_DOMAIN', 'localhost')
    platform_protocol = os.environ.get('PLATFORM_PROTOCOL', 'http')
    
    print("=" * 70)
    print("🚀 LOCAL DEVELOPMENT STACK READY")
    print("=" * 70)
    print("🐋 DOCKER SERVICES:")
    print(f"  🌐 Supabase (Kong Gateway):      {platform_protocol}://{platform_domain}:8000")
    print(f"  🗄️  Supabase Studio:             {platform_protocol}://{platform_domain}:8000 (via Kong)")
    print(f"  📝 n8n (Workflow Automation):     {platform_protocol}://{platform_domain}:5678")
    print(f"  🔌 LangConnect API:              {platform_protocol}://{platform_domain}:8080")
    print(f"  🤖 MCP Server:                   {platform_protocol}://{platform_domain}:8002")
    print(f"  🌪️  Windmill Platform:           {platform_protocol}://{platform_domain}:9000")
    print(f"  📊 Windmill Database:            {platform_domain}:5433")
    print("")
    print("💻 LOCAL DEVELOPMENT SERVICES:")
    print(f"  🧠 LangGraph (AI Backend):       {platform_protocol}://{platform_domain}:2024")
    print(f"  🌐 Web Frontend:                 {platform_protocol}://{platform_domain}:3000")
    print("=" * 70)
    print("🎉 Complete development stack ready!")
    print("⚡ Hot Reloading: LangConnect & MCP Server auto-reload in Docker")
    print("🌪️  Windmill: Full workflow automation platform")
    print("🚀 Fast Development: LangGraph & Web Frontend run locally")
    print("🐋 Streamlined Config: Domain-first approach with auto-generated URLs")
    print("🔒 Security: Services are only accessible from configured domain")
    print("📋 Environment: Simplified .env.local with minimal variables")
    print("🗄️  Database: Automatic migrations applied")
    print("")
    print("🎯 All services started! Press Ctrl+C to stop all services.")
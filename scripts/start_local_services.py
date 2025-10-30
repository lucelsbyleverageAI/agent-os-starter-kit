#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import signal
import atexit
from pathlib import Path
import requests
from typing import List, Optional
import argparse

# Add the project root to Python path and import utilities
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.utils import (
    get_project_name, load_env_file, check_dependencies, check_docker_running,
    start_docker_services, wait_for_services_health, print_service_urls,
    stop_docker_services
)

# Global list to track background processes for cleanup
background_processes: List[subprocess.Popen] = []

def cleanup_processes():
    """Clean up all background processes on script exit."""
    print("\n🛑 Cleaning up all services...")
    
    # Stop Docker services
    print("🐋 Stopping Docker services...")
    try:
        project_name = get_project_name()
        stop_docker_services(project_name)
    except Exception as e:
        print(f"⚠️  Error stopping Docker services: {e}")
    
    # Clean up background processes
    for process in background_processes:
        try:
            if process.poll() is None:  # Still running
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception:
            pass

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    cleanup_processes()
    sys.exit(0)

# Register cleanup handlers
atexit.register(cleanup_processes)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def run_background_command(cmd: List[str], cwd: Optional[str] = None, env: Optional[dict] = None) -> subprocess.Popen:
    """Run a command in the background and track it for cleanup."""
    print(f"Starting in background: {' '.join(cmd)}")
    if cwd:
        print(f"  Working directory: {cwd}")
    
    process = subprocess.Popen(
        cmd, 
        cwd=cwd, 
        env=env
    )
    background_processes.append(process)
    return process

def start_langgraph():
    """Start LangGraph development server."""
    print("🤖 Starting LangGraph development server...")

    # Print relevant environment variables for debugging
    print("\n🔎 LangGraph environment variables:")
    print("  SUPABASE_URL:", os.environ.get("SUPABASE_URL"))
    print("  SUPABASE_ANON_KEY:", os.environ.get("SUPABASE_ANON_KEY"))
    print("")
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    langgraph_dir = project_root / "langgraph"
    
    # First install dependencies
    print("📦 Installing LangGraph dependencies...")
    subprocess.run(["poetry", "install"], cwd=str(langgraph_dir), check=True)
    
    # Start LangGraph dev server
    cmd = ["poetry", "run", "langgraph", "dev", "--allow-blocking"]
    
    print(f"🚀 Starting: {' '.join(cmd)} (in {langgraph_dir})")
    
    # Use host environment (preserves localhost URLs)
    env = os.environ.copy()
    
    process = subprocess.Popen(
        cmd,
        cwd=str(langgraph_dir),
        env=env,
        stdin=None,
        stdout=None,
        stderr=None
    )
    background_processes.append(process)
    
    # Give it time to start up
    print("⏳ Waiting for LangGraph to start...")
    time.sleep(5)
    
    # Check if it's responding
    try:
        response = requests.get("http://localhost:2024", timeout=5)
        print(f"✅ LangGraph is responding (HTTP {response.status_code})")
        return process
    except requests.RequestException:
        print("⚠️  LangGraph not yet responding (may still be starting)")
        return process

def start_web_frontend(production_mode=False):
    """Start web frontend server.

    Args:
        production_mode: If True, builds and runs in production mode. If False, runs in dev mode.
    """
    mode_label = "production" if production_mode else "development"
    print(f"🌐 Starting web frontend {mode_label} server...")

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    web_dir = project_root / "apps" / "web"

    if not web_dir.exists():
        print(f"❌ Web frontend directory not found: {web_dir.absolute()}")
        return None

    # First install dependencies
    print("📦 Installing web frontend dependencies...")
    try:
        subprocess.run(["yarn", "install"], cwd=str(web_dir), check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install web frontend dependencies: {e}")
        return None

    # Use host environment (preserves localhost URLs)
    env = os.environ.copy()

    if production_mode:
        # Build the production version first
        print(f"🏗️  Building production version (in {web_dir})...")
        try:
            subprocess.run(["yarn", "build"], cwd=str(web_dir), check=True, env=env)
            print("✅ Production build completed")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to build web frontend: {e}")
            return None

        # Start the production server
        print(f"🚀 Starting: yarn run start (in {web_dir})")
        process = subprocess.Popen(
            ["yarn", "run", "start"],
            cwd=str(web_dir),
            env=env,
            stdin=None,
            stdout=None,
            stderr=None
        )
    else:
        # Start the development server
        print(f"🚀 Starting: yarn run dev (in {web_dir})")
        process = subprocess.Popen(
            ["yarn", "run", "dev"],
            cwd=str(web_dir),
            env=env,
            stdin=None,
            stdout=None,
            stderr=None
        )

    background_processes.append(process)

    # Give it time to start up
    wait_time = 5 if production_mode else 8
    print(f"⏳ Waiting for web frontend to start...")
    time.sleep(wait_time)

    # Check if it's responding
    try:
        response = requests.get("http://localhost:3000", timeout=5)
        print(f"✅ Web frontend is responding (HTTP {response.status_code})")
        return process
    except requests.RequestException:
        print("⚠️  Web frontend not yet responding (may still be starting)")
        return process

def check_services_health():
    """Check the health of all running services."""
    print("🔍 Checking service health...")
    
    # Get platform configuration
    platform_domain = os.environ.get('PLATFORM_DOMAIN', 'localhost')
    platform_protocol = os.environ.get('PLATFORM_PROTOCOL', 'http')
    
    services = [
        ("Supabase (Kong Gateway)", f"{platform_protocol}://{platform_domain}:8000"),
        ("n8n", f"{platform_protocol}://{platform_domain}:5678"),
        ("LangConnect", f"{platform_protocol}://{platform_domain}:8080/health"),
        ("MCP Server", f"{platform_protocol}://{platform_domain}:8002/health"),
        ("Windmill Server", f"{platform_protocol}://{platform_domain}:9000/health")
    ]
    
    for service_name, url in services:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code in [200, 301, 302]:
                print(f"✅ {service_name} is responding")
            else:
                print(f"⚠️  {service_name} returned status {response.status_code}")
        except requests.RequestException:
            print(f"❌ {service_name} not responding")

def check_development_servers():
    """Check if LangGraph and web frontend are responding."""
    print("🔍 Checking development servers...")
    
    # Get platform domain from environment, default to localhost
    platform_domain = os.environ.get('PLATFORM_DOMAIN', 'localhost')
    platform_protocol = os.environ.get('PLATFORM_PROTOCOL', 'http')
    
    time.sleep(15)  # Give servers time to start
    
    # Check LangGraph
    try:
        result = subprocess.run(
            ["curl", "-s", "-f", f"{platform_protocol}://{platform_domain}:2024"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print("✅ LangGraph server is responding")
        else:
            print("⚠️  LangGraph server not yet ready (may still be starting)")
    except Exception:
        print("⚠️  LangGraph server not yet ready (may still be starting)")
    
    # Check Web Frontend
    try:
        result = subprocess.run(
            ["curl", "-s", "-f", f"{platform_protocol}://{platform_domain}:3000"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print("✅ Web frontend is responding")
        else:
            print("⚠️  Web frontend not yet ready (may still be starting)")
    except Exception:
        print("⚠️  Web frontend not yet ready (may still be starting)")



def fix_poetry_lock_files():
    """Fix any corrupted poetry.lock files with <empty> constraints."""
    print("🔧 Checking for poetry.lock files with empty constraints...")

    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Paths to check for poetry.lock files
    poetry_lock_paths = [
        project_root / "apps" / "langconnect" / "poetry.lock",
        project_root / "apps" / "mcp" / "poetry.lock",
        project_root / "langgraph" / "poetry.lock"
    ]

    for lock_path in poetry_lock_paths:
        if lock_path.exists():
            try:
                with open(lock_path, 'r') as f:
                    content = f.read()

                if '<empty>' in content:
                    print(f"  🔧 Fixing empty constraints in {lock_path}")
                    fixed_content = content.replace('"optax (<empty>)"', '"optax"')

                    with open(lock_path, 'w') as f:
                        f.write(fixed_content)
                    print(f"  ✅ Fixed {lock_path}")
                else:
                    print(f"  ✅ {lock_path} is clean")
            except Exception as e:
                print(f"  ⚠️  Could not check/fix {lock_path}: {e}")

def main():
    """Main function to start all services."""
    parser = argparse.ArgumentParser(description="Start Agent Platform in local development mode")
    parser.add_argument('--skip-frontend', action='store_true', help='Skip starting web frontend')
    parser.add_argument('--skip-langgraph', action='store_true', help='Skip starting LangGraph')
    parser.add_argument('--production-frontend', action='store_true', help='Run web frontend in production mode (build + start)')
    args = parser.parse_args()

    print("🚀 Starting Agent Platform in LOCAL DEVELOPMENT mode...")
    print("🐋 Docker: All infrastructure services")
    print("💻 Local: LangGraph + Web Frontend (optional)")
    print("📋 Using streamlined .env.local with domain-first approach")
    print(f"🏷️  Project name: {get_project_name()}")

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    if not check_docker_running():
        sys.exit(1)

    # Load environment variables
    if not load_env_file():
        sys.exit(1)

    print(f"🌐 Platform domain: {os.environ.get('PLATFORM_DOMAIN', 'localhost')}")
    print(f"🔗 Protocol: {os.environ.get('PLATFORM_PROTOCOL', 'http')}")

    try:
        # Fix any corrupted poetry.lock files before Docker build
        fix_poetry_lock_files()

        # Stop existing containers
        project_name = get_project_name()
        stop_docker_services(project_name)

        # Start all Docker services
        if not start_docker_services(project_name):
            sys.exit(1)
        
        # Wait for services to be ready
        wait_for_services_health()
        
        # Start LangGraph (optional)
        langgraph_process = None
        if not args.skip_langgraph:
            langgraph_process = start_langgraph()
        else:
            print("⚠️  Skipping LangGraph (--skip-langgraph flag)")
        
        # Start Web Frontend (optional)
        web_frontend_process = None
        if not args.skip_frontend:
            web_frontend_process = start_web_frontend(production_mode=args.production_frontend)
        else:
            print("⚠️  Skipping Web Frontend (--skip-frontend flag)")
        
        # Check service health
        check_services_health()
        
        # Check development servers
        if not args.skip_langgraph or not args.skip_frontend:
            check_development_servers()
        
        # Print service URLs
        print_service_urls()
        
        # Keep the script running
        try:
            iteration = 0
            while True:
                time.sleep(10)
                iteration += 1
                
                # Check if processes are still alive every 30 seconds
                if iteration % 3 == 0:
                    print(f"\n🔍 Checking background processes (iteration {iteration})...")
                    if langgraph_process and langgraph_process.poll() is None:
                        print(f"  ✅ LangGraph process is running")
                    elif langgraph_process:
                        print(f"  ❌ LangGraph process has stopped")
                    
                    if web_frontend_process and web_frontend_process.poll() is None:
                        print(f"  ✅ Web frontend process is running")
                    elif web_frontend_process:
                        print(f"  ❌ Web frontend process has stopped")
                    
                    # Quick health check
                    platform_domain = os.environ.get('PLATFORM_DOMAIN', 'localhost')
                    platform_protocol = os.environ.get('PLATFORM_PROTOCOL', 'http')
                    
                    if langgraph_process:
                        try:
                            response = requests.get(f"{platform_protocol}://{platform_domain}:2024", timeout=2)
                            print(f"  🧠 LangGraph: HTTP {response.status_code}")
                        except Exception as e:
                            print(f"  🧠 LangGraph: Not responding ({str(e)[:50]}...)")
                    
                    if web_frontend_process:
                        try:
                            response = requests.get(f"{platform_protocol}://{platform_domain}:3000", timeout=2)
                            print(f"  🌐 Web Frontend: HTTP {response.status_code}")
                        except Exception as e:
                            print(f"  🌐 Web Frontend: Not responding ({str(e)[:50]}...)")
                
        except KeyboardInterrupt:
            print("\n🛑 Received interrupt signal...")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {e}")
        cleanup_processes()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        cleanup_processes()
        sys.exit(1)

if __name__ == "__main__":
    main() 
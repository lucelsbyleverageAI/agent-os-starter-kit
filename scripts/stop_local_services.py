#!/usr/bin/env python3
import subprocess
import argparse
import sys
import signal
import os
import time
import shutil
from pathlib import Path

# Add the project root to Python path and import utilities
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.utils import (
    get_project_name, stop_docker_services, stop_background_processes,
    find_processes_by_pattern, kill_processes
)

def run_command_silent(cmd, cwd=None):
    """Run a shell command silently and return success status."""
    try:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def remove_persistent_data():
    """Remove persistent data stored in filesystem directories (not Docker volumes)."""
    print("🗑️  Removing persistent filesystem data...")
    
    # Supabase stores database data in filesystem directory, not Docker volume
    supabase_data_dir = "supabase/docker/volumes/db/data"
    
    try:
        if os.path.exists(supabase_data_dir):
            print(f"🗄️  Removing Supabase database data: {supabase_data_dir}")
            shutil.rmtree(supabase_data_dir)
            print("✅ Supabase database data removed")
        else:
            print(f"✅ Supabase database data directory not found (already clean)")
            
        # Check for other potential data directories that might persist
        other_data_dirs = [
            "supabase/docker/volumes/storage",  # Supabase storage files
            "supabase/docker/volumes/functions", # Edge functions
        ]
        
        for data_dir in other_data_dirs:
            if os.path.exists(data_dir) and os.listdir(data_dir):  # Only if exists and not empty
                print(f"🗂️  Removing {data_dir} contents...")
                shutil.rmtree(data_dir)
                os.makedirs(data_dir)  # Recreate empty directory
                print(f"✅ {data_dir} cleaned")
        
        return True
        
    except Exception as e:
        print(f"❌ Error removing persistent data: {e}")
        print("⚠️  You may need to manually remove the supabase/docker/volumes/db/data directory")
        return False

def check_running_containers():
    """Check if any containers are still running in the project."""
    print("🔍 Checking for remaining Docker containers...")
    
    project_name = get_project_name()
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"label=com.docker.compose.project={project_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        
        running_containers = result.stdout.strip().split('\n')
        running_containers = [name for name in running_containers if name]  # Remove empty strings
        
        if running_containers:
            print("⚠️  Some Docker containers are still running:")
            for container in running_containers:
                print(f"   - {container}")
            return False
        else:
            print(f"✅ No Docker containers running from the {project_name} project")
            return True
            
    except subprocess.CalledProcessError:
        print("❌ Error checking container status")
        return False

def check_remaining_processes():
    """Check if any development processes are still running."""
    print("🔍 Checking for remaining background processes...")
    
    patterns = [
        "poetry run langgraph dev",
        "langgraph dev",
        "yarn dev", 
        "next dev"
    ]
    
    found_processes = find_processes_by_pattern(patterns, "remaining background")
    
    if found_processes:
        print("⚠️  Some background processes are still running:")
        for pid, command in found_processes:
            print(f"   - PID {pid}: {command[:80]}...")
        return False
    else:
        print("✅ No background development processes found")
        return True

def show_cleanup_summary(volumes_removed=False, persistent_data_removed=False, problematic_cleaned=False, complete_reset=False):
    """Show a summary of what was cleaned up."""
    print("\n" + "="*70)
    if complete_reset:
        print("🧹 COMPLETE RESET CLEANUP FINISHED")
    else:
        print("🧹 COMPLETE STACK CLEANUP FINISHED")
    print("="*70)
    print("✅ All Docker services stopped (Supabase + Agent Platform)")
    print("✅ All background processes stopped (LangGraph + Web Frontend)")
    print("✅ All containers removed")
    print("✅ Docker networks cleaned up")
    
    if complete_reset:
        print("✅ ALL Docker containers force removed (including problematic ones)")
        print("✅ ALL project Docker volumes removed")
        print("✅ ALL persistent filesystem data removed")
        print("✅ Problematic Windmill containers/volumes cleaned")
    elif volumes_removed:
        print("✅ All Docker volumes removed")
    elif problematic_cleaned:
        print("✅ Problematic volumes cleaned (Windmill cache)")
    if persistent_data_removed and not complete_reset:
        print("✅ All persistent filesystem data removed (Supabase database, storage)")
    
    print("="*70)
    
    if complete_reset:
        print("\n🔥 COMPLETE RESET PERFORMED - Completely fresh environment!")
        print("🚀 This was the most thorough cleanup possible")
        print("💡 All problematic containers and volumes have been eliminated")
        print("🎯 Next startup will be completely clean with no Docker conflicts")
    elif volumes_removed or persistent_data_removed:
        print("\n🗑️  Complete data cleanup performed - you now have a fresh environment")
        print("🚀 Next startup will initialize everything from scratch")
    elif problematic_cleaned:
        print("\n🧹 Problematic volumes cleaned - this should prevent Docker startup issues")
        print("💡 Your main data is preserved in other Docker volumes and filesystem directories")
    else:
        print("\n💡 Your data is preserved in Docker volumes and filesystem directories")
    
    print("🚀 Run 'python scripts/start_local_services.py' to start the complete stack again")

def clean_problematic_volumes():
    """Clean up problematic Docker volumes that may cause permission issues."""
    print("🧹 Cleaning up potentially problematic Docker volumes...")
    project_name = get_project_name()
    
    # List of volumes that commonly cause issues (especially Windmill volumes)
    problematic_volumes = [
        f"{project_name}_windmill_worker_dependency_cache",
        f"{project_name}_windmill_worker_logs",
        f"{project_name}_windmill_lsp_cache"
    ]
    
    cleaned_count = 0
    for volume in problematic_volumes:
        try:
            # Check if volume exists
            result = subprocess.run([
                "docker", "volume", "inspect", volume
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"   🗑️  Removing problematic volume: {volume}")
                remove_result = subprocess.run([
                    "docker", "volume", "rm", volume
                ], capture_output=True, check=False)
                
                if remove_result.returncode == 0:
                    cleaned_count += 1
                    print(f"   ✅ Successfully removed: {volume}")
                else:
                    print(f"   ⚠️  Failed to remove: {volume} (may be in use)")
            
        except Exception as e:
            print(f"   ❌ Error processing volume {volume}: {e}")
    
    if cleaned_count > 0:
        print(f"✅ Cleaned up {cleaned_count} problematic volume(s)")
    else:
        print("✅ No problematic volumes found to clean")
    
    return cleaned_count > 0

def force_cleanup():
    """Force stop and remove any remaining containers from the project."""
    print("🔨 Force cleaning up any remaining Docker containers...")
    
    project_name = get_project_name()
    
    # Get all container IDs from the project
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project_name}", "--format", "{{.ID}}"],
            capture_output=True, text=True, check=True
        )
        
        container_ids = result.stdout.strip().split('\n')
        container_ids = [cid for cid in container_ids if cid]  # Remove empty strings
        
        if container_ids:
            print(f"🗑️  Force removing {len(container_ids)} containers...")
            subprocess.run(["docker", "rm", "-f"] + container_ids, check=True)
            print("✅ Force Docker cleanup complete")
        else:
            print("✅ No containers found to force remove")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during force Docker cleanup: {e}")
    
    # Also clean problematic volumes when force cleaning
    clean_problematic_volumes()

def complete_reset_cleanup():
    """
    Perform a complete reset cleanup that handles problematic containers and volumes.
    
    This is the most thorough cleanup option that:
    1. Force removes ALL containers (including problematic ones in 'Created' state)
    2. Removes ALL volumes (including problematic ones that are locked)
    3. Cleans up networks
    4. Handles the specific Windmill container issues
    
    This should be used when you want a completely fresh start.
    """
    print("🧹 COMPLETE RESET: Performing thorough cleanup of all Agent Platform components...")
    
    project_name = get_project_name()
    
    # Step 1: Force remove ALL containers (not just project ones, to catch problematic containers)
    print("🔨 Step 1: Force removing ALL containers to release volume locks...")
    try:
        # Get all container IDs
        result = subprocess.run(
            ["docker", "ps", "-aq"],
            capture_output=True, text=True, check=True
        )
        
        all_container_ids = result.stdout.strip().split('\n')
        all_container_ids = [cid for cid in all_container_ids if cid]  # Remove empty strings
        
        if all_container_ids:
            print(f"🗑️  Force removing {len(all_container_ids)} containers...")
            subprocess.run(["docker", "rm", "-f"] + all_container_ids, check=False)
            print("✅ All containers force removed")
        else:
            print("✅ No containers found")
            
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Error during container cleanup (continuing anyway): {e}")
    
    # Step 2: Remove ALL project volumes
    print("🗑️  Step 2: Removing ALL project volumes...")
    try:
        # Get all volumes for the project
        result = subprocess.run(
            ["docker", "volume", "ls", "-q"],
            capture_output=True, text=True, check=True
        )
        
        all_volumes = result.stdout.strip().split('\n')
        project_volumes = [vol for vol in all_volumes if vol and project_name in vol]
        
        if project_volumes:
            print(f"🗑️  Removing {len(project_volumes)} project volumes...")
            for volume in project_volumes:
                try:
                    subprocess.run(["docker", "volume", "rm", volume], check=False)
                    print(f"   ✅ Removed: {volume}")
                except Exception as e:
                    print(f"   ⚠️  Failed to remove {volume}: {e}")
            print("✅ All project volumes processed")
        else:
            print("✅ No project volumes found")
            
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Error during volume cleanup (continuing anyway): {e}")
    
    # Step 3: Clean up networks (but only project-specific ones)
    print("🌐 Step 3: Cleaning up project networks...")
    try:
        # Remove networks for our project
        subprocess.run(
            ["docker", "network", "prune", "-f"], 
            check=False, 
            capture_output=True
        )
        print("✅ Networks cleaned")
    except Exception as e:
        print(f"⚠️  Error during network cleanup: {e}")
    
    # Step 4: Final verification
    print("🔍 Step 4: Verifying cleanup...")
    
    # Check for remaining project containers
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project_name}"],
            capture_output=True, text=True, check=True
        )
        if result.stdout.strip():
            remaining_containers = len(result.stdout.strip().split('\n')) - 1  # Subtract header
            if remaining_containers > 0:
                print(f"⚠️  {remaining_containers} project containers still exist")
            else:
                print("✅ No project containers remain")
        else:
            print("✅ No project containers remain")
    except Exception as e:
        print(f"⚠️  Error checking remaining containers: {e}")
    
    # Check for remaining project volumes
    try:
        result = subprocess.run(
            ["docker", "volume", "ls", "-q"],
            capture_output=True, text=True, check=True
        )
        
        remaining_volumes = [vol for vol in result.stdout.strip().split('\n') if vol and project_name in vol]
        if remaining_volumes:
            print(f"⚠️  {len(remaining_volumes)} project volumes still exist:")
            for vol in remaining_volumes:
                print(f"     - {vol}")
        else:
            print("✅ No project volumes remain")
    except Exception as e:
        print(f"⚠️  Error checking remaining volumes: {e}")
    
    print("✅ Complete reset cleanup finished!")
    return True

def force_kill_processes():
    """Force kill any remaining background processes."""
    print("🔨 Force cleaning up any remaining background processes...")
    
    patterns = [
        "poetry run langgraph dev",
        "langgraph dev",
        "yarn dev",
        "next dev"
    ]
    
    found_processes = find_processes_by_pattern(patterns, "remaining background")
    force_killed = kill_processes(found_processes, "remaining background")
    return force_killed

def confirm_destructive_action(message: str, skip_confirm: bool = False) -> bool:
    """Ask for user confirmation for destructive actions."""
    if skip_confirm:
        return True
    
    response = input(f"{message} (y/N): ").lower()
    return response == 'y'

def main():
    parser = argparse.ArgumentParser(description='Stop the Complete Agent Platform Development Stack.')
    parser.add_argument('--remove-volumes', action='store_true',
                      help='Remove Docker volumes (WARNING: Deletes all data!)')
    parser.add_argument('--clean-problematic', action='store_true',
                      help='Clean problematic volumes (Windmill cache)')
    parser.add_argument('--force', action='store_true',
                      help='Force stop any remaining containers and processes')
    parser.add_argument('--complete-reset', action='store_true',
                      help='COMPLETE RESET: Force remove ALL containers and volumes')
    parser.add_argument('-y', '--yes', action='store_true',
                      help='Skip confirmation prompts')
    args = parser.parse_args()

    project_name = get_project_name()
    print("🛑 Stopping Complete Agent Platform Development Stack...")
    print("📦 Includes: Docker services + LangGraph + Web Frontend")
    print(f"🏷️  Project name: {project_name}")
    
    # Confirm destructive actions
    if args.complete_reset:
        print("🧹 COMPLETE RESET MODE SELECTED!")
        print("⚠️  WARNING: This will perform the most thorough cleanup possible!")
        print("   • ALL Docker containers will be force removed")
        print("   • ALL project Docker volumes will be removed")
        print("   • ALL DATA WILL BE PERMANENTLY DELETED!")
        if not confirm_destructive_action("Are you absolutely sure you want a complete reset?", args.yes):
            print("❌ Aborted by user")
            sys.exit(0)
    elif args.remove_volumes:
        print("⚠️  WARNING: --remove-volumes will delete all your data!")
        print("   • All Docker volumes will be removed")
        print("   • Supabase database data will be permanently deleted")
        if not confirm_destructive_action("Are you sure you want to continue?", args.yes):
            print("❌ Aborted by user")
            sys.exit(0)
    
    if args.clean_problematic:
        print("🧹 Will clean up problematic volumes (Windmill cache) to prevent startup issues")
    
    # Stop background processes first
    background_stopped = stop_background_processes()
    
    # Handle complete reset (most thorough option)
    if args.complete_reset:
        print("\n🧹 Starting complete reset cleanup...")
        complete_reset_success = complete_reset_cleanup()
        
        # Remove persistent filesystem data as part of complete reset
        persistent_data_removed = remove_persistent_data()
        
        # Complete reset handles all cleanup, so mark everything as done
        docker_success = complete_reset_success
        problematic_cleaned = True
        volumes_removed = True
        
    else:
        # Regular cleanup flow
        # Stop Docker services
        docker_success = stop_docker_services(project_name, args.remove_volumes)
        
        # Remove persistent filesystem data if requested
        persistent_data_removed = False
        if args.remove_volumes:
            persistent_data_removed = remove_persistent_data()
        
        # Track if problematic volumes were cleaned
        problematic_cleaned = args.clean_problematic
        volumes_removed = args.remove_volumes
        
        if not docker_success:
            print("⚠️  Some errors occurred during Docker shutdown")
            if args.force:
                force_cleanup()
                # Force cleanup also cleans problematic volumes
                problematic_cleaned = True
    
    # Check if everything stopped
    containers_stopped = check_running_containers()
    processes_stopped = check_remaining_processes()
    
    # Force cleanup if requested and things are still running
    if args.force and (not containers_stopped or not processes_stopped):
        if not containers_stopped:
            force_cleanup()
            problematic_cleaned = True
        if not processes_stopped:
            force_kill_processes()
        
        # Final check
        check_running_containers()
        check_remaining_processes()
    
    # If we had issues and cleaned problematic volumes, recommend a complete restart
    if problematic_cleaned and not args.remove_volumes:
        print("\n⚠️  Problematic volumes were cleaned - recommend using --remove-volumes for a fresh start")
    
    # Show summary
    show_cleanup_summary(
        volumes_removed=volumes_removed,
        persistent_data_removed=persistent_data_removed,
        problematic_cleaned=problematic_cleaned,
        complete_reset=args.complete_reset
    )

if __name__ == "__main__":
    main() 
#!/bin/bash
# SSH Tunnel to Production Database
# Keep this terminal open during migration

# CONFIGURATION - Update these values for your setup
PRODUCTION_SSH_HOST="your-production-server"   # Your SSH host (e.g., "e18-server" or "user@host.com")
DB_CONTAINER_IP="localhost"                     # Database IP (use "localhost" if DB is on host, or Docker IP like "172.18.0.7")
DB_PORT="5432"                                  # Production database port
LOCAL_PORT="5433"                               # Local port to use for tunnel

# HOW TO FIND YOUR DATABASE CONTAINER IP:
# If your production database runs in Docker and doesn't expose port 5432 to localhost, you need the container's IP:
# 1. SSH to your production server: ssh your-production-server
# 2. Find the database container name: docker ps | grep postgres
# 3. Get container IP: docker inspect CONTAINER_NAME | grep IPAddress
# 4. Update DB_CONTAINER_IP above with the IP address (e.g., "172.18.0.7")

echo "🔐 Opening SSH tunnel to production database..."
echo "   SSH Host: $PRODUCTION_SSH_HOST"
echo "   Remote: $DB_CONTAINER_IP:$DB_PORT"
echo "   Local: localhost:$LOCAL_PORT"
echo ""
echo "Keep this terminal open. Press Ctrl+C to close tunnel."
echo ""

# Open SSH tunnel
# Format: ssh -L [local_port]:[remote_host]:[remote_port] [ssh_host] -N
ssh -L ${LOCAL_PORT}:${DB_CONTAINER_IP}:${DB_PORT} ${PRODUCTION_SSH_HOST} -N


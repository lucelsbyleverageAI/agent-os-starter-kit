FROM docker.n8n.io/n8nio/n8n:latest

# Bake workflow and credential templates into the image so imports don't rely on host bind mounts
USER root
RUN mkdir -p /data/credentials /data/workflows
COPY n8n/data/ /data/
RUN chown -R node:node /data
USER node

# Note: actual import is still controlled by docker-compose command for n8n-import


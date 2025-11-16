# Backup Strategy for Agent OS Production Deployment

**Deployment Environment:** Hetzner VPS + Coolify
**Date Created:** 2025-11-16
**Status:** Implementation Guide

---

## Executive Summary

This document outlines a **2-tier backup strategy** optimized for self-hosted Coolify deployments to protect your Agent OS production deployment from data loss scenarios including accidental deletion, hardware failure, and deployment errors.

### Strategy Overview

1. **Automated Backups** (via offen/docker-volume-backup) → Databases + Volumes → Hetzner Object Storage
2. **Server Snapshots** (via Hetzner Cloud) → Disaster recovery baseline

**Estimated Monthly Cost:** ~€10-13 (€4.99 Object Storage + €4-8 for snapshots depending on server size)

### Why This Strategy?

For self-hosted Coolify without UI backup features, this approach:
- ✅ **Unified Solution**: One tool backs up both databases and volumes
- ✅ **Docker-Native**: Works perfectly with docker-compose deployments
- ✅ **No Coolify Dependencies**: Doesn't require Coolify UI features
- ✅ **Production-Tested**: offen/docker-volume-backup is widely used and trusted
- ✅ **Simple to Test**: Easy restoration procedures

---

## What Data Needs Backup?

Based on your `docker-compose.production.yml`, here are the critical data assets:

### 📊 Databases (Highest Priority)

| Database | Service | Size (typical) | Criticality |
|----------|---------|----------------|-------------|
| Main PostgreSQL | `db_prod` (Supabase) | Varies | **CRITICAL** - All user data, auth, knowledge bases |
| Windmill DB | `windmill-db-prod` | Small | HIGH - Workflow definitions |
| n8n DB | Stored in main PostgreSQL | Small | HIGH - Automation workflows |

### 📁 Docker Volumes (High Priority)

| Volume | Purpose | Backup Frequency |
|--------|---------|------------------|
| `supabase-db-data` | PostgreSQL database files | **Daily** (via DB dump) |
| `n8n_storage` | n8n workflow data | Daily |
| `langconnect_storage` | LangConnect API data | Daily |
| `mcp_server_storage` | MCP server data | Daily |
| `windmill_db_data` | Windmill PostgreSQL data | Daily |
| `supabase-storage` | File uploads (Supabase Storage) | **Daily** (important user files) |
| `windmill_worker_logs` | Worker execution logs | Weekly (optional) |
| `windmill_worker_dependency_cache` | Dependency cache | Not needed (regenerable) |
| `windmill_lsp_cache` | LSP cache | Not needed (regenerable) |
| `db-config` | Database configuration | Weekly |

---

## Recommended 3-Tier Backup Strategy

### Tier 1: Database Backups (Coolify Native) ✅

**What:** Automated PostgreSQL dumps via Coolify's built-in backup system
**Where:** Hetzner Object Storage (S3-compatible)
**Cost:** €4.99/month (includes 1TB storage + 1TB egress)
**Frequency:** Daily at 2 AM UTC
**Retention:** 30 daily backups, 12 monthly backups

#### Implementation Steps:

1. **Set Up Hetzner Object Storage**
   - Go to Hetzner Cloud Console → Object Storage
   - Create new bucket: `agent-os-backups`
   - Note credentials: Access Key ID and Secret Access Key
   - Region: `eu-central` (same as your VPS for free egress)

2. **Configure S3 in Coolify**
   - Navigate to your Coolify dashboard
   - Go to `Settings` → `S3 Storages` → `Add New S3 Storage`
   - Enter:
     - Name: `Hetzner Object Storage`
     - Endpoint: `https://s3.eu-central-003.io.cloud.ovh.net` (Hetzner's S3 endpoint - verify in your Hetzner console)
     - Bucket: `agent-os-backups`
     - Access Key: `[from step 1]`
     - Secret Key: `[from step 1]`
   - Click `Verify` to test connection

3. **Enable Database Backups**

   For **Main PostgreSQL** (`db_prod`):
   - In Coolify, navigate to your Agent OS project → `db_prod` service
   - Go to `Backups` tab
   - Click `Create a Scheduled Backup`
   - Configure:
     - **Frequency:** `daily` (cron: `0 2 * * *` = 2 AM daily)
     - **S3 Enabled:** ✓ (select your Hetzner storage)
     - **Retention (local):** 7 days (fallback if S3 fails)
   - Save configuration

   For **Windmill Database** (`windmill-db-prod`):
   - Repeat the same process
   - Set frequency to `daily` at 2:30 AM (stagger from main DB)

4. **Test Your Backup**
   - After configuration, click `Backup Now` to test
   - Verify backup appears in Hetzner Object Storage bucket
   - Check Coolify logs for any errors

#### Recovery Process:
```bash
# In Coolify UI:
1. Navigate to database → Backups tab
2. Find desired backup
3. Click "Restore" button
4. Confirm restoration (⚠️ this will overwrite current data)
```

---

### Tier 2: Docker Volume Backups ✅

**What:** Automated backups of all Docker volumes (including files, configs, caches)
**Where:** Same Hetzner Object Storage bucket (subfolder `/volumes/`)
**Tool:** `offen/docker-volume-backup` (open-source, 15MB, widely trusted)
**Frequency:** Daily at 3 AM UTC (after DB backups complete)
**Retention:** 14 daily backups

#### Why This Matters:

While Coolify backs up databases via dumps, Docker volumes contain:
- **Supabase Storage files** (user uploads, documents)
- **n8n workflows** (if not in DB)
- **Application configs** that aren't in the database
- **State that would be lost** in a container rebuild

#### Implementation Steps:

1. **Update docker-compose.production.yml**

   Add this service at the end of your compose file:

   ```yaml
   # ==========================================
   # BACKUP SERVICE
   # ==========================================

   volume-backup:
     image: offen/docker-volume-backup:latest
     container_name: volume-backup-prod
     restart: unless-stopped
     networks:
       - coolify
     environment:
       # Backup schedule (3 AM daily, after DB backups)
       - BACKUP_CRON_EXPRESSION=0 3 * * *

       # S3 configuration (Hetzner Object Storage)
       - AWS_S3_BUCKET_NAME=agent-os-backups
       - AWS_S3_PATH=/volumes/  # Subfolder in bucket
       - AWS_ENDPOINT=https://s3.eu-central-003.io.cloud.ovh.net  # Verify your endpoint
       - AWS_ACCESS_KEY_ID=${BACKUP_AWS_ACCESS_KEY_ID}
       - AWS_SECRET_ACCESS_KEY=${BACKUP_AWS_SECRET_ACCESS_KEY}

       # Backup retention
       - BACKUP_RETENTION_DAYS=14

       # Compression settings
       - BACKUP_COMPRESSION=gz

       # Archive name format
       - BACKUP_FILENAME=volume-backup-%Y-%m-%dT%H-%M-%S.tar.gz

       # Pruning old backups
       - BACKUP_PRUNING_PREFIX=volume-backup-

       # Stop containers during backup for consistency
       - BACKUP_STOP_DURING_BACKUP_LABEL=docker-volume-backup.stop-during-backup

     volumes:
       # Mount Docker socket to control containers
       - /var/run/docker.sock:/var/run/docker.sock:ro

       # Mount all volumes to backup (read-only for safety)
       - supabase-db-data:/backup/supabase-db-data:ro
       - supabase-storage:/backup/supabase-storage:ro
       - n8n_storage:/backup/n8n_storage:ro
       - langconnect_storage:/backup/langconnect_storage:ro
       - mcp_server_storage:/backup/mcp_server_storage:ro
       - windmill_db_data:/backup/windmill_db_data:ro
       - windmill_worker_logs:/backup/windmill_worker_logs:ro
       - db-config:/backup/db-config:ro

     depends_on:
       - db_prod
       - windmill-db-prod
   ```

2. **Add Labels to Critical Services**

   Add this label to services that should pause during backup (for data consistency):

   ```yaml
   # Example: Update db_prod service
   db_prod:
     # ... existing config ...
     labels:
       - docker-volume-backup.stop-during-backup=true

   # Also add to:
   # - windmill-db-prod
   # - storage_prod (Supabase Storage)
   # - n8n
   ```

3. **Add Environment Variables to .env.local**

   ```bash
   # Backup Configuration (same credentials as Coolify S3)
   BACKUP_AWS_ACCESS_KEY_ID=your_hetzner_access_key
   BACKUP_AWS_SECRET_ACCESS_KEY=your_hetzner_secret_key
   ```

4. **Deploy and Test**

   ```bash
   # In Coolify, redeploy your application to apply changes
   # Or manually restart if you have terminal access:
   docker compose -f docker-compose.production.yml up -d

   # Trigger immediate test backup (don't wait for cron)
   docker exec volume-backup-prod backup

   # Check logs
   docker logs volume-backup-prod

   # Verify in Hetzner Object Storage bucket under /volumes/
   ```

#### Recovery Process:

```bash
# 1. Download backup from Hetzner S3
aws s3 cp s3://agent-os-backups/volumes/volume-backup-2025-11-16T03-00-00.tar.gz ./

# 2. Extract to temporary location
mkdir restore-temp
tar -xzf volume-backup-2025-11-16T03-00-00.tar.gz -C restore-temp/

# 3. Stop services
docker compose -f docker-compose.production.yml down

# 4. Restore volume data
# (Example for supabase-storage)
docker run --rm \
  -v agent-os_supabase-storage:/target \
  -v $(pwd)/restore-temp/backup/supabase-storage:/source:ro \
  alpine sh -c "rm -rf /target/* && cp -a /source/. /target/"

# 5. Restart services
docker compose -f docker-compose.production.yml up -d
```

**Better Alternative:** Use Coolify's UI to restore from backup if they add this feature, or create a restoration script.

---

### Tier 3: Server Snapshots (Disaster Recovery Baseline) 🔄

**What:** Full server disk snapshots via Hetzner Cloud
**Where:** Hetzner's infrastructure (automatically distributed)
**Cost:** ~20% of your server's monthly cost (~€4-8/month for typical VPS)
**Frequency:** Weekly (every Sunday at 4 AM)
**Retention:** 4 weekly snapshots (1 month)

#### Why This Matters:

- **Complete disaster recovery** if server becomes unbootable
- **Quick rollback** for catastrophic deployment failures
- **Captures OS, Docker, and all configurations** in one atomic snapshot
- **Does NOT replace DB/volume backups** (snapshots are point-in-time, not granular)

#### Limitations:

⚠️ **Critical:** Hetzner server snapshots **DO NOT include attached Volumes** (if you use Hetzner Volumes separately from the main disk). They only snapshot the server's root disk.
✅ **Good News:** Your docker-compose uses named volumes stored on the root disk, so these ARE included.

#### Implementation Steps:

**Option A: Manual via Hetzner Cloud Console (Recommended for simplicity)**

1. Log into Hetzner Cloud Console
2. Go to your VPS server
3. Navigate to `Backups` section
4. Click `Enable Backups`
5. Configure:
   - Backup window: Sunday 4-6 AM
   - Retention: Automatic (keeps 7 backups, rotates oldest)
6. Cost: Displays ~20% of server price

**Option B: Automated via Hetzner API (Advanced)**

Create a cron job on a separate machine (or GitHub Actions):

```bash
# Install Hetzner CLI
brew install hcloud  # or apt-get install hcloud

# Authenticate
hcloud context create agent-os-prod

# Create weekly snapshot (add to cron)
#!/bin/bash
SERVER_NAME="your-vps-name"
SNAPSHOT_NAME="agent-os-$(date +%Y-%m-%d)"

# Create snapshot
hcloud server create-image $SERVER_NAME \
  --description "Weekly backup" \
  --type snapshot \
  --labels "auto-backup=true"

# Delete snapshots older than 30 days
hcloud image list -o json | \
  jq -r '.[] | select(.labels["auto-backup"]=="true") | .id + " " + .created' | \
  while read id created; do
    if [[ $(date -d "$created" +%s) -lt $(date -d "30 days ago" +%s) ]]; then
      hcloud image delete $id
    fi
  done
```

#### Recovery Process:

**Full Server Restoration:**

1. In Hetzner Cloud Console → Servers
2. Click your VPS → `Snapshots` tab
3. Click `Create Server from Snapshot`
4. Choose snapshot date
5. Update DNS/IP if needed
6. Update Coolify configuration if server IP changed

**Important:** For consistency, shut down your VPS before creating a snapshot:
```bash
# SSH into server
sudo shutdown -h now

# In Hetzner Console: Create snapshot
# Then: Power server back on
```

---

## Backup Strategy Summary Table

| Tier | What | Tool | Frequency | Retention | Cost/mo | Recovery Time |
|------|------|------|-----------|-----------|---------|---------------|
| 1 | **Databases** | Coolify native | Daily 2 AM | 30 daily, 12 monthly | €4.99 | ~5 min |
| 2 | **Docker Volumes** | offen/docker-volume-backup | Daily 3 AM | 14 daily | Included in Tier 1 | ~30 min |
| 3 | **Full Server** | Hetzner Snapshots | Weekly Sunday 4 AM | 4 weekly | €4-8 | ~15 min |

**Total Cost:** €10-15/month for comprehensive protection

---

## Testing Your Backups (Critical!)

**"Untested backups are Schrödinger's backups - they're both working and broken until you test them."**

### Monthly Backup Test Checklist

**Last Tested:** _________
**Next Test Date:** _________

- [ ] **Database Restore Test**
  1. Create test database in Coolify
  2. Restore latest backup to test database
  3. Verify data integrity (spot-check tables)
  4. Delete test database

- [ ] **Volume Restore Test**
  1. Download latest volume backup from S3
  2. Extract and verify archive integrity
  3. Spot-check critical files (Supabase storage, n8n workflows)

- [ ] **Snapshot Restore Test** (Quarterly)
  1. Create test server from latest snapshot
  2. Verify services start successfully
  3. Check database connectivity
  4. Delete test server

### Automated Backup Monitoring

Add this to your monitoring stack (if you use one):

```yaml
# Example: Uptime Kuma / Healthchecks.io checks
- Check: "Coolify DB backup completed" (daily)
  - Monitor S3 bucket for new files
  - Alert if no backup in 25 hours

- Check: "Volume backup completed" (daily)
  - Parse volume-backup logs
  - Alert if backup failed

- Check: "Hetzner snapshot exists" (weekly)
  - Query Hetzner API for snapshot age
  - Alert if >8 days old
```

---

## Recovery Scenarios

### Scenario 1: Accidentally Deleted Database Table

**Recovery Path:** Tier 1 (Database Backup)

```bash
1. Identify backup timestamp before deletion
2. In Coolify → Database → Backups → Select backup
3. Download backup locally
4. Extract specific table using pg_restore:
   pg_restore -t table_name backup.dump | psql -U postgres -d postgres
```

**Downtime:** None (selective restore)

---

### Scenario 2: Corrupted Docker Volume

**Recovery Path:** Tier 2 (Volume Backup)

```bash
1. Stop affected service
2. Download volume backup from S3
3. Extract and replace corrupted volume
4. Restart service
```

**Downtime:** 10-30 minutes

---

### Scenario 3: Complete Server Failure / Accidental Deletion

**Recovery Path:** Tier 3 (Server Snapshot) + Tier 1 (Database)

```bash
1. Create new server from latest Hetzner snapshot
2. Update DNS/IP addresses
3. If snapshot is >1 day old, restore latest DB backup
4. Verify all services
```

**Downtime:** 30-60 minutes

---

### Scenario 4: Ransomware / Malicious Encryption

**Recovery Path:** Tier 3 (clean snapshot) + Tier 1 (verified clean backup)

```bash
1. Isolate infected server (shut down)
2. Create new server from snapshot BEFORE infection
3. Restore databases from known-clean backup
4. Audit and patch security vulnerability
5. Update credentials
```

**Downtime:** 1-4 hours

---

## Implementation Checklist

### Phase 1: Immediate (Week 1)
- [ ] Set up Hetzner Object Storage bucket
- [ ] Configure Coolify S3 storage connection
- [ ] Enable database backups for `db_prod`
- [ ] Enable database backups for `windmill-db-prod`
- [ ] Test one manual backup and restore

### Phase 2: Volume Backups (Week 2)
- [ ] Update docker-compose.production.yml with volume-backup service
- [ ] Add labels to critical services
- [ ] Add environment variables to .env.local
- [ ] Deploy and test volume backup
- [ ] Verify backups appear in S3

### Phase 3: Server Snapshots (Week 3)
- [ ] Enable Hetzner Cloud Backups via console
- [ ] Wait for first snapshot
- [ ] Test snapshot restoration on test server (optional but recommended)

### Phase 4: Monitoring (Week 4)
- [ ] Set up backup monitoring alerts
- [ ] Document restoration procedures
- [ ] Schedule quarterly full recovery test
- [ ] Add calendar reminder for monthly backup verification

---

## Backup Security Considerations

### Encryption
- ✅ **In Transit:** S3 connections use HTTPS (encrypted)
- ⚠️ **At Rest:** Hetzner Object Storage encrypts at rest by default, but consider client-side encryption for sensitive data
- 🔐 **Credentials:** Store S3 keys in Coolify's encrypted secrets, never in git

### Access Control
- Use separate S3 credentials with **write-only permissions** for backup service
- Use separate S3 credentials with **read-only permissions** for disaster recovery team
- Enable Hetzner 2FA for console access

### Compliance
- **GDPR:** Backups contain user data - ensure retention policies comply
- **Data Residency:** Hetzner `eu-central` keeps data in EU
- **Right to Deletion:** Document process for purging backups on user request

---

## Alternative/Additional Tools (Optional)

### Restic (Advanced Users)
- **Pros:** Deduplication, encryption, incremental backups
- **Cons:** More complex setup, requires separate server/cron
- **Use Case:** If backup sizes become expensive (>100GB)

### Velero (Kubernetes)
- Not applicable (you're using Docker Compose, not K8s)

### Backup Strategy Evolution
As your data grows:
- **<10GB:** Current strategy is perfect
- **10-50GB:** Add Restic for deduplication
- **>50GB:** Consider incremental backups or multi-region replication

---

## Cost Breakdown (Monthly)

| Item | Cost |
|------|------|
| Hetzner Object Storage (1TB included) | €4.99 |
| Hetzner Server Snapshots (~20% of server) | €4-8 (depends on your VPS size) |
| **TOTAL** | **€9-13/month** |

**Cost Optimization Tips:**
- Use `eu-central` region for free egress to/from your VPS
- Set retention to 14 days for volumes (not 30) to save space
- Exclude cache volumes (windmill_worker_dependency_cache, lsp_cache)

---

## FAQ

**Q: Can I use the cheaper Hetzner Storage Box instead of Object Storage?**
A: No, Storage Box is not S3-compatible. You need Object Storage for Coolify and offen/docker-volume-backup.

**Q: What if I want to backup to multiple locations (3-2-1 rule)?**
A: Configure a second S3 destination (e.g., Backblaze B2, Wasabi) in Coolify and enable it for critical databases.

**Q: How do I backup .env.local secrets?**
A: Store .env.local in a password manager (1Password, Bitwarden) or encrypted git repo. DO NOT commit to regular git.

**Q: Can Coolify backup my application code?**
A: No need - your code is in git. Backups are for DATA only. For config, backup docker-compose files to git.

**Q: What about n8n workflows?**
A: n8n stores workflows in PostgreSQL (covered by Tier 1) AND n8n_storage volume (covered by Tier 2). You're double-protected.

**Q: Should I backup the Coolify server itself?**
A: Yes! If Coolify is on a separate VPS, enable Hetzner Snapshots for that server too. Coolify has built-in backup at `Settings → Backup`.

---

## Support & Resources

- **Coolify Docs:** https://coolify.io/docs/databases/backups
- **offen/docker-volume-backup:** https://github.com/offen/docker-volume-backup
- **Hetzner Object Storage:** https://docs.hetzner.com/storage/object-storage/
- **Hetzner Snapshots:** https://docs.hetzner.com/cloud/servers/backups-snapshots/overview/

---

## Document Maintenance

**Last Updated:** 2025-11-16
**Next Review:** 2025-12-16 (or after major architecture changes)
**Owner:** Luc (AI Engineer)

### Change Log
- 2025-11-16: Initial backup strategy created

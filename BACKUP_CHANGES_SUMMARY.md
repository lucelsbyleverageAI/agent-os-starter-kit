# Backup System - Changes Summary

**Date:** 2025-11-16
**Status:** Ready for deployment - requires Hetzner S3 setup

---

## What Was Changed

### 1. docker-compose.production.yml

**Added:**
- New `volume-backup` service using `offen/docker-volume-backup:latest`
- Configured to backup all critical volumes to Hetzner S3
- Scheduled for daily backups at 3 AM UTC
- 14-day retention policy

**Modified:**
- Added `docker-volume-backup.stop-during-backup=true` labels to:
  - `db_prod` (main PostgreSQL database)
  - `windmill-db-prod` (Windmill database)
  - `storage_prod` (Supabase Storage)

  This ensures these services pause during backup for data consistency.

### 2. New Files Created

- `.env.production.backup.example` - Template for S3 credentials
- `BACKUP_IMPLEMENTATION_GUIDE.md` - Step-by-step setup instructions
- `BACKUP_STRATEGY.md` - Comprehensive backup strategy documentation
- `BACKUP_CHANGES_SUMMARY.md` - This file

---

## What Gets Backed Up

### Databases (via volume snapshots)
- ✅ Main PostgreSQL (Supabase) - all user data, auth, knowledge bases
- ✅ Windmill PostgreSQL - workflow definitions

### Docker Volumes
- ✅ `supabase-db-data` - PostgreSQL data files
- ✅ `supabase-storage` - User file uploads
- ✅ `n8n_storage` - n8n workflow data
- ✅ `langconnect_storage` - LangConnect API data
- ✅ `mcp_server_storage` - MCP server data
- ✅ `windmill_db_data` - Windmill database files
- ✅ `db-config` - Database configuration

### Not Backed Up (Intentionally)
- ❌ `windmill_worker_dependency_cache` - Regenerable
- ❌ `windmill_lsp_cache` - Regenerable
- ❌ `windmill_worker_logs` - Can be regenerated

---

## Environment Variables Required

Add these to Coolify environment variables (or production .env):

```bash
BACKUP_S3_BUCKET_NAME=agent-os-backups
BACKUP_S3_ENDPOINT=https://[your-endpoint].com
BACKUP_S3_ACCESS_KEY_ID=[your-access-key]
BACKUP_S3_SECRET_ACCESS_KEY=[your-secret-key]
```

**Where to get these:**
1. Create bucket in Hetzner Cloud Console → Object Storage
2. Generate S3 credentials in bucket settings
3. Copy endpoint URL from bucket details

---

## Deployment Checklist

Before deploying to production:

- [ ] Set up Hetzner Object Storage bucket (`agent-os-backups`)
- [ ] Generate S3 credentials in Hetzner console
- [ ] Add 4 environment variables to Coolify project
- [ ] Commit changes to git repository
- [ ] Push to main branch
- [ ] Trigger Coolify redeploy
- [ ] Verify all services start successfully
- [ ] Run manual test backup: `docker exec volume-backup-prod backup`
- [ ] Verify backup appears in Hetzner S3 bucket
- [ ] Enable Hetzner server snapshots (weekly)

---

## How Backups Work

### Daily Automated Backups (3 AM UTC)

1. **Pre-Backup:** Backup container stops services with `stop-during-backup` label
   - Stops: `db_prod`, `windmill-db-prod`, `storage_prod`
   - Ensures database consistency

2. **Backup Creation:** Creates compressed archive of all mounted volumes
   - Format: `backup-YYYY-MM-DDTHH-MM-SS.tar.gz`
   - Compression: gzip

3. **Upload:** Uploads archive to Hetzner S3
   - Path: `/agent-os-backups/backup-[timestamp].tar.gz`
   - Transfer encrypted (HTTPS)

4. **Cleanup:** Deletes local backups older than 14 days
   - Keeps S3 backups for 14 days
   - Automatic pruning

5. **Post-Backup:** Restarts stopped services
   - Downtime: ~2-5 minutes at 3 AM

### Weekly Server Snapshots (Hetzner)

- Full server disk snapshot
- Includes OS, Docker, all configurations
- Keeps 7 snapshots (1 month rotation)
- Used for disaster recovery

---

## Cost Breakdown

| Item | Cost/Month | Notes |
|------|------------|-------|
| Hetzner Object Storage | €4.99 | 1TB storage + 1TB egress included |
| Hetzner Server Snapshots | €4-8 | ~20% of VPS cost |
| **Total** | **€10-13** | Depends on VPS size |

---

## Testing

After deployment, test the backup:

```bash
# SSH to production server

# Trigger immediate backup
docker exec volume-backup-prod backup

# Check logs
docker logs volume-backup-prod --tail 50

# Verify in Hetzner console
# → Object Storage → agent-os-backups
# → Should see backup-[timestamp].tar.gz file
```

---

## Restoration

### Quick Restore (Single Volume)

```bash
# 1. Download backup from S3
# 2. Extract backup archive
# 3. Stop service
# 4. Restore volume data
# 5. Restart service
```

See `BACKUP_STRATEGY.md` for detailed procedures.

### Full Disaster Recovery

1. Create new server from Hetzner snapshot
2. Download latest backup from S3
3. Restore volumes if snapshot >1 day old
4. Update DNS/IP if changed

Recovery time: ~30-60 minutes

---

## Monitoring

### Weekly Check (5 minutes)

```bash
# SSH to server
docker logs volume-backup-prod --tail 50

# Look for: "Backup completed successfully"
# Verify: Recent timestamp
# Check: No errors
```

### Monthly Full Test

- [ ] Download backup from S3
- [ ] Verify archive integrity
- [ ] Extract and spot-check files
- [ ] Document test results

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│           3 AM Daily (Automated)                     │
│                                                      │
│  1. Stop Critical Services                          │
│     └─ db_prod, windmill-db-prod, storage_prod     │
│                                                      │
│  2. Create Backup Archive                           │
│     └─ /backup/supabase-db-data                     │
│     └─ /backup/supabase-storage                     │
│     └─ /backup/n8n_storage                          │
│     └─ /backup/langconnect_storage                  │
│     └─ /backup/mcp_server_storage                   │
│     └─ /backup/windmill_db_data                     │
│     └─ /backup/db-config                            │
│                                                      │
│  3. Compress (gzip)                                 │
│     └─ backup-2025-11-16T03-00-00.tar.gz           │
│                                                      │
│  4. Upload to Hetzner S3                            │
│     └─ s3://agent-os-backups/backup-*.tar.gz       │
│                                                      │
│  5. Prune Old Backups (>14 days)                    │
│                                                      │
│  6. Restart Stopped Services                        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│           Weekly (Hetzner Automatic)                 │
│                                                      │
│  1. Pause Server (optional)                         │
│  2. Create Full Disk Snapshot                       │
│  3. Resume Server                                   │
│  4. Rotate Old Snapshots (keep 7)                   │
└─────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Follow `BACKUP_IMPLEMENTATION_GUIDE.md`** for step-by-step setup
2. **Test first backup** after deployment
3. **Schedule monthly restoration test** to verify backups work
4. **Document recovery procedures** specific to your team

---

## Files Modified/Created

```
Modified:
  docker-compose.production.yml

Created:
  .env.production.backup.example
  BACKUP_IMPLEMENTATION_GUIDE.md
  BACKUP_STRATEGY.md
  BACKUP_CHANGES_SUMMARY.md
```

---

## Support & Resources

- **Quick Start:** `BACKUP_IMPLEMENTATION_GUIDE.md`
- **Full Documentation:** `BACKUP_STRATEGY.md`
- **offen/docker-volume-backup:** https://github.com/offen/docker-volume-backup
- **Hetzner Object Storage:** https://docs.hetzner.com/storage/object-storage/
- **Hetzner Snapshots:** https://docs.hetzner.com/cloud/servers/backups-snapshots/

---

**Prepared by:** Claude Code
**Date:** 2025-11-16
**Status:** ✅ Ready for Production Deployment

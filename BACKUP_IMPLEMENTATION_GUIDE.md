# Backup Implementation Guide - Quick Start

**For:** Agent OS Production Deployment on Self-Hosted Coolify
**Time Required:** ~30 minutes
**Cost:** €10-13/month

---

## Overview

This guide implements automated backups for your production deployment using:
1. **offen/docker-volume-backup** - Backs up databases + volumes to Hetzner S3 (daily at 3 AM)
2. **Hetzner Snapshots** - Full server snapshots for disaster recovery (weekly)

---

## Step 1: Set Up Hetzner Object Storage (10 minutes)

### 1.1 Create Storage Bucket

1. Log into **Hetzner Cloud Console**: https://console.hetzner.cloud/
2. Navigate to **Object Storage** (left sidebar)
3. Click **"Create Bucket"**
4. Configure:
   - **Name:** `agent-os-backups`
   - **Location:** `eu-central` (same as your VPS - free data transfer)
5. Click **"Create & Buy now"**
   - Cost: **€4.99/month** (includes 1TB storage + 1TB egress)

### 1.2 Generate S3 Credentials

1. Click on your newly created bucket
2. Go to **"S3 Credentials"** tab
3. Click **"Generate credentials"** or **"Create access key"**
4. **IMMEDIATELY COPY** (shown only once):
   ```
   Access Key ID: XXXXXXXXXXXXXXXXXXXX
   Secret Access Key: YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
   ```
5. Save these in your **password manager** or secure notes

### 1.3 Note the S3 Endpoint

1. In the bucket details, find the **"Endpoint"** URL
2. Should look like: `https://fsn1.your-objectstorage.com` or similar
3. Copy this URL

**Checkpoint:**
- [ ] Bucket `agent-os-backups` created
- [ ] Access Key ID saved securely
- [ ] Secret Access Key saved securely
- [ ] S3 Endpoint URL copied

---

## Step 2: Add Backup Configuration to Coolify (10 minutes)

### 2.1 Add Environment Variables in Coolify

1. **In Coolify Dashboard**, navigate to your **Agent OS project**
2. Go to **"Environment Variables"** or **"Configuration"**
3. Add these 4 variables:

```bash
BACKUP_S3_BUCKET_NAME=agent-os-backups

BACKUP_S3_ENDPOINT=https://fsn1.your-objectstorage.com
# ↑ Replace with YOUR endpoint from Step 1.3

BACKUP_S3_ACCESS_KEY_ID=XXXXXXXXXXXXXXXXXXXX
# ↑ Replace with YOUR access key from Step 1.2

BACKUP_S3_SECRET_ACCESS_KEY=YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
# ↑ Replace with YOUR secret key from Step 1.2
```

4. **Save** the environment variables

### 2.2 Verify Variables Are Set

1. In Coolify, check that all 4 variables appear in your project's environment
2. They should be marked as "set" or show placeholder values (Coolify hides secrets)

**Checkpoint:**
- [ ] All 4 BACKUP_S3_* variables added to Coolify
- [ ] Variables saved successfully

---

## Step 3: Deploy Updated Configuration (5 minutes)

### 3.1 Commit and Push Changes

The docker-compose.production.yml has already been updated with:
- ✅ `volume-backup` service configured
- ✅ Labels added to `db_prod`, `windmill-db-prod`, `storage_prod`

Commit these changes to your repository:

```bash
cd /Users/lucelsby/Documents/repos/e18/e18-agent-os

git add docker-compose.production.yml
git commit -m "feat: Add automated backup service with Hetzner S3

- Add offen/docker-volume-backup service for daily backups
- Configure backup of all critical volumes and databases
- Add stop-during-backup labels for data consistency
- Set 14-day retention policy
- Schedule daily backups at 3 AM UTC"

git push origin main
```

### 3.2 Redeploy in Coolify

1. **In Coolify**, go to your Agent OS project
2. Click **"Redeploy"** or **"Deploy"** button
3. Wait for deployment to complete (~2-5 minutes)
4. Verify all services start successfully

**Checkpoint:**
- [ ] Changes committed to git
- [ ] Changes pushed to repository
- [ ] Coolify redeployment successful
- [ ] All services running (check logs)

---

## Step 4: Test the Backup (5 minutes)

### 4.1 Trigger Manual Backup

SSH into your production server or use Coolify's terminal:

```bash
# Trigger an immediate backup (don't wait for 3 AM cron)
docker exec volume-backup-prod backup
```

You should see output like:
```
INFO: Starting backup...
INFO: Stopping containers with label docker-volume-backup.stop-during-backup=true
INFO: Stopped: supabase-db, windmill-db-prod, supabase-storage-prod
INFO: Creating backup archive...
INFO: Backup created: backup-2025-11-16T14-30-00.tar.gz
INFO: Uploading to S3...
INFO: Upload successful
INFO: Restarting stopped containers...
INFO: Backup completed successfully
```

### 4.2 Verify Backup in Hetzner S3

1. Go back to **Hetzner Cloud Console** → **Object Storage**
2. Click on `agent-os-backups` bucket
3. **Browse files** - you should see:
   ```
   /agent-os-backups/backup-2025-11-16T14-30-00.tar.gz
   ```
4. Check file size (should be several hundred MB to a few GB depending on your data)

### 4.3 Check Backup Logs

```bash
# View backup container logs
docker logs volume-backup-prod

# Should show successful backup execution
```

**Checkpoint:**
- [ ] Manual backup triggered successfully
- [ ] Backup file appears in Hetzner S3 bucket
- [ ] File size looks reasonable (>0 bytes)
- [ ] All services restarted after backup

---

## Step 5: Enable Hetzner Server Snapshots (5 minutes)

### 5.1 Enable Automatic Backups

1. **In Hetzner Cloud Console**, navigate to **Servers**
2. Click on your **VPS running Coolify/Agent OS**
3. Go to **"Backups"** tab or section
4. Click **"Enable Backups"**
5. Configure:
   - **Backup window:** Select a time (e.g., Sunday 4-6 AM)
   - **Retention:** Automatic (keeps 7 snapshots, rotates oldest)
6. Review cost: ~20% of your server's monthly cost (€4-8 for typical VPS)
7. Click **"Enable"** or **"Confirm"**

### 5.2 Wait for First Snapshot

- First snapshot will be created during the next backup window
- You'll receive an email notification when it's ready
- Snapshots appear in the "Snapshots" section of your server

**Checkpoint:**
- [ ] Hetzner Backups enabled on production VPS
- [ ] Backup window configured
- [ ] Cost confirmed and acceptable

---

## ✅ Implementation Complete!

Your backup system is now active:

| What | When | Where | Cost |
|------|------|-------|------|
| **Automated Backups** | Daily 3 AM UTC | Hetzner S3 | €4.99/mo |
| **Server Snapshots** | Weekly (your window) | Hetzner Cloud | €4-8/mo |
| **Retention** | 14 days (volumes), 7 snapshots (server) | - | - |
| **Total Cost** | - | - | **€10-13/mo** |

---

## Next Steps

### 1. Set Up Monitoring (Optional but Recommended)

Add a calendar reminder or monitoring:

```bash
# Check backups weekly
Every Monday:
1. SSH to server
2. Run: docker logs volume-backup-prod --tail 50
3. Verify last backup succeeded
4. Check Hetzner S3 bucket has recent files
```

### 2. Test Restoration (Within 1 Month)

Schedule time to test backup restoration:
- [ ] Download a backup from S3
- [ ] Extract locally to verify contents
- [ ] Optional: Restore to test environment

See `BACKUP_STRATEGY.md` Section "Testing Your Backups" for detailed procedures.

### 3. Document Your Setup

Save this information securely:

```
PRODUCTION BACKUP CONFIGURATION
================================
S3 Bucket: agent-os-backups
S3 Region: eu-central
Backup Schedule: Daily 3 AM UTC
Retention: 14 days
Server Snapshots: Weekly [your day/time]

Access Key ID: [in password manager]
Secret Access Key: [in password manager]
S3 Endpoint: [your endpoint]

Last Tested: [date]
Next Test Due: [date + 30 days]
```

---

## Troubleshooting

### Backup Container Not Starting

```bash
# Check logs
docker logs volume-backup-prod

# Common issues:
# 1. S3 credentials incorrect → verify in Coolify env vars
# 2. S3 endpoint wrong → check Hetzner console for correct URL
# 3. Bucket doesn't exist → create in Hetzner console
```

### Backup Failing with "Access Denied"

```bash
# Test S3 connectivity from server
docker run --rm \
  -e AWS_ACCESS_KEY_ID=$BACKUP_S3_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$BACKUP_S3_SECRET_ACCESS_KEY \
  amazon/aws-cli \
  s3 ls s3://agent-os-backups --endpoint-url $BACKUP_S3_ENDPOINT

# Should list bucket contents
# If error: check credentials are correct
```

### Containers Not Restarting After Backup

```bash
# Manually restart stopped services
docker start supabase-db windmill-db-prod supabase-storage-prod

# Check backup logs for errors
docker logs volume-backup-prod | grep ERROR
```

### Backup File Size is 0 Bytes

```bash
# Volumes might be empty or mount points incorrect
# Verify volumes exist and have data:
docker volume ls | grep -E '(supabase|windmill|n8n|langconnect|mcp)'

# Inspect a volume
docker run --rm -v supabase-db-data:/data alpine ls -lah /data
```

---

## Recovery Procedures

### Quick Recovery (Single File/Volume)

See `BACKUP_STRATEGY.md` → "Recovery Scenarios" for detailed procedures.

### Full Disaster Recovery

If server is completely lost:

1. **Create new server from Hetzner snapshot**
   - Hetzner Console → Snapshots → Create Server
2. **Download latest backup from S3**
3. **Restore volumes** (if snapshot is >1 day old)
4. **Update DNS/IP** if changed
5. **Verify all services**

Estimated recovery time: **30-60 minutes**

---

## Support

- **Backup Strategy Full Docs:** `BACKUP_STRATEGY.md`
- **offen/docker-volume-backup Docs:** https://github.com/offen/docker-volume-backup
- **Hetzner Object Storage Docs:** https://docs.hetzner.com/storage/object-storage/
- **Hetzner Snapshots Docs:** https://docs.hetzner.com/cloud/servers/backups-snapshots/

---

**Last Updated:** 2025-11-16
**Next Review:** After first successful backup test

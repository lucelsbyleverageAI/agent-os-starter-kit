# Backup System - Deployment Checklist

**Branch:** `feature/automated-backups`
**Status:** Ready for testing

---

## Pre-Deployment: Set Up Hetzner S3 (10 minutes)

### 1. Create Hetzner Object Storage Bucket

- [ ] Log into Hetzner Cloud Console: https://console.hetzner.cloud/
- [ ] Navigate to **Object Storage** (left sidebar)
- [ ] Click **"Create Bucket"**
- [ ] Configure:
  - Name: `agent-os-backups`
  - Location: `eu-central` (same as your VPS)
- [ ] Click **"Create & Buy now"** (Cost: €4.99/month)

### 2. Generate S3 Credentials

- [ ] Click on the `agent-os-backups` bucket
- [ ] Go to **"S3 Credentials"** tab
- [ ] Click **"Generate credentials"** or **"Create access key"**
- [ ] **COPY IMMEDIATELY** (shown only once):
  ```
  Access Key ID: ____________________________________
  Secret Access Key: ____________________________________
  ```
- [ ] Save in password manager or secure notes

### 3. Note S3 Endpoint

- [ ] In bucket details, find **"Endpoint"** URL
- [ ] Copy endpoint (e.g., `https://fsn1.your-objectstorage.com`)
- [ ] Endpoint: ____________________________________

---

## Deployment: Configure Coolify (10 minutes)

### 1. Switch Coolify to Feature Branch

- [ ] In Coolify dashboard, go to your **Agent OS project**
- [ ] Find **"Git"** or **"Source"** settings
- [ ] Change branch from `main` to `feature/automated-backups`
- [ ] Save changes

### 2. Add Environment Variables

In Coolify, add these 4 environment variables:

```bash
BACKUP_S3_BUCKET_NAME=agent-os-backups

BACKUP_S3_ENDPOINT=https://[YOUR_ENDPOINT_FROM_STEP_3]

BACKUP_S3_ACCESS_KEY_ID=[YOUR_ACCESS_KEY_FROM_STEP_2]

BACKUP_S3_SECRET_ACCESS_KEY=[YOUR_SECRET_KEY_FROM_STEP_2]
```

- [ ] `BACKUP_S3_BUCKET_NAME` added
- [ ] `BACKUP_S3_ENDPOINT` added (with YOUR endpoint)
- [ ] `BACKUP_S3_ACCESS_KEY_ID` added (with YOUR key)
- [ ] `BACKUP_S3_SECRET_ACCESS_KEY` added (with YOUR secret)
- [ ] All variables saved

### 3. Deploy

- [ ] In Coolify, click **"Redeploy"** or **"Deploy"** button
- [ ] Wait for deployment to complete (~2-5 minutes)
- [ ] Verify no errors in deployment logs
- [ ] Check all services are running (green status)

---

## Testing: Verify Backup Works (10 minutes)

### 1. SSH into Production Server

```bash
ssh [your-production-server]
```

### 2. Verify Backup Container is Running

```bash
docker ps | grep volume-backup

# Should show:
# volume-backup-prod   offen/docker-volume-backup:latest   Up X minutes
```

- [ ] Backup container is running

### 3. Check Container Logs

```bash
docker logs volume-backup-prod

# Should show:
# - Container started
# - Cron schedule registered: 0 3 * * *
# - No errors
```

- [ ] No errors in logs
- [ ] Cron schedule shows: `0 3 * * *`

### 4. Trigger Manual Test Backup

```bash
# Trigger immediate backup (don't wait for 3 AM)
docker exec volume-backup-prod backup
```

**Expected output:**
```
INFO: Starting backup...
INFO: Stopping containers with label docker-volume-backup.stop-during-backup=true
INFO: Stopped: supabase-db, windmill-db-prod, supabase-storage-prod
INFO: Creating backup archive...
INFO: Compressing with gzip...
INFO: Backup created: backup-2025-11-16T[timestamp].tar.gz (size: XXX MB)
INFO: Uploading to S3: s3://agent-os-backups/agent-os-backups/backup-[timestamp].tar.gz
INFO: Upload complete
INFO: Restarting stopped containers...
INFO: Backup completed successfully in X seconds
```

- [ ] Backup started successfully
- [ ] Containers stopped (db_prod, windmill-db-prod, storage_prod)
- [ ] Archive created (size >0 MB)
- [ ] Upload to S3 successful
- [ ] Containers restarted
- [ ] **No errors**

### 5. Verify Backup in Hetzner S3

- [ ] Go to Hetzner Cloud Console → Object Storage
- [ ] Click on `agent-os-backups` bucket
- [ ] Click **"Browse files"** or **"Files"**
- [ ] Verify you see: `/agent-os-backups/backup-2025-11-16T[timestamp].tar.gz`
- [ ] Check file size (should be several hundred MB to a few GB)
- [ ] File size: __________ MB/GB

### 6. Verify All Services Are Back Online

```bash
# Check all containers are running
docker ps

# Verify critical services
docker ps | grep -E "(supabase-db|windmill-db-prod|supabase-storage-prod)"

# All 3 should show "Up" status
```

- [ ] `supabase-db` is running (Up X minutes)
- [ ] `windmill-db-prod` is running (Up X minutes)
- [ ] `supabase-storage-prod` is running (Up X minutes)

### 7. Test Application Functionality

- [ ] Visit your application frontend (https://app.e18-apps.com or your domain)
- [ ] Log in successfully
- [ ] Verify database is accessible (data loads)
- [ ] No errors or issues

---

## Post-Testing: Enable Server Snapshots (5 minutes)

### 1. Enable Hetzner Backups

- [ ] In Hetzner Cloud Console, go to **Servers**
- [ ] Click on your production VPS
- [ ] Go to **"Backups"** tab
- [ ] Click **"Enable Backups"**
- [ ] Configure backup window (e.g., Sunday 4 AM)
- [ ] Review cost (~€4-8/month, ~20% of VPS cost)
- [ ] Click **"Enable"**
- [ ] First snapshot will be created in next backup window

---

## Success Criteria ✅

All of these should be true:

- [ ] Hetzner S3 bucket created and accessible
- [ ] 4 environment variables added to Coolify
- [ ] Feature branch deployed successfully
- [ ] Backup container running without errors
- [ ] Manual test backup completed successfully
- [ ] Backup file appears in Hetzner S3 bucket
- [ ] Backup file size is reasonable (>100 MB)
- [ ] All services restarted after backup
- [ ] Application is functioning normally
- [ ] Hetzner server backups enabled

---

## Troubleshooting

### Backup Container Not Starting

```bash
# Check logs for errors
docker logs volume-backup-prod

# Common issues:
# 1. Missing environment variables → Check Coolify env vars
# 2. Invalid S3 credentials → Verify in Hetzner console
# 3. Wrong S3 endpoint → Check endpoint URL format
```

### "Access Denied" Error During Upload

```bash
# Test S3 connectivity manually
docker run --rm \
  -e AWS_ACCESS_KEY_ID=$BACKUP_S3_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$BACKUP_S3_SECRET_ACCESS_KEY \
  amazon/aws-cli \
  s3 ls s3://agent-os-backups --endpoint-url $BACKUP_S3_ENDPOINT

# Should list bucket contents or create bucket
# If error: credentials or endpoint are incorrect
```

### Containers Don't Restart After Backup

```bash
# Manually restart
docker start supabase-db windmill-db-prod supabase-storage-prod

# Check why backup script failed to restart them
docker logs volume-backup-prod | tail -50
```

### Backup File is 0 Bytes or Missing

```bash
# Check volumes exist and have data
docker volume ls | grep -E '(supabase|windmill|n8n|langconnect|mcp)'

# Inspect volume contents
docker run --rm -v supabase-db-data:/data alpine ls -lah /data
# Should show files, not empty
```

---

## Rollback Plan (If Issues)

If testing fails and you need to rollback:

### 1. Switch Back to Main Branch in Coolify

- [ ] Coolify → Project → Git Settings
- [ ] Change branch to `main`
- [ ] Redeploy

### 2. Remove Environment Variables (Optional)

- [ ] Remove the 4 `BACKUP_S3_*` variables from Coolify
- [ ] They won't cause issues if left (just unused)

### 3. Verify Application Works

- [ ] Check all services running
- [ ] Test application functionality

---

## Next Steps After Successful Testing

### 1. Merge to Main (After Confirming It Works)

```bash
# Locally
git checkout main
git merge feature/automated-backups
git push origin main

# Then update Coolify branch back to 'main'
```

### 2. Schedule Monthly Backup Test

- [ ] Add calendar reminder for 1 month from now
- [ ] Test: Download backup from S3, verify integrity
- [ ] Document: Update test date in BACKUP_STRATEGY.md

### 3. Document Your Configuration

Save this information securely:

```
PRODUCTION BACKUP CONFIGURATION
================================
Branch: feature/automated-backups (testing) → main (after merge)
S3 Bucket: agent-os-backups
S3 Region: eu-central
S3 Endpoint: [your endpoint]

Backup Schedule: Daily 3 AM UTC
Retention: 14 days
Server Snapshots: Weekly [day/time you chose]

First Backup: [date/time]
Last Tested: [date]
Next Test Due: [date + 30 days]

Hetzner Account: [your account email]
S3 Credentials: [stored in password manager]
```

---

## Support

**Questions during deployment?**
- Check `BACKUP_IMPLEMENTATION_GUIDE.md` for detailed steps
- Check `BACKUP_STRATEGY.md` for troubleshooting
- Review logs: `docker logs volume-backup-prod`

**After successful deployment:**
- Set up monitoring (weekly log checks)
- Test restoration within 30 days
- Document your specific recovery procedures

---

**Last Updated:** 2025-11-16
**Branch:** `feature/automated-backups`
**Status:** 🧪 Ready for Testing

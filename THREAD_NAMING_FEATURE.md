# AI Thread Naming & Summarization Feature

## Overview

This feature implements automatic AI-powered thread naming and summarization using GPT-4o-mini. Threads are automatically named at specific message intervals, providing users with meaningful conversation titles without manual effort.

## Key Features

✅ **Automatic Naming** - Threads are named at messages 1, 5, 10, 15, 20... (every 5 messages)
✅ **User Intent Protection** - User-renamed threads are never overwritten by AI
✅ **Background Processing** - Non-blocking, runs in background scheduler
✅ **Cost-Effective** - Uses GPT-4o-mini (~$0.0004 per thread naming)
✅ **Manual Regeneration** - Users can request AI naming via API endpoint
✅ **Detailed Summaries** - Generates paragraph-length conversation summaries

## Architecture

```
User Sends Message
    ↓
Thread Touch API
  - Increments message_count
  - Sets needs_naming flag (if count = 1, 5, 10, 15...)
  - Only if user_renamed = false
    ↓
Background Scheduler (30s interval)
  - Finds threads with needs_naming = true
  - Processes max 5 threads per batch
    ↓
Thread Naming Service
  1. Fetches messages from LangGraph
  2. Formats conversation for LLM
  3. Calls GPT-4o-mini with structured output
  4. Updates threads_mirror (name + summary)
    ↓
Frontend receives updated name via cache invalidation
```

## Database Schema Changes

New columns added to `threads_mirror` table:

```sql
message_count INTEGER DEFAULT 0
  - Tracks total messages for interval detection

needs_naming BOOLEAN DEFAULT true
  - Flag indicating thread needs AI processing

last_naming_at TIMESTAMPTZ
  - Prevents redundant processing (cooldown)

user_renamed BOOLEAN DEFAULT false
  - Protection flag - AI never overwrites when true
```

## Configuration

Environment variables in `.env.local`:

```bash
# Enable/disable the feature
THREAD_NAMING_ENABLED=true

# Model to use (gpt-4o-mini recommended for cost)
THREAD_NAMING_MODEL=gpt-4o-mini

# How often scheduler checks for threads (seconds)
THREAD_NAMING_INTERVAL_SECONDS=30

# Max threads to process per batch
THREAD_NAMING_BATCH_SIZE=5

# Minimum seconds between naming attempts for same thread
THREAD_NAMING_MIN_INTERVAL_SECONDS=60

# Required: OpenAI API key for naming
OPENAI_API_KEY=sk-your-api-key
```

## API Endpoints

### 1. Thread Touch (Existing, Modified)

**Endpoint:** `POST /api/langconnect/agents/mirror/threads/touch`

**Changes:**
- Now increments `message_count`
- Sets `needs_naming` flag at intervals (1, 5, 10, 15...)
- Respects `user_renamed` flag

**No API changes required** - existing frontend code continues to work.

### 2. Regenerate Thread Name (New)

**Endpoint:** `POST /api/langconnect/agents/mirror/threads/{thread_id}/regenerate-name`

**Purpose:** Allows users to manually request AI naming

**Authentication:** Requires user JWT (thread owner only)

**Response:**
```json
{
  "success": true,
  "thread_id": "uuid",
  "message": "Thread queued for AI naming. This may take a few moments."
}
```

**Behavior:**
- Queues thread for AI naming
- Resets `user_renamed` flag (allows AI naming again)
- Background job picks it up within 30 seconds

**Example Frontend Usage:**
```typescript
const regenerateName = async (threadId: string) => {
  const response = await fetchWithAuth(
    `/api/langconnect/agents/mirror/threads/${threadId}/regenerate-name`,
    { method: 'POST' }
  );

  if (response.ok) {
    // Optionally show toast: "Thread name is being regenerated..."
    // Name will update via cache invalidation within 30-60 seconds
  }
};
```

## User Rename Protection

The system automatically detects when users manually rename threads:

**Trigger Function:**
```sql
CREATE TRIGGER trigger_track_thread_rename
  BEFORE UPDATE ON threads_mirror
  FOR EACH ROW
  EXECUTE FUNCTION track_thread_rename();
```

**Behavior:**
- If `name` changes but `last_naming_at` unchanged → User renamed
- Sets `user_renamed = true` automatically
- Sets `needs_naming = false`
- AI will never overwrite this thread

**Reset Protection:**
- Only via `regenerate-name` endpoint
- Explicitly opts thread back into AI naming
- Resets `user_renamed = false`

## Message Intervals

Threads are renamed at these message counts:

| Message Count | Action |
|---------------|--------|
| 1 | First AI naming (initial conversation snapshot) |
| 5 | Second naming (conversation has developed) |
| 10 | Third naming |
| 15 | Fourth naming |
| 20+ | Every 5 messages thereafter |

**Rationale:**
- Message 1: Quick initial name from first exchange
- Message 5: Conversation topic clearer, better naming
- Every 5 after: Keep name updated as conversation evolves

## Testing

### Manual Testing Steps

1. **Start the platform:**
   ```bash
   make start-dev
   ```

2. **Verify migration applied:**
   ```bash
   # Check if new columns exist
   docker exec -it supabase-db psql -U postgres -d postgres -c "
     SELECT column_name, data_type
     FROM information_schema.columns
     WHERE table_schema = 'langconnect'
     AND table_name = 'threads_mirror'
     AND column_name IN ('message_count', 'needs_naming', 'user_renamed', 'last_naming_at');
   "
   ```

3. **Create a new thread:**
   - Navigate to chat interface
   - Send first message
   - Check logs: `docker logs langconnect -f`
   - Should see: `[threads:touch] thread_id=... message_count=1 needs_naming=true`

4. **Wait for AI naming (~30-60 seconds):**
   - Check scheduler logs: `docker logs langconnect -f | grep "thread naming"`
   - Should see: `"Thread naming completed: 1 succeeded, 0 failed"`

5. **Verify name updated:**
   - Query database:
     ```sql
     SELECT thread_id, name, summary, message_count, needs_naming, user_renamed
     FROM langconnect.threads_mirror
     ORDER BY created_at DESC
     LIMIT 1;
     ```
   - Or check frontend - thread should have AI-generated name

6. **Test user rename protection:**
   - Manually rename the thread in UI
   - Send 5 more messages (total = 6)
   - Verify AI does NOT rename it again
   - Check: `user_renamed` should be `true`

7. **Test regenerate endpoint:**
   ```bash
   # Get thread ID from database
   THREAD_ID="your-thread-uuid"

   # Call regenerate endpoint (requires JWT)
   curl -X POST "http://localhost:8080/mirror/threads/${THREAD_ID}/regenerate-name" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json"
   ```

### Monitoring

**LangConnect Logs:**
```bash
# Watch all thread naming activity
docker logs langconnect -f | grep -E "(threads:|Thread naming)"

# Example output:
# [threads:touch] actor=user-123 thread_id=abc... message_count=1
# Thread naming completed: 1 succeeded, 0 failed
# [threads:touch] actor=user-123 thread_id=abc... message_count=5
# Generated name: 'AI Integration Discussion' (summary length: 287 chars)
```

**Database Queries:**
```sql
-- Threads needing naming
SELECT thread_id, message_count, needs_naming, user_renamed, last_naming_at
FROM langconnect.threads_mirror
WHERE needs_naming = true AND user_renamed = false;

-- Recently named threads
SELECT thread_id, name, summary, message_count, last_naming_at
FROM langconnect.threads_mirror
WHERE last_naming_at > NOW() - INTERVAL '1 hour'
ORDER BY last_naming_at DESC;

-- User-renamed threads (protected from AI)
SELECT thread_id, name, user_renamed, message_count
FROM langconnect.threads_mirror
WHERE user_renamed = true;
```

## Cost Estimation

Using **GPT-4o-mini** (as of 2025):
- Input: $0.150 / 1M tokens
- Output: $0.600 / 1M tokens

**Per Thread Naming:**
- Average input: ~2,000 tokens (10-message conversation)
- Average output: ~100 tokens (name + summary)
- Cost: $0.0004 per naming

**Example Usage:**
- 100 threads/day
- 3 renamings per thread (messages 1, 5, 10)
- 300 naming operations × $0.0004 = **$0.12/day**
- **Monthly cost: ~$3.60**

Extremely cost-effective!

## Troubleshooting

### Threads not being named

**Check 1: Feature enabled?**
```bash
docker exec langconnect env | grep THREAD_NAMING_ENABLED
# Should output: THREAD_NAMING_ENABLED=true
```

**Check 2: OpenAI API key configured?**
```bash
docker exec langconnect env | grep OPENAI_API_KEY
# Should output: OPENAI_API_KEY=sk-...
```

**Check 3: Scheduler running?**
```bash
docker logs langconnect 2>&1 | grep "Sync scheduler initialized"
# Should see: thread_naming=30s
```

**Check 4: Database flags correct?**
```sql
SELECT thread_id, needs_naming, user_renamed, last_naming_at
FROM langconnect.threads_mirror
WHERE thread_id = 'your-thread-uuid';
```

Expected:
- `needs_naming = true` (if at interval)
- `user_renamed = false` (if not manually renamed)
- `last_naming_at = NULL` (if never named) or `< NOW() - 60 seconds`

### Names not appearing in UI

**Check 1: Cache version incremented?**
```sql
SELECT threads_version FROM langconnect.cache_state WHERE id = 1;
```

**Check 2: Frontend polling?**
- Thread sidebar should refresh on `refreshThreads` event
- Check browser console for event dispatch

### AI naming quality issues

**Issue:** Names too generic ("New Conversation", "Chat Thread")

**Solution:** Adjust system prompt in `thread_naming_service.py`:
```python
"role": "system",
"content": (
    "You are a conversation summarizer. Focus on SPECIFIC topics and key details. "
    "Avoid generic names. Make names descriptive and unique."
)
```

**Issue:** Names too long

**Solution:** Enforce stricter length in prompt:
```python
"1. A very concise name (EXACTLY 3-5 words, no more)"
```

## Migration Notes

### Existing Threads

The migration automatically:
- Marks all existing named threads as `user_renamed = true`
- Protects them from AI overwrites
- Excludes default names like "New Thread"

### Rollback

To disable without code changes:
```bash
# In .env.local
THREAD_NAMING_ENABLED=false
```

To fully rollback schema:
```sql
ALTER TABLE langconnect.threads_mirror
DROP COLUMN IF EXISTS message_count,
DROP COLUMN IF EXISTS needs_naming,
DROP COLUMN IF EXISTS last_naming_at,
DROP COLUMN IF EXISTS user_renamed;

DROP TRIGGER IF EXISTS trigger_track_thread_rename ON langconnect.threads_mirror;
DROP FUNCTION IF EXISTS langconnect.track_thread_rename();
```

## Future Enhancements

**Potential improvements:**

1. **Summary UI Display**
   - Show full summary on thread hover
   - Display in thread metadata modal

2. **User Preferences**
   - Per-user toggle for AI naming
   - Preferred naming intervals

3. **Multi-language Support**
   - Detect conversation language
   - Generate names in user's language

4. **Name History**
   - Store previous AI-generated names
   - Allow users to revert to earlier names

5. **Custom Prompts**
   - Admin-configurable naming prompts
   - Domain-specific naming styles

6. **Rate Limiting**
   - Limit regenerate endpoint calls per user
   - Prevent API abuse

## Files Changed

### New Files
- `database/migrations/lanconnect/004_add_thread_naming_fields.sql` - Migration
- `apps/langconnect/langconnect/services/thread_naming_service.py` - Service
- `THREAD_NAMING_FEATURE.md` - This documentation

### Modified Files
- `apps/langconnect/langconnect/api/mirror_apis.py`
  - Updated `touch_thread_in_mirror()` to track message counts
  - Added `regenerate_thread_name()` endpoint
- `apps/langconnect/langconnect/services/sync_scheduler.py`
  - Added `_run_thread_naming()` background job
  - Added configuration for naming interval
- `.env.local.example`
  - Added thread naming configuration section

## Support

For issues or questions:
1. Check logs: `docker logs langconnect -f`
2. Verify database state with SQL queries above
3. Test with `THREAD_NAMING_ENABLED=false` to isolate issue
4. Review OpenAI API usage: https://platform.openai.com/usage

## License

This feature is part of the Agent OS Starter Kit and follows the same license as the main project.

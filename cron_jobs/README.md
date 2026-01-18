# CRON Jobs

This folder contains Python scripts that can be executed as CRON jobs.

## Setup Instructions

### 1. Make scripts executable

```bash
chmod +x cron_jobs/*.py
```

### 2. Set up CRON job

Edit your crontab:
```bash
crontab -e
```

### 3. Add CRON job entry

Example CRON job entries:

```bash
# Run a job every day at 2:00 AM
0 2 * * * cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend && /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/example_job.py >> cron_jobs/logs/cron_output.log 2>&1

# Run a job every hour
0 * * * * cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend && /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/example_job.py >> cron_jobs/logs/cron_output.log 2>&1

# Run a job every 30 minutes
*/30 * * * * cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend && /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/example_job.py >> cron_jobs/logs/cron_output.log 2>&1

# Run a job every Monday at 9:00 AM
0 9 * * 1 cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend && /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/example_job.py >> cron_jobs/logs/cron_output.log 2>&1
```

### CRON Schedule Format

```
* * * * *
│ │ │ │ │
│ │ │ │ └─── Day of week (0-7, where 0 and 7 are Sunday)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

### Important Notes

1. **Use absolute paths**: Always use absolute paths in CRON jobs since CRON runs with a minimal environment.

2. **Activate virtual environment**: Use the full path to the Python interpreter in your virtual environment, or activate it explicitly:
   ```bash
   /path/to/venv/bin/python cron_jobs/your_script.py
   ```

3. **Set working directory**: Use `cd` to set the working directory before running the script.

4. **Logging**: Scripts should log to files in the `logs/` directory. CRON output is also redirected to log files.

5. **Environment variables**: If your scripts need environment variables, either:
   - Load them from a `.env` file in the script
   - Set them in the CRON job entry:
     ```bash
     0 2 * * * cd /path/to/project && export VAR_NAME=value && /path/to/python script.py
     ```

6. **Test your script**: Before adding to CRON, test it manually:
   ```bash
   cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend
   /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/example_job.py
   ```

## Viewing CRON Logs

Check CRON execution logs:
```bash
# View system CRON logs (macOS)
log show --predicate 'process == "cron"' --last 1h

# View your script logs
tail -f cron_jobs/logs/cron_job_*.log
```

## Listing Active CRON Jobs

```bash
crontab -l
```

## Removing CRON Jobs

```bash
crontab -e  # Then remove or comment out the line
```

## Available CRON Jobs

### send_meal_messages_to_slack.py

Generates and sends meal messages to Slack for all active users with active meal plans.

**What it does:**
- Fetches all active users with active meal plans for today
- For each user, generates messages for breakfast, lunch, snacks, and dinner
- If user has a cook with non-English language, includes translated text and voice note
- Sends formatted messages to Slack webhook

**Message format:**
```
user_id: <user_id>
user_name: <user_name>
meal_type: <breakfast|lunch|snacks|dinner>

Today's <meal_type> is <meal_items>

[Translated text if cook has non-English language]

[Voice Note: Download MP3 link if generated and uploaded]
```

**Required environment variables:**
- `SLACK_WEBHOOK_URL`: Slack webhook URL for sending messages
- Standard Supabase and other service credentials (from `.env` file)

**Optional environment variables (for voice note uploads):**
- `SLACK_BOT_TOKEN`: Slack bot token (xoxb-...) for uploading MP3 files via Files API (recommended)
- `SLACK_CHANNEL`: Optional Slack channel ID to post voice notes to
- `GCS_BUCKET_NAME`: Google Cloud Storage bucket name (fallback if Slack Files API not available)

**Note on voice notes:**
- Slack webhooks cannot upload files directly
- If `SLACK_BOT_TOKEN` is provided, voice notes will be uploaded via Slack Files API
- If not, voice notes will be uploaded to Google Cloud Storage (if `GCS_BUCKET_NAME` is set)
- If neither is available, voice note info will be included in the message but the file won't be uploaded

**Example CRON entry (run daily at 8:00 AM):**
```bash
0 8 * * * cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend && /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/send_meal_messages_to_slack.py >> cron_jobs/logs/meal_messages_slack.log 2>&1
```

**Test manually:**
```bash
cd /Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend
/Users/utkarshsharmagmail.com/Documents/projects/foodeasy-backend/venv/bin/python cron_jobs/send_meal_messages_to_slack.py
```

# Monarch API — persistent storage on Railway

The API saves users, login names, settings, balances, logs, progress, schedules,
positions, profit history, trades, and open-position chart data in
`monarch.sqlite3`. Updates commit before a successful response is returned.
SQLite is included with Python; no database dependency or separate database
service is required. The existing endpoint URLs and parameters are preserved.
Adding an existing user now returns `user already exists` instead of resetting
that user's data.

## Before your first deployment

The old API holds all data only in memory and has no complete export endpoint.
Attaching a volume or deploying this code does not copy that running memory.
If existing data matters, preserve/reconstruct it from your clients or another
source before restarting or deploying. Data already lost in an earlier restart
cannot be recovered by this change. A new volume starts with an empty database.

## Railway setup

1. Open the Railway project and the environment that hosts this API.
2. Right-click the project canvas (or open the command palette with Cmd+K),
   create a **Volume**, and attach it to the **API service**.
3. Set its mount path to **`/data`**. Mount the directory, not a filename.
4. Commit and push `Monarch_API.py`, `persistence.py`, `.gitignore`, this README,
   and `tests/test_persistence.py` to the GitHub branch Railway deploys.
5. Set the service's start command to **`python Monarch_API.py`**. Use one service
   replica and one worker so only one background market-data collector runs.
6. Apply the Railway changes/deploy. The volume must be attached when the new
   code starts. Do not initialize the database in a build or pre-deploy command.
7. Check deployment logs for **`Persistent storage: /data/monarch.sqlite3`**.
   Railway supplies `RAILWAY_VOLUME_MOUNT_PATH` automatically; do not manually
   set it. No other storage environment variable is needed.
8. Create a test user and change a setting or add a log. Restart the service,
   then log in and confirm the same data remains. Repeat with a redeploy if desired.
9. Enable a backup schedule under the service's **Backups** tab.

The code refuses to start when Railway's environment ID is present but its
volume mount variable is absent, rather than silently using temporary storage.
If startup reports a filesystem permission error because your image uses a
non-root user, Railway documents setting `RAILWAY_RUN_UID=0` for volume access.

## Files and backups

Railway retains files written inside the attached volume across restarts and
redeploys. Keep the same volume attached. Deleting/replacing that volume does
not preserve its data. The source code lives in GitHub; the database lives on
Railway and must not be committed to GitHub.

No manual file upload is needed for a new installation. To migrate a database
created by this version locally, stop writers first, then use Railway's volume
file browser/CLI to upload `data/monarch.sqlite3` as `/monarch.sqlite3` within the
volume before starting the API. Do not overwrite an existing production database
unless intentionally restoring/replacing it. Use Railway's volume backups for
routine backups rather than copying a database while requests are writing to it.

The database contains the existing user identifiers and account data. Treat
backup files as private. This update preserves the existing authentication model.

## Local development and checks

Locally, the database defaults to `data/monarch.sqlite3` beside the script. This
folder is ignored by Git. Run `python Monarch_API.py` as before.

Run tests with `python -m unittest discover -s tests -v` in your Python environment.
They cover a fresh process restart, persisted removal, duplicate-user protection,
failed-save rollback, sequential access from independent storage instances, and
Railway path configuration. Tests use temporary databases and disable the
background collector; they do not call market-data services.

This implementation stores a transactional snapshot of the dictionaries. It
suits a small API, but each update serializes the full state. If data or traffic
grows substantially, migrate to per-record database tables or PostgreSQL.
The existing daily reset function remains unstarted, as in the original script.

## Publishing Monarch software updates

`POST /update-software` accepts the existing admin `key` and a `new_version`
as query parameters. Its JSON body is a dictionary mapping these six filenames
to their complete UTF-8 text contents:

- `Monarch_V3.py`
- `claude_runtime.py`
- `buy_sell.py`
- `trade_journal.py`
- `Cali_System_Prompt.txt`
- `WatchdogSystemPrompt.txt`

The API validates the filenames, nonempty contents, and Python syntax without
executing the upload. It saves the version and contents together in
`software_update.json` beside `monarch.sqlite3`. On Railway this is
`/data/software_update.json` when the volume is mounted at `/data`. There is no
new database table, package, or storage service to configure. Keep the existing
volume attached across deployments. The version is read from this file rather
than a variable that resets when the API restarts.

To enable updates:

1. Deploy the updated `Monarch_API.py` to Railway. Confirm the API service has
   its existing persistent volume mounted at `/data` and logs
   `Persistent storage: /data/monarch.sqlite3`.
2. On the Mac, set the device paths in the scripts being published to the
   correct Jetson paths. Uploads install the exact source text; no path rewriting
   is performed. Keep the configured runtime and prompt locations stable across
   releases. The prompts are installed at the existing `CaliPromptPath` and
   `WDPromptPath`; Python files go beside the running `Monarch_V3.py`.
3. Install the updated `Monarch_Official/Monarch_V3.py` on the Jetson once,
   while Monarch is stopped, so it has the new updater. Preserve the Jetson's
   runtime JSON, `.env`, logs, and account settings.
4. Run `Update Software.py` from the project root on the Mac. The six source
   paths and API URL are at the top. Enter a new version such as `V3.1`, confirm
   with `Y`, and enter the admin key. Optionally set `MONARCH_ADMIN_KEY` in the
   publisher's environment to skip that last prompt. This is the API's existing
   admin key, not a Monarch user password.
5. Start/restart Monarch on the Jetson. Its startup check supplies its user
   password as `user` and its saved version as `local_version` to
   `GET /check-for-updates`. If the version differs, the response includes
   `Update_Available: true`, `version`, and `files`.

Monarch validates all six files first, stages them, and saves the previous files
in `software_update_backup` beside its script. It replaces the files, updates
only `Settings.Version` in the local runtime JSON, and restarts. A caught write
failure restores files already replaced. An unavailable API or invalid release
prints an update-skipped message and leaves Monarch running its installed version.
If restoration itself fails, startup stops and identifies the backup directory.
Backups contain the previous runtime data as well; keep them private.

The check runs at startup, before trading threads start; it does not interrupt
a running trading session when you publish. Use a different version for each
changed release. Re-uploading the identical release is allowed after a connection
timeout, but changing files under the same latest version is rejected. Version
comparison is equality, not numeric ordering, as requested.

The updater does not install new pip dependencies. Syntax validation cannot
prove that a release will run correctly, and it does not automatically roll back
application errors after restart. Retain the backup for manual recovery. File
replacement is atomic per file, not across the entire set in a sudden power loss.

Offline update tests live in the project root's `tests/test_software_updates.py`.
Run `python -m unittest discover -s tests -p test_software_updates.py -v` from the
project root. They use temporary files and a local test API, never the broker or
the deployed Railway service.

## Railway references

- [Using Volumes](https://docs.railway.com/volumes): creating/attaching volumes,
  mount paths, runtime variables, permissions, and runtime-only availability.
- [Volume backups](https://docs.railway.com/volumes/backups)
- [Railway volume CLI](https://docs.railway.com/cli/volume)

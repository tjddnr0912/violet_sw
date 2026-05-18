# Little Lion Phase 1c — Ops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the Phase 1a backend (+ Phase 1b PWA) as an always-on, remotely-reachable service on the user's M1 Max — survive reboots, auto-restart on crash, accessible from iPhone via Tailscale, with weekly LanceDB snapshots and a single-command healthcheck.

**Architecture:** macOS `launchd` keeps the backend alive. Tailscale exposes it on a private mesh. A small set of shell scripts handle ops chores: Ollama model pinning, LanceDB backup/restore, log rotation, vault conflict cleanup, token rotation. A `bin/healthcheck` script gates Phase 1 completion.

**Tech Stack:**
- macOS launchd (`~/Library/LaunchAgents/`)
- Tailscale (free tier)
- Bash 5+
- (optional, Phase 2) Cloudflare Tunnel

**Reference docs:**
- `docs/specs/2026-05-18-little-lion-personal-assistant-design.md` §9 Remote Access + §12 Risks
- `docs/specs/2026-05-18-little-lion-design-deep-dive.md` §8 Failure Modes

**Prerequisite:** Phase 1a + 1b complete; `./scripts/run_dev.sh` produces a working backend at `http://127.0.0.1:8765`.

**Working directory:** All commands assume CWD `/Users/seongwookjang/project/git/violet_sw/015_little_lion/`.

**Idiom for tasks in this plan:** Ops tasks rarely fit TDD. Each task is structured as **Configure → Install → Verify → Commit**, where "Verify" is an explicit shell command and expected output. Treat the verify step as the test gate.

---

## Task 1: launchd agent for always-on backend

**Files:**
- Create: `infra/launchd/com.violet.littlelion.plist`
- Create: `infra/launchd/install-agent.sh`
- Create: `infra/launchd/uninstall-agent.sh`

- [ ] **Step 1: Create `infra/launchd/com.violet.littlelion.plist`**

Use the project's installed Python path. The variable `<HOMEPATH>` and `<PROJECTPATH>` are placeholders the install script replaces.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
                       "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.violet.littlelion</string>

    <key>ProgramArguments</key>
    <array>
      <string>__PROJECTPATH__/.venv/bin/python</string>
      <string>-m</string>
      <string>backend.main</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__PROJECTPATH__</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
      <key>HOME</key>
      <string>__HOMEPATH__</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
      <key>SuccessfulExit</key>
      <false/>
      <key>Crashed</key>
      <true/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>__HOMEPATH__/Library/Logs/violet-littlelion.out.log</string>

    <key>StandardErrorPath</key>
    <string>__HOMEPATH__/Library/Logs/violet-littlelion.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>

    <key>Nice</key>
    <integer>5</integer>
  </dict>
</plist>
```

- [ ] **Step 2: Create `infra/launchd/install-agent.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOME_DIR="$HOME"
LABEL="com.violet.littlelion"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
SOURCE="$PROJECT_ROOT/infra/launchd/com.violet.littlelion.plist"

if [[ ! -f "$PROJECT_ROOT/.venv/bin/python" ]]; then
  echo "ERROR: .venv missing at $PROJECT_ROOT/.venv — run 'python -m venv .venv && pip install -e .[dev]' first" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

sed -e "s|__PROJECTPATH__|$PROJECT_ROOT|g" \
    -e "s|__HOMEPATH__|$HOME_DIR|g" \
    "$SOURCE" > "$TARGET"

# Reload if already present
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed launchd agent: $TARGET"
echo "Logs: $HOME/Library/Logs/violet-littlelion.{out,err}.log"
```

- [ ] **Step 3: Create `infra/launchd/uninstall-agent.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
LABEL="com.violet.littlelion"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Uninstalled."
```

- [ ] **Step 4: Make executable + install**

```bash
chmod +x infra/launchd/install-agent.sh infra/launchd/uninstall-agent.sh
./infra/launchd/install-agent.sh
```

- [ ] **Step 5: Verify**

Run (within 15s after install):
```bash
launchctl print "gui/$(id -u)/com.violet.littlelion" | grep -E "state|last exit code|pid"
curl -fsS http://127.0.0.1:8765/healthz
```
Expected: state is `running`, healthz returns `{"status":"ok"}`.

Then test crash recovery:
```bash
PID=$(launchctl print "gui/$(id -u)/com.violet.littlelion" | awk '/pid =/ {print $3}')
kill -9 "$PID"
sleep 12
curl -fsS http://127.0.0.1:8765/healthz
```
Expected: healthz still returns `{"status":"ok"}` (launchd restarted within ThrottleInterval).

- [ ] **Step 6: Commit**

```bash
git add infra/launchd/com.violet.littlelion.plist \
        infra/launchd/install-agent.sh \
        infra/launchd/uninstall-agent.sh
git commit -m "Add launchd agent: always-on backend with crash-only KeepAlive"
```

---

## Task 2: Tailscale install + access doc

**Files:**
- Create: `infra/tailscale-setup.md`
- Create: `infra/tailscale-firewall-check.sh`

- [ ] **Step 1: Create `infra/tailscale-setup.md`**

```markdown
# Tailscale Setup — Little Lion Remote Access

Goal: reach `http://<mac-name>:8765` from iPhone Safari (or any other Tailscale device) without exposing the port to the open internet.

## On the Mac (server)

1. Install Tailscale.app from https://tailscale.com/download/macos. Sign in.
2. Verify connectivity:
   ```bash
   tailscale status        # should list this Mac with a 100.x.y.z address
   tailscale ip -4         # prints the Mac's Tailscale IP
   ```
3. (Optional) Give the Mac a friendly hostname in the Tailscale admin console (e.g. `lion`). After that, MagicDNS resolves `lion` from any device.

## On the iPhone

1. Install Tailscale from the App Store. Sign in with the same account.
2. Open Tailscale, ensure VPN profile is enabled.
3. In Safari, navigate to `http://lion:8765` (or `http://<mac-tailscale-ip>:8765` if MagicDNS is off).
4. Continue per `docs/IOS_INSTALL.md` (paste BACKEND_AUTH_TOKEN, Add to Home Screen).

## Hardening (Phase 1 baseline)

The backend already binds to `127.0.0.1` by default; with Tailscale, we want it reachable on the Tailscale interface too. Two options:

- **Option A (recommended):** keep BACKEND_HOST=127.0.0.1 and use Tailscale's "Serve" feature:
  ```bash
  tailscale serve --bg --https=443 http://127.0.0.1:8765
  ```
  Pros: TLS termination by Tailscale, single command.
  Cons: requires Tailscale Funnel for non-Tailscale clients (we don't want that).

- **Option B:** bind backend to 0.0.0.0 but rely on Tailscale's network ACL to prevent LAN exposure:
  ```bash
  # in .env
  BACKEND_HOST=0.0.0.0
  ```
  Combined with a packet filter (`pf`) rule that only allows port 8765 from the Tailscale interface. Use `infra/tailscale-firewall-check.sh` to verify the rule is active.

For Phase 1, use **Option A**.

## Token-on-top defense

Even on Tailscale, the backend still requires the `BACKEND_AUTH_TOKEN` bearer. If you suspect token leakage, rotate via `infra/rotate-token.sh` (Task 7).
```

- [ ] **Step 2: Create `infra/tailscale-firewall-check.sh`** (Option B verifier)

```bash
#!/usr/bin/env bash
# Verifies that port 8765 is reachable on the Tailscale interface but blocked elsewhere.
# Best-effort: requires the Mac to be on Tailscale already.
set -euo pipefail

TS_IP=$(tailscale ip -4 2>/dev/null | head -1 || true)
if [[ -z "$TS_IP" ]]; then
  echo "FAIL: tailscale not configured."
  exit 1
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
echo "Tailscale IP: $TS_IP"
echo "LAN IP:       ${LAN_IP:-(none)}"

# Tailscale interface must respond on 8765
if ! curl -fsS --max-time 3 "http://$TS_IP:8765/healthz" >/dev/null; then
  echo "FAIL: backend not reachable on Tailscale interface."
  exit 1
fi
echo "OK: backend reachable on Tailscale."

# LAN interface must NOT respond (we don't want LAN devices to see it)
if [[ -n "$LAN_IP" ]]; then
  if curl -fsS --max-time 2 "http://$LAN_IP:8765/healthz" >/dev/null 2>&1; then
    echo "WARN: backend is also reachable on LAN ($LAN_IP). Consider binding to 127.0.0.1 + tailscale serve."
  else
    echo "OK: LAN does not see port 8765."
  fi
fi
```

- [ ] **Step 3: Make script executable + install Tailscale per doc**

```bash
chmod +x infra/tailscale-firewall-check.sh
# Follow infra/tailscale-setup.md to install and sign in on Mac + iPhone.
```

- [ ] **Step 4: Verify**

```bash
tailscale status
tailscale ip -4
./infra/tailscale-firewall-check.sh
```
Expected: status shows the Mac connected; firewall check prints `OK: backend reachable on Tailscale`.

Then from iPhone, open `http://lion:8765/healthz` in Safari — should return `{"status":"ok"}`.

- [ ] **Step 5: Commit**

```bash
git add infra/tailscale-setup.md infra/tailscale-firewall-check.sh
git commit -m "Add Tailscale setup doc + firewall reachability check"
```

---

## Task 3: Ollama model pin + ensure script

**Files:**
- Create: `ollama/models.yaml`
- Create: `ollama/ensure-models.sh`

- [ ] **Step 1: Create `ollama/models.yaml`** — single source of truth for pinned versions

```yaml
# Ollama model pins. Lock to specific tags so Phase 1 doesn't regress on
# upstream version bumps. See deep-dive §8 #6 for the embedding-dim migration
# protocol when these change.
models:
  - name: qwen2.5:14b           # Stage 3 default for rag / general reasoning
    purpose: general
    expected_size_gb: 9
  - name: qwen2.5-coder:7b      # Stage 3 default for code
    purpose: code
    expected_size_gb: 5
  - name: qwen2.5:0.5b          # Stage 2 classifier (router/classifier.py)
    purpose: classifier
    expected_size_gb: 0.5
  - name: nomic-embed-text      # RAG embeddings (768-dim)
    purpose: embedding
    expected_size_gb: 0.3
```

- [ ] **Step 2: Create `ollama/ensure-models.sh`**

```bash
#!/usr/bin/env bash
# Pulls every model listed in ollama/models.yaml that isn't already present.
# Run after a fresh install or after editing models.yaml.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v ollama >/dev/null; then
  echo "ERROR: ollama CLI not installed (brew install ollama)" >&2
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "ERROR: ollama server not running. Start with: ollama serve &" >&2
  exit 1
fi

INSTALLED=$(curl -s http://127.0.0.1:11434/api/tags | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('\n'.join(m['name'] for m in data.get('models', [])))
")

# Read names from YAML without a YAML parser (each '- name: foo' line)
while IFS= read -r name; do
  if echo "$INSTALLED" | grep -qx "$name"; then
    echo "✓ $name already present"
  else
    echo "↓ pulling $name"
    ollama pull "$name"
  fi
done < <(grep -E '^\s+- name:' ollama/models.yaml | sed 's/.*- name: *//' | tr -d '"')

echo "Done."
```

- [ ] **Step 3: Make executable + run**

```bash
chmod +x ollama/ensure-models.sh
./ollama/ensure-models.sh
```

- [ ] **Step 4: Verify**

```bash
curl -s http://127.0.0.1:11434/api/tags | python3 -c "
import json, sys
names = {m['name'] for m in json.load(sys.stdin)['models']}
required = {'qwen2.5:14b', 'qwen2.5-coder:7b', 'qwen2.5:0.5b', 'nomic-embed-text'}
missing = required - names
print('MISSING:', missing) if missing else print('ALL PRESENT')
"
```
Expected: `ALL PRESENT`.

- [ ] **Step 5: Commit**

```bash
git add ollama/models.yaml ollama/ensure-models.sh
git commit -m "Pin Ollama models + ensure-models.sh idempotent pull script"
```

---

## Task 4: Healthcheck script (Phase 1 gate)

**Files:**
- Create: `bin/healthcheck`

- [ ] **Step 1: Create `bin/healthcheck`**

```bash
#!/usr/bin/env bash
# Phase 1 completion gate. Verifies that every piece of the system is alive
# and can do a real /chat round trip producing an atom in the vault.
set -euo pipefail
cd "$(dirname "$0")/.."

source .env 2>/dev/null || { echo "FAIL: .env missing"; exit 1; }

FAIL=0
ok()   { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; FAIL=1; }

echo "1) launchd agent"
if launchctl print "gui/$(id -u)/com.violet.littlelion" >/dev/null 2>&1; then
  ok "agent loaded"
else
  fail "agent not loaded — run infra/launchd/install-agent.sh"
fi

echo "2) backend /healthz"
if curl -fsS --max-time 3 "http://127.0.0.1:${BACKEND_PORT:-8765}/healthz" | grep -q '"ok"'; then
  ok "backend up"
else
  fail "backend not responding"
fi

echo "3) Ollama models"
NEEDED=("qwen2.5:14b" "qwen2.5-coder:7b" "qwen2.5:0.5b" "nomic-embed-text")
TAGS=$(curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags || echo "{}")
for m in "${NEEDED[@]}"; do
  if echo "$TAGS" | grep -q "\"$m\""; then
    ok "$m"
  else
    fail "$m not pulled"
  fi
done

echo "4) Tailscale reachable from this host"
if tailscale status >/dev/null 2>&1 && [[ -n "$(tailscale ip -4 || true)" ]]; then
  ok "tailscale up ($(tailscale ip -4 | head -1))"
else
  fail "tailscale not configured"
fi

echo "5) Vault path readable + writable"
VAULT="${LITTLE_LION_VAULT_PATH}"
if [[ -d "$VAULT" && -w "$VAULT" ]]; then
  ok "vault rw ($VAULT)"
else
  fail "vault not rw — check LITTLE_LION_VAULT_PATH"
fi

echo "6) End-to-end /chat smoke (writes a probe atom)"
RESP=$(curl -fsS -X POST "http://127.0.0.1:${BACKEND_PORT:-8765}/chat" \
  -H "Authorization: Bearer $BACKEND_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"/local healthcheck probe '"$(date +%s)"'"}' || echo "{}")
SID=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id',''))" 2>/dev/null || true)
TRACE_PATH="$VAULT/assistant/_traces/${SID}.json"
if [[ -n "$SID" && -f "$TRACE_PATH" ]]; then
  ok "trace persisted: ${TRACE_PATH#$VAULT/}"
else
  fail "end-to-end chat did not produce a trace ($SID, $TRACE_PATH)"
fi

echo
if [[ $FAIL -eq 0 ]]; then
  echo "PHASE 1 GATE: PASS ✓"
else
  echo "PHASE 1 GATE: FAIL ✗ — fix the items above"
  exit 1
fi
```

- [ ] **Step 2: Make executable**

```bash
chmod +x bin/healthcheck
```

- [ ] **Step 3: Verify**

```bash
./bin/healthcheck
```
Expected: `PHASE 1 GATE: PASS ✓`.

- [ ] **Step 4: Commit**

```bash
git add bin/healthcheck
git commit -m "Add bin/healthcheck (Phase 1 completion gate, 6 checks)"
```

---

## Task 5: LanceDB weekly backup + restore

**Files:**
- Create: `bin/backup-lancedb`
- Create: `bin/restore-lancedb`
- Create: `infra/launchd/com.violet.littlelion-backup.plist`

- [ ] **Step 1: Create `bin/backup-lancedb`**

```bash
#!/usr/bin/env bash
# Weekly LanceDB snapshot. Keeps 8 most-recent snapshots, deletes older.
set -euo pipefail
cd "$(dirname "$0")/.."

source .env 2>/dev/null || { echo "FAIL: .env missing"; exit 1; }
DB_PATH="${RAG_DB_PATH:-./data/lancedb}"
BACKUP_DIR="./data/lancedb-backups"

if [[ ! -d "$DB_PATH" ]]; then
  echo "Nothing to back up — $DB_PATH missing."
  exit 0
fi

mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y-%m-%d)
TARGET="$BACKUP_DIR/lancedb-$DATE.tar.gz"

if [[ -f "$TARGET" ]]; then
  echo "Already backed up today: $TARGET"
  exit 0
fi

tar -czf "$TARGET" -C "$(dirname "$DB_PATH")" "$(basename "$DB_PATH")"
SIZE=$(du -h "$TARGET" | cut -f1)
echo "Backup written: $TARGET ($SIZE)"

# Retain 8 most recent
ls -1t "$BACKUP_DIR"/lancedb-*.tar.gz | tail -n +9 | xargs -I{} rm -f {}
echo "Retention: $(ls -1 "$BACKUP_DIR"/lancedb-*.tar.gz | wc -l | tr -d ' ') snapshots."
```

- [ ] **Step 2: Create `bin/restore-lancedb`**

```bash
#!/usr/bin/env bash
# Restore the LanceDB from a snapshot. Stops the launchd agent first.
set -euo pipefail
cd "$(dirname "$0")/.."

source .env 2>/dev/null || { echo "FAIL: .env missing"; exit 1; }
DB_PATH="${RAG_DB_PATH:-./data/lancedb}"
BACKUP_DIR="./data/lancedb-backups"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <YYYY-MM-DD | latest>"
  echo "Available:"
  ls -1 "$BACKUP_DIR"/lancedb-*.tar.gz 2>/dev/null | sed 's@.*/@  @'
  exit 1
fi

if [[ "$1" == "latest" ]]; then
  SNAPSHOT=$(ls -1t "$BACKUP_DIR"/lancedb-*.tar.gz | head -1)
else
  SNAPSHOT="$BACKUP_DIR/lancedb-$1.tar.gz"
fi

if [[ ! -f "$SNAPSHOT" ]]; then
  echo "FAIL: snapshot $SNAPSHOT missing." >&2
  exit 1
fi

echo "Stopping backend..."
launchctl bootout "gui/$(id -u)/com.violet.littlelion" 2>/dev/null || true

echo "Replacing $DB_PATH with $SNAPSHOT..."
rm -rf "$DB_PATH"
tar -xzf "$SNAPSHOT" -C "$(dirname "$DB_PATH")"

echo "Restarting backend..."
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.violet.littlelion.plist"
sleep 5
curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8765}/healthz" || echo "WARN: backend slow to start"
echo "Done."
```

- [ ] **Step 3: Create `infra/launchd/com.violet.littlelion-backup.plist`** (every Sunday at 03:30)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
                       "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.violet.littlelion-backup</string>

    <key>ProgramArguments</key>
    <array>
      <string>__PROJECTPATH__/bin/backup-lancedb</string>
    </array>

    <key>WorkingDirectory</key>
    <string>__PROJECTPATH__</string>

    <key>StartCalendarInterval</key>
    <dict>
      <key>Weekday</key>
      <integer>0</integer>
      <key>Hour</key>
      <integer>3</integer>
      <key>Minute</key>
      <integer>30</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>__HOMEPATH__/Library/Logs/violet-littlelion-backup.log</string>

    <key>StandardErrorPath</key>
    <string>__HOMEPATH__/Library/Logs/violet-littlelion-backup.err.log</string>
  </dict>
</plist>
```

- [ ] **Step 4: Extend `infra/launchd/install-agent.sh`** to also install the backup agent

Add at the end of `install-agent.sh` (before the final echo):

```bash
# ─── Backup agent ────────────────────────────────────────────────────────
BACKUP_LABEL="com.violet.littlelion-backup"
BACKUP_TARGET="$HOME/Library/LaunchAgents/$BACKUP_LABEL.plist"
BACKUP_SOURCE="$PROJECT_ROOT/infra/launchd/com.violet.littlelion-backup.plist"

sed -e "s|__PROJECTPATH__|$PROJECT_ROOT|g" \
    -e "s|__HOMEPATH__|$HOME_DIR|g" \
    "$BACKUP_SOURCE" > "$BACKUP_TARGET"

launchctl bootout "gui/$(id -u)/$BACKUP_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$BACKUP_TARGET"
launchctl enable "gui/$(id -u)/$BACKUP_LABEL"
echo "Installed backup agent: $BACKUP_TARGET (runs Sun 03:30)"
```

Also add to `uninstall-agent.sh`:
```bash
launchctl bootout "gui/$(id -u)/com.violet.littlelion-backup" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.violet.littlelion-backup.plist"
```

- [ ] **Step 5: Install + verify**

```bash
chmod +x bin/backup-lancedb bin/restore-lancedb
./infra/launchd/install-agent.sh    # reinstalls both agents
./bin/backup-lancedb                # run once manually to make a baseline
ls data/lancedb-backups/
```
Expected: at least one `.tar.gz` exists. `launchctl print "gui/$(id -u)/com.violet.littlelion-backup"` shows next fire time.

- [ ] **Step 6: Commit**

```bash
git add bin/backup-lancedb bin/restore-lancedb \
        infra/launchd/com.violet.littlelion-backup.plist \
        infra/launchd/install-agent.sh infra/launchd/uninstall-agent.sh
git commit -m "Add weekly LanceDB backup (Sun 03:30) + restore command"
```

---

## Task 6: Vault conflict cleanup script

**Files:**
- Create: `bin/vault-conflicts`

The writer (Phase 1a Task 5) creates `<slug>-conflict-N.md` when it detects the user touched an atom. This script lists those + their counterparts so the user can merge in Obsidian.

- [ ] **Step 1: Create `bin/vault-conflicts`**

```bash
#!/usr/bin/env bash
# Lists all assistant atom conflicts in the vault, side-by-side.
set -euo pipefail
cd "$(dirname "$0")/.."

source .env 2>/dev/null || { echo "FAIL: .env missing"; exit 1; }
ATOMS="$LITTLE_LION_VAULT_PATH/${LITTLE_LION_ASSISTANT_SUBDIR:-assistant}/atoms"

if [[ ! -d "$ATOMS" ]]; then
  echo "No atoms directory ($ATOMS)."; exit 0
fi

shopt -s nullglob
CONFLICTS=("$ATOMS"/*-conflict-*.md)
if [[ ${#CONFLICTS[@]} -eq 0 ]]; then
  echo "No conflicts. ✓"
  exit 0
fi

echo "Found ${#CONFLICTS[@]} conflict(s):"
for cf in "${CONFLICTS[@]}"; do
  base_slug=$(basename "$cf" .md | sed -E 's/-conflict-[0-9]+$//')
  echo
  echo "  base : $ATOMS/$base_slug.md"
  echo "  alt  : $cf"
  echo "  diff (--- base | +++ alt):"
  if command -v diff >/dev/null && [[ -f "$ATOMS/$base_slug.md" ]]; then
    diff -u --label "$base_slug.md" --label "$(basename "$cf")" "$ATOMS/$base_slug.md" "$cf" \
      | sed 's/^/    /' | head -50
  fi
done

echo
echo "Resolve in Obsidian: keep one version, delete the other (or merge sections + delete the conflict file)."
```

- [ ] **Step 2: Make executable**

```bash
chmod +x bin/vault-conflicts
```

- [ ] **Step 3: Verify (no conflicts expected on fresh install)**

```bash
./bin/vault-conflicts
```
Expected: `No conflicts. ✓` (or the listing format if any exist).

- [ ] **Step 4: Commit**

```bash
git add bin/vault-conflicts
git commit -m "Add bin/vault-conflicts: list and diff atom write conflicts"
```

---

## Task 7: Token rotation

**Files:**
- Create: `bin/rotate-token`

- [ ] **Step 1: Create `bin/rotate-token`**

```bash
#!/usr/bin/env bash
# Generate a new 32-byte hex token, update .env, restart backend.
# After rotation, you must re-enter the token in Settings on every client.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "FAIL: .env missing" >&2; exit 1
fi

NEW=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Backup, replace, verify
cp .env ".env.bak.$(date +%s)"
if grep -q '^BACKEND_AUTH_TOKEN=' .env; then
  sed -i.tmp "s|^BACKEND_AUTH_TOKEN=.*|BACKEND_AUTH_TOKEN=$NEW|" .env
  rm .env.tmp
else
  echo "BACKEND_AUTH_TOKEN=$NEW" >> .env
fi

echo "New token written. Restarting backend..."
launchctl bootout "gui/$(id -u)/com.violet.littlelion" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.violet.littlelion.plist"

sleep 4
if curl -fsS --max-time 3 "http://127.0.0.1:${BACKEND_PORT:-8765}/healthz" >/dev/null; then
  echo "Backend restarted with new token."
  echo
  echo "New token (paste into iPhone Settings + browser Settings):"
  echo
  echo "  $NEW"
  echo
else
  echo "FAIL: backend did not come back up." >&2; exit 1
fi
```

- [ ] **Step 2: Make executable**

```bash
chmod +x bin/rotate-token
```

- [ ] **Step 3: Verify (test rotation)**

```bash
./bin/rotate-token
# Re-paste new token in browser/iPhone Settings.
./bin/healthcheck   # from Task 4 — should still PASS
```

- [ ] **Step 4: Commit**

```bash
git add bin/rotate-token
git commit -m "Add bin/rotate-token: 32-byte hex + .env update + backend restart"
```

---

## Task 8: Log rotation

**Files:**
- Create: `bin/rotate-logs`
- Create: `infra/launchd/com.violet.littlelion-logs.plist`

launchd doesn't rotate logs itself. We add a daily cron-style agent that compresses yesterday's log file and keeps 14 days.

- [ ] **Step 1: Create `bin/rotate-logs`**

```bash
#!/usr/bin/env bash
# Rotate violet-littlelion stdout/stderr logs daily; keep 14 days gzip'd.
set -euo pipefail
LOG_DIR="$HOME/Library/Logs"
KEEP=14
YDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)

for base in violet-littlelion.out.log violet-littlelion.err.log violet-littlelion-backup.log violet-littlelion-backup.err.log; do
  src="$LOG_DIR/$base"
  if [[ -f "$src" && -s "$src" ]]; then
    gzip -c "$src" > "$LOG_DIR/$base.$YDAY.gz"
    : > "$src"
    echo "Rotated $base → $base.$YDAY.gz"
  fi
done

# Retention
find "$LOG_DIR" -maxdepth 1 -name 'violet-littlelion*.gz' -mtime +$KEEP -delete -print | sed 's/^/Deleted: /'
```

- [ ] **Step 2: Create `infra/launchd/com.violet.littlelion-logs.plist`** (daily 02:00)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
                       "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.violet.littlelion-logs</string>

    <key>ProgramArguments</key>
    <array>
      <string>__PROJECTPATH__/bin/rotate-logs</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>2</integer>
      <key>Minute</key>
      <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>__HOMEPATH__/Library/Logs/violet-littlelion-rotate.log</string>
  </dict>
</plist>
```

- [ ] **Step 3: Extend `install-agent.sh` / `uninstall-agent.sh`** to handle the logs agent (same `sed` + `launchctl bootstrap` pattern as Task 5 Step 4).

```bash
# In install-agent.sh, add after the backup-agent block:
LOG_LABEL="com.violet.littlelion-logs"
LOG_TARGET="$HOME/Library/LaunchAgents/$LOG_LABEL.plist"
LOG_SOURCE="$PROJECT_ROOT/infra/launchd/com.violet.littlelion-logs.plist"
sed -e "s|__PROJECTPATH__|$PROJECT_ROOT|g" \
    -e "s|__HOMEPATH__|$HOME_DIR|g" \
    "$LOG_SOURCE" > "$LOG_TARGET"
launchctl bootout "gui/$(id -u)/$LOG_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LOG_TARGET"
launchctl enable "gui/$(id -u)/$LOG_LABEL"
echo "Installed logs rotation agent: $LOG_TARGET (runs daily 02:00)"
```

In `uninstall-agent.sh`:
```bash
launchctl bootout "gui/$(id -u)/com.violet.littlelion-logs" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.violet.littlelion-logs.plist"
```

- [ ] **Step 4: Install + smoke**

```bash
chmod +x bin/rotate-logs
./infra/launchd/install-agent.sh
./bin/rotate-logs       # manual one-time rotation
ls ~/Library/Logs/ | grep violet-littlelion
```
Expected: log directory contains both current `.log` files (possibly empty) and any rotated `.gz` files from this run.

- [ ] **Step 5: Commit**

```bash
git add bin/rotate-logs infra/launchd/com.violet.littlelion-logs.plist \
        infra/launchd/install-agent.sh infra/launchd/uninstall-agent.sh
git commit -m "Add daily log rotation (02:00) with 14-day retention"
```

---

## Task 9: System runbook (consolidated ops doc)

**Files:**
- Create: `docs/RUNBOOK.md`

- [ ] **Step 1: Create `docs/RUNBOOK.md`**

```markdown
# Little Lion — Operations Runbook

## Topology
- Mac M1 Max: always-on backend at `127.0.0.1:8765`, served on Tailscale via `tailscale serve`
- iPhone / laptop: PWA installed via Safari "Add to Home Screen"
- Vault: iCloud-synced Obsidian directory; the backend reads + writes the `assistant/` subtree

## Daily-life commands

| Need | Command |
|------|---------|
| Check everything is healthy | `./bin/healthcheck` |
| Restart backend | `launchctl bootout gui/$(id -u)/com.violet.littlelion && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.violet.littlelion.plist` |
| Tail backend logs | `tail -f ~/Library/Logs/violet-littlelion.{out,err}.log` |
| Rotate the auth token | `./bin/rotate-token` (then re-paste in clients) |
| Find atom write conflicts | `./bin/vault-conflicts` |
| Manual LanceDB backup | `./bin/backup-lancedb` |
| Restore LanceDB | `./bin/restore-lancedb <YYYY-MM-DD\|latest>` |
| Re-pull / update Ollama models | `./ollama/ensure-models.sh` |
| Update PWA after frontend change | `cd frontend && npm run build` (backend picks up `dist/` automatically) |
| Uninstall everything | `./infra/launchd/uninstall-agent.sh` |

## Failure modes (cross-reference deep-dive §8)

| Symptom | First action |
|---------|-------------|
| /healthz returns nothing | `tail -50 ~/Library/Logs/violet-littlelion.err.log`; if Ollama down, `ollama serve` |
| iPhone PWA shows "no token" | Settings → paste BACKEND_AUTH_TOKEN |
| iPhone PWA shows "Mic error" | iOS Settings → Safari → Camera & Microphone → Allow |
| Atom write fails on iCloud sync delay | Check `~/Library/Logs/violet-littlelion.err.log` for `assistant-touched-at` mismatch; resolve via `./bin/vault-conflicts` |
| LanceDB corrupted (search returns garbage) | `./bin/restore-lancedb latest`; if still bad, `python scripts/index_vault.py` to rebuild from vault |
| Cost spike on Claude/Gemini | Check `~/Library/Logs/violet-littlelion.out.log` for `route_reason`. Force local with `/local` prefix or set `OFFLINE_MODE=true` temporarily |

## Phase 1 completion gate

`./bin/healthcheck` must print `PHASE 1 GATE: PASS ✓`. Until then, Phase 2 work is paused.

## Cadence

| Job | When | Mechanism |
|-----|------|-----------|
| LanceDB backup | Sun 03:30 | `com.violet.littlelion-backup` launchd |
| Log rotation | Daily 02:00 | `com.violet.littlelion-logs` launchd |
| Reflection / cross-link decay | (Phase 2) | not yet implemented |
| Threshold calibration | (Phase 2) | not yet implemented |
| Manual weekly review (`_review-queue.md`) | Sat morning | Open vault, walk the queue |
```

- [ ] **Step 2: Verify all links resolve**

```bash
test -x bin/healthcheck
test -x bin/rotate-token
test -x bin/vault-conflicts
test -x bin/backup-lancedb
test -x bin/restore-lancedb
test -x ollama/ensure-models.sh
test -x infra/launchd/install-agent.sh
test -x infra/launchd/uninstall-agent.sh
echo "OK: all runbook commands exist + executable"
```

- [ ] **Step 3: Commit**

```bash
git add docs/RUNBOOK.md
git commit -m "Add operations runbook (commands, failure modes, cadence)"
```

---

## Task 10: Final Phase 1 sign-off

**Files:**
- Create: `docs/PHASE1_DONE.md`

This task is the human signal that Phase 1 is shippable. It runs the gate one more time and writes a small sign-off doc so future-you can confirm completeness.

- [ ] **Step 1: Run the gate**

```bash
./bin/healthcheck
```
Expected: `PHASE 1 GATE: PASS ✓`. If any check fails, fix the underlying task before continuing.

- [ ] **Step 2: Real iPhone smoke**

From the iPhone:
1. Open the PWA from the home screen.
2. Type "내 vault에서 라우터 관련 atom 모아줘" → Send.
3. Verify: an assistant reply appears, "Why this answer?" toggle shows the model picked, atom_slug is in the response, opening Obsidian shows a new node in the graph view + edges to existing notes.

- [ ] **Step 3: Write `docs/PHASE1_DONE.md`**

```markdown
# Phase 1 — Shipped

## Date
__YYYY-MM-DD__ (fill in)

## Acceptance evidence
- `./bin/healthcheck` → PHASE 1 GATE: PASS ✓ (capture date + git SHA)
- iPhone end-to-end: text query → atom in vault + cross-link visible in Obsidian graph view
- launchd agents loaded:
  - `com.violet.littlelion` (backend)
  - `com.violet.littlelion-backup` (Sun 03:30)
  - `com.violet.littlelion-logs` (daily 02:00)

## Known limitations entering Phase 2
- No TTS (audio response). Phase 2 evaluates macOS `say` → Coqui XTTS-v2.
- No reflection job: cross-links live forever once made. Phase 2 implements link-decay + threshold calibration.
- No cost cap: every Claude/Gemini call is unmetered. Phase 2 wires a daily token budget.
- No Apple Calendar / Reminders integration.

## Next phase entry point
See `docs/specs/2026-05-18-little-lion-personal-assistant-design.md` §10 Phase 2 roadmap.
```

- [ ] **Step 4: Commit**

```bash
git add docs/PHASE1_DONE.md
git commit -m "Sign off Phase 1: gate passing, iPhone smoke confirmed"
```

---

## Self-Review Results

**1. Spec coverage** (Phase 1 ops scope from design §9, §12 + deep-dive §8):
- Always-on backend → Task 1 (launchd KeepAlive crash-only)
- Tailscale remote access → Task 2
- Ollama model pin → Task 3
- Healthcheck gate → Task 4
- LanceDB backup → Task 5
- Vault conflicts → Task 6
- Token rotation → Task 7
- Log rotation → Task 8
- Runbook → Task 9
- Sign-off → Task 10

**2. Placeholder scan** — `__YYYY-MM-DD__` in Phase1_DONE intentional (filled at sign-off). All scripts have full implementations.

**3. Internal consistency** — every launchd plist uses the `__PROJECTPATH__` / `__HOMEPATH__` sed pattern + `install-agent.sh` does the substitution for all 3 plists (backend, backup, logs). The `uninstall-agent.sh` symmetrically removes all 3. `bin/healthcheck` uses paths/env consistent with Phase 1a `.env.example`.

**4. Cross-references** — design doc §9 (remote access) and §12 (risks) map to specific tasks. Deep-dive §8 failure modes are referenced in `docs/RUNBOOK.md` "Failure modes" table.

---

## Execution Handoff

**Plan complete and saved to `015_little_lion/docs/specs/2026-05-18-little-lion-phase1c-ops-plan.md`. Phase 1 plan set (1a + 1b + 1c) is complete. Execution order: 1a → 1b → 1c. Same two modes apply (Subagent-Driven recommended; Inline as fallback). After 1c Task 10 prints PASS, Phase 1 is shipped.**

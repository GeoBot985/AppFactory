Spec ID

SPEC-CHESS-OBS-004

Title

Implement observability layer: structured logging, per-turn diagnostics, and GUI debug panel

Purpose

Make the system transparent and inspectable.

After Spec 3:

the system runs
but you have no real visibility into why things happen

Spec 4 ensures you can see:

what was sent to the model
what the model returned
how it was parsed
why it failed (if it failed)
how many retries occurred
how long everything took

Without this, debugging LLM behavior is guesswork.

Design Rule

Observability must be:

read-only
non-intrusive
deterministic
structured

It must never affect:

move selection
retry logic
controller flow

It only records and displays.

Scope
In scope
structured logging (file-based)
per-turn diagnostic records
raw model response capture
timing metrics
retry tracking
GUI debug panel
log formatting
Out of scope
analytics dashboards
long-term storage systems
external logging services
performance optimization
File Changes
New files
src/logging/turn_logger.py
src/gui/debug_panel.py
Updated files
src/controller/game_controller.py
src/gui/main_window.py
src/config.py
Logging Strategy

Use JSONL (JSON per line).

Reason:

append-only
easy to parse later
no schema migration headaches
works with grep and scripts
Log File Location
runtime/logs/game_log.jsonl

Create directory if it doesn’t exist.

Turn Log Schema

Each turn must produce one structured record:

{
  "timestamp": "2026-04-01T12:00:00",
  "move_number": 5,
  "side": "white",
  "model": "qwen2.5:3b",

  "fen": "...",

  "prompt": "...",

  "raw_response": "...",

  "parsed_move": "e2e4",

  "legal": true,

  "retries": 1,

  "attempts": [
    {
      "attempt": 1,
      "raw_response": "...",
      "parsed_move": null,
      "error": "no_uci_found"
    },
    {
      "attempt": 2,
      "raw_response": "e2e4",
      "parsed_move": "e2e4",
      "error": null
    }
  ],

  "duration_ms": 842,

  "result": "move_applied"
}
What Must Be Logged
Required fields
timestamp
move number
side
model name
FEN
prompt
raw response (every attempt)
parsed move
legality
retry count
per-attempt breakdown
total duration
final outcome
Logger Class
TurnLogger
class TurnLogger:
    def log_turn(self, turn_data: dict):
        ...
Behavior
open file in append mode
write one JSON line
flush immediately (important for debugging crashes)
Controller Integration

Wrap the entire turn in timing:

start_time = time.time()
...
duration = (time.time() - start_time) * 1000

Collect:

all attempts
final result
duration

Then send to logger.

Attempt Tracking

Inside retry loop:

attempts = []

for attempt in range(max_retries):
    try:
        raw = model_output
        parsed = ...
        error = None
    except Exception as e:
        error = str(e)

    attempts.append({
        "attempt": attempt + 1,
        "raw_response": raw,
        "parsed_move": parsed,
        "error": error
    })

Do not lose failed attempts.

Error Classification

Standardize errors:

"no_uci_found"
"invalid_format"
"illegal_move"
"timeout"
"connection_error"

Do not log random exception strings only.

GUI Debug Panel

This is the visible part.

New Component: DebugPanel
Location

Right-side panel (below controls)

Must Display (Live)
Current Turn
move number
side
model
Raw Model Output

Full text response from model

Parsed Move

What the system extracted

Validation Result
legal / illegal
error type if failed
Retry Count

Example:

Attempt 2 of 3
Timing

Example:

Response time: 842 ms
Optional (but useful)
truncated prompt preview (first ~200 chars)
last error message
Update Contract

Controller must call:

gui.update_debug_panel({
    "model": ...,
    "raw_response": ...,
    "parsed_move": ...,
    "valid": ...,
    "attempt": ...,
    "max_attempts": ...,
    "duration_ms": ...
})
UI Behavior Rules
panel updates after every attempt (not just success)
final state overwrites previous attempt
no scrolling spam for now (keep latest only)
Logging vs GUI

Important separation:

Feature	GUI	Log
Latest state	✅	❌
Full history	❌	✅
Failed attempts	partial	full
Prompts	optional	full
Performance Constraints
logging must not block main loop
file writes are small → acceptable sync write
do not batch logs yet
Failure Behavior

Logging must never crash the system.

Wrap logging in:

try:
    logger.log_turn(...)
except Exception:
    pass

Same for debug panel updates.

Observability must never break execution.

Config Additions
ENABLE_LOGGING = True
LOG_FILE_PATH = "runtime/logs/game_log.jsonl"
ENABLE_DEBUG_PANEL = True
Minimal Visual Layout (Debug Panel)

Example:

----------------------------------
Model: Qwen (White)
Move #: 5

Raw:
"I choose e2e4 because..."

Parsed:
e2e4

Status:
VALID

Attempts:
2 / 3

Time:
842 ms
----------------------------------
Testing Requirements
New test file
tests/test_logging.py
Test 1 — log file created

Run one turn → file exists

Test 2 — valid turn logged

Check JSON structure contains required fields

Test 3 — retry attempts recorded

Simulate failure → attempts array contains multiple entries

Test 4 — duration recorded

Ensure duration_ms > 0

Test 5 — logging failure safe

Force logging error → controller continues running

Acceptance Criteria

This spec is complete when:

each turn produces a structured JSON log entry
failed attempts are captured (not lost)
raw model responses are recorded
parsed moves are recorded
legality is recorded
retry counts are accurate
timing is recorded
debug panel shows live model behavior
GUI updates correctly after each attempt
logging never crashes system
controller logic unchanged in behavior
What You Gain After Spec 4

Now you can actually answer:

Why did the model fail?
How often does it fail?
What kind of mistakes does it make?
Does the legal move list help?
How long do responses take?
Which model behaves better?

Without guessing.
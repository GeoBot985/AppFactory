Spec ID

SPEC-CHESS-WATCHER-006

Title

Implement watcher layer to inspect, classify, and deterministically intervene on LLM move proposals before execution

Purpose

Add a narrow supervisory layer that can:

inspect each model response before execution
classify what kind of failure or risk it represents
intervene deterministically when needed
provide a cleaner boundary between “LLM proposes” and “system executes”

This is not a second controller.
This is not a second model.
This is a rule-bound interception layer.

Core Design Idea

The flow becomes:

controller builds prompt
model returns raw output
parser extracts proposed move
watcher inspects proposal and context
watcher returns a decision
controller obeys that decision
only then can a move be applied

So the watcher is the gate between proposal and execution.

Design Rule

The watcher must be:

deterministic
explicit
auditable
narrow in scope

It must not:

generate chess moves
replace the controller
replace the adapter
invent strategy
act like an LLM

It only classifies and decides among pre-defined actions.

Scope
In scope
watcher component
proposal inspection
deterministic failure classification
intervention decisions
standardized action outputs
watcher logging
GUI display of watcher outcome
Out of scope
strategic chess evaluation
Stockfish integration
autonomous move correction
second-model arbitration
debate mode
adaptive learning
Problem Statement

Right now, even with retries and prompt tuning, the controller only knows:

valid
invalid
illegal
timeout
connection error

That is enough to keep the system running, but not enough to express the architectural pattern you actually care about:

a general-use agent flow where a supervisory layer can snap in and apply deterministic control when behavior crosses a line

This spec introduces that pattern in a small, concrete way.

File Changes
New files
src/watcher/move_watcher.py
tests/test_move_watcher.py
Updated files
src/controller/game_controller.py
src/gui/debug_panel.py
src/logging/turn_logger.py
src/config.py
Core Component
MoveWatcher
Required responsibility

Accept turn context and return a deterministic decision object.

Required interface
class MoveWatcher:
    def inspect(self, context: dict) -> dict:
        ...
Input Context

The watcher must receive enough context to make a deterministic decision.

Minimum required fields
{
    "side": "white",
    "model_name": "qwen2.5:3b",
    "move_number": 5,
    "fen": "...",
    "raw_response": "I choose e2e4",
    "parsed_move": "e2e4",
    "parse_error": None,
    "is_legal": True,
    "attempt": 1,
    "max_attempts": 3,
    "prompt_profile": "DEFAULT_STRICT"
}

Optional extra fields may be included, but this minimum must be supported.

Output Decision Object

The watcher must return a structured decision.

Required shape
{
    "decision": "allow",
    "reason_code": "ok",
    "message": "Move allowed",
    "force_retry": False,
    "forfeit": False
}
Allowed Decisions

Only these decisions are allowed:

allow

Move may proceed.

retry

Move must not be applied. Controller should retry the turn.

forfeit

Game ends immediately. Player forfeits.

No other decision types in this spec.

Standard Reason Codes

Use explicit reason codes.

Minimum required set
ok
parse_failed
illegal_move
empty_response
extra_text_detected
repeated_invalid_response
retry_limit_reached
timeout
connection_error

You can add more, but do not remove or blur these.

Watcher Decision Rules

These rules must be deterministic and ordered.

Rule 1 — Parse failure

If no move could be parsed:

Decision
retry if attempts remain
forfeit if retry limit reached
Reason code
parse_failed
Rule 2 — Empty response

If raw response is missing or blank:

Decision
retry if attempts remain
forfeit if retry limit reached
Reason code
empty_response

This is separate from parse failure because it is a cleaner category.

Rule 3 — Illegal move

If parsed move exists but is not legal:

Decision
retry if attempts remain
forfeit if retry limit reached
Reason code
illegal_move
Rule 4 — Extra text detected

If parsed move is valid but raw response contains additional text before or after the move:

Default decision
allow
But record:
reason code = extra_text_detected

This is important. The watcher should be able to flag soft violations without blocking the turn.

Do not make this harsh by default. Small models often include extra text.

Rule 5 — Repeated invalid response pattern

If the current attempt is not the first, and the response repeats the same failure pattern as before:

Examples:

identical empty response twice
same illegal move twice
same natural-language non-UCI answer twice
Decision
retry if attempts remain
forfeit if retry limit reached
Reason code
repeated_invalid_response

This requires the controller to pass in prior-attempt summary for the current turn.

Rule 6 — Timeout

If adapter reports timeout:

Decision
retry if attempts remain
forfeit if retry limit reached
Reason code
timeout
Rule 7 — Connection error

If adapter cannot reach Ollama:

Default decision
retry if attempts remain
forfeit if retry limit reached
Reason code
connection_error

You may later want global pause behavior, but not in this spec.

Rule 8 — Legal clean move

If parsed move exists and is legal:

Decision
allow
Reason code
ok or extra_text_detected
Retry Limit Enforcement

Watcher must not independently count all turn history across the game.

It only decides based on:

current attempt number
max attempts
current failure class
optional same-turn prior attempt data

The controller remains owner of retry counting.

Soft vs Hard Violations

This is important.

Soft violation

Example:

legal move present
extra text detected

Watcher should:

allow move
flag issue in message/reason
Hard violation

Example:

no UCI move
illegal move
timeout
retry limit reached

Watcher should:

block move
retry or forfeit

This distinction is the whole point of the watcher being more nuanced than raw legality checks.

Prior Attempt Context

To support repeated-pattern detection, controller must pass:

"prior_attempts": [
    {
        "raw_response": "Move pawn to e4",
        "parsed_move": None,
        "reason_code": "parse_failed"
    }
]

Watcher may use only same-turn prior attempts.
Do not make it inspect full game memory in this spec.

Controller Integration

The controller must call watcher after parsing and legality determination, but before applying the move.

Required order
get raw response
parse move
compute legality if possible
call watcher
obey decision
Controller Behavior by Watcher Decision
If allow
apply move
continue normally
If retry
do not apply move
record watcher result
generate retry prompt
continue retry loop
If forfeit
end game immediately
record forfeit reason
update GUI and logs
Logging Requirements

Spec 4 logging must be extended with watcher fields.

Required fields
{
  "watcher_decision": "retry",
  "watcher_reason_code": "illegal_move",
  "watcher_message": "Parsed move is illegal in current position"
}

Per-attempt logs should also include watcher output where relevant.

GUI Debug Panel Updates

Debug panel must now also display watcher outcome.

Minimum additions
watcher decision
watcher reason code
watcher message
Example
Watcher:
Decision: RETRY
Reason: illegal_move
Message: Parsed move is illegal in current position

Keep it readable and brief.

Config Additions

Add watcher toggles to config:

ENABLE_WATCHER = True
WATCHER_STRICT_EXTRA_TEXT = False
ENABLE_WATCHER

Allows watcher to be turned on/off cleanly for comparison.

WATCHER_STRICT_EXTRA_TEXT

Reserved behavior switch:

if false: extra text is soft violation
if true: extra text becomes retry-worthy

For this spec, default must be False.

Extra Text Detection Rule

Implement a simple deterministic method.

If raw response stripped and normalized is not exactly the parsed move token, then extra text is present.

Example:

raw = "e2e4" → no extra text
raw = "I choose e2e4" → extra text
raw = "e2e4\n" → no extra text after normalization

Keep this simple and explicit.

No Auto-Correction

Watcher must not:

replace illegal move with nearest legal move
pick a fallback move
repair notation

That would quietly move it from watcher to agent. Not allowed.

Testing Requirements
New test file
tests/test_move_watcher.py
Minimum tests
Test 1 — legal clean move allowed

Input:

parsed move legal
no extra text

Expect:

decision = allow
reason = ok
Test 2 — legal move with extra text allowed but flagged

Input:

raw = "I choose e2e4"
parsed = e2e4
legal = true

Expect:

decision = allow
reason = extra_text_detected
Test 3 — parse failure retries before max

Input:

parsed_move = None
attempt = 1
max_attempts = 3

Expect:

decision = retry
reason = parse_failed
Test 4 — parse failure forfeits at max

Input:

parsed_move = None
attempt = 3
max_attempts = 3

Expect:

decision = forfeit
reason = retry_limit_reached or parse_failed with forfeit true
Choose one scheme and keep it consistent.
Test 5 — illegal move retries before max

Input:

parsed move exists
legal = false
attempt = 2
max_attempts = 3

Expect:

decision = retry
reason = illegal_move
Test 6 — repeated identical invalid response flagged

Input:

same parse failure or same illegal move as prior attempt

Expect:

decision reflects repeated invalid response
reason = repeated_invalid_response
Test 7 — timeout handled deterministically

Input:

parse error indicates timeout

Expect:

retry or forfeit based on attempt count
Acceptance Criteria

This spec is complete when:

watcher exists as separate component
controller calls watcher before move execution
watcher returns only allow/retry/forfeit decisions
parse failures, illegal moves, timeouts, and connection errors are classified explicitly
soft violations like extra text are flagged without blocking by default
repeated invalid responses can be detected within a turn
watcher decisions are logged
watcher decisions are shown in GUI debug panel
disabling watcher through config cleanly bypasses it
no auto-correction or move invention occurs in watcher code
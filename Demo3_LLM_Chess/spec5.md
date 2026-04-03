Spec ID

SPEC-CHESS-PROMPT-005

Title

Implement prompt profiles and configurable move-generation constraints for local Ollama chess players

Purpose

Add a controlled way to vary how each model is prompted so you can test behavior without rewriting the orchestrator.

After Spec 4, you can observe:

invalid outputs
illegal moves
slow responses
noisy responses

Now you need a clean mechanism to adjust:

prompt style
strictness
verbosity suppression
legal move presentation
retry wording

This spec keeps that logic outside the controller and outside the adapter.

Design Rule

Prompt strategy must be configurable, not hardcoded into the controller.

The controller should only do this:

ask prompt builder for a prompt
send prompt to model
validate returned move

It must not know:

whether the player is “aggressive”
whether legal moves are shown inline or grouped
whether retry prompts are harsher
whether the model gets compact or verbose board context

That belongs in prompt policy.

Scope
In scope
prompt profiles per player
configurable prompt-building options
retry prompt variants
strict output instruction hardening
compact vs full state rendering
legal move list formatting options
per-model prompt configuration
Out of scope
watcher veto/intervention
strategic engine evaluation
debate/acknowledgement mode
tournament analytics
dynamic self-modifying prompts
Problem Statement

Right now the likely prompt logic is a single generic template.

That is too blunt.

Small local models differ a lot. Some need:

a shorter prompt
more explicit formatting instructions
stronger “return only UCI” reminders
legal move lists shown one per line instead of comma-separated
a compact board summary instead of extra prose

Without a configurable prompt layer, every change becomes a code edit in the wrong place.

File Changes
New files
src/prompt/prompt_profiles.py
tests/test_prompt_profiles.py
Updated files
src/prompt/prompt_builder.py
src/llm/player.py
src/config.py
src/controller/game_controller.py
Core Components
1. PromptProfile

A structured configuration object describing how prompts should be built for a given model.

Required fields
class PromptProfile:
    name: str
    include_fen: bool
    include_ascii_board: bool
    include_move_history: bool
    include_legal_moves: bool
    legal_moves_format: str   # "comma", "space", "lines"
    history_format: str       # "san", "uci"
    board_style: str          # "compact", "full"
    strict_output_mode: bool
    max_history_moves: int
    retry_tone: str           # "neutral", "firm", "strict"

A dataclass is fine.

2. PromptBuilder

PromptBuilder must now accept a PromptProfile and use it to build prompts.

Required interface
build_prompt(board, move_history, side, profile, retry_context=None) -> str

The retry context is optional and used only when re-prompting after a failed attempt.

3. LLMPlayer

Each player must carry its own prompt profile.

Required shape
class LLMPlayer:
    def __init__(self, name: str, color: str, adapter, prompt_profile):
        self.name = name
        self.color = color
        self.adapter = adapter
        self.prompt_profile = prompt_profile

This allows:

White model with compact strict prompting
Black model with fuller board context
both still running under the same controller
Prompt Content Requirements
Base prompt content

The builder must be able to include the following blocks, depending on profile:

player side
FEN
ASCII board
recent move history
legal move list
final response contract
Mandatory output instruction

Every prompt must end with a hard constraint block.

Required final block
Return exactly one legal move in UCI format.
Examples: e2e4, g1f3, e7e8q
Do not explain.
Do not include any other text.
Return only the move.

This is non-negotiable even in looser profiles.

Prompt Profile Behavior
Profile option: include_fen

If true, include FEN.
Default should be true.

Reason: FEN is the canonical state.

Profile option: include_ascii_board

If true, include readable board text.

Reason: many small models do better with visual layout plus FEN.

Profile option: include_move_history

If true, include recent moves.

Use only the last max_history_moves.

Do not dump the full game every turn.

Profile option: include_legal_moves

If true, include legal moves list.

For this project, default should be true.

Reason: you are constraining models, not testing pure chess skill.

Profile option: legal_moves_format

Support at minimum:

"comma"
Legal moves:
e2e4, d2d4, g1f3
"space"
Legal moves:
e2e4 d2d4 g1f3
"lines"
Legal moves:
- e2e4
- d2d4
- g1f3

Some small models parse one format better than another. This should be testable.

Profile option: history_format

Support:

san
uci

Default to san for readability.

Profile option: board_style

Support:

compact
full
Compact

Only essential sections, minimal prose.

Full

Slightly more descriptive labels and structure.

Do not let “full” become essay mode.

Profile option: strict_output_mode

If true:

repeat output constraints more strongly
include an explicit invalid-output warning

Example extra block:

Any response that is not a single UCI move will be rejected.

This is useful for weak models.

Profile option: retry_tone

Support:

neutral
firm
strict

This affects the retry prefix only.

Neutral
Your previous response was invalid. Please return one legal UCI move.
Firm
Your previous response was invalid or illegal. Choose only from the listed legal moves.
Strict
Your previous response was rejected. Return exactly one legal UCI move from the provided list. Any extra text will fail.
Default Profiles

Create at least three built-in profiles.

1. DEFAULT_STRICT

Balanced default for small local models.

Recommended:

include_fen = true
include_ascii_board = true
include_move_history = true
include_legal_moves = true
legal_moves_format = "comma"
history_format = "san"
board_style = "compact"
strict_output_mode = true
max_history_moves = 6
retry_tone = "firm"
2. COMPACT_HARDLINE

For weaker models that get distracted.

Recommended:

include_fen = true
include_ascii_board = false
include_move_history = false
include_legal_moves = true
legal_moves_format = "space"
history_format = "uci"
board_style = "compact"
strict_output_mode = true
max_history_moves = 0
retry_tone = "strict"
3. READABLE_BOARD

For models that do better with visible state.

Recommended:

include_fen = true
include_ascii_board = true
include_move_history = true
include_legal_moves = true
legal_moves_format = "lines"
history_format = "san"
board_style = "full"
strict_output_mode = true
max_history_moves = 8
retry_tone = "firm"
Retry Prompt Handling

The controller must not manually stitch retry messages anymore.

Instead it should pass retry context into the prompt builder.

Required behavior

On retry, controller sends something like:

retry_context = {
    "attempt": 2,
    "max_attempts": 3,
    "failure_type": "illegal_move",
    "previous_response": raw_response
}

Then PromptBuilder decides how to incorporate that based on profile.

This keeps prompt behavior centralized.

Retry Failure Types

Standardize:

no_uci_found
invalid_format
illegal_move
timeout
connection_error

These should already align with Spec 4 logging.

Config Requirements

Add profile configuration to config.py.

Example
WHITE_MODEL_NAME = "qwen2.5:3b"
BLACK_MODEL_NAME = "llama3.2:3b"

WHITE_PROMPT_PROFILE = "DEFAULT_STRICT"
BLACK_PROMPT_PROFILE = "READABLE_BOARD"

The actual loaded objects can come from prompt_profiles.py.

Controller Changes

The controller must:

read active player’s profile
ask prompt builder for prompt using that profile
use retry context when needed

It must not:

decide prompt wording itself
decide formatting itself
embed hardcoded retry strings
Logging Integration

Spec 4 logs should now also capture:

prompt profile name
retry tone used
legal move formatting used

This matters because later you’ll want to correlate behavior with prompt strategy.

Add fields
{
  "prompt_profile": "DEFAULT_STRICT",
  "legal_moves_format": "comma",
  "retry_tone": "firm"
}
GUI Integration

Minimal requirement only.

Debug panel may optionally show:

active prompt profile name

Do not dump the whole prompt strategy into the GUI. That becomes clutter.

Testing Requirements
New test file
tests/test_prompt_profiles.py
Minimum tests
Test 1 — default profile builds valid prompt

Ensure prompt contains:

side
FEN
legal moves
output contract
Test 2 — compact profile omits optional sections

For COMPACT_HARDLINE, ensure prompt omits:

ASCII board
move history
Test 3 — readable board profile includes line-formatted legal moves

Ensure legal moves appear one per line.

Test 4 — retry context changes prompt

Given retry context with illegal_move, ensure retry warning appears.

Test 5 — strict output mode adds extra hardening

Ensure prompt includes explicit rejection language.

Test 6 — max history truncation works

Ensure only configured number of recent moves are included.

Acceptance Criteria

This spec is complete when:

prompt behavior is configurable per player
controller no longer hardcodes retry prompt wording
prompt builder supports multiple profiles
legal move formatting is selectable
compact vs full prompt style works
strict output hardening is configurable
retry context is passed centrally through prompt builder
active prompt profile is logged
tests verify profile behavior
What This Gives You

After Spec 5 you will be able to do proper controlled comparisons like:

same two models, different prompt profiles
same model on both sides, different prompt strictness
compact vs readable board prompts
comma-separated vs line-separated legal moves
neutral vs strict retry wording

That is enough scope for your stated goal.
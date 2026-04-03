Spec ID

SPEC-CHESS-CTRL-003

Title

Implement deterministic game controller with LLM turn loop, retry logic, and GUI integration

Purpose

Bring the system to life.

This spec wires everything together so that:

two LLMs take alternating turns
each turn follows a strict observe → respond loop
moves are validated deterministically
illegal or malformed responses are handled properly
the GUI reflects everything in real time
the system remains stable even when models behave badly

This is the core of your architecture.

Problem Statement

Right now you have:

a GUI shell (Spec 2)
an Ollama adapter (Spec 1A)
a chess engine (python-chess)

But nothing is actually running the game.

This spec creates the referee / orchestrator.

Design Rule (Non-negotiable)

The controller is the single source of truth for execution flow.

It owns:

turn order
retries
legality checks
move application
game state transitions
GUI updates

The LLM does not control the game.

Scope
In scope
turn loop implementation
model alternation (white/black)
prompt building integration
adapter invocation
UCI parsing integration
move validation via python-chess
retry logic
forfeit handling
GUI updates
threading / async safety
Out of scope
advanced watcher logic
Stockfish evaluation
tournament mode
persistence/export
advanced time controls
File Changes
New / Primary file
src/controller/game_controller.py
Supporting updates
src/prompt/prompt_builder.py
src/llm/player.py
src/gui/main_window.py
src/config.py
Core Class
GameController
Responsibilities
manage game lifecycle
execute turn loop
coordinate players, engine, and GUI
enforce rules and retries
handle timing and pacing
Initialization
class GameController:
    def __init__(self, white_player, black_player, gui, config):
        self.white = white_player
        self.black = black_player
        self.gui = gui
        self.config = config

        self.board = chess.Board()
        self.running = False
        self.paused = False
        self.move_history = []
Game State Flags

Required flags:

self.running   # game is active
self.paused    # paused state
self.game_over # terminal state

Do not overload meaning. Keep these explicit.

Public Control Methods

These must be callable from GUI:

start_game()
pause_game()
resume_game()
reset_game()
step_turn()
Method Behavior
start_game()
reset board if needed
set running = True
set paused = False
update GUI state
start loop in background thread
pause_game()
set paused = True
GUI reflects paused state
resume_game()
set paused = False
continue loop
reset_game()
stop loop
reset board
clear history
clear GUI panels
set state to idle
step_turn()
execute exactly one full turn cycle
do not start loop
used for debugging
Turn Loop (Core Logic)
Required structure
while self.running and not self.game_over:
    if self.paused:
        sleep briefly
        continue

    self.execute_single_turn()

    sleep(self.config.move_delay)

This loop must not run on the Tkinter thread.

Threading Requirement

Run the loop in a worker thread.

All GUI updates must be routed through:

gui.root.after(0, lambda: ...)

Never update Tkinter directly from worker thread.

Single Turn Execution
execute_single_turn()
Steps
Determine active player
Build prompt
Attempt move with retries
Validate move
Apply move
Update GUI
Check game end
Step 1 — Determine Player
player = self.white if self.board.turn == chess.WHITE else self.black
Step 2 — Build Prompt

Call PromptBuilder with:

FEN
ASCII board
legal moves
move history
side to move

Do not build prompts inside controller manually.

Step 3 — Retry Loop
Required structure
for attempt in range(MAX_RETRIES):
    try:
        move_str = player.choose_move(prompt)
        parsed_move = chess.Move.from_uci(move_str)
    except:
        continue

    if parsed_move in self.board.legal_moves:
        success
    else:
        retry
Retry Rules
max 3 attempts
invalid format = retry
illegal move = retry
timeout = retry
adapter failure = retry
Retry Prompt Augmentation

On retry, prepend:

Your previous move was invalid or illegal.
You must return exactly one legal move from the list.
Return only the move in UCI format.

Do not rebuild everything. Just prefix.

Step 4 — Validation

Use python-chess:

if move in self.board.legal_moves:

No shortcuts.
No custom validation.

Step 5 — Apply Move
self.board.push(move)
self.move_history.append(move)
Step 6 — GUI Updates

Must include:

Board
gui.update_board(self.board)
Move log

Convert to SAN:

san = self.board.san(move)

Append to move log.

Model output panel

Show:

model name
raw response
parsed move
validity
retry count
Step 7 — Game End Detection

Use:

self.board.is_game_over()

Handle:

checkmate
stalemate
insufficient material
repetition
50-move rule
Game Result Handling

On game end:

set self.running = False
set self.game_over = True
display result:

Examples:

"White wins by checkmate"
"Draw by stalemate"
"Black forfeits after invalid moves"
Forfeit Handling

If all retries fail:

declare player forfeited
end game immediately

Example:

Black forfeits after 3 invalid attempts
White wins
Timing / Delay

Between successful moves:

time.sleep(self.config.move_delay)

Do not sleep during retries.

Error Handling

Controller must catch:

adapter failures
parsing failures
network errors
timeouts

Never let exceptions crash the loop silently.

All errors must:

be logged
be surfaced in GUI
Logging Requirements

At minimum per turn:

move number
side
model name
raw response
parsed move
legal/illegal
retries
final result
PromptBuilder Contract

Must return a complete prompt string.

Controller only calls:

prompt = prompt_builder.build(board, move_history, side)

No prompt logic inside controller.

State Consistency Rule

At all times:

board is the single source of truth
move_history matches board state
GUI reflects board state exactly

No divergence allowed.

GUI Interaction Contract

Controller must only call GUI through defined methods.

No direct widget manipulation.

Minimal Working Flow

When complete, the system must:

Launch GUI
Click Start
White model receives prompt
White proposes move
Move validated and applied
GUI updates
Black model receives updated prompt
Repeat until game ends
Testing Requirements
New test file
tests/test_controller.py
Test 1 — single turn execution

Mock adapter → returns valid move
Expect:

board updated
move history updated
Test 2 — invalid then valid move

Mock adapter:

attempt 1: invalid
attempt 2: valid

Expect:

retry occurs
valid move applied
Test 3 — all retries fail

Mock adapter always invalid

Expect:

forfeit triggered
game ends
Test 4 — alternating turns

Simulate 2 moves

Expect:

white then black
correct turn switching
Test 5 — game over detection

Set board near checkmate

Expect:

game ends correctly
result reported
Acceptance Criteria

This spec is complete only when:

controller runs in background thread
GUI remains responsive
two models alternate turns
prompts are generated correctly
UCI moves are parsed and validated
illegal moves trigger retries
retry limit enforced
forfeits handled correctly
board updates correctly after each move
move log updates correctly
game end detected correctly
GUI reflects all state transitions
What You Now Have

After Spec 3:

You no longer have “components”.

You have:

a deterministic orchestrator
constrained LLM agents
a visible execution loop
strict control boundaries
a working model-vs-model system

This is exactly the pattern you were describing earlier:

“loose orchestrator that snaps to deterministic control”

Except now it’s not theory.
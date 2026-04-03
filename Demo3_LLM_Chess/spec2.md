Spec ID

SPEC-CHESS-GUI-002

Title

Implement Tkinter chess board UI and match control panel for LLM-vs-LLM play

Purpose

Build the first working graphical shell for the chess project so that:

a chess board is visible
pieces are rendered correctly
the current game state is shown
model-vs-model play can be watched
the controller has a GUI target for updates
the system is ready to plug into the Ollama move loop

This spec is about presentation and control surface, not chess intelligence.

Problem Statement

Right now the architecture is fine on paper, but there is no actual match interface.

We need a GUI that can:

render the board
display piece positions from deterministic board state
show whose turn it is
show model names
show move history
show raw model output and validation result
provide start / pause / reset controls
remain responsive while the controller runs

Without this, the project is still just components and talk.

Design Rule

The GUI must never own chess truth.

The GUI is a view/controller surface only.

The deterministic game state remains in the chess engine/controller layer.

Tkinter displays state that it is given.

Scope
In scope
Tkinter main window
board canvas
piece rendering
side information panel
move log
status display
match control buttons
speed control
GUI update hooks for controller
Out of scope
drag-and-drop piece movement
human-vs-engine interaction
Stockfish analysis
tournament mode
advanced animations
LLM reasoning display beyond raw text/status
Dependencies

Required for this phase:

pip install python-chess

Tkinter should come with Python on Windows.

No extra GUI frameworks.
No web frontend.
No pygame.

File Changes
New files
src/gui/main_window.py
src/gui/board_view.py
src/gui/control_panel.py
src/gui/move_log_view.py
tests/test_gui_smoke.py
Updated files
src/controller/game_controller.py
src/main.py
src/config.py

If your actual folder layout differs, preserve the same responsibilities.

GUI Layout Requirements
Main window structure

Use a simple two-column layout.

Left side
chess board
Right side
match details
controls
move history
raw response / status panel

This is enough for a first version and matches the actual purpose of the app.

Window Sections
1. Board area

A square board drawn on a Tkinter Canvas.

Required:

8x8 grid
alternating light/dark squares
rank/file labels optional but recommended
pieces clearly visible
board updates after each move
2. Match info panel

Must display:

White model name
Black model name
current side to move
move number
game status
3. Control panel

Must provide:

Start Match
Pause Match
Resume Match
Reset Match
Step Turn
4. Playback control

Must provide:

move delay / autoplay speed control
simple slider or dropdown is enough
5. Move log

Must display:

move number
SAN move history preferred
latest move visible without scrolling gymnastics
6. Model output panel

Must display:

active model name
raw model response
parsed move
validation result
retry count if applicable

This matters because this is not just a chess UI. It is a controlled LLM orchestration demo.

Board Rendering Requirements
Source of truth

Board rendering must be driven from a python-chess.Board object supplied by the controller.

Do not store a second shadow board inside the GUI.

Rendering approach

Use one of these:

Preferred for Spec 2

Unicode chess pieces on canvas/text items.

Reason:

fast
no asset pipeline
no image loading mess
enough for first version
Piece mapping

Use standard Unicode symbols:

White king: ♔
White queen: ♕
White rook: ♖
White bishop: ♗
White knight: ♘
White pawn: ♙
Black king: ♚
Black queen: ♛
Black rook: ♜
Black bishop: ♝
Black knight: ♞
Black pawn: ♟

If font support causes trouble on the machine, fall back later to image assets, but do not start there.

Board Orientation

For version 1:

White at bottom
Black at top

No board flipping yet.

Controller Integration Contract

The controller must be able to call GUI methods like:

update_board(board)
update_status(text)
update_turn(side)
update_move_log(moves)
update_model_output(model_name, raw_response, parsed_move, validity, retry_count)
set_controls_running_state(...)
show_game_result(result_text)

The exact method names can vary, but the contract must be explicit and stable.

Required GUI Classes
MainWindow

Owns and wires together:

board view
control panel
move log
status widgets

Responsibilities:

build the layout
expose high-level update methods
connect button callbacks to controller
BoardView

Responsibilities:

draw board squares
draw pieces
redraw on demand from current python-chess.Board

Must not:

generate legal moves
own turn logic
apply moves itself
ControlPanel

Responsibilities:

buttons
speed control
model labels
basic match info widgets

Must expose callback hooks for:

start
pause
resume
reset
step
MoveLogView

Responsibilities:

display ordered move history
support append/update
keep latest entries visible

Use a simple Tkinter Text, Listbox, or read-only text area.
Do not overcomplicate this.

Responsiveness Requirement

The GUI must not freeze while waiting for model responses.

This is mandatory.

Required approach

Model turns must run outside the Tkinter main thread.

Use:

a worker thread for controller/model actions
root.after(...) for GUI-safe updates back into Tkinter

Do not update Tkinter widgets directly from worker threads.

That is how you get random nonsense and brittle crashes.

Match State Rules

GUI should visually represent these states:

idle
running
paused
finished
error

Controls should enable/disable accordingly.

Example expectations
idle: Start enabled, Pause disabled
running: Pause enabled, Reset enabled, Start disabled
paused: Resume enabled, Reset enabled
finished: Reset enabled, Start enabled
error: Reset enabled
Initial Launch Behavior

On launch, the app must show:

standard starting position
configured model names
status = Idle
empty move log
empty model output panel

This gives the user immediate visual confirmation that the app is working even before any model move occurs.

Speed Control

Add a simple control for delay between turns.

Minimum behavior

User can choose a delay in seconds or milliseconds between turns.

Example options:

0.5s
1s
2s
5s

Or a slider.

The controller reads this value between successful moves.

Step Turn Button

This is important.

Step Turn should trigger exactly one model turn:

one observation
one proposed move
one validation cycle
one applied move or one failure outcome

This gives you controlled debugging instead of only autoplay chaos.

Reset Behavior

Reset must:

restore initial board state
clear move history
clear raw response display
reset retry display
reset status to Idle
keep configured model names intact

Do not require an app restart just to begin a new game.

Error Display

When controller/model errors occur, the GUI must surface them clearly.

Display at least:

short status text
last error message

Examples:

Ollama server not reachable
No valid UCI move found
Black forfeits after 3 invalid attempts

No silent failures.

Minimal Visual Style

Keep it plain and readable.

Requirements:

decent padding
text not jammed against borders
board clearly separated from side panel
controls grouped logically
move log readable at normal window size

Do not waste time beautifying beyond that in Spec 2.

Suggested main.py Behavior

The main entrypoint should:

load config
create Tk root
create GUI window
create deterministic controller
inject GUI into controller
bind control callbacks
render initial position
start Tk main loop

That gives you a clean boot path.

Testing Requirements
New test file
tests/test_gui_smoke.py
Minimum tests
Test 1 — window creation smoke test

App window can be created without crashing.

Test 2 — board view renders initial position

Initial python-chess.Board() renders 32 pieces.

Test 3 — move log accepts updates

Move log widget updates cleanly with a sample move list.

Test 4 — status panel updates

Status/turn/model output fields can be updated through public methods.

These tests can be lightweight. The point is to catch obvious breakage.

Acceptance Criteria

This spec is complete only when:

Tkinter window launches successfully
initial chess position is visible
pieces render correctly
move log panel exists and updates
control buttons exist and are wired
status/model output panel exists
GUI remains responsive
controller can update GUI via clear methods
no chess rules are implemented in GUI code
no model logic is implemented in GUI code
Non-Negotiable Boundary

Do not let GUI classes start doing any of this:

move legality checking
turn ownership
retries
board mutation logic beyond display refresh
model prompt building
network calls to Ollama

That belongs elsewhere.

Developer Notes

Keep Python files small.
Do not dump the whole GUI into one monster module.

Aim for:

one file per responsibility
thin widgets
controller as the traffic cop
GUI as render target

That will matter later when you add:

tournament mode
reasoning panes
watcher diagnostics
manual stepping
export logs
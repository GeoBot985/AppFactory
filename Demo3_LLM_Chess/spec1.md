Spec ID

SPEC-CHESS-LLM-001A

Title

Update chess project to use two local Ollama models instead of Gemini

Purpose

Replace the wrong cloud-model assumption with the actual intended design:

two local Ollama models
deterministic chess controller
Tkinter GUI
strict model I/O contract
models propose moves only
engine validates and applies moves

This spec updates the architecture and implements the first usable local-model adapter.

Problem Statement

The previous adapter spec targeted Gemini, which is not part of this project.

The actual requirement is:

use the user’s local Ollama install
allow two separate local models to compete
keep the board under deterministic control
send current game state to the active model
accept exactly one move proposal back
validate move via chess engine
never let the model manipulate board state directly
Required Design Rule

The LLM is not the game engine.

The LLM is only a move proposer.

The deterministic system owns:

board state
legal move generation
turn order
retries
illegal move handling
result detection
GUI updates
logging
Scope
In scope
remove Gemini-specific assumptions from design
create a local OllamaAdapter
support two named Ollama models
define strict prompt and response contract
parse UCI move output
add timeout/error handling
integrate with LLMPlayer
Out of scope
Stockfish evaluation
tournament mode
debate mode
multi-agent watcher logic beyond basic validation
cloud APIs
Dependencies

Install only what is needed for this phase:

pip install python-chess requests

Tkinter is usually bundled with Python on Windows.

No Gemini library.
No cloud SDKs.

Configuration Requirements

Add model configuration in a simple deterministic form.

Example config
WHITE_MODEL = "qwen2.5:3b"
BLACK_MODEL = "llama3.2:3b"
OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_TIMEOUT_SECONDS = 30
MAX_MOVE_RETRIES = 3

This can live in config.py for now.

File Changes
New files
src/llm/ollama_adapter.py
tests/test_ollama_adapter.py
Updated files
src/llm/player.py
src/controller/game_controller.py
src/prompt/prompt_builder.py
src/config.py

If exact filenames differ in the new repo, keep the responsibility split the same.

Ollama Adapter Requirements
Class

Create:

class OllamaAdapter:
    def __init__(self, model_name: str, base_url: str, timeout: int = 30):
        ...
    
    def get_move(self, prompt: str) -> str:
        ...
API Contract

Use the local Ollama HTTP API.

Endpoint
POST /api/generate
Request shape
{
  "model": "qwen2.5:3b",
  "prompt": "full prompt text here",
  "stream": false
}

Use non-streaming mode for the first version. It is simpler and more reliable.

Response Handling

The adapter must extract text from the Ollama response and return exactly one parsed UCI move.

The adapter must not:

validate legality
update the board
know whose turn logic is next
interact with Tkinter

It only does:

send prompt
receive raw response
extract UCI move
raise clear exception if parsing fails
Prompt Contract

The prompt builder must send a strict prompt containing:

model’s side
FEN
ASCII board
recent move history
legal moves list
final instruction to return one UCI move only
Required ending
Return exactly one legal move in UCI format.
Examples: e2e4, g1f3, e7e8q
Do not explain.
Do not include any other text.
Return only the move.

This must be present every time.

Why legal move list is required

Because small local models will otherwise hallucinate constantly.

For this project, include the legal moves list in every prompt.
That is the whole point of constrained play.

UCI Parsing Rules

The adapter must parse only UCI-like tokens.

Accepted pattern
\b[a-h][1-8][a-h][1-8][qrbn]?\b
Parsing behavior
lower-case the response
strip whitespace
ignore surrounding junk
find the first valid UCI token
return it
if none found, raise ValueError

Do not silently invent fallback moves.

Controller Responsibilities

The controller remains the referee.

On each turn
Read current board state
Build prompt
Send prompt to active model through adapter
Parse returned UCI move
Check move legality with python-chess
If legal, apply move and update GUI
If illegal, retry up to configured limit
If retries exhausted, declare loss or forfeit
Retry Policy

Retry belongs in the controller, not the adapter.

Required behavior

Per turn:

max 3 attempts
failed parse counts as failed attempt
illegal move counts as failed attempt
after final failure, mark player as forfeited
Retry prompt enhancement

On retry, prepend a deterministic correction message such as:

Your previous response was invalid or illegal.
You must return exactly one legal move in UCI format.
Choose only from the listed legal moves.
Return only the move.
Logging Requirements

Log enough to debug model behavior.

Per turn log fields
move number
side to play
model name
FEN
raw response
parsed move
legality result
retry count
final applied move or failure reason

Plain JSONL or text is fine for version 1.

LLMPlayer Update

LLMPlayer must become adapter-agnostic.

Required shape
class LLMPlayer:
    def __init__(self, name: str, color: str, adapter):
        self.name = name
        self.color = color
        self.adapter = adapter

    def choose_move(self, prompt: str) -> str:
        return self.adapter.get_move(prompt)

This allows:

white = one Ollama model
black = another Ollama model
Example Wiring
white_adapter = OllamaAdapter(model_name="qwen2.5:3b", base_url=OLLAMA_BASE_URL)
black_adapter = OllamaAdapter(model_name="llama3.2:3b", base_url=OLLAMA_BASE_URL)

white_player = LLMPlayer(name="Qwen", color="white", adapter=white_adapter)
black_player = LLMPlayer(name="Llama", color="black", adapter=black_adapter)
Minimal Ollama Adapter Behavior
Required implementation logic
POST to local Ollama
check HTTP status
parse JSON
read response field
extract UCI token
raise useful exception on:
connection failure
timeout
malformed response
no UCI token found
Error Messages

Keep them explicit.

Examples:

ConnectionError: Ollama server not reachable at http://localhost:11434
TimeoutError: Ollama model response exceeded 30 seconds
ValueError: No valid UCI move found in model response
RuntimeError: Ollama returned malformed JSON payload

No vague nonsense.

Test Requirements
New test file
tests/test_ollama_adapter.py
Minimum tests
Test 1 — valid plain UCI

Input:

e2e4

Expected:

e2e4
Test 2 — noisy sentence containing UCI

Input:

I choose g1f3 because it develops a knight.

Expected:

g1f3
Test 3 — JSON-ish junk containing move

Input:

{"move":"d2d4"}

Expected:

d2d4
Test 4 — invalid natural language

Input:

Move the king pawn two spaces

Expected:
exception raised

Test 5 — adapter handles timeout cleanly

Mock timeout from requests call.
Expected:
clear timeout exception

Test 6 — adapter handles Ollama unavailable

Mock connection failure.
Expected:
clear connection exception

Acceptance Criteria

This spec is complete only when:

Gemini references are removed from the active chess adapter design
two local Ollama models can be configured by name
adapter calls local Ollama successfully
model output is parsed into UCI
controller validates legality with python-chess
illegal outputs trigger retry logic
GUI remains separate from model logic
no model is allowed to modify board state directly
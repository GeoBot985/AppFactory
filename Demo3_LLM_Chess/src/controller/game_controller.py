import chess
import time
import threading
import re
from enum import Enum
from typing import Optional

from src.config import (
    MAX_MOVE_RETRIES,
    ENABLE_LOGGING,
    LOG_FILE_PATH,
    ENABLE_DEBUG_PANEL,
    ENABLE_WATCHER,
    WATCHER_STRICT_EXTRA_TEXT,
)
from src.prompt.prompt_builder import build_prompt, build_legal_move_options
from src.prompt.model_prompt_registry import get_model_prompt_settings
from src.logging.turn_logger import TurnLogger
from src.llm.ollama_adapter import MoveParseError
from src.llm.move_parser import MoveSelectionParseError, parse_move_selection
from src.watcher.move_watcher import MoveWatcher

class GameState(Enum):
    IDLE = 0
    RUNNING = 1
    PAUSED = 2
    FINISHED = 3
    ERROR = 4

class GameController:
    def __init__(self, white_player, black_player):
        self.white_player = white_player
        self.black_player = black_player
        self.gui = None
        self.board = chess.Board()
        self.move_history = []
        self.state = GameState.IDLE
        self.game_thread = None
        self.stop_event = threading.Event()
        
        if ENABLE_LOGGING:
            self.logger = TurnLogger(LOG_FILE_PATH)
        else:
            self.logger = None
        self.watcher = MoveWatcher(WATCHER_STRICT_EXTRA_TEXT) if ENABLE_WATCHER else None

    def _safe_gui_call(self, callback, *args):
        if not self.gui:
            return

        try:
            self.gui.after(0, callback, *args)
        except Exception:
            pass

    def _classify_attempt_error(self, exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"
        if isinstance(exc, ConnectionError):
            return "connection_error"
        if isinstance(exc, ValueError):
            message = str(exc).lower()
            if "selection" in message:
                return "invalid_selection_format"
            if "option number" in message:
                return "invalid_selection_format"
            if "uci" in message:
                return "no_uci_found"
            return "invalid_format"
        if isinstance(exc, chess.InvalidMoveError):
            return "invalid_format"
        return "invalid_format"

    def _resolve_move_index(self, parsed_index: int, legal_move_options: list[dict[str, object]]) -> str:
        if parsed_index < 1 or parsed_index > len(legal_move_options):
            raise IndexError("Move selection is out of range")
        return str(legal_move_options[parsed_index - 1]["uci"])

    def _request_move_response(self, player, prompt: str, profile) -> dict:
        if profile.move_output_mode == "index":
            raw_response = player.adapter.get_response(prompt)
            parsed = parse_move_selection(raw_response)
            return {
                "raw": raw_response,
                "parsed": None,
                "parsed_index": parsed["parsed_index"],
            }
        move_data = player.adapter.get_move(prompt)
        return {
            "raw": move_data["raw"],
            "parsed": move_data["parsed"],
            "parsed_index": None,
        }

    def _try_parse_san_response(self, raw_response: Optional[str]):
        if not raw_response:
            return None

        candidates = []
        candidate = raw_response.strip()
        if candidate:
            candidates.append(candidate)
            candidates.append(candidate.strip("\"'"))
            candidates.append(candidate.rstrip(".!,;:"))
            candidates.append(candidate.rstrip("+#"))
            candidates.append(candidate.rstrip("+#").rstrip(".!,;:"))

        seen = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                return self.board.parse_san(candidate)
            except ValueError:
                continue
        return None

    def _try_parse_unique_square_response(self, raw_response: Optional[str]):
        if not raw_response:
            return None

        candidate = raw_response.strip().lower()
        if len(candidate) != 2:
            return None
        if candidate[0] not in "abcdefgh" or candidate[1] not in "12345678":
            return None

        matching_to = [move for move in self.board.legal_moves if chess.square_name(move.to_square) == candidate]
        if len(matching_to) == 1:
            return matching_to[0]

        matching_from = [move for move in self.board.legal_moves if chess.square_name(move.from_square) == candidate]
        if len(matching_from) == 1:
            return matching_from[0]

        return None

    def _try_parse_piece_square_response(self, raw_response: Optional[str]):
        if not raw_response:
            return None

        candidate = raw_response.strip().strip("\"'").rstrip(".!,;:").rstrip("+#")
        match = re.fullmatch(r"([KQRBN])?x?([a-h][1-8])", candidate)
        if not match:
            return None

        piece_symbol, target_square = match.groups()
        piece_type = None
        if piece_symbol:
            piece_type = chess.PIECE_SYMBOLS.index(piece_symbol.lower())

        matching_moves = []
        for move in self.board.legal_moves:
            if chess.square_name(move.to_square) != target_square:
                continue
            if piece_type is not None:
                piece = self.board.piece_at(move.from_square)
                if not piece or piece.piece_type != piece_type:
                    continue
            matching_moves.append(move)

        if len(matching_moves) == 1:
            return matching_moves[0]

        return None

    def _build_debug_payload(
        self,
        *,
        player_name: str,
        prompt_profile_name: str,
        move_number: int,
        side: str,
        prompt: str,
        raw_response: Optional[str],
        parsed_index: Optional[int],
        parsed_move: Optional[str],
        resolved_move: Optional[str],
        validity: str,
        error: Optional[str],
        watcher_decision: Optional[str],
        watcher_reason_code: Optional[str],
        watcher_message: Optional[str],
        attempt: int,
        duration_ms: int,
    ):
        return {
            "model": player_name,
            "prompt_profile": prompt_profile_name,
            "move_number": move_number,
            "side": side,
            "raw_response": raw_response or "",
            "parsed_index": parsed_index,
            "parsed_move": parsed_move,
            "resolved_move": resolved_move,
            "validity": validity,
            "error": error,
            "watcher_decision": watcher_decision,
            "watcher_reason_code": watcher_reason_code,
            "watcher_message": watcher_message,
            "attempt": attempt,
            "max_attempts": MAX_MOVE_RETRIES,
            "duration_ms": duration_ms,
            "prompt_preview": prompt[:200],
        }

    def _watcher_bypass_decision(self, *, attempt, max_attempts, raw_response, parsed_move, error_str, is_legal):
        if parsed_move and is_legal:
            return {
                "decision": "allow",
                "reason_code": "ok",
                "message": "Watcher disabled",
                "force_retry": False,
                "forfeit": False,
            }
        if attempt < max_attempts:
            return {
                "decision": "retry",
                "reason_code": error_str or "parse_failed",
                "message": "Watcher disabled",
                "force_retry": True,
                "forfeit": False,
            }
        return {
            "decision": "forfeit",
            "reason_code": "retry_limit_reached",
            "message": "Watcher disabled",
            "force_retry": False,
            "forfeit": True,
        }

    def set_gui(self, gui):
        self.gui = gui
        self.gui.set_controller(self)
        self.gui.update_model_names(self.white_player.name, self.black_player.name)
        self.reset_game()

    def set_player_model(self, color: str, model_name: str):
        if not model_name:
            return

        player = self.white_player if color == "white" else self.black_player
        settings = get_model_prompt_settings(model_name)
        player.name = model_name
        player.adapter.model_name = model_name
        player.prompt_profile = settings.profile
        player.prompt_instructions = settings.custom_instructions

        if self.gui:
            self._safe_gui_call(self.gui.update_model_names, self.white_player.name, self.black_player.name)

    def start_game(self):
        if self.state in [GameState.IDLE, GameState.FINISHED, GameState.ERROR]:
            self.reset_game()
            self.state = GameState.RUNNING
            self.gui.update_status("Running")
            self.gui.control_panel.set_control_state("running")
            self.game_thread = threading.Thread(target=self.play_game_loop)
            self.game_thread.start()

    def pause_game(self):
        if self.state == GameState.RUNNING:
            self.state = GameState.PAUSED
            self.gui.update_status("Paused")
            self.gui.control_panel.set_control_state("paused")

    def resume_game(self):
        if self.state == GameState.PAUSED:
            self.state = GameState.RUNNING
            self.gui.update_status("Running")
            self.gui.control_panel.set_control_state("running")

    def reset_game(self):
        self.stop_event.set()
        if self.game_thread and self.game_thread.is_alive():
            self.game_thread.join()

        self.board.reset()
        self.move_history = []
        self.state = GameState.IDLE
        
        if self.gui:
            self._safe_gui_call(self.gui.board_view.update_board, self.board)
            self._safe_gui_call(self.gui.move_log_view.clear_log)
            if ENABLE_DEBUG_PANEL:
                self._safe_gui_call(self.gui.clear_debug_panel)
            self._safe_gui_call(self.gui.update_status, "Idle")
            self._safe_gui_call(self.gui.update_turn, "White")
            self._safe_gui_call(self.gui.control_panel.set_control_state, "idle")
            
        self.stop_event.clear()

    def step_turn(self):
        if self.state in [GameState.IDLE, GameState.PAUSED]:
            if not self.game_thread or not self.game_thread.is_alive():
                self.gui.after(0, self.gui.update_status, "Stepping")
                self.game_thread = threading.Thread(target=self.execute_single_turn)
                self.game_thread.start()

    def play_game_loop(self):
        while not self.board.is_game_over() and not self.stop_event.is_set():
            if self.state == GameState.RUNNING:
                self.execute_single_turn()
                if self.stop_event.is_set() or self.board.is_game_over():
                    break
                delay = self.gui.control_panel.delay_scale.get()
                time.sleep(delay)
            else:
                time.sleep(0.1)
        
        if not self.stop_event.is_set() and self.board.is_game_over():
            self.state = GameState.FINISHED
            outcome = self.board.outcome()
            status = f"Finished: {self.board.result()}"
            if outcome:
                winner = "White" if outcome.winner == chess.WHITE else "Black" if outcome.winner == chess.BLACK else "No one"
                status = f"Finished: {winner} wins by {outcome.termination.name.lower()}." if outcome.winner is not None else f"Draw by {outcome.termination.name.lower()}."
            
            self._safe_gui_call(self.gui.update_status, status)
            self._safe_gui_call(self.gui.control_panel.set_control_state, "finished")

    def execute_single_turn(self):
        if self.board.is_game_over(): return

        start_time = time.time()
        player = self.white_player if self.board.turn == chess.WHITE else self.black_player
        side = "White" if self.board.turn == chess.WHITE else "Black"
        move_number = self.board.fullmove_number
        turn_fen = self.board.fen()
        self._safe_gui_call(self.gui.update_turn, side)

        attempts_data = []
        final_result = "forfeit"
        profile = player.prompt_profile
        legal_move_options = build_legal_move_options(self.board)
        prompt = build_prompt(
            board=self.board,
            move_history=self.move_history,
            side=side.lower(),
            profile=profile,
            custom_instructions=player.prompt_instructions,
            legal_move_options=legal_move_options,
        )
        final_raw_response = None
        final_parsed_index = None
        final_parsed_move = None
        final_resolved_move = None
        final_legal = False
        final_error = None
        final_watcher_decision = None
        final_watcher_reason_code = None
        final_watcher_message = None
        move = None
        applied_move_number = move_number
        applied_color = side.lower()
        
        for attempt in range(MAX_MOVE_RETRIES):
            raw_response, parsed_move, resolved_move, error_str, validity = None, None, None, None, "Error"
            parsed_index = None
            is_legal = False
            move = None
            attempt_start_time = time.time()
            
            try:
                current_prompt = prompt
                if attempt > 0:
                    retry_context = {
                        "attempt": attempt + 1,
                        "max_attempts": MAX_MOVE_RETRIES,
                        "failure_type": final_error or "invalid_format",
                        "previous_response": final_raw_response,
                    }
                    current_prompt = build_prompt(
                        board=self.board,
                        move_history=self.move_history,
                        side=side.lower(),
                        profile=profile,
                        custom_instructions=player.prompt_instructions,
                        retry_context=retry_context,
                        legal_move_options=legal_move_options,
                    )
                
                move_data = self._request_move_response(player, current_prompt, profile)
                raw_response = move_data["raw"]
                parsed_move = move_data["parsed"]
                parsed_index = move_data["parsed_index"]

                if profile.move_output_mode == "index":
                    try:
                        resolved_move = self._resolve_move_index(parsed_index, legal_move_options)
                    except IndexError:
                        error_str = "selection_out_of_range"
                    else:
                        parsed_move = resolved_move
                        move = chess.Move.from_uci(resolved_move)
                else:
                    move = chess.Move.from_uci(parsed_move)
                
                if error_str is None and move in self.board.legal_moves:
                    validity = "Legal"
                    is_legal = True
                elif error_str is None:
                    validity = "Illegal"
                    error_str = "resolved_move_illegal" if profile.move_output_mode == "index" else "illegal_move"

            except MoveSelectionParseError as e:
                raw_response = e.raw_response
                error_str = self._classify_attempt_error(e)
            except MoveParseError as e:
                raw_response = e.raw_response
                move = self._try_parse_san_response(raw_response)
                if move is None:
                    move = self._try_parse_piece_square_response(raw_response)
                if move is None:
                    move = self._try_parse_unique_square_response(raw_response)
                if move is not None:
                    parsed_move = move.uci()
                    resolved_move = parsed_move
                    validity = "Legal" if move in self.board.legal_moves else "Illegal"
                    is_legal = move in self.board.legal_moves
                    error_str = None if is_legal else "illegal_move"
                else:
                    error_str = self._classify_attempt_error(e)
            except Exception as e:
                error_str = self._classify_attempt_error(e)

            attempt_duration_ms = (time.time() - attempt_start_time) * 1000
            final_raw_response = raw_response
            final_parsed_index = parsed_index
            final_parsed_move = parsed_move
            final_resolved_move = resolved_move
            final_error = error_str

            watcher_context = {
                "side": side.lower(),
                "model_name": player.name,
                "move_number": move_number,
                "fen": turn_fen,
                "raw_response": raw_response,
                "parsed_index": parsed_index,
                "parsed_move": parsed_move,
                "parse_error": error_str,
                "is_legal": is_legal,
                "attempt": attempt + 1,
                "max_attempts": MAX_MOVE_RETRIES,
                "prompt_profile": profile.name,
                "move_output_mode": profile.move_output_mode,
                "prior_attempts": [
                    {
                        "raw_response": prior["raw_response"],
                        "parsed_index": prior.get("parsed_index"),
                        "parsed_move": prior["parsed_move"],
                        "reason_code": prior.get("watcher_reason_code"),
                    }
                    for prior in attempts_data
                ],
            }
            watcher_result = (
                self.watcher.inspect(watcher_context)
                if self.watcher
                else self._watcher_bypass_decision(
                    attempt=attempt + 1,
                    max_attempts=MAX_MOVE_RETRIES,
                    raw_response=raw_response,
                    parsed_move=parsed_move,
                    error_str=error_str,
                    is_legal=is_legal,
                )
            )
            final_watcher_decision = watcher_result["decision"]
            final_watcher_reason_code = watcher_result["reason_code"]
            final_watcher_message = watcher_result["message"]

            attempts_data.append({
                "attempt": attempt + 1,
                "raw_response": raw_response,
                "parsed_index": parsed_index,
                "parsed_move": parsed_move,
                "resolved_move": resolved_move,
                "error": error_str,
                "watcher_decision": watcher_result["decision"],
                "watcher_reason_code": watcher_result["reason_code"],
                "watcher_message": watcher_result["message"],
            })

            if ENABLE_DEBUG_PANEL:
                debug_data = self._build_debug_payload(
                    player_name=player.name,
                    prompt_profile_name=profile.name,
                    move_number=move_number,
                    side=side,
                    prompt=current_prompt,
                    raw_response=raw_response,
                    parsed_index=parsed_index,
                    parsed_move=parsed_move,
                    resolved_move=resolved_move,
                    validity=validity,
                    error=error_str,
                    watcher_decision=watcher_result["decision"],
                    watcher_reason_code=watcher_result["reason_code"],
                    watcher_message=watcher_result["message"],
                    attempt=attempt + 1,
                    duration_ms=round(attempt_duration_ms),
                )
                self._safe_gui_call(self.gui.update_debug_panel, debug_data)

            if watcher_result["decision"] == "allow":
                final_result = "move_applied"
                final_legal = is_legal
                san_move = self.board.san(move)
                self.board.push(move)
                self.move_history.append(san_move)
                
                applied_move_number = move_number
                applied_color = side.lower()
                
                self._safe_gui_call(self.gui.board_view.update_board, self.board)
                self._safe_gui_call(self.gui.move_log_view.add_move, san_move, applied_move_number, applied_color)
                if self.state == GameState.PAUSED:
                    self._safe_gui_call(self.gui.update_status, "Paused")
                break
            if watcher_result["decision"] == "forfeit":
                break
        
        total_duration_ms = (time.time() - start_time) * 1000
        if self.logger:
            log_data = {
                "move_number": move_number,
                "side": side.lower(),
                "model": player.name,
                "prompt_profile": profile.name,
                "move_output_mode": profile.move_output_mode,
                "legal_moves_format": profile.legal_moves_format,
                "retry_tone": profile.retry_tone,
                "fen": turn_fen,
                "prompt": prompt,
                "raw_response": final_raw_response,
                "parsed_index": final_parsed_index,
                "parsed_move": final_parsed_move,
                "resolved_move": final_resolved_move,
                "legal": final_legal,
                "watcher_decision": final_watcher_decision,
                "watcher_reason_code": final_watcher_reason_code,
                "watcher_message": final_watcher_message,
                "retries": len(attempts_data) - 1,
                "attempts": attempts_data,
                "duration_ms": round(total_duration_ms),
                "result": final_result,
            }
            try:
                self.logger.log_turn(log_data)
            except Exception:
                pass

        if final_result != "move_applied":
            self.state = GameState.ERROR
            self._safe_gui_call(self.gui.update_status, f"Error: {player.name} forfeits.")
            self._safe_gui_call(self.gui.control_panel.set_control_state, "error")

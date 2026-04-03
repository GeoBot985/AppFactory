import sys
import os
import threading

# Add project root to path so `src` is imported as a package without shadowing stdlib modules.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.config import (
    WHITE_MODEL_NAME,
    BLACK_MODEL_NAME,
    OLLAMA_BASE_URL,
    MODEL_TIMEOUT_SECONDS,
    WHITE_PROMPT_PROFILE,
    BLACK_PROMPT_PROFILE,
)
from src.llm.ollama_adapter import OllamaAdapter
from src.llm.player import LLMPlayer
from src.controller.game_controller import GameController
from src.gui.main_window import MainWindow
from src.prompt.prompt_profiles import get_prompt_profile
from src.prompt.model_prompt_registry import get_model_prompt_settings


def _load_models_async(app, white_player, black_player):
    def worker():
        try:
            available_models = OllamaAdapter.list_models(OLLAMA_BASE_URL, timeout=MODEL_TIMEOUT_SECONDS)
        except Exception:
            available_models = []

        def apply_models():
            model_choices = available_models or [white_player.name, black_player.name]

            if white_player.name not in model_choices:
                white_player.name = model_choices[0]
                white_player.adapter.model_name = model_choices[0]
            white_settings = get_model_prompt_settings(white_player.name)
            if WHITE_PROMPT_PROFILE:
                white_player.prompt_profile = white_settings.profile
            white_player.prompt_instructions = white_settings.custom_instructions

            if black_player.name not in model_choices:
                black_player.name = model_choices[min(1, len(model_choices) - 1)]
                black_player.adapter.model_name = black_player.name
            black_settings = get_model_prompt_settings(black_player.name)
            if BLACK_PROMPT_PROFILE:
                black_player.prompt_profile = black_settings.profile
            black_player.prompt_instructions = black_settings.custom_instructions

            app.update_model_names(white_player.name, black_player.name)
            app.set_available_models(model_choices)

        try:
            app.after(0, apply_models)
        except RuntimeError:
            pass

    threading.Thread(target=worker, daemon=True).start()


def main():
    # Create adapters and players
    white_adapter = OllamaAdapter(model_name=WHITE_MODEL_NAME, base_url=OLLAMA_BASE_URL, timeout=MODEL_TIMEOUT_SECONDS)
    black_adapter = OllamaAdapter(model_name=BLACK_MODEL_NAME, base_url=OLLAMA_BASE_URL, timeout=MODEL_TIMEOUT_SECONDS)

    white_settings = get_model_prompt_settings(WHITE_MODEL_NAME)
    black_settings = get_model_prompt_settings(BLACK_MODEL_NAME)

    white_player = LLMPlayer(
        name=WHITE_MODEL_NAME,
        color="white",
        adapter=white_adapter,
        prompt_profile=get_prompt_profile(WHITE_PROMPT_PROFILE),
        prompt_instructions=white_settings.custom_instructions,
    )
    black_player = LLMPlayer(
        name=BLACK_MODEL_NAME,
        color="black",
        adapter=black_adapter,
        prompt_profile=get_prompt_profile(BLACK_PROMPT_PROFILE),
        prompt_instructions=black_settings.custom_instructions,
    )

    # Create game controller
    game_controller = GameController(white_player, black_player)
    
    # Create and run GUI
    app = MainWindow()
    game_controller.set_gui(app)
    app.update_model_names(white_player.name, black_player.name)
    app.set_available_models([white_player.name, black_player.name])
    _load_models_async(app, white_player, black_player)
    
    # Start the GUI main loop
    app.mainloop()

if __name__ == "__main__":
    main()

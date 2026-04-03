class LLMPlayer:
    """
    A player that uses an LLM adapter to choose a move.
    """
    def __init__(self, name: str, color: str, adapter, prompt_profile, prompt_instructions: str = ""):
        self.name = name
        self.color = color
        self.adapter = adapter
        self.prompt_profile = prompt_profile
        self.prompt_instructions = prompt_instructions

    def choose_move(self, prompt: str) -> str:
        """
        Chooses a move using the adapter.
        """
        return self.adapter.get_move(prompt)

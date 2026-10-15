"""Condition custom models on stock recordings instead of incompatible stock states."""
def enable_stock_references(engine, settings, known_voices, sources=None):
    if not (settings.pocket_tts_config or settings.pocket_tts_checkpoint):
        return None  # Stock model keeps the original predefined-state path.
    model = engine._model
    if not getattr(model, 'has_voice_cloning', False):
        return None
    if sources is None:
        from pocket_tts.utils.utils import _ORIGINS_OF_PREDEFINED_VOICES
        sources = _ORIGINS_OF_PREDEFINED_VOICES
    references = {name: sources[name] for name in known_voices if name in sources}
    original = model.get_state_for_audio_prompt
    def get_state(voice, truncate=False):
        if isinstance(voice, str) and voice in references:
            return original(references[voice], truncate=True)
        return original(voice, truncate=truncate)
    model.get_state_for_audio_prompt = get_state
    return set(references)

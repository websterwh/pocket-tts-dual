"""Build the advertised catalog and configured custom voice aliases."""
def voice_aliases(settings, known_voices, default_voice, extra, stock_references=None):
    if not isinstance(extra, dict) or any(
        not isinstance(name, str) or not name.strip()
        or not isinstance(target, str) or not target.strip()
        for name, target in extra.items()
    ):
        raise ValueError("WYOMING_VOICES must be a JSON object mapping voice names to paths or voice IDs")
    custom_model = bool(settings.pocket_tts_config or settings.pocket_tts_checkpoint)
    catalog = (stock_references or ()) if custom_model else known_voices
    aliases = {name: name for name in sorted(catalog)}
    aliases.update(extra)
    aliases['default'] = default_voice
    return aliases

from types import SimpleNamespace
from dual.stock import enable_stock_references
from dual.voices import voice_aliases

class Model:
    has_voice_cloning=True
    def __init__(self):self.calls=[]
    def get_state_for_audio_prompt(self, voice, truncate=False):
        self.calls.append((voice,truncate))
        return {'voice':voice}

def test_custom_model_reencodes_official_audio_and_preserves_custom_references():
    model=Model();engine=SimpleNamespace(_model=model)
    settings=SimpleNamespace(pocket_tts_config='/models/config.yaml',pocket_tts_checkpoint='')
    available=enable_stock_references(engine,settings,{'anna','alba','unknown'},
                                     {'anna':'hf://official/anna.wav','alba':'hf://official/alba.wav'})
    assert available=={'anna','alba'}
    assert model.get_state_for_audio_prompt('anna') == {'voice':'hf://official/anna.wav'}
    assert model.calls[-1]==('hf://official/anna.wav',True)
    for source in ['/models/a.wav','/models/b.safetensors']:
        assert model.get_state_for_audio_prompt(source)=={'voice':source}
        assert model.calls[-1]==(source,False)
    aliases=voice_aliases(settings,{'anna','alba','unknown'},'/models/a.wav',
                         {'Reader':'/models/b.safetensors'},stock_references=available)
    assert aliases=={'anna':'anna','alba':'alba','Reader':'/models/b.safetensors','default':'/models/a.wav'}

def test_stock_model_keeps_original_state_loading():
    model=Model();original=model.get_state_for_audio_prompt
    settings=SimpleNamespace(pocket_tts_config='',pocket_tts_checkpoint='')
    assert enable_stock_references(SimpleNamespace(_model=model),settings,{'anna'}) is None
    assert model.get_state_for_audio_prompt == original

def test_non_cloning_custom_model_does_not_offer_reference_catalog():
    model=Model();model.has_voice_cloning=False
    settings=SimpleNamespace(pocket_tts_config='/models/config.yaml',pocket_tts_checkpoint='')
    assert enable_stock_references(SimpleNamespace(_model=model),settings,{'anna'}) is None

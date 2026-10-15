from types import SimpleNamespace
import pytest
from dual.voices import voice_aliases

@pytest.mark.parametrize('config,checkpoint', [('/models/config.yaml',''), ('','/models/checkpoint.safetensors')])
def test_custom_models_advertise_only_default_and_explicit_references(config,checkpoint):
    settings=SimpleNamespace(pocket_tts_config=config,pocket_tts_checkpoint=checkpoint)
    extra={'Narrator':'/models/narrator.wav','Reader':'/models/reader.safetensors'}
    aliases=voice_aliases(settings,{'alba','anna'},'/models/default.wav',extra)
    assert aliases == {**extra,'default':'/models/default.wav'}
    assert extra == {'Narrator':'/models/narrator.wav','Reader':'/models/reader.safetensors'}

def test_stock_models_preserve_catalog_and_explicit_alias_overrides():
    settings=SimpleNamespace(pocket_tts_config='',pocket_tts_checkpoint='')
    assert voice_aliases(settings,{'alba','anna'},'alba',{'anna':'/models/anna.wav'}) == {
        'alba':'alba','anna':'/models/anna.wav','default':'alba'}

@pytest.mark.parametrize('extra',[[],{'empty':''},{'bad':2},{'':'/models/a.wav'}])
def test_invalid_alias_configuration_fails_clearly(extra):
    settings=SimpleNamespace(pocket_tts_config='',pocket_tts_checkpoint='')
    with pytest.raises(ValueError,match='WYOMING_VOICES'):
        voice_aliases(settings,{'alba'},'alba',extra)

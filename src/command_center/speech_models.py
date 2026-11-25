"""Two fixed offline formats. File keys are part of the approved profile digest."""

from .offline_speech import MODEL_FILES

GIGAAM_REPOSITORY = 'istupakov/gigaam-v3-onnx'
GIGAAM_REVISION = '322c3b29492673eb7d0b434bfa9dfb8653e34d02'
GIGAAM_MANIFEST = {
    'LICENSE.txt': 'f00de6715714c7a63d08639cdbfaa40224eefc407302614bd19f1a8b98c875aa',
    'config.json': '0641fcf73f4af791c73f05083e38a658ff5dcbee3534a0c61396c10f4b97f0fe',
    'v3_e2e_ctc.int8.onnx': '2e3fcb7a7b66030336fd10c2fcfb033bd1dc7e1bf238fe5cfd83b1d0cfc9d28e',
    'v3_e2e_ctc_vocab.txt': '142de7570b3de5b3035ce111a89c228e80e6085273731d944093ddf24fa539cd',
}


def model_files(manifest):
    if isinstance(manifest, dict) and set(manifest) == set(MODEL_FILES):
        return MODEL_FILES
    if manifest == GIGAAM_MANIFEST:
        return tuple(GIGAAM_MANIFEST)
    raise ValueError('voice_model_format_or_snapshot_not_supported')


def model_target(manifest):
    return '/models/whisper-base' if model_files(manifest) == MODEL_FILES else '/models/gigaam-v3'


def decoder(directory, manifest):
    if model_files(manifest) == MODEL_FILES:
        from .offline_speech import OfflineSpeech
        return OfflineSpeech(directory, manifest)
    from .gigaam_speech import GigaamSpeech
    return GigaamSpeech(directory, manifest)

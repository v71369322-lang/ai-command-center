"""Offline, single-candidate speech experiment. Never connects to Telegram/API.

Run each candidate in a fresh process for comparable peak working-set readings.
The JSON case list has id, audio (relative to the list), reference, critical_phrases.
Reports omit transcript/reference text. Lexical metrics always need human review.
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

from command_center.offline_speech import decode_audio, verify_model
from command_center.speech_quality import assess


def peak_memory():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError('speech_evaluation_memory_measurement_failed')
        return counters.PeakWorkingSetSize / (1024 * 1024)
    import resource
    scale = 1024 * 1024 if sys.platform == 'darwin' else 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / scale


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--beam', type=int, choices=(1, 5), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-output', type=Path,
                        help='Opt-in private transcript file; must not exist. Keep outside Git.')
    args = parser.parse_args()
    if args.review_output and (args.review_output.exists()
                               or args.review_output.resolve() == args.output.resolve()):
        parser.error('private review output must be a new, separate file')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    fingerprint = verify_model(args.model.resolve(), manifest)
    cases = json.loads(args.cases.read_text(encoding='utf-8-sig'))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError('speech_evaluation_cases_invalid')
    import ctranslate2
    import faster_whisper
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from faster_whisper import WhisperModel
    started = time.perf_counter()
    model = WhisperModel(str(args.model.resolve()), device='cpu', compute_type='int8',
                         cpu_threads=1, num_workers=1, local_files_only=True)
    load_seconds = time.perf_counter() - started
    results, review = [], []
    for case in cases:
        audio = (args.cases.parent / case['audio']).read_bytes()
        started = time.perf_counter()
        samples = decode_audio(audio)
        segments, _ = model.transcribe(samples, language='ru', task='transcribe',
            beam_size=args.beam, best_of=1, temperature=0, condition_on_previous_text=False,
            vad_filter=True, vad_parameters={'min_silence_duration_ms': 500})
        transcript = ' '.join(segment.text.strip() for segment in segments).strip()
        elapsed = time.perf_counter() - started
        results.append({'id': case['id'], 'audio_sha256': sha256(audio).hexdigest(),
            'reference_sha256': sha256(case['reference'].encode()).hexdigest(),
            'audio_seconds': len(samples) / 16000, 'decode_inference_seconds': round(elapsed, 3),
            **assess(case['reference'], transcript, case.get('critical_phrases', []))})
        if args.review_output:
            review.append({'id': case['id'], 'reference': case['reference'], 'transcript': transcript})
    report = {'model_fingerprint': fingerprint, 'beam': args.beam, 'threads': 1,
              'compute_type': 'int8', 'load_seconds': round(load_seconds, 3),
              'peak_working_set_mib': round(peak_memory(), 1), 'platform': sys.platform,
              'faster_whisper_version': faster_whisper.__version__,
              'ctranslate2_version': ctranslate2.__version__,
              'paid_api': False, 'production_changed': False, 'cases': results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.review_output:
        # O_EXCL prevents symlink/replacement races; Windows callers must also use
        # a private parent ACL (POSIX mode bits alone do not restrict Windows ACLs).
        descriptor = os.open(args.review_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(review, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'cases': len(results), 'beam': args.beam,
                      'peak_working_set_mib': report['peak_working_set_mib'], 'paid_api': False}))


if __name__ == '__main__':
    main()

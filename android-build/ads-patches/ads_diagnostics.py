"""Bounded, local-only VAST diagnostics. No URLs, tokens or user identifiers."""
import datetime
import json
import os
import threading
import uuid

_LOCK = threading.Lock()
_SESSION = uuid.uuid4().hex[:12]  # process-local diagnostic correlation, never sent
_FIELDS = {'motivo', 'iniciado', 'segundos', 'duracao_anuncio', 'retomada_confirmada',
           'http_status', 'network_error', 'empty', 'elapsed_ms', 'tentativa_midia',
           'largura', 'altura', 'bitrate', 'media_attempts', 'active', 'reason'}
_REASONS = {'no-fill', 'no-fill-ou-sem-midia', 'sem-midia-compativel', 'falha-rede-vast',
            'timeout-vast', 'http-error', 'timeout', 'network', 'too-large', 'xml-invalido',
            'startup-timeout', 'travamento', 'erro-player', 'excecao-player', 'player-recusou',
            'tela-preta-sem-quadro', 'timeout-anuncio', 'concluido', 'pulado', 'interrompido',
            'sem-stream-resolvido', 'conteudo-alterado', 'sem-tag', 'wrapper-ciclico',
            'limite-wrappers', 'vip', 'same-session', 'same-opening', 'return', 'busy',
            'no-video', 'no-path', 'module-unavailable', 'dispatch-failed', 'exception'}


def status(receipt):
    reason = receipt.get('motivo', '')
    if receipt.get('iniciado') and reason in ('concluido', 'pulado'):
        return 'VAST OK (%ss)' % receipt.get('segundos', 0)
    if reason in ('no-fill', 'no-fill-ou-sem-midia'):
        return 'VAST NO-FILL (HTTP %s%s)' % (receipt.get('http_status') or '?',
                                               ' vazio' if receipt.get('empty') else ' sem anuncio')
    if reason == 'timeout-vast' or receipt.get('network_error') == 'timeout':
        return 'VAST TIMEOUT'
    if reason in ('falha-rede-vast', 'http-error'):
        return 'VAST NETWORK FAIL'
    if reason in ('vip', 'same-session', 'same-opening', 'return', 'busy', 'no-video', 'no-path'):
        return 'VAST SKIP'
    if reason == 'sem-stream-resolvido':
        return 'VAST CONTENT NOT READY'
    return 'VAST MEDIA FAIL'


def record(phase, receipt=None):
    """Append redacted JSONL to Kodi temp; never block content on log failure.

    One 128 KiB current file + one rotated file. No external telemetry or UI
    modification. Failure to write falls back to Kodi log, not an exception.
    """
    try:
        import xbmc
        data = receipt or {}
        safe = {key: value for key, value in data.items() if key in _FIELDS
                and (isinstance(value, (bool, int, float)) or value is None
                     or (key in ('motivo', 'reason', 'network_error') and value in _REASONS))}
        row = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
               'session': _SESSION, 'phase': phase if phase in ('boot', 'gate', 'request', 'tag', 'media', 'result') else 'result',
               'status': status(safe), **safe}
        if row['phase'] == 'boot':
            row['status'] = 'VAST MONITOR READY' if safe.get('active') else 'VAST MONITOR OFF'
        elif row['phase'] == 'request':
            row['status'] = 'VAST REQUEST'
        elif row['phase'] == 'tag' and not safe.get('network_error'):
            row['status'] = 'VAST HTTP %s' % (safe.get('http_status') or '?')
        text = json.dumps(row, ensure_ascii=True, allow_nan=False)
        try:
            import xbmcvfs
            path = xbmcvfs.translatePath('special://temp/smarted_vast.log')
        except (ImportError, AttributeError):
            path = xbmc.translatePath('special://temp/smarted_vast.log')
        if not path or path.startswith('special:'):
            return False
        with _LOCK:
            if os.path.exists(path) and os.path.getsize(path) >= 128 * 1024:
                os.replace(path, path + '.1')
            with open(path, 'a', encoding='utf-8') as output:
                output.write(text + '\n')
        return True
    except Exception:
        try:
            xbmc.log('[SmartVastDiag] local diagnostic write failed', getattr(xbmc, 'LOGWARNING', 2))
        except Exception:
            pass
        return False

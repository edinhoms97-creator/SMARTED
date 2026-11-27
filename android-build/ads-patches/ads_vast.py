# Function-level replacements for the ORIGINAL ads_vast.py, not a new UI.
# Runtime globals/helpers below belong to the original module and are kept.


def tag_configurada(padrao=''):
    """Validation stage: Clickadilla only, same tag on every device."""
    return VAST_TAG_PADRAO


def baixar(url, timeout=TIMEOUT_HTTP):
    """Verified TLS 1.2+, Chrome Android headers, bounded response/time."""
    if not url:
        return None
    try:
        import ssl
        import time as _clock
        from urllib.request import Request, urlopen
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        budget = min(max(float(timeout), 0.1), 8.0)
        deadline = _clock.monotonic() + budget
        request = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/xml,text/xml,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
        })
        with urlopen(request, timeout=budget, context=context) as response:
            chunks = []
            size = 0
            while True:
                if _clock.monotonic() >= deadline:
                    return None
                chunk = response.read(65536)
                if not chunk:
                    return b''.join(chunks)
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    return None
                chunks.append(chunk)
    except Exception:
        return None


def disparar(urls):
    """Tracking transport; original async scheduling is retained."""
    import datetime
    import random
    from urllib.parse import quote
    enviados = 0
    for url in urls or []:
        url = str(url).replace('[CACHEBUSTER]', str(random.randint(10000000, 99999999)))
        url = url.replace('[TIMESTAMP]', quote(datetime.datetime.now(datetime.timezone.utc).isoformat()))
        if baixar(url, timeout=6) is not None:
            enviados += 1
    return enviados


def reproduzir(anuncio, log=None, tempo_maximo=TEMPO_MAXIMO_ANUNCIO, tocar=None, dormir=None, anterior=''):
    """Keep the original Kodi player/helpers. Never complete a failed/stopped ad."""
    if not anuncio or not anuncio.get('url'):
        return {'exibido': False, 'motivo': 'sem-anuncio'}
    tocar = tocar or _tocar
    dormir = dormir or time.sleep
    anterior = anterior or _arquivo_atual()
    events = anuncio.get('eventos') or {}

    class _AdEvents(xbmc.Player):
        active = False
        ended = False
        stopped = False
        failed = False

        def onPlayBackEnded(self):
            if self.active:
                self.ended = True

        def onPlayBackStopped(self):
            if self.active:
                self.stopped = True

        def onPlayBackError(self):
            self.failed = True

    observer = _AdEvents()

    def error():
        urls = list(anuncio.get('errors') or []) + list(events.get('error') or [])
        _disparar_eventos([url.replace('[ERRORCODE]', '405') for url in urls])

    if not tocar(anuncio['url'], log):
        error()
        return {'exibido': False, 'motivo': 'player-recusou', 'precisa_restaurar': True, 'url_anuncio': anuncio['url']}
    if not _aguardar_anuncio_tocar(log, dormir=dormir, anterior=anterior):
        error()
        return {'exibido': False, 'motivo': 'nao-iniciou', 'precisa_restaurar': True, 'url_anuncio': anuncio['url']}
    observer.active = True
    _disparar_eventos(anuncio.get('impressao') or [])
    _disparar_eventos(events.get('start') or [])
    fired = {'start'}
    start = _agora()
    progress_at = start
    last_position = -1.0
    no_frame_at = None
    reason = 'interrompido'
    while _agora() - start < tempo_maximo:
        if observer.ended:
            reason = 'concluido'
            break
        if observer.failed:
            reason = 'erro-player'
            break
        if observer.stopped:
            reason = 'pulado'
            break
        if not _player_tocando_video():
            # Allow Kodi's end/stop callback to arrive, but never infer
            # completion merely because the player stopped.
            dormir(0.1)
            reason = 'concluido' if observer.ended else ('pulado' if observer.stopped else 'interrompido')
            break
        now = _agora()
        _garantir_tela_cheia()
        if _audio_sem_quadro_video():
            no_frame_at = now if no_frame_at is None else no_frame_at
            if now - no_frame_at >= TEMPO_TELA_PRETA_AUDIO:
                _desligar_surface_tela_preta(log=log)
                reason = 'tela-preta-sem-quadro'
                break
        else:
            no_frame_at = None
        position, duration = _posicao_e_duracao()
        if position > last_position + 0.01:
            last_position, progress_at = position, now
        elif now - progress_at >= min(float(TEMPO_TRAVAMENTO_ANUNCIO), 12.0):
            reason = 'travamento'
            break
        duration = duration or anuncio.get('duracao') or 0
        if duration > 0:
            for name, threshold in (('firstQuartile', .25), ('midpoint', .5), ('thirdQuartile', .75)):
                if position / duration >= threshold and name not in fired:
                    _disparar_eventos(events.get(name) or [])
                    fired.add(name)
        dormir(0.1)
    else:
        reason = 'timeout-anuncio'
    if reason == 'concluido':
        for name in ('firstQuartile', 'midpoint', 'thirdQuartile', 'complete'):
            if name not in fired:
                _disparar_eventos(events.get(name) or [])
                fired.add(name)
    elif reason == 'pulado':
        _disparar_eventos(events.get('skip') or [])
        fired.add('skip')
    else:
        error()
    observer.active = False
    return {'exibido': True, 'motivo': reason, 'segundos': round(_agora() - start, 1),
            'eventos': sorted(fired), 'precisa_restaurar': True, 'url_anuncio': anuncio['url']}


def restaurar(estado, log=None, espera=20, dormir=None, agora=None, url_anuncio=''):
    """Preserve the original reconnect routes, then CONFIRM the VOD seek."""
    restored = _smarted_restaurar_original(estado, log=log, espera=espera, dormir=dormir,
                                         agora=agora, url_anuncio=url_anuncio)
    if not restored or not estado:
        return False
    dormir = dormir or time.sleep
    agora = agora or _agora
    try:
        player = xbmc.Player()
        if not player.isPlayingVideo() or (url_anuncio and player.getPlayingFile() == url_anuncio):
            return False
        target = float(estado.get('posicao') or 0)
        if not estado.get('ao_vivo'):
            player.seekTime(target)
            deadline = agora() + 3
            confirmed = False
            for _ in range(60):
                if not player.isPlayingVideo():
                    break
                if abs(float(player.getTime()) - target) <= .25:
                    confirmed = True
                    break
                if agora() >= deadline:
                    break
                dormir(.05)
            if not confirmed:
                if log:
                    log('[SmartAds] VAST: seek nao confirmado; alvo %.3fs' % target)
                return False
        if estado.get('smarted_estava_pausado') and not xbmc.getCondVisibility('Player.Paused'):
            player.pause()
        return True
    except Exception:
        return False


def exibir_e_devolver(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
                     baixar_tag=None, tocar=None, dormir=None, estado=None):
    """No-fill leaves the content untouched; ad completion/skip restores it."""
    if estado is None:
        estado = estado_do_conteudo(log=log)
    if estado:
        estado = dict(estado)
        try:
            estado.setdefault('smarted_estava_pausado', bool(xbmc.getCondVisibility('Player.Paused')))
        except Exception:
            estado.setdefault('smarted_estava_pausado', False)
    receipt = exibir(log=log, tag=tag, altura_tela=altura_tela, tempo_maximo=tempo_maximo,
                     baixar_tag=baixar_tag, tocar=tocar, dormir=dormir)
    if estado and (receipt.get('exibido') or receipt.get('precisa_restaurar') or not _player_tocando_video()):
        confirmed = restaurar(estado, log=log, dormir=dormir, url_anuncio=receipt.get('url_anuncio', ''))
        receipt['conteudo_devolvido'] = confirmed
        receipt['retomada_confirmada'] = confirmed
    return receipt

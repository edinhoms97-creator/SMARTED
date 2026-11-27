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


def exibir(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
           baixar_tag=None, tocar=None, dormir=None):
    """Bounded wrapper chain; distinguish no-fill, network and malformed XML."""
    import xml.etree.ElementTree as _ET
    if not tag:
        return {'exibido': False, 'motivo': 'sem-tag'}
    deadline = _agora() + 8.0
    current = tag
    visited = set()
    for _ in range(PROFUNDIDADE_WRAPPER + 1):
        remaining = deadline - _agora()
        if remaining <= 0:
            return {'exibido': False, 'motivo': 'timeout-vast'}
        if current in visited:
            return {'exibido': False, 'motivo': 'wrapper-ciclico'}
        visited.add(current)
        try:
            data = baixar_tag(current) if baixar_tag else baixar(current, timeout=remaining)
        except Exception:
            data = None
        if data is None:
            return {'exibido': False, 'motivo': 'falha-rede-vast'}
        if not data or not data.strip():
            return {'exibido': False, 'motivo': 'no-fill'}
        try:
            _ET.fromstring(sem_namespace(data).strip())
        except Exception:
            return {'exibido': False, 'motivo': 'xml-invalido'}
        ad = escolher_anuncio(data, altura_tela)
        if ad:
            receipt = reproduzir(ad, log=log, tempo_maximo=tempo_maximo, tocar=tocar, dormir=dormir)
            receipt['tipo_midia'] = ad.get('tipo')
            receipt['duracao_anuncio'] = ad.get('duracao')
            return receipt
        target = tag_do_wrapper(data) or tag_do_vmap(data)
        if not target:
            return {'exibido': False, 'motivo': 'no-fill-ou-sem-midia'}
        current = target
    return {'exibido': False, 'motivo': 'limite-wrappers'}


def reproduzir(anuncio, log=None, tempo_maximo=TEMPO_MAXIMO_ANUNCIO, tocar=None, dormir=None, anterior=''):
    """Confirm progress, own callbacks and release failed ads before fallback."""
    if not anuncio or not anuncio.get('url'):
        return {'exibido': False, 'motivo': 'sem-anuncio'}
    tocar = tocar or _tocar
    dormir = dormir or time.sleep
    anterior = anterior or _arquivo_atual()
    events = anuncio.get('eventos') or {}
    owned_file = ['']

    class _AdEvents(xbmc.Player):
        active = False
        ended = False
        stopped = False
        failed = False

        def onPlayBackEnded(self):
            if self.active and not _player_tocando_video():
                self.ended = True

        def onPlayBackStopped(self):
            if self.active and not _player_tocando_video():
                self.stopped = True

        def onPlayBackError(self):
            if self.active and not _player_tocando_video():
                self.failed = True

    observer = _AdEvents()
    fired = set()
    started = False
    needs_restore = False
    reason = 'player-recusou'
    start = _agora()
    progress_at = start
    last_position = 0.0
    no_frame_at = None

    def error():
        urls = list(anuncio.get('errors') or []) + list(events.get('error') or [])
        _disparar_eventos([url.replace('[ERRORCODE]', '405') for url in urls])

    try:
        if tocar(anuncio['url'], log):
            needs_restore = _arquivo_atual() != anterior or not _player_tocando_video()
            if not _aguardar_anuncio_tocar(log, dormir=dormir, anterior=anterior):
                reason = 'nao-iniciou'
            else:
                owned_file[0] = _arquivo_atual()
                # The old VOD's clock is not proof that the ad has started.
                if not owned_file[0] or owned_file[0] == anterior:
                    reason = 'anuncio-nao-assumiu-player'
                else:
                    needs_restore = True
                    observer.active = True
                    reason = 'interrompido'
                    start = progress_at = _agora()
                    while _agora() - start < tempo_maximo:
                        playing = _player_tocando_video()
                        current = _arquivo_atual()
                        if playing and current and current != owned_file[0]:
                            reason, needs_restore = 'conteudo-alterado', False
                            break  # never stop/seek a newer user-selected film
                        if not playing:
                            # Kodi's end/stop notification may lag the media state.
                            for _ in range(8):
                                if observer.ended or observer.stopped or observer.failed:
                                    break
                                dormir(.1)
                            reason = ('concluido' if observer.ended and started else
                                      'pulado' if observer.stopped and started else
                                      'erro-player' if observer.failed else 'interrompido')
                            break
                        now = _agora()
                        no_frame = _audio_sem_quadro_video()
                        if no_frame:
                            no_frame_at = now if no_frame_at is None else no_frame_at
                            if now - no_frame_at >= min(float(TEMPO_TELA_PRETA_AUDIO), 4.0):
                                reason = 'tela-preta-sem-quadro'
                                break
                        else:
                            no_frame_at = None
                        position, duration = _posicao_e_duracao()
                        if position > last_position + .01:
                            last_position, progress_at = position, now
                            if not started and not no_frame:
                                started = True
                                _disparar_eventos(anuncio.get('impressao') or [])
                                _disparar_eventos(events.get('start') or [])
                                fired.add('start')
                        elif now - progress_at >= min(float(TEMPO_TRAVAMENTO_ANUNCIO), 8.0):
                            reason = 'travamento'
                            break
                        if started:
                            _garantir_tela_cheia()
                            duration = duration or anuncio.get('duracao') or 0
                            if duration > 0:
                                for name, threshold in (('firstQuartile', .25), ('midpoint', .5), ('thirdQuartile', .75)):
                                    if position / duration >= threshold and name not in fired:
                                        _disparar_eventos(events.get(name) or [])
                                        fired.add(name)
                        dormir(.1)
                    else:
                        reason = 'timeout-anuncio'
        else:
            needs_restore = _arquivo_atual() != anterior or not _player_tocando_video()
    except Exception:
        reason = 'excecao-player'
        needs_restore = _arquivo_atual() != anterior or not _player_tocando_video()
    finally:
        observer.active = False
        # Never leave the failed creative playing under the VOD. Never stop
        # the untouched VOD (refusal/no-fill) or a newer user-selected video.
        if needs_restore and _player_tocando_video():
            current = _arquivo_atual()
            if current and current != anterior and (not owned_file[0] or current == owned_file[0]):
                try:
                    xbmc.Player().stop()
                except Exception:
                    pass
    eligible = started and reason in ('concluido', 'pulado')
    if reason == 'concluido' and started:
        for name in ('firstQuartile', 'midpoint', 'thirdQuartile', 'complete'):
            if name not in fired:
                _disparar_eventos(events.get(name) or [])
                fired.add(name)
    elif reason == 'pulado' and started:
        _disparar_eventos(events.get('skip') or [])
        fired.add('skip')
    elif reason != 'conteudo-alterado':
        error()
    return {'exibido': eligible, 'iniciado': started, 'motivo': reason,
            'segundos': round(_agora() - start, 1), 'eventos': sorted(fired),
            'precisa_restaurar': needs_restore, 'url_anuncio': anuncio['url']}


def restaurar(estado, log=None, espera=20, dormir=None, agora=None, url_anuncio=''):
    """Reuse original reconnect candidates; never mistake the ad for the VOD."""
    if not estado or not estado.get('caminho'):
        return False
    dormir = dormir or time.sleep
    agora = agora or _agora
    target = float(estado.get('posicao') or 0)
    live = bool(estado.get('ao_vivo'))
    deadline = agora() + min(float(espera), 12.0)
    candidates = _candidatos_restauracao(estado)
    for route in candidates:
        try:
            opened = False
            if live:
                try:
                    import ao_vivo
                    opened = bool(ao_vivo._tocar_de_novo(route))
                except Exception:
                    pass
            if not opened:
                opened = _iniciar_em_tela_cheia(route, log=log)
            if not opened:
                continue
            route_deadline = min(deadline, agora() + 6.0)
            ready = False
            for _ in range(120):
                current = _arquivo_atual()
                if _player_tocando_video() and current and current != url_anuncio:
                    ready = True
                    break
                if agora() >= route_deadline:
                    break
                dormir(.05)
            if not ready:
                continue
            player = xbmc.Player()
            if not live:
                player.seekTime(target)
                seek_deadline = min(deadline, agora() + 3.0)
                confirmed = False
                for _ in range(60):
                    if not player.isPlayingVideo() or (url_anuncio and player.getPlayingFile() == url_anuncio):
                        break
                    if abs(float(player.getTime()) - target) <= .25:
                        confirmed = True
                        break
                    if agora() >= seek_deadline:
                        break
                    dormir(.05)
                if not confirmed:
                    continue
            _garantir_tela_cheia()
            if estado.get('smarted_estava_pausado') and not xbmc.getCondVisibility('Player.Paused'):
                player.pause()
            return True
        except Exception:
            continue
    if log:
        log('[SmartAdsDiag] retomada-nao-confirmada (sem declarar sucesso)')
    return False


def exibir_e_devolver(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
                     baixar_tag=None, tocar=None, dormir=None, estado=None):
    """No-fill is non-destructive; media exceptions still restore the VOD."""
    if estado is None:
        estado = estado_do_conteudo(log=log)
    if estado:
        estado = dict(estado)
        try:
            estado.setdefault('smarted_estava_pausado', bool(xbmc.getCondVisibility('Player.Paused')))
        except Exception:
            estado.setdefault('smarted_estava_pausado', False)
    def start_ad(url, logger):
        if estado and _player_tocando_video() and _arquivo_atual() != estado['caminho']:
            return False  # user changed the film while the tag was loading
        return (tocar or _tocar)(url, logger)
    try:
        receipt = exibir(log=log, tag=tag, altura_tela=altura_tela, tempo_maximo=tempo_maximo,
                         baixar_tag=baixar_tag, tocar=start_ad, dormir=dormir)
    except Exception:
        receipt = {'exibido': False, 'motivo': 'excecao-fluxo',
                   'precisa_restaurar': bool(estado and (_arquivo_atual() != estado['caminho'] or not _player_tocando_video()))}
    # A user selecting another film during the ad must not be sent back.
    restore = receipt.get('motivo') != 'conteudo-alterado' and estado and (
        receipt.get('exibido') or receipt.get('precisa_restaurar') or not _player_tocando_video())
    if restore:
        try:
            confirmed = restaurar(estado, log=log, dormir=dormir, url_anuncio=receipt.get('url_anuncio', ''))
        except Exception:
            confirmed = False
        receipt['conteudo_devolvido'] = bool(confirmed)
        receipt['retomada_confirmada'] = bool(confirmed)
        if not confirmed:
            receipt['exibido'] = False  # failure must not consume the cooldown
    return receipt

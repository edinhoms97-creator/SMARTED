# Function-level replacements for the ORIGINAL ads_vast.py, not a new UI.
# Runtime globals/helpers below belong to the original module and are kept.


def tag_configurada(padrao=''):
    """Validation stage: Clickadilla only, same tag on every device."""
    return VAST_TAG_PADRAO


def baixar(url, timeout=TIMEOUT_HTTP, user_agent=None):
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
            'User-Agent': user_agent or 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
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
    from ads_tracking import expand, device_user_agent
    enviados = 0
    ua = device_user_agent(xbmc)
    for url in urls or []:
        if baixar(expand(url, user_agent=ua), timeout=6, user_agent=ua) is not None:
            enviados += 1
    return enviados


def exibir(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
           baixar_tag=None, tocar=None, dormir=None):
    """Bounded wrapper chain; distinguish no-fill, network and malformed XML."""
    import xml.etree.ElementTree as _ET
    if not tag:
        return {'exibido': False, 'motivo': 'sem-tag'}
    from ads_tracking import expand, device_user_agent
    ua = device_user_agent(xbmc)
    inherited_impressions, inherited_errors, inherited_events = [], [], {}
    def failure(reason, code):
        if inherited_errors:
            _disparar_eventos([expand(url, error_code=code, user_agent=ua) for url in inherited_errors])
        return {'exibido': False, 'motivo': reason}
    session_deadline = _agora() + min(35.0, max(.5, float(tempo_maximo)))
    deadline = min(session_deadline, _agora() + 8.0)
    current = tag
    visited = set()
    for _ in range(PROFUNDIDADE_WRAPPER + 1):
        remaining = deadline - _agora()
        if remaining <= 0:
            return failure('timeout-vast', 301)
        if current in visited:
            return failure('wrapper-ciclico', 302)
        visited.add(current)
        try:
            request_url = expand(current, user_agent=ua)
            data = baixar_tag(request_url) if baixar_tag else baixar(request_url, timeout=remaining)
        except Exception:
            data = None
        if data is None:
            return failure('falha-rede-vast', 301)
        if not data or not data.strip():
            return failure('no-fill', 303)
        try:
            root = _ET.fromstring(sem_namespace(data).strip())
        except Exception:
            return failure('xml-invalido', 100)
        ad = escolher_anuncio(data, altura_tela)
        if ad:
            ad = dict(ad)
            ad['impressao'] = inherited_impressions + list(ad.get('impressao') or [])
            ad['errors'] = inherited_errors + list(ad.get('errors') or [])
            events = {name: list(urls) for name, urls in inherited_events.items()}
            for name, urls in (ad.get('eventos') or {}).items():
                events.setdefault(name, []).extend(urls)
            ad['eventos'] = events
            remaining_session = session_deadline - _agora()
            if remaining_session <= 0:
                return failure('timeout-vast', 301)
            receipt = reproduzir(ad, log=log, tempo_maximo=remaining_session, tocar=tocar, dormir=dormir)
            receipt['tipo_midia'] = ad.get('tipo')
            receipt['duracao_anuncio'] = ad.get('duracao')
            return receipt
        wrapper = next(iter(root.iter('Wrapper')), None)
        if wrapper is not None:
            inherited_impressions.extend((n.text or '').strip() for n in wrapper.iter('Impression') if (n.text or '').strip())
            inherited_errors.extend((n.text or '').strip() for n in wrapper.iter('Error') if (n.text or '').strip())
            for node in wrapper.iter('Tracking'):
                if node.get('event') and (node.text or '').strip():
                    inherited_events.setdefault(node.get('event'), []).append(node.text.strip())
        target = tag_do_wrapper(data) or tag_do_vmap(data)
        if not target:
            return failure('no-fill-ou-sem-midia', 303)
        current = target
    return failure('limite-wrappers', 302)


def _media_escolhido(inline, altura_tela=0):
    """Conservative progressive MP4 for Android cold hardware-decoder start.

    Codec/profile metadata in VAST is optional and is NOT a bitstream probe.
    Explicitly incompatible codecs/profiles are rejected; unknown MP4 is a
    fallback protected by the same progress/absolute watchdogs.
    """
    import re
    from urllib.parse import urlsplit
    candidates = []
    def number(value):
        try:
            return max(0, int(float(value or 0)))
        except (ValueError, TypeError, OverflowError):
            return 0
    target = min(number(altura_tela) or 720, 720)
    for linear in inline.iter('Linear'):
        for media in linear.iter('MediaFile'):
            url = (media.text or '').strip()
            if urlsplit(url).scheme.lower() not in ('https', 'http'):
                continue
            mime = (media.get('type') or '').lower().split(';')[0].strip()
            if mime not in ('video/mp4', 'video/x-m4v') and not (not mime and urlsplit(url).path.lower().endswith(('.mp4', '.m4v'))):
                continue
            if (media.get('delivery') or 'progressive').lower() != 'progressive':
                continue
            codec = (media.get('codec') or media.get('codecs') or '').lower()
            profile = (media.get('profile') or '').lower()
            if any(word in codec for word in ('hev', 'hvc', 'h265', 'h.265', 'av01', 'av1', 'vp9', 'vp09', 'vp8', '10bit')):
                continue
            avc = re.search(r'avc[13]\.([0-9a-f]{2})', codec)
            if (avc and avc.group(1) not in ('42', '4d')) or (profile and profile not in ('baseline', 'constrained baseline', 'main')):
                continue
            if codec and not any(word in codec for word in ('avc1', 'avc3', 'h264', 'h.264')):
                continue
            if ('mp4a.' in codec and 'mp4a.40.2' not in codec) or any(word in codec for word in ('ac-3', 'ec-3', 'opus', 'vorbis', 'dts')):
                continue
            width, height = number(media.get('width')), number(media.get('height'))
            bitrate = max(number(media.get('bitrate')), number(media.get('maxBitrate')))
            if width > 1920 or height > 1080 or bitrate > 5000:
                continue
            # Known standard AVC/AAC, moderate bitrate and 720p are preferred;
            # do not equate the display's resolution with decoder suitability.
            rank = (0 if height and height <= target else 1 if height else 2,
                    0 if codec else 1, 0 if bitrate and bitrate <= 3000 else 1,
                    abs((height or target) - target), bitrate or 2500)
            candidates.append((rank, {'url': url, 'tipo': mime or 'video/mp4',
                                     'largura': width, 'altura': height, 'bitrate': bitrate,
                                     'codec': codec, 'progressivo': True}))
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else None


def reproduzir(anuncio, log=None, tempo_maximo=TEMPO_MAXIMO_ANUNCIO, tocar=None, dormir=None, anterior=''):
    """Confirm progress, own callbacks and release failed ads before fallback."""
    if not anuncio or not anuncio.get('url'):
        return {'exibido': False, 'motivo': 'sem-anuncio'}
    tocar = tocar or _tocar
    dormir = dormir or time.sleep
    anterior = anterior or _arquivo_atual()
    events = anuncio.get('eventos') or {}
    owned_file = ['']
    trace_start, observed_position = _agora(), [0.0]
    trace_rows, last_native_event = [], ['none']
    def trace(event, native=False, accepted=True):
        if native:
            last_native_event[0] = event
        row = {'ms': max(0, round((_agora() - trace_start) * 1000)),
               'position': round(observed_position[0], 3), 'event': event,
               'accepted': bool(accepted)}
        if len(trace_rows) >= 64:
            del trace_rows[1]
        trace_rows.append(row)

    class _AdEvents(xbmc.Player):
        active = False
        ended = False
        stopped = False
        failed = False

        def onPlayBackEnded(self):
            trace('ended', native=True, accepted=self.active and not _player_tocando_video())
            if self.active and not _player_tocando_video():
                self.ended = True

        def onPlayBackStopped(self):
            trace('stopped', native=True, accepted=self.active and not _player_tocando_video())
            if self.active and not _player_tocando_video():
                self.stopped = True

        def onPlayBackError(self):
            trace('error', native=True, accepted=self.active and (_arquivo_atual() == owned_file[0] or not _player_tocando_video()))
            if self.active and (_arquivo_atual() == owned_file[0] or not _player_tocando_video()):
                self.failed = True

        def onAVStarted(self):
            trace('AVStarted', native=True, accepted=self.active)

        def onAVChange(self):
            trace('AVChange', native=True, accepted=self.active)

        def onPlayBackPaused(self):
            trace('paused-callback', native=True, accepted=self.active)

        def onPlayBackResumed(self):
            trace('resumed-callback', native=True, accepted=self.active)

        def onPlayBackSeek(self, time, seekOffset):
            trace('seek-callback', native=True, accepted=self.active)

    observer = _AdEvents()
    fired = set()
    started = False
    needs_restore = False
    reason = 'player-recusou'
    start = _agora()
    # The active-time budget includes decoder startup, but excludes native pause.
    import math
    try:
        declared = float(anuncio.get('duracao') or 0)
        if not math.isfinite(declared) or declared <= 0:
            declared = 30.0
    except (TypeError, ValueError):
        declared = 30.0
    absolute_limit = min(35.0, max(0.5, float(tempo_maximo)), declared + 5.0)
    deadline = start + absolute_limit
    progress_at = start
    last_position = 0.0
    no_frame_at = None
    paused_at = None
    paused_total = 0.0

    def error():
        urls = list(anuncio.get('errors') or []) + list(events.get('error') or [])
        from ads_tracking import expand, device_user_agent
        _disparar_eventos([expand(url, error_code=405, user_agent=device_user_agent(xbmc)) for url in urls])

    try:
        trace('dispatch')
        if tocar(anuncio['url'], log):
            needs_restore = _arquivo_atual() != anterior or not _player_tocando_video()
            # Do not enter the original wait helper: its independent startup
            # timeout could outlive the entire pre-roll watchdog budget.
            startup_deadline = min(deadline, _agora() + 8.0)
            while _agora() < startup_deadline:
                if _player_tocando_video() and _arquivo_atual() not in ('', anterior):
                    break
                dormir(.5)
            if not (_player_tocando_video() and _arquivo_atual() not in ('', anterior)):
                reason = 'nao-iniciou'
            else:
                owned_file[0] = _arquivo_atual()
                # The old VOD's clock is not proof that the ad has started.
                if not owned_file[0] or owned_file[0] == anterior:
                    reason = 'anuncio-nao-assumiu-player'
                else:
                    needs_restore = True
                    observer.active = True
                    trace('owned')
                    reason = 'interrompido'
                    progress_at = _agora()
                    while _agora() < deadline:
                        playing = _player_tocando_video()
                        current = _arquivo_atual()
                        if playing and current and current != owned_file[0]:
                            reason, needs_restore = 'conteudo-alterado', False
                            break  # never stop/seek a newer user-selected film
                        if observer.failed:
                            reason = 'erro-player'
                            break
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
                        paused = bool(xbmc.getCondVisibility('Player.Paused'))
                        if paused:
                            if paused_at is None:
                                paused_at = now
                                trace('paused-observed')
                            # Native controls own play/pause. A paused clock
                            # is not decoder failure. Do not toggle/reopen or
                            # force fullscreen while controls have focus.
                            progress_at, no_frame_at = now, None
                            before_sleep = _agora()
                            dormir(.5)
                            pause_elapsed = max(0.0, _agora() - before_sleep)
                            paused_total += pause_elapsed
                            deadline += pause_elapsed
                            continue
                        if paused_at is not None:
                            paused_at, progress_at, no_frame_at = None, now, None
                            trace('resumed-observed')
                        no_frame = _audio_sem_quadro_video()
                        if no_frame:
                            no_frame_at = now if no_frame_at is None else no_frame_at
                            if now - no_frame_at >= 3.0:
                                reason = 'tela-preta-sem-quadro'
                                break
                        else:
                            no_frame_at = None
                        position, duration = _posicao_e_duracao()
                        observed_position[0] = float(position or 0)
                        if duration and math.isfinite(float(duration)) and float(duration) > 0:
                            deadline = min(deadline, start + float(duration) + 5.0 + paused_total)
                        if position > last_position + .01:
                            last_position, progress_at = position, now
                            if not started and not no_frame:
                                started = True
                                _disparar_eventos(anuncio.get('impressao') or [])
                                _disparar_eventos(events.get('start') or [])
                                fired.add('start')
                                trace('real-start')
                                _garantir_tela_cheia()
                                from ads_resume import guard_transition
                                guard_transition(xbmc, owned_file[0])
                        elif now - progress_at >= 3.0:
                            reason = 'travamento'
                            break
                        if started:
                            duration = duration or anuncio.get('duracao') or 0
                            if duration > 0:
                                for name, threshold in (('firstQuartile', .25), ('midpoint', .5), ('thirdQuartile', .75)):
                                    if position / duration >= threshold and name not in fired:
                                        _disparar_eventos(events.get(name) or [])
                                        fired.add(name)
                        dormir(.5)
                    else:
                        reason = 'timeout-anuncio'
        else:
            needs_restore = _arquivo_atual() != anterior or not _player_tocando_video()
    except Exception:
        reason = 'excecao-player'
        needs_restore = _arquivo_atual() != anterior or not _player_tocando_video()
    finally:
        terminal_native_event, detected_at = last_native_event[0], _agora()
        trace(reason)
        observer.active = False
        # Never leave the failed creative playing under the VOD. Never stop
        # the untouched VOD (refusal/no-fill) or a newer user-selected video.
        if needs_restore:
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
            'precisa_restaurar': needs_restore, 'url_anuncio': anuncio['url'],
            'player_trace': list(trace_rows), 'last_native_event': terminal_native_event,
            'freeze_position': round(observed_position[0], 3) if reason in ('travamento', 'tela-preta-sem-quadro') else None,
            'freeze_wall_ms': round(((no_frame_at if reason == 'tela-preta-sem-quadro' else progress_at) - trace_start) * 1000) if reason in ('travamento', 'tela-preta-sem-quadro') else None,
            'freeze_detected_wall_ms': round((detected_at - trace_start) * 1000) if reason in ('travamento', 'tela-preta-sem-quadro') else None}


def restaurar(estado, log=None, espera=20, dormir=None, agora=None, url_anuncio=''):
    """Direct resolved playback only: never reopen plugin/server selectors."""
    from ads_resume import capture, restore
    state = estado if estado and estado.get('_resolved_snapshot') else capture(estado, xbmc.Player(), xbmc)
    return restore(state, xbmc, wait=espera, sleep=dormir or time.sleep, clock=agora or _agora,
                   ad_url=url_anuncio, fullscreen=_garantir_tela_cheia, log=log)


def exibir_e_devolver(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
                     baixar_tag=None, tocar=None, dormir=None, estado=None):
    """No-fill is non-destructive; media exceptions still restore the VOD."""
    if estado is None:
        estado = estado_do_conteudo(log=log)
    if estado:
        from ads_resume import capture
        estado = capture(dict(estado), xbmc.Player(), xbmc)
        try:
            estado.setdefault('smarted_estava_pausado', bool(xbmc.getCondVisibility('Player.Paused')))
        except Exception:
            estado.setdefault('smarted_estava_pausado', False)
    def start_ad(url, logger):
        nonlocal estado
        if not estado:
            estado = estado_do_conteudo(log=log)
        if not estado or not estado.get('resolved_streams'):
            return False  # no safe direct return; never reopen the provider UI
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
        if confirmed:
            receipt['caminho_devolvido'] = estado.get('_restored_path', '')
        if not confirmed:
            receipt['exibido'] = False  # failure must not consume the cooldown
    from ads_resume import write_lifecycle
    write_lifecycle(receipt, xbmc)
    return receipt


def estado_do_conteudo(player=None, log=None):
    """Capture the original live/VOD state plus a session-owned resolved item."""
    from ads_resume import capture
    player = player or xbmc.Player()
    state = _smarted_estado_do_conteudo_original(player=player, log=log)
    return capture(state, player, xbmc)

# Function-level replacements for the ORIGINAL ads_vast.py, not a new UI.
# Runtime globals/helpers below belong to the original module and are kept.


def tag_configurada(padrao=''):
    """Validation stage: Clickadilla only, same tag on every device."""
    return VAST_TAG_PADRAO


def baixar(url, timeout=TIMEOUT_HTTP, diagnostico=None):
    """Verified TLS 1.2+, real runtime User-Agent, bounded response/time."""
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
        from ads_tracking import device_user_agent
        request = Request(url, headers={
            'User-Agent': device_user_agent(xbmc),
            'Accept': 'application/xml,text/xml,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
        })
        with urlopen(request, timeout=budget, context=context) as response:
            if diagnostico is not None:
                diagnostico['http_status'] = getattr(response, 'status', None) or getattr(response, 'code', None)
            chunks = []
            size = 0
            while True:
                if _clock.monotonic() >= deadline:
                    if diagnostico is not None:
                        diagnostico['network_error'] = 'timeout'
                    return None
                chunk = response.read(65536)
                if not chunk:
                    if diagnostico is not None:
                        diagnostico['empty'] = not bool(size)
                        diagnostico['elapsed_ms'] = round((_clock.monotonic() - (deadline - budget)) * 1000)
                    return b''.join(chunks)
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    if diagnostico is not None:
                        diagnostico['network_error'] = 'too-large'
                    return None
                chunks.append(chunk)
    except Exception as exc:
        if diagnostico is not None:
            import socket
            from urllib.error import HTTPError, URLError
            diagnostico['network_error'] = ('timeout' if isinstance(exc, (TimeoutError, socket.timeout))
                or (isinstance(exc, URLError) and isinstance(exc.reason, (TimeoutError, socket.timeout)))
                else 'http-error' if isinstance(exc, HTTPError) else 'network')
            if isinstance(exc, HTTPError):
                diagnostico['http_status'] = exc.code
        return None


def disparar(urls):
    """Tracking transport; original async scheduling is retained."""
    from ads_tracking import expand, device_user_agent
    enviados = 0
    ua = device_user_agent(xbmc)
    for url in urls or []:
        if baixar(expand(url, user_agent=ua), timeout=6) is not None:
            enviados += 1
    return enviados


def exibir(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
           baixar_tag=None, tocar=None, dormir=None):
    """Bounded wrapper chain; distinguish no-fill, network and malformed XML."""
    import xml.etree.ElementTree as _ET
    if not tag:
        return {'exibido': False, 'motivo': 'sem-tag'}
    from ads_tracking import expand, device_user_agent
    from ads_diagnostics import record
    transport = {}
    ua = device_user_agent(xbmc)
    inherited_impressions, inherited_errors, inherited_events = [], [], {}
    def failure(reason, code):
        if inherited_errors:
            _disparar_eventos([expand(url, error_code=code, user_agent=ua) for url in inherited_errors])
        return {'exibido': False, 'motivo': reason, **transport}
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
            transport.clear()
            data = baixar_tag(request_url) if baixar_tag else baixar(request_url, timeout=remaining, diagnostico=transport)
        except Exception as exc:
            transport['network_error'] = 'timeout' if isinstance(exc, TimeoutError) else 'network'
            data = None
        record('tag', transport)
        if data is None:
            return failure('timeout-vast' if transport.get('network_error') == 'timeout' else 'falha-rede-vast', 301)
        if not data or not data.strip():
            transport['empty'] = True
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
            media = []
            for inline in root.iter('InLine'):
                choices = _media_escolhido(inline, altura_tela, todos=True)
                if choices and choices[0]['url'] == ad['url']:
                    media = choices
                    break
            media = media or [{'url': ad['url'], 'tipo': ad.get('tipo')}]
            replaced, receipt = False, None
            for index, candidate in enumerate(media):
                remaining_session = session_deadline - _agora()
                if remaining_session <= 0:
                    break
                attempt = dict(ad, **candidate)
                receipt = reproduzir(attempt, log=log, tempo_maximo=remaining_session, tocar=tocar, dormir=dormir)
                replaced = replaced or bool(receipt.get('precisa_restaurar'))
                receipt.update(tipo_midia=candidate.get('tipo'), duracao_anuncio=ad.get('duracao'),
                               tentativa_midia=index + 1, media_attempts=index + 1, **transport)
                record('media', {**receipt, **{k: candidate[k] for k in ('largura', 'altura', 'bitrate') if k in candidate}})
                if (receipt.get('iniciado') or receipt.get('motivo') not in
                        ('startup-timeout', 'erro-player', 'excecao-player', 'player-recusou')):
                    break
            if receipt is None:
                return failure('timeout-vast', 301)
            receipt['precisa_restaurar'] = replaced and receipt.get('motivo') != 'conteudo-alterado'
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
            if any(True for _node in root.iter('MediaFile')):
                inherited_errors.extend((n.text or '').strip() for n in root.iter('Error') if (n.text or '').strip())
                return failure('sem-midia-compativel', 403)
            return failure('no-fill-ou-sem-midia', 303)
        current = target
    return failure('limite-wrappers', 302)


def _media_escolhido(inline, altura_tela=0, todos=False):
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
    for linear in list(inline.iter('Linear'))[:1]:
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
            if width > 1280 or height > 720 or bitrate > 3000:
                continue
            # Known standard AVC/AAC, moderate bitrate and 720p are preferred;
            # do not equate the display's resolution with decoder suitability.
            rank = (0 if height and height <= target else 1 if height else 2,
                    0 if codec else 1, 0 if bitrate and bitrate <= 3000 else 1,
                    abs((height or target) - target), bitrate or 2500)
            candidates.append((rank, {'url': url, 'tipo': mime or 'video/mp4',
                                     'largura': width, 'altura': height, 'bitrate': bitrate,
                                     'codec': codec, 'progressivo': True}))
    ordered, seen = [], set()
    for _, candidate in sorted(candidates, key=lambda pair: pair[0]):
        if candidate['url'] not in seen:
            seen.add(candidate['url'])
            ordered.append(candidate)
    return ordered[:3] if todos else (ordered[0] if ordered else None)


def reproduzir(anuncio, log=None, tempo_maximo=TEMPO_MAXIMO_ANUNCIO, tocar=None, dormir=None, anterior=''):
    """Original Kodi player; 3.5s to real progress, then 3s stall/+5s margin."""
    if not anuncio or not anuncio.get('url'):
        return {'exibido': False, 'motivo': 'sem-anuncio', 'iniciado': False}
    import math
    tocar, dormir = tocar or _tocar, dormir or time.sleep
    anterior = anterior or _arquivo_atual()
    url = anuncio['url']
    events = anuncio.get('eventos') or {}
    class _AdEvents(xbmc.Player):
        active = False
        ended = False
        stopped = False
        failed = False
        def onPlayBackEnded(self):
            if self.active and started and not _player_tocando_video():
                self.ended = True
        def onPlayBackStopped(self):
            if self.active and started and not _player_tocando_video():
                self.stopped = True
        def onPlayBackError(self):
            if self.active and (_arquivo_atual() == url or (started and not _player_tocando_video())):
                self.failed = True
    observer = _AdEvents()
    fired, started, dispatched, needs_restore = set(), False, False, False
    reason = 'player-recusou'
    start = _agora()
    try:
        declared = float(anuncio.get('duracao') or 30)
        if not math.isfinite(declared) or declared <= 0:
            declared = 30.0
    except (TypeError, ValueError):
        declared = 30.0
    deadline = start + min(35.0, max(.1, float(tempo_maximo)), declared + 5.0)
    startup_deadline = min(deadline, start + 3.5)
    last_position, progress_at, no_frame_at = 0.0, start, None
    startup_position = None
    try:
        dispatched = bool(tocar(url, log))
        if dispatched:
            observer.active = True
            reason = 'startup-timeout'
            while _agora() < deadline:
                now = _agora()
                current, playing = _arquivo_atual(), _player_tocando_video()
                if current and current not in (anterior, url):
                    reason, needs_restore = 'conteudo-alterado', False
                    break
                if current == url or not playing:
                    needs_restore = True
                if observer.failed:
                    reason = 'erro-player'
                    break
                if not started:
                    if now >= startup_deadline:
                        reason = 'startup-timeout'
                        break
                    # isPlayingVideo/AVStarted/codec headers alone do not
                    # prove a first frame. Require a progressing media clock.
                    if playing and current == url:
                        position, duration = _posicao_e_duracao()
                        position = float(position or 0)
                        no_frame = _audio_sem_quadro_video()
                        advanced = (math.isfinite(position) and startup_position is not None
                                    and position > startup_position + .01)
                        startup_position = position
                        if advanced:
                            last_position = position
                        if advanced and position > .1 and not no_frame:
                            started, progress_at, reason = True, now, 'interrompido'
                            _disparar_eventos(anuncio.get('impressao') or [])
                            _disparar_eventos(events.get('start') or [])
                            fired.add('start')
                    if not started:
                        if now >= startup_deadline:
                            reason = 'startup-timeout'
                            break
                        dormir(min(.1, max(0, startup_deadline - now)))
                        continue
                if not playing:
                    for _ in range(8):
                        if observer.ended or observer.stopped or observer.failed:
                            break
                        dormir(.1)
                    reason = ('concluido' if observer.ended else 'pulado' if observer.stopped
                              else 'erro-player' if observer.failed else 'interrompido')
                    break
                position, duration = _posicao_e_duracao()
                position = float(position or 0)
                if not math.isfinite(position):
                    raise ValueError('invalid media clock')
                if duration and math.isfinite(float(duration)) and float(duration) > 0:
                    deadline = min(deadline, start + float(duration) + 5.0)
                if _audio_sem_quadro_video():
                    no_frame_at = now if no_frame_at is None else no_frame_at
                    if now - no_frame_at >= 3.0:
                        reason = 'tela-preta-sem-quadro'
                        break
                else:
                    no_frame_at = None
                if position > last_position + .01:
                    last_position, progress_at = position, now
                elif now - progress_at >= 3.0:
                    reason = 'travamento'
                    break
                _garantir_tela_cheia()
                total = duration or anuncio.get('duracao') or 0
                if total and float(total) > 0:
                    for name, fraction in (('firstQuartile', .25), ('midpoint', .5), ('thirdQuartile', .75)):
                        if position / float(total) >= fraction and name not in fired:
                            _disparar_eventos(events.get(name) or [])
                            fired.add(name)
                dormir(min(.5, max(0, deadline - _agora())))
            else:
                reason = 'timeout-anuncio' if started else 'startup-timeout'
    except Exception:
        reason = 'excecao-player'
        needs_restore = dispatched and (_arquivo_atual() != anterior or not _player_tocando_video())
    finally:
        observer.active = False
        current = _arquivo_atual()
        if reason != 'conteudo-alterado' and dispatched and (current == url or (not current and not _player_tocando_video())):
            needs_restore = True
            try:
                xbmc.Player().stop()  # release failed creative BEFORE fallback/content
            except Exception:
                pass
    if reason == 'concluido' and started:
        _disparar_eventos(events.get('complete') or [])
        fired.add('complete')
    elif reason == 'pulado' and started:
        _disparar_eventos(events.get('skip') or [])
        fired.add('skip')
    elif reason != 'conteudo-alterado':
        from ads_tracking import expand, device_user_agent
        urls = list(anuncio.get('errors') or []) + list(events.get('error') or [])
        _disparar_eventos([expand(value, error_code=405, user_agent=device_user_agent(xbmc)) for value in urls])
    return {'exibido': started and reason in ('concluido', 'pulado'), 'iniciado': started,
            'motivo': reason, 'segundos': round(_agora() - start, 2), 'eventos': sorted(fired),
            'precisa_restaurar': needs_restore, 'url_anuncio': url}


def estado_do_conteudo(player=None, log=None):
    """Capture the original live/VOD state plus a session-owned resolved item."""
    from ads_resume import capture
    player = player or xbmc.Player()
    state = _smarted_estado_do_conteudo_original(player=player, log=log)
    return capture(state, player, xbmc)


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
    expected_content = (estado or {}).get('caminho') or _arquivo_atual()
    unavailable = [False]
    creative_paths, replaced = set(), [False]
    def start_ad(url, logger):
        nonlocal estado
        # Query VAST even if the first callback preceded a usable snapshot.
        # Recapture before replacing anything; the main stream keeps playing
        # during tag IO. No-fill never touches its player/surface.
        current = _arquivo_atual()
        if current and current not in ({expected_content} | creative_paths):
            return False
        if not estado or not estado.get('resolved_streams'):
            estado = estado_do_conteudo(log=log)
        if not estado or not estado.get('resolved_streams'):
            unavailable[0] = True
            return False
        if not replaced[0]:
            if current != estado['caminho']:
                return False
            estado.setdefault('smarted_estava_pausado', bool(xbmc.getCondVisibility('Player.Paused')))
            try:
                estado['posicao'] = float(xbmc.Player().getTime()) or 0.0
            except Exception:
                pass
        creative_paths.add(url)
        accepted = (tocar or _tocar)(url, logger)
        replaced[0] = replaced[0] or bool(accepted)
        return accepted
    try:
        receipt = exibir(log=log, tag=tag, altura_tela=altura_tela, tempo_maximo=tempo_maximo,
                         baixar_tag=baixar_tag, tocar=start_ad, dormir=dormir)
    except Exception:
        receipt = {'exibido': False, 'motivo': 'excecao-fluxo',
                   'precisa_restaurar': bool(estado and (_arquivo_atual() != estado['caminho'] or not _player_tocando_video()))}
    if unavailable[0]:
        receipt.update(motivo='sem-stream-resolvido', precisa_restaurar=False)
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
    from ads_diagnostics import record
    record('result', receipt)
    return receipt

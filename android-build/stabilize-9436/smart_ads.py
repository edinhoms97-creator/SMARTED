# Applied to reconstructed 9436b5e + tracking; native providers/player retained.
def motor_anuncio(agora=None):
    """User-authorized VAST validation on phones too; AdMob activation deferred."""
    from ads_openings import emit
    reason = 'validacao-vast-celular-admob-adiado'
    if globals().get('_smarted_provider_signature') != (MOTOR_VAST, reason):
        globals()['_smarted_provider_signature'] = (MOTOR_VAST, reason)
        emit(xbmc, 'provider-selected', provider=MOTOR_VAST, reason=reason)
    return MOTOR_VAST, reason


def abrir_anuncio(atividade, log=None, uri=''):
    """Native VAST never left Kodi: no external-activity focus wait on return."""
    disparou = tocar_anuncio(atividade, log, uri)
    if disparou:
        if not usar_vast():
            _kodi_em_foco()  # preserve the original external-ad contract
        if atividade == ATIVIDADE_PREROLL:
            try:
                if xbmc.Player().isPlayingVideo() and not xbmc.getCondVisibility('Window.IsActive(fullscreenvideo)'):
                    xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')
            except Exception:
                pass
    return disparou


def iniciar_monitor(log=None, intervalo=None):
    from ads_openings import watch_home
    monitor = _smarted_iniciar_monitor_original(log, intervalo)
    if monitor is not None:
        watch_home(monitor, xbmc)
    return monitor


class MonitorPreRoll:
    def _talvez_mostrar(self):
        from ads_openings import blocked, emit
        if not usar_vast():
            emit(xbmc, 'native-admob-eligibility-delegated')
            return self._smarted_talvez_mostrar_original()
        from ads_openings import state, context, emit, blocked, reset_boundary
        if self._em_vast:
            blocked(self, xbmc, 'ad-cycle-running')
            return 'blocked'
        if not _e_video(self):
            blocked(self, xbmc, 'video-not-ready')
            return 'pending'
        path = self._caminho()
        if not path:
            blocked(self, xbmc, 'path-not-ready')
            return 'pending'
        if vip_ativo():
            blocked(self, xbmc, 'vip-exempt')
            return 'blocked'
        if getattr(self, '_smarted_gate_path', None) != path:
            self._smarted_gate_path = path
            emit(xbmc, 'eligibility-ready')
        ledger = state(self)
        channel = xbmc.getInfoLabel('VideoPlayer.ChannelName') or ''
        generation = ledger.claim(_normalizar_caminho_chave(path), channel)
        if generation is None:
            blocked(self, xbmc, 'ad-cycle-running' if ledger.in_ad else 'opening-already-attempted')
            return 'blocked'
        self._smarted_last_block = None
        reset_boundary(self, xbmc, 'opening-accepted')
        context(generation)
        emit(xbmc, 'opening-claimed')
        self.sessao = generation
        self.ultimo_caminho = path
        self._ate_ignorar_volta_vast = 0.0
        self._volta_vast_chave = ''
        try:
            # Only an accepted new opening clears persisted eligibility. Repeated
            # AV/Started, pause, seek and native ad-return never enter this branch.
            with _LOCK_OPORTUNIDADE:
                esquecer()
                mostrar_preroll(self.log, self.intervalo, caminho=path,
                                chave=_chave_conteudo(path), sessao=generation,
                                disparar=self._disparar)
        except Exception as exc:
            emit(xbmc, 'opening-failed-open', error=type(exc).__name__)
        finally:
            if not self._em_vast:  # VIP, scheduling failure or ineligible metadata
                ledger.finish(generation, _normalizar_caminho_chave(path))
        return 'accepted'

    def _disparar(self, atividade, log):
        if not usar_vast():
            return self._smarted_disparar_original(atividade, log)
        if self._em_vast:
            return False
        path = self._caminho() or self.ultimo_caminho or ''
        self._em_vast = True
        try:
            threading.Thread(target=self._ciclo_vast, args=(atividade, log, path),
                             name='smarted-vast-preroll', daemon=True).start()
        except Exception:
            self._em_vast = False
            if log:
                log('[SmartAdsDiag] falha-agendamento-vast')
        return False  # queued work is not an impression

    def _ciclo_vast(self, atividade, log, caminho_inicial=''):
        from ads_openings import state, context, emit
        ledger = state(self)
        generation = ledger.generation
        context(generation)
        success = False
        changed = False
        receipt = {}
        with self._vast_lock:
            self._em_vast = True
            try:
                # Only synchronize dispatch bookkeeping, NOT network/media/tracking.
                # Callback threads must never wait for the duration of an ad.
                with _LOCK_OPORTUNIDADE:
                    key = _chave_conteudo(caminho_inicial)
                globals()['_smarted_last_receipt'] = {}
                success = bool(abrir_anuncio(atividade, log))
                receipt = globals().get('_smarted_last_receipt') or {}
                changed = receipt.get('motivo') == 'conteudo-alterado'
                with _LOCK_OPORTUNIDADE:
                    if success:
                        ads_regra.registrar_anuncio(key, time.time())
                        ads_regra.concluir_anuncio(time.time())
                    else:
                        ads_regra.cancelar_anuncio(key)
            except Exception as exc:
                with _LOCK_OPORTUNIDADE:
                    ads_regra.cancelar_anuncio(caminho_inicial)
                emit(xbmc, 'cycle-failed-open', error=type(exc).__name__)
            finally:
                returned = self._caminho() or caminho_inicial
                returned_key = _normalizar_caminho_chave(returned)
                # No creative/restore ran: a different VOD is a selection, not
                # an alias of the failed request's movie. Keep same-channel
                # token refresh and actual native restoration aliases intact.
                no_media_attempt = not receipt.get('url_anuncio') and not receipt.get('precisa_restaurar') and 'retomada_confirmada' not in receipt
                same_channel = bool(ledger.channel and xbmc.getInfoLabel('VideoPlayer.ChannelName') == ledger.channel)
                if not success and no_media_attempt and returned_key and returned_key not in ledger.aliases and not same_channel:
                    changed = True
                    emit(xbmc, 'content-changed-during-attempt')
                # Alternate resolved URLs from the native resume belong to this
                # opening too; no eighteen-second wall-clock suppression needed.
                ledger.finish(generation, '' if changed else _normalizar_caminho_chave(returned))
                self._em_vast = False
                emit(xbmc, 'cycle-finished', ad_and_resume_confirmed=success)
            if not changed:
                self._garantir_player_tela_cheia()
                if returned:
                    self._vigiar_imagem(returned)  # reference helper, live only
        if changed:
            ledger.close()
            self._talvez_mostrar()  # genuinely new selection, never the old VOD
        return success

    def onPlayBackStopped(self):
        if not usar_vast():
            return self._smarted_stop_original()
        from ads_openings import state, emit
        if self._em_vast or not state(self).close():
            return
        # A stop notification is the boundary. isPlayingVideo may still expose
        # the old frame/file here; it must not veto closing the old opening.
        self._ate_ignorar_volta_vast = 0.0
        self._volta_vast_chave = ''
        self._smarted_gate_path = None
        self._smarted_stopped_path = self._caminho() or self.ultimo_caminho or ''
        self._smarted_wait_for_video_boundary = True
        self._limpar_retomada()
        emit(xbmc, 'opening-closed', boundary='stop')

    def onPlayBackEnded(self):
        if not usar_vast():
            return self._smarted_end_original()
        from ads_openings import state, emit
        if self._em_vast:
            return
        # Continuous live reconnect is not a user opening. VOD/episode end is,
        # even if the content ended inside the former 18-second suppression.
        try:
            import ao_vivo
            if self.ultimo_caminho and ao_vivo.eh_ao_vivo(self.ultimo_caminho):
                return
        except Exception:
            pass
        if state(self).close():
            self._ate_ignorar_volta_vast = 0.0
            self._volta_vast_chave = ''
            self._smarted_gate_path = None
            self._smarted_stopped_path = self._caminho() or self.ultimo_caminho or ''
            self._smarted_wait_for_video_boundary = True
            self._limpar_retomada()
            emit(xbmc, 'opening-closed', boundary='end')

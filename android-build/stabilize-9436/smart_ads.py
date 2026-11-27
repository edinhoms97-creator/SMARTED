# Applied only to reconstructed 9436b5e + restored tracking. No provider/UI patch.
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
        if not usar_vast():
            return self._smarted_talvez_mostrar_original()
        from ads_openings import state, context, emit
        ledger = state(self)
        if self._em_vast or not _e_video(self):
            return
        path = self._caminho()
        if not path:
            return
        channel = xbmc.getInfoLabel('VideoPlayer.ChannelName') or ''
        generation = ledger.claim(_normalizar_caminho_chave(path), channel)
        if generation is None:
            return
        self._smarted_wait_for_video_boundary = False
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
            self._smarted_wait_for_video_boundary = True
            self._limpar_retomada()
            emit(xbmc, 'opening-closed', boundary='end')

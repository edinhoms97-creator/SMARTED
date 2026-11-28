# Function/method replacements in the original ad module only; no UI changes.
def iniciar_monitor(log=None, intervalo=None):
    """Install the original native observer; catch up if AV preceded install."""
    monitor = _smarted_iniciar_monitor_original(log, intervalo)
    if monitor is not None and usar_vast():
        # Event-driven catch-up, not a startup delay or a second player.
        monitor._talvez_mostrar()
    return monitor


def motor_anuncio(agora=None):
    return (MOTOR_VAST, 'validacao-clickadilla-1508180-admob-desativado')


def tocar_anuncio_de_video(log=None):
    """A dispatch/start failure is NOT an impression or a consumed interval."""
    if globals().get('_smarted_vast_running'):
        if log:
            log('[SmartAdsDiag] requisicao-duplicada-ignorada')
        return False
    globals()['_smarted_vast_running'] = True
    try:
        module = _ads_vast()
        if module is None:
            if log:
                log('[SmartAdsDiag] modulo-vast-indisponivel')
            return False
        tag = module.tag_configurada(VAST_TAG_PADRAO)
        try:
            height = int(float(_info('System.ScreenHeight') or 0))
        except Exception:
            height = 0
        if log:
            log('[SmartAdsDiag] solicitacao-vast-iniciada')
        receipt = module.exibir_e_devolver(log=log, tag=tag, altura_tela=height)
        globals()['_smarted_vast_restored_path'] = receipt.get('caminho_devolvido', '') if receipt.get('retomada_confirmada') else ''
        success = bool(receipt.get('exibido')) and receipt.get('retomada_confirmada') is not False
        if log:
            # No film URLs, tracking tokens, account IDs or personal settings.
            import json as _json
            safe = {key: receipt.get(key) for key in ('motivo', 'iniciado', 'segundos', 'retomada_confirmada', 'tipo_midia', 'duracao_anuncio', 'last_native_event', 'freeze_position', 'freeze_wall_ms', 'freeze_detected_wall_ms', 'player_trace')}
            safe['anuncio_confirmado'] = success
            log('[SmartAdsDiag] ' + _json.dumps(safe, ensure_ascii=True))
        return success
    except Exception as exc:
        if log:
            log('[SmartAdsDiag] excecao-vast:%s (conteudo liberado)' % type(exc).__name__)
        return False
    finally:
        globals()['_smarted_vast_running'] = False


def mostrar_preroll(log=None, intervalo=None, agora=None, caminho=None, chave=None,
                    sessao=None, disparar=None, forcar=False):
    """One attempted pre-roll per content opening, never per pause/seek/resume."""
    with _LOCK_OPORTUNIDADE:
        if vip_ativo():
            return False  # retain the original VIP exemption
        key = chave or _chave_conteudo(caminho)
        if not globals().get('_smarted_regra_iniciada'):
            # A new app process must not inherit the previous process's
            # claimed opportunity or the old two-minute cooldown state.
            data = ads_regra._ler()
            for field in ('tentativa', 'anunciado', 'anunciados', 'em_exibicao', 'piso'):
                data.pop(field, None)
            ads_regra._gravar(data)
            globals()['_smarted_regra_iniciada'] = True
            globals()['_ultima_sessao'] = None
            globals()['_ultimo_caminho_preroll'] = None
        if (not forcar and sessao is not None and sessao == globals().get('_ultima_sessao')
                and key == globals().get('_ultimo_caminho_preroll')):
            return False
        if not forcar:
            ads_regra.abrir_troca(key)
            allowed, reason = ads_regra.pode_anunciar(key, agora)
            if not allowed:
                globals()['_ultima_sessao'] = sessao
                if log:
                    log('[SmartAdsDiag] sem-nova-tentativa: ' + reason)
                return False
            # Claim BEFORE dispatch: no-fill/failure also consume this one
            # opportunity, but never block a different content opening.
            data = ads_regra._ler()
            data['tentativa'] = key
            ads_regra._gravar(data)
        globals()['_ultima_sessao'] = sessao
        result = (disparar or tocar_anuncio_com_aviso)(ATIVIDADE_PREROLL, log)
        if result and not forcar:
            ads_regra.registrar_anuncio(key, time.time())
            ads_regra.concluir_anuncio(time.time())
        elif not result and not forcar:
            ads_regra.cancelar_anuncio(key)
        globals()['_ultimo_momento'] = time.time()
        globals()['_ultimo_caminho_preroll'] = key
        if log:
            log('[SmartAdsDiag] regra=uma-tentativa-por-abertura; sem-cooldown')
        return bool(result)


class MonitorPreRoll:
    # Only listed VAST gate/dispatch/stop methods are replaced. Other methods/attributes in
    # the ORIGINAL MonitorPreRoll class are preserved by AST scope checks.
    def _talvez_mostrar(self):
        if not usar_vast():
            return self._smarted_talvez_mostrar_original()
        if self._em_vast:
            return
        try:
            if not _e_video(self):
                return  # onAVStarted invokes this again; no timer/sleep
            path = self._caminho()
            if not path:
                return
            normalized = _normalizar_caminho_chave(path)
            if (self._ate_ignorar_volta_vast > time.monotonic()
                    and self._volta_vast_chave and normalized == self._volta_vast_chave):
                return
            if normalized != self._volta_vast_chave:
                self._ate_ignorar_volta_vast, self._volta_vast_chave = 0.0, ''
            # Legacy AdMob Retomada.e_volta is not a VAST opening identity.
            # Do not let that other lifecycle swallow the first content.
            self.ultimo_caminho = path
            mostrar_preroll(self.log, self.intervalo, caminho=path,
                            chave=_chave_conteudo(path), sessao=self.sessao,
                            disparar=self._disparar)
            if not self._em_vast:
                self._vigiar_imagem(path)  # VIP/dedup: original live helper, never with a queued ad
        except Exception as exc:
            if self.log:
                log_message = '[SmartAdsDiag] abertura-vast:%s' % type(exc).__name__
                self.log(log_message)

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
        # Scheduling is NOT showing an ad. The original caller holds
        # _LOCK_OPORTUNIDADE and may cancel before returning. The worker
        # acquires that lock AFTER the caller exits, then books the result.
        return False

    def _ciclo_vast(self, atividade, log, caminho_inicial=''):
        success = False
        with _LOCK_OPORTUNIDADE:
            with self._vast_lock:
                self._em_vast = True
                key = caminho_inicial
                globals()['_smarted_vast_restored_path'] = ''
                try:
                    key = _chave_conteudo(caminho_inicial)
                    success = bool(abrir_anuncio(atividade, log))
                    if success:
                        ads_regra.registrar_anuncio(key, time.time())
                        ads_regra.concluir_anuncio(time.time())
                    else:
                        ads_regra.cancelar_anuncio(key)
                except Exception as exc:
                    success = False
                    ads_regra.cancelar_anuncio(key)
                    if log:
                        log('[SmartAdsDiag] ciclo-vast:%s' % type(exc).__name__)
                finally:
                    # Suppress late resume callbacks even after failure;
                    # never request another ad for the returned same VOD.
                    try:
                        restored = globals().pop('_smarted_vast_restored_path', '')
                        returned = restored if restored and self._caminho() == restored else caminho_inicial
                        self._volta_vast_chave = _normalizar_caminho_chave(returned)
                        if restored and returned == restored:
                            # A proxy->direct URL or server fallback is still
                            # the SAME opening, not another ad opportunity.
                            data = ads_regra._ler()
                            data['conteudo'] = _chave_conteudo(restored)
                            data['tentativa'] = data['conteudo']
                            ads_regra._gravar(data)
                            self.ultimo_caminho = restored
                        self._ate_ignorar_volta_vast = time.monotonic() + 18.0
                    finally:
                        self._em_vast = False
                self._garantir_player_tela_cheia()
                path = self._caminho() or caminho_inicial
                if path:
                    self._vigiar_imagem(path)  # original helper: live only
        return success

    def onPlayBackStopped(self):
        # A real close creates a fresh opportunity, even reopening the same
        # URL within seconds. A stale ad stop must not reset an active VOD.
        if self._em_vast or _e_video(self):
            return
        self._ate_ignorar_volta_vast = 0.0
        self._volta_vast_chave = ''
        self._limpar_retomada()
        self.ultimo_caminho = None
        self.sessao += 1
        esquecer()

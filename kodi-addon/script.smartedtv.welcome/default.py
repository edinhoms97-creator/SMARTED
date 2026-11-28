# -*- coding: utf-8 -*-
"""Janela independente de boas-vindas do SMARTEDTV para Kodi Omega 21.

Esta tela é somente a camada visual. A validação VIP, o compartilhamento
nativo e a continuidade do fluxo gratuito precisam ser conectados às funções
existentes do SMARTEDTV quando este módulo for integrado ao addon principal.
"""
import xbmc
import xbmcgui
import xbmcaddon
import os


class WelcomeDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super(WelcomeDialog, self).__init__(*args, **kwargs)
        self._closing = False

    def onInit(self):
        # Mantém o foco inicial no campo de código, como no HTML de referência.
        try:
            self.setFocusId(310)
        except Exception:
            pass

    def onClick(self, control_id):
        if control_id == 312:
            self.setProperty("show_free_dialog", "true")
            try:
                self.setFocusId(905)
            except Exception:
                pass
        elif control_id == 905:
            self.clearProperty("show_free_dialog")
            try:
                self.setFocusId(312)
            except Exception:
                pass
        elif control_id == 906:
            # Modo gratuito com anúncios: tenta o pre-roll VAST
            # (Clickadilla, Spot #1508180) e fecha a janela. Qualquer
            # falha (no-fill, rede, timeout) cai no fallback limpo:
            # a janela fecha e o addon principal assume o canal/VOD.
            self._play_preroll_or_close()
        elif control_id == 121:
            self._apk_action(share=True)
        elif control_id in (122, 123):
            # Same IDs as the original welcome: download / update.
            self._apk_action()
        elif control_id in (120, 311):
            # Sem integração com checkout, share ou API VIP nesta janela isolada:
            # não simula sucesso nem validações.
            return

    def _apk_action(self, share=False):
        """Delegate to original link handlers; no alternate skin or installer."""
        try:
            import vip
            return vip.compartilhar() if share else vip.open_apk_download()
        except ImportError:
            # This standalone reference is not bundled into the original APK.
            # Keep its link action useful without inventing a backend.
            from apk_link import open_or_share
            return open_or_share(share=share)

    def _play_preroll_or_close(self):
        """Keep dialog alive until ad + restoration finish; never block UI."""
        if getattr(self, "_ad_busy", False):
            return
        self._ad_busy = True
        import threading

        def run():
            try:
                import vast_player
                result = vast_player.run_session()
                xbmc.log("SMARTEDTV VAST: " + str(result), xbmc.LOGINFO)
            except Exception as exc:
                xbmc.log("SMARTEDTV VAST fallback: " + str(exc), xbmc.LOGWARNING)
            finally:
                self._ad_busy = False
                self.close()

        threading.Thread(target=run).start()

    def onAction(self, action):
        if getattr(self, "_ad_busy", False):
            return
        if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU):
            if self.getProperty("show_free_dialog") == "true":
                self.clearProperty("show_free_dialog")
                try:
                    self.setFocusId(312)
                except Exception:
                    pass
                return
            self.close()


def open_welcome():
    addon = xbmcaddon.Addon()
    addon_path = addon.getAddonInfo("path")
    dialog = WelcomeDialog(
        "DialogWelcome.xml",
        addon_path,
        "Default",
        "1080i"
    )
    dialog.doModal()
    del dialog


if __name__ == "__main__":
    open_welcome()

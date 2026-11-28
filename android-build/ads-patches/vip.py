# Only APK-link action functions/constants of the ORIGINAL vip.py are patched.
# License validation, cloud requests, payments and device logic stay unchanged.


def resolver_apk_publicado():
    """One official universal APK, independent of Mobile/TV/projector folders."""
    return APK, 'dropbox-oficial'


def open_apk_download():
    """Direct Dropbox download via Android browser/system download manager.

    Android owns download/installer permissions and user confirmation. Never
    pretend an install completed just because an ACTION_VIEW was dispatched.
    """
    return abrir_url(APK, 'download do SMARTEDTV.apk')


def procurar_atualizacao():
    """The update button opens exactly the same official universal APK."""
    return open_apk_download()


def compartilhar(texto=None):
    """Share the official APK, or display it if Android has no share target."""
    message = 'Baixe o SMARTEDTV aqui: %s' % APK
    if _compartilhar_texto(message):
        return True
    try:
        xbmcgui.Dialog().textviewer('Compartilhar aplicativo', message)
        return True
    except Exception:
        return False


def abrir_dropbox():
    """Welcome button 121: share/display the official APK, not a folder page."""
    return compartilhar()


def dropbox_configurado():
    """The pinned public universal APK does not require a per-device folder."""
    return bool(APK and APK.startswith('https://www.dropbox.com/scl/fi/') and 'dl=1' in APK)


def url_do_apk_por_nome():
    """Keep the original welcome download fallback on the same official file."""
    return APK

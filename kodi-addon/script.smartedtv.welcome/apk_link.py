"""Official APK action for the standalone reference, not an APK UI replacement."""
import xbmc
import xbmcgui

APK_URL = 'https://www.dropbox.com/scl/fi/ixfw289m0sibcyfyrxf9g/SMARTEDTV.apk?rlkey=z59708sngkysw0c1ntmmur6lv&st=okcfec6i&dl=1'


def open_or_share(share=False):
    if share:
        # Displaying the complete official link is also usable on TV devices
        # without any app registered for Android's ACTION_SEND.
        xbmcgui.Dialog().textviewer('Compartilhar aplicativo', APK_URL)
    else:
        xbmc.executebuiltin('StartAndroidActivity(,android.intent.action.VIEW,,%s)' % APK_URL)
    return True

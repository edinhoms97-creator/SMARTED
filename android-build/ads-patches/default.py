# ORIGINAL script.smartedtv.welcome/default.py: APK-link helper/constants patch.
# All original class methods, XML/layout, focus and boot behavior are unchanged.
# APK_DOWNLOAD and DROPBOX_URL are replaced from the pinned official URL by
# tools/patch_original_ads.py. This file does not define a replacement welcome.


def _link_do_dropbox_desta_versao(vip=None):
    """Same official universal APK even in the original welcome fallback."""
    return APK_DOWNLOAD

# -*- coding: utf-8 -*-
"""One Android/Kodi entry point; no device-dependent ad provider routing."""
import xbmc
import xbmcgui


def main():
    monitor = xbmc.Monitor()
    home = xbmcgui.Window(10000)
    key = "Smartedtv.Startup.Launched"
    # A global Kodi window property survives service restarts in the same
    # process, but not restarting the app. Avoid stacking modal welcomes.
    if home.getProperty(key) == "true":
        return
    # Wait for Kodi's initial GUI before opening a modal; bounded, abortable.
    for _ in range(100):
        if monitor.waitForAbort(.1):
            return
        if (not xbmc.getCondVisibility("Window.IsActive(startup)")
                and not xbmc.getCondVisibility("Window.IsActive(splash)")):
            break
    home.setProperty(key, "true")
    xbmc.executebuiltin("RunScript(script.smartedtv.welcome)")


if __name__ == "__main__":
    main()

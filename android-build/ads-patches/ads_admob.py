# -*- coding: utf-8 -*-
"""Isolated AdMob configuration, intentionally NOT initialized/imported at boot.

The existing Android SDK/bridge is not changed. Only activate in a later,
separate validation stage after VAST approval and ad-format verification.
"""
ENABLED = False
APP_ID = 'ca-app-pub-2066014755407744~5076693043'
APP_OPEN_ID = 'ca-app-pub-2066014755407744/4214378379'
VIDEO_ID = 'ca-app-pub-2066014755407744/3572039686'


def enabled():
    return ENABLED is True

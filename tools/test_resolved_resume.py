#!/usr/bin/env python3
"""Resolved pre-roll restoration contracts. No network, server UI or emulator."""
import argparse
import importlib.util
import json
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / 'android-build/ads-patches'
PRIMARY = 'https://video.invalid/movie.mp4?token=one|User-Agent=Kodi&Referer=https%3A%2F%2Fhost.invalid'
SECOND = 'https://backup.invalid/movie.mp4?token=two'


class Item:
    def __init__(self, path=PRIMARY, label='Movie', identity='tt123', kind='movie', episode=1):
        self.path, self.label, self.identity, self.kind, self.episode = path, label, identity, kind, episode
        self.properties = {'ForceResolvePlugin': 'true', 'inputstream': 'inputstream.adaptive', 'inputstream.adaptive.stream_headers': 'Referer=original'}
    def getPath(self): return self.path
    def setPath(self, path): self.path = path
    def getProperty(self, name): return self.properties.get(name, '')
    def setProperty(self, name, value): self.properties[name] = value
    def getVideoInfoTag(self): return self
    def getMediaType(self): return self.kind
    def getUniqueID(self, key): return self.identity
    def getSeason(self): return 1
    def getEpisode(self): return self.episode
    def setInfo(self, *args): pass
    def setArt(self, *args): pass
    def setMimeType(self, value): self.mime = value
    def setContentLookup(self, value): pass


class Runtime:
    def __init__(self):
        self.now = 1000.
        self.file, self.position, self.playing = PRIMARY, 42.125, True
        self.item = Item()
        self.observers, self.opens, self.stops, self.seeks, self.pauses = [], [], [], [], []
        self.fail = set()
        self.stall = set()
        self.ignore_seek = set()
        self.startup_delay = 0
        self.pending = None
        self.started = self.now
        self.playlist = []
        self.properties = {}
        self.user_change = False
        runtime = self
        class Player:
            def __init__(self):
                if type(self) is not Player:
                    runtime.observers.append(self)
            def isPlayingVideo(self): return runtime.playing
            def getPlayingFile(self): return runtime.file
            def getTime(self): return runtime.position
            def getTotalTime(self): return 120
            def getPlayingItem(self): return runtime.item
            def play(self, url, listitem=None, windowed=False):
                runtime.opens.append((url, listitem, windowed))
                runtime.started = runtime.now
                if runtime.startup_delay:
                    runtime.pending = (url, runtime.now + runtime.startup_delay)
                else:
                    runtime.file, runtime.position, runtime.playing = url, 0, True
                    for observer in runtime.observers:
                        observer.onAVStarted()
            def seekTime(self, target):
                runtime.seeks.append((runtime.file, target))
                if runtime.file not in runtime.ignore_seek:
                    runtime.position = target
            def stop(self):
                runtime.stops.append(runtime.file)
                runtime.file, runtime.playing = '', False
            def pause(self): runtime.pauses.append(runtime.file)
        self.Player = Player
        self.kodi = types.SimpleNamespace(Player=Player, PLAYLIST_VIDEO=1,
            PlayList=lambda _: types.SimpleNamespace(size=lambda:len(self.playlist), __getitem__=lambda _, i:self.playlist[i]),
            getCondVisibility=lambda _:False,
            executeJSONRPC=lambda _:json.dumps({'result':{'item':{'title':'Exact movie','art':{'thumb':'local-thumb'}}}}),
            executebuiltin=lambda *args: self.forbidden())
        # Special-method lookup uses the class, not a SimpleNamespace field.
        class Playlist:
            def size(self): return len(runtime.playlist)
            def __getitem__(self, index): return runtime.playlist[index]
        self.kodi.PlayList = lambda _:Playlist()
        class Window:
            def setProperty(self, key, value): runtime.properties[key] = value
            def getProperty(self, key): return runtime.properties.get(key, '')
            def clearProperty(self, key): runtime.properties.pop(key, None)
        self.gui = types.SimpleNamespace(Window=lambda _: Window(), ListItem=lambda label='',path='': Item(path=path,label=label))

    def forbidden(self):
        raise AssertionError('No RunPlugin/PlayMedia/plugin route or selector allowed')

    def sleep(self, seconds):
        self.now += seconds
        if self.user_change and self.now - self.started >= .2:
            self.file = 'https://other.invalid/user-new-film.mp4'
            self.position = 3
            self.playing = True
            return
        if self.pending:
            url, at = self.pending
            if self.now >= at:
                self.file, self.position, self.playing = url, 0, True
                self.pending = None
                for observer in self.observers:
                    observer.onAVStarted()
            return
        if self.file in self.fail and self.now - self.started >= .2:
            self.playing = False
            for observer in self.observers:
                observer.onPlayBackError()
        elif self.playing and self.file not in self.stall:
            self.position += seconds

    def snapshot(self, live=False, alternatives=None):
        return resume.capture({'caminho': PRIMARY, 'url_real': '',
            'plugin_path':'plugin://provider/?mode=choose-server', 'posicao':42.125,
            'ao_vivo':live, 'content_id':'movie-one', 'alternativas_resolvidas':alternatives or []},
            self.Player(), self.kodi, self.gui)

    def restore(self, state, **kwargs):
        self.file, self.position, self.playing = 'ad', 21, False
        return resume.restore(state, self.kodi, self.gui, sleep=self.sleep,
                              clock=lambda:self.now, ad_url='ad', **kwargs)


class Tests(unittest.TestCase):
    def alternate(self):
        return {'url':SECOND,'resolved':True,'content_id':'movie-one',
                'properties':{'inputstream.adaptive.stream_headers':'Referer=backup'}}

    def test_snapshot_retains_exact_url_listitem_headers_metadata_and_timestamp(self):
        r = Runtime()
        state = r.snapshot()
        self.assertIs(state['listitem'], r.item)
        self.assertIs(state['resolved_streams'][0]['listitem'], r.item)
        self.assertEqual(state['resolved_streams'][0]['url'], PRIMARY)
        self.assertEqual(state['metadata']['title'], 'Exact movie')
        self.assertEqual(state['posicao'],42.125)
        self.assertNotIn('plugin://', str(state['resolved_streams']))

    def test_movie_restores_direct_item_without_reopening_selector(self):
        r = Runtime()
        self.assertTrue(r.restore(r.snapshot()))
        self.assertEqual(r.opens[0], (PRIMARY,r.item,False))
        self.assertEqual(r.item.getProperty('ForceResolvePlugin'),'false')
        self.assertEqual(r.item.getProperty('original_listitem_url'),'')
        self.assertEqual(r.seeks,[(PRIMARY,42.125)])
        self.assertGreaterEqual(r.position,42.125)
        self.assertLess(r.position,43.7)

    def test_live_channel_restores_cleanly_without_seek(self):
        r = Runtime()
        self.assertTrue(r.restore(r.snapshot(live=True)))
        self.assertEqual(r.opens[0][0],PRIMARY)
        self.assertEqual(r.seeks,[])
        self.assertGreater(r.position,0)

    def test_expired_primary_automatically_tries_next_resolved_server(self):
        r = Runtime(); r.fail.add(PRIMARY)
        state = r.snapshot(alternatives=[self.alternate()])
        self.assertTrue(r.restore(state))
        self.assertEqual([c[0] for c in r.opens],[PRIMARY,SECOND])
        self.assertEqual(r.file,SECOND)
        self.assertEqual(r.opens[1][1].getProperty('inputstream.adaptive.stream_headers'),'Referer=backup')
        self.assertIn((SECOND,42.125),r.seeks)

    def test_live_fallback_uses_next_stream_without_seek(self):
        r = Runtime(); r.fail.add(PRIMARY)
        self.assertTrue(r.restore(r.snapshot(live=True,alternatives=[self.alternate()])))
        self.assertEqual(r.file,SECOND)
        self.assertEqual(r.seeks,[])

    def test_resume_stall_falls_back_not_false_success_from_isplaying(self):
        r = Runtime(); r.stall.add(PRIMARY)
        self.assertTrue(r.restore(r.snapshot(alternatives=[self.alternate()])))
        self.assertEqual(r.file,SECOND)
        self.assertIn(PRIMARY,r.stops)

    def test_unconfirmed_seek_falls_back(self):
        r = Runtime(); r.ignore_seek.add(PRIMARY)
        self.assertTrue(r.restore(r.snapshot(alternatives=[self.alternate()])))
        self.assertEqual(r.file,SECOND)

    def test_plugin_only_target_does_not_become_a_restore_candidate(self):
        r = Runtime(); r.item.path='plugin://provider/choose'
        state=resume.capture({'caminho':'plugin://provider/choose','posicao':42},r.Player(),r.kodi,r.gui)
        self.assertEqual(state['resolved_streams'],[])
        self.assertFalse(r.restore(state))
        self.assertEqual(r.opens,[])

    def test_plugin_alternatives_or_other_film_are_never_selected(self):
        r=Runtime()
        alternatives=[{'url':'plugin://provider/select','resolved':True,'content_id':'movie-one'},
                      {'url':SECOND,'resolved':True,'content_id':'other-film'},
                      {'url':SECOND,'resolved':False,'content_id':'movie-one'}]
        self.assertEqual(len(r.snapshot(alternatives=alternatives)['resolved_streams']),1)

    def test_playlist_next_episode_is_not_an_alternative_server(self):
        r=Runtime(); r.item=Item(kind='episode',identity='series',episode=1)
        r.playlist=[r.item,Item(SECOND,kind='episode',identity='series',episode=2)]
        self.assertEqual(len(r.snapshot()['resolved_streams']),1)
        r.playlist.append(Item(SECOND,kind='episode',identity='series',episode=1))
        self.assertEqual(len(r.snapshot()['resolved_streams']),2)

    def test_cross_interpreter_context_is_bound_to_current_stream_and_consumed_once(self):
        r=Runtime()
        self.assertTrue(resume.publish_context(PRIMARY,[self.alternate()],'movie-one',r.gui))
        self.assertEqual(len(r.snapshot()['resolved_streams']),2)
        self.assertEqual(len(r.snapshot()['resolved_streams']),1)
        resume.publish_context(SECOND,[self.alternate()],'movie-one',r.gui)
        self.assertEqual(len(r.snapshot()['resolved_streams']),1)

    def test_actual_brazuca_movies_list_restores_only_resolved_media_slots(self):
        from urllib.parse import quote
        r=Runtime()
        slots=SECOND+'|https://mixdrop.invalid/e/host-page|plugin://provider/choose'
        origin='plugin://plugin.video.BrazucaPlay.Matrix/?mode=3&url='+quote('#movies_list='+slots,safe='')
        state=resume.capture({'caminho':PRIMARY,'plugin_path':origin,'posicao':42.125},r.Player(),r.kodi,r.gui)
        self.assertEqual([c['url'] for c in state['resolved_streams']],[PRIMARY,SECOND])
        r.fail.add(PRIMARY)
        self.assertTrue(r.restore(state))
        self.assertEqual(r.file,SECOND)

    def test_stale_context_does_not_restore_old_tokens(self):
        r=Runtime()
        resume.publish_context(PRIMARY,[self.alternate()],'movie-one',r.gui,now=0)
        self.assertEqual(len(r.snapshot()['resolved_streams']),1)

    def test_user_new_selection_is_not_sought_or_stopped(self):
        r=Runtime(); r.user_change=True
        self.assertFalse(r.restore(r.snapshot()))
        self.assertEqual(r.file,'https://other.invalid/user-new-film.mp4')
        self.assertNotIn(r.file,r.stops)
        self.assertFalse(any(url==r.file for url,pos in r.seeks))

    def test_exhaustion_is_bounded_and_never_reopens_plugin(self):
        r=Runtime(); r.fail.update((PRIMARY,SECOND))
        self.assertFalse(r.restore(r.snapshot(alternatives=[self.alternate()]),wait=2))
        self.assertLessEqual(r.now-1000,2.2)
        self.assertEqual([c[0] for c in r.opens],[PRIMARY,SECOND])

    def test_paused_vod_is_repaused_only_after_confirmed_seek(self):
        r=Runtime(); state=r.snapshot();state['smarted_estava_pausado']=True
        self.assertTrue(r.restore(state))
        self.assertEqual(r.pauses,[PRIMARY])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--original',type=Path)
    args,rest=parser.parse_known_args();folder=args.original or FOLDER
    spec=importlib.util.spec_from_file_location('tested_ads_resume',folder/'ads_resume.py')
    resume=importlib.util.module_from_spec(spec);spec.loader.exec_module(resume)
    unittest.main(argv=[__file__]+rest)

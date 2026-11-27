# Replacements for tag/transport/tracking only. Native playback remains in base.
def tag_configurada(padrao=''):
    # Do not let a saved Hilltop window property override this test's network.
    return VAST_TAG_PADRAO


def baixar(url, timeout=TIMEOUT_HTTP, user_agent=None):
    """Original GET contract, verified TLS 1.2+ and real runtime pixel UA."""
    if not url:
        return None
    try:
        import ssl
        from urllib.request import Request, urlopen
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        request = Request(url, headers={
            'User-Agent': user_agent or 'Mozilla/5.0 (Linux; Android 11; Android TV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/xml, text/xml, */*',
        })
        response = urlopen(request, timeout=timeout, context=context)
        try:
            return response.read()
        finally:
            response.close()
    except Exception:
        return None


def disparar(urls):
    """Only URLs supplied by VAST; keep base's asynchronous scheduling."""
    from ads_tracking import expand, device_user_agent
    ua = device_user_agent(xbmc)
    return sum(baixar(expand(url, user_agent=ua), timeout=6, user_agent=ua) is not None
               for url in urls or [])


def exibir(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
           baixar_tag=None, tocar=None, dormir=None):
    """Base parser/player; add selected Wrapper tracking inheritance only."""
    import xml.etree.ElementTree as ET
    from ads_tracking import expand, device_user_agent
    ua = device_user_agent(xbmc)
    impressions, errors, events = [], [], {}
    visited = set()
    fetch = baixar_tag or baixar
    current = tag
    def fail(reason, code):
        _disparar_eventos([expand(url, error_code=code, user_agent=ua) for url in errors])
        return {'exibido': False, 'motivo': reason}
    if not current:
        return fail('sem-tag', 100)
    for level in range(PROFUNDIDADE_WRAPPER + 1):
        if current in visited:
            return fail('wrapper-ciclico', 302)
        visited.add(current)
        try:
            data = fetch(expand(current, user_agent=ua))
        except Exception:
            data = None
        if data is None:
            return fail('tag-sem-resposta', 301)
        if not data or not data.strip():
            return fail('no-fill', 303)
        try:
            root = ET.fromstring(sem_namespace(data).strip())
        except Exception:
            return fail('xml-invalido', 100)
        ad = escolher_anuncio(data, altura_tela)
        if ad:
            ad = dict(ad)
            ad['impressao'] = impressions + list(ad.get('impressao') or [])
            ad['errors'] = errors + list(ad.get('errors') or [])
            combined = {name: list(urls) for name, urls in events.items()}
            for name, urls in (ad.get('eventos') or {}).items():
                combined.setdefault(name, []).extend(urls)
            ad['eventos'] = combined
            receipt = reproduzir(ad, log=log, tempo_maximo=tempo_maximo,
                                 tocar=tocar, dormir=dormir)
            receipt['anuncio'] = ad.get('id') or ad.get('url')
            return receipt
        target = tag_do_wrapper(data) or tag_do_vmap(data)
        if not target:
            return fail('vast-sem-criativo', 303)
        # Select the same Wrapper URI as the base, never collect sibling Ads.
        selected = next((node for node in root.iter('Wrapper')
                         if (node.findtext('.//VASTAdTagURI') or node.findtext('.//VASTAdTagURL') or '').strip() == target), None)
        if selected is not None:
            impressions.extend((node.text or '').strip() for node in selected.iter('Impression') if (node.text or '').strip())
            errors.extend((node.text or '').strip() for node in selected.iter('Error') if (node.text or '').strip())
            for node in selected.iter('Tracking'):
                if (node.text or '').strip():
                    events.setdefault(node.get('event', ''), []).append(node.text.strip())
        if level == PROFUNDIDADE_WRAPPER:
            return fail('wrapper-limite', 302)
        current = target
    return fail('wrapper-limite', 302)

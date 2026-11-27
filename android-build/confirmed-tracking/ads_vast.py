# TRACKING ONLY over user-confirmed reference 9436b5e. No native control changes.
def disparar(urls):
    """Pixel GETs with expanded macros and actual Kodi UA, not tag headers."""
    import ssl
    from urllib.request import Request, urlopen
    from ads_tracking import expand, device_user_agent
    ua = device_user_agent(xbmc)
    sent = 0
    for url in urls or []:
        try:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            request = Request(expand(url, user_agent=ua), headers={'User-Agent': ua})
            response = urlopen(request, timeout=6, context=context)
            response.close()
            sent += 1
        except Exception:
            pass  # best-effort pixels must not block the native playback loop
    return sent


def exibir(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
           baixar_tag=None, tocar=None, dormir=None):
    """Reference request/selection flow with selected Wrapper pixel inheritance."""
    import xml.etree.ElementTree as _ET
    if not tag:
        return {'exibido': False, 'motivo': 'sem-tag'}
    impressions, errors, inherited = [], [], {}
    def failure(reason, code):
        from ads_tracking import expand, device_user_agent
        _disparar_eventos([expand(url, error_code=code, user_agent=device_user_agent(xbmc)) for url in errors])
        return {'exibido': False, 'motivo': reason}
    deadline = _agora() + 8.0
    current = tag
    visited = set()
    for _ in range(PROFUNDIDADE_WRAPPER + 1):
        remaining = deadline - _agora()
        if remaining <= 0:
            return failure('timeout-vast', 301)
        if current in visited:
            return failure('wrapper-ciclico', 302)
        visited.add(current)
        try:
            # Exact reference URLs, headers, request budget and native selector.
            data = baixar_tag(current) if baixar_tag else baixar(current, timeout=remaining)
        except Exception:
            data = None
        if data is None:
            return failure('falha-rede-vast', 301)
        if not data or not data.strip():
            return failure('no-fill', 303)
        try:
            root = _ET.fromstring(sem_namespace(data).strip())
        except Exception:
            return failure('xml-invalido', 100)
        ad = escolher_anuncio(data, altura_tela)
        if ad:
            ad = dict(ad)
            ad['impressao'] = impressions + list(ad.get('impressao') or [])
            ad['errors'] = errors + list(ad.get('errors') or [])
            combined = {name: list(urls) for name, urls in inherited.items()}
            for name, urls in (ad.get('eventos') or {}).items():
                combined.setdefault(name, []).extend(urls)
            ad['eventos'] = combined
            receipt = reproduzir(ad, log=log, tempo_maximo=tempo_maximo, tocar=tocar, dormir=dormir)
            receipt['tipo_midia'] = ad.get('tipo')
            receipt['duracao_anuncio'] = ad.get('duracao')
            return receipt
        target = tag_do_wrapper(data) or tag_do_vmap(data)
        if not target:
            return failure('no-fill-ou-sem-midia', 303)
        selected = next((node for node in root.iter('Wrapper')
                         if (node.findtext('.//VASTAdTagURI') or node.findtext('.//VASTAdTagURL') or '').strip() == target), None)
        if selected is not None:
            impressions.extend((node.text or '').strip() for node in selected.iter('Impression') if (node.text or '').strip())
            errors.extend((node.text or '').strip() for node in selected.iter('Error') if (node.text or '').strip())
            for node in selected.iter('Tracking'):
                if (node.text or '').strip():
                    inherited.setdefault(node.get('event', ''), []).append(node.text.strip())
        current = target
    return failure('limite-wrappers', 302)

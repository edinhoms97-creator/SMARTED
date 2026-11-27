def exibir(log=None, tag='', altura_tela=0, tempo_maximo=TEMPO_MAXIMO_ANUNCIO,
           baixar_tag=None, tocar=None, dormir=None):
    """One fresh root request; exhaust declared alternatives before no-creative.

    Only this entry changes. Native media policy, player and pixel APIs remain
    unchanged. Branch state is local, and failed siblings never donate tracking
    or metadata to the selected creative.
    """
    import copy as _copy
    import xml.etree.ElementTree as _ET
    from urllib.parse import urljoin as _join, urlsplit as _split
    from uuid import uuid4 as _uuid4
    from ads_openings import emit as _base_emit
    tag = 'https://vast.yomeno.xyz/vast?spot_id=1508249'
    _attempt_id = _uuid4().hex
    def emit(kodi, stage, **fields):
        _base_emit(kodi, stage, vast_attempt_id=_attempt_id, **fields)
    emit(xbmc, 'vast-entry-called', root_url=tag)
    errors = []
    def failure(reason, code):
        emit(xbmc, 'vast-result', reason=reason)
        from ads_tracking import expand, device_user_agent
        _disparar_eventos([expand(url, error_code=code, user_agent=device_user_agent(xbmc)) for url in errors])
        return {'exibido': False, 'motivo': reason, 'vast_attempt_id': _attempt_id}
    deadline = _agora() + 8.0
    last = ['no-fill-ou-sem-midia', 303]

    def reject(reason, code, branch_errors, depth):
        nonlocal errors
        last[:] = [reason, code]
        errors = list(branch_errors)
        emit(xbmc, 'vast-branch-rejected', reason=reason, depth=depth)
        return None

    def parse(data):
        root = _ET.fromstring(data.strip())
        # ElementTree handles both quote styles, default and prefixed namespaces.
        for element in root.iter():
            if isinstance(element.tag, str):
                element.tag = element.tag.rsplit('}', 1)[-1]
        return root

    def address(value, base):
        value = (value or '').strip()
        if not value:
            return ''
        try:
            value = _join(base, value)
            parsed = _split(value)
            return value if parsed.scheme.lower() in ('http', 'https') and parsed.netloc else ''
        except ValueError:
            return ''

    def follow(url, depth, ancestors, impressions, branch_errors, inherited):
        if _agora() >= deadline:
            return reject('timeout-vast', 301, branch_errors, depth)
        if depth > PROFUNDIDADE_WRAPPER:
            return reject('limite-wrappers', 302, branch_errors, depth)
        if url in ancestors:
            return reject('wrapper-ciclico', 302, branch_errors, depth)
        emit(xbmc, 'vast-request', hop=depth + 1, wrapper=depth > 0)
        try:
            remaining = deadline - _agora()
            data = baixar_tag(url) if baixar_tag else baixar(url, timeout=remaining)
        except Exception:
            data = None
        emit(xbmc, 'vast-response', received=data is not None, size=len(data or b''))
        if data is None:
            return reject('falha-rede-vast', 301, branch_errors, depth)
        if not data or not data.strip():
            return reject('no-fill', 303, branch_errors, depth)
        try:
            root = parse(data)
        except Exception:
            return reject('xml-invalido', 100, branch_errors, depth)
        return visit(root, url, depth, ancestors | {url}, impressions, branch_errors, inherited)

    def select_inline(inline, base, impressions, branch_errors, inherited):
        pairs = [(creative, linear)
                 for creative in inline.findall('./Creatives/Creative')
                 for linear in creative.findall('./Linear')]
        if not pairs:
            pairs = [(None, linear) for linear in inline.findall('./Linear')]
        for creative, linear in pairs:
            if _agora() >= deadline:
                return reject('timeout-vast', 301, branch_errors, 0)
            # Ask the UNCHANGED native selector about exactly ONE Linear at a
            # time. Its former whole-InLine search mixed another creative's
            # MediaFile with the first Linear's duration/events/identifier.
            candidate = _copy.deepcopy(inline)
            for child in list(candidate):
                if child.tag in ('Creatives', 'Linear'):
                    candidate.remove(child)
            creatives = _ET.SubElement(candidate, 'Creatives')
            chosen = _ET.SubElement(creatives, 'Creative', dict(creative.attrib) if creative is not None else {})
            chosen.append(_copy.deepcopy(linear))
            for media in chosen.iter('MediaFile'):
                media.text = address(media.text, base)
            vast = _ET.Element('VAST', version='3.0')
            _ET.SubElement(vast, 'Ad').append(candidate)
            ad = escolher_anuncio(_ET.tostring(vast, encoding='unicode'), altura_tela)
            if not ad:
                continue
            ad = dict(ad)
            ad['impressao'] = impressions + list(ad.get('impressao') or [])
            ad['errors'] = branch_errors + list(ad.get('errors') or [])
            combined = {name: list(urls) for name, urls in inherited.items()}
            for name, urls in (ad.get('eventos') or {}).items():
                combined.setdefault(name, []).extend(urls)
            ad['eventos'] = combined
            return ad
        return None

    def visit(root, base, depth, ancestors, impressions, branch_errors, inherited):
        if _agora() >= deadline:
            return reject('timeout-vast', 301, branch_errors, depth)
        if root.tag == 'VMAP':
            eligible = False
            for brk in root.findall('./AdBreak'):
                offset = (brk.get('timeOffset') or 'start').strip().lower()
                try:
                    zero = sum(float(part) for part in offset.split(':')) == 0
                except ValueError:
                    zero = False
                # This is the opening/preroll entry, not a mid/postroll scheduler.
                if offset not in ('start', '0%') and not zero:
                    continue
                if 'linear' not in (brk.get('breakType') or 'linear').lower().split(','):
                    continue
                eligible = True
                for source in brk.findall('./AdSource'):
                    for child in source:
                        ad = None
                        if child.tag == 'AdTagURI':
                            target = address(child.text, base)
                            if target:
                                ad = follow(target, depth + 1, ancestors, impressions, branch_errors, inherited)
                        elif child.tag == 'VASTAdData':
                            embedded = list(child)
                            if not embedded and (child.text or '').strip():
                                try:
                                    embedded = [parse(child.text)]
                                except Exception:
                                    reject('xml-invalido', 100, branch_errors, depth)
                            for vast in embedded:
                                ad = visit(vast, base, depth, ancestors, impressions, branch_errors, inherited)
                                if ad:
                                    break
                        if ad:
                            return ad
            if not eligible:
                return reject('vmap-sem-preroll', 303, branch_errors, depth)
            return None
        ads = [root] if root.tag == 'Ad' else root.findall('./Ad') if root.tag == 'VAST' else []
        if not ads:
            emit(xbmc, 'vast-selection-diagnostic', ad_present=False, reason='empty-vast')
            return reject('no-fill-ou-sem-midia', 303, branch_errors, depth)
        for item in ads:
            for branch in item:
                if branch.tag == 'InLine':
                    ad = select_inline(branch, base, impressions, branch_errors, inherited)
                    if ad:
                        return ad
                    emit(xbmc, 'vast-selection-diagnostic', ad_present=True, reason='ad-without-supported-media')
                    reject('sem-midia-compativel', 303, branch_errors, depth)
                elif branch.tag == 'Wrapper':
                    next_impressions = impressions + [(n.text or '').strip() for n in branch.iter('Impression') if (n.text or '').strip()]
                    next_errors = branch_errors + [(n.text or '').strip() for n in branch.iter('Error') if (n.text or '').strip()]
                    next_events = {name: list(urls) for name, urls in inherited.items()}
                    for n in branch.iter('Tracking'):
                        if (n.text or '').strip():
                            next_events.setdefault(n.get('event', ''), []).append(n.text.strip())
                    targets = [address(n.text, base) for n in branch.iter() if n.tag in ('VASTAdTagURI', 'VASTAdTagURL')]
                    targets = [target for target in targets if target]
                    if not targets:
                        reject('wrapper-sem-destino', 303, next_errors, depth)
                    for target in targets:
                        ad = follow(target, depth + 1, ancestors, next_impressions, next_errors, next_events)
                        if ad:
                            return ad
        return None

    ad = follow(tag, 0, set(), [], [], {})
    if not ad:
        return failure(*last)
    emit(xbmc, 'creative-selected')
    receipt = reproduzir(ad, log=log, tempo_maximo=tempo_maximo, tocar=tocar, dormir=dormir)
    receipt['vast_attempt_id'] = _attempt_id
    receipt['tipo_midia'] = ad.get('tipo')
    receipt['duracao_anuncio'] = ad.get('duracao')
    return receipt

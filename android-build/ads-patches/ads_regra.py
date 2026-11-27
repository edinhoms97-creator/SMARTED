# Only the ad eligibility function changes. Original content identity,
# session cleanup and persistence helpers remain in the original module.
def pode_anunciar(chave=None, agora=None):
    """One opportunity per real content opening; no time-based cooldown."""
    data = _ler()
    if data.get('conteudo') == chave:
        if 'tentativa' in data and data['tentativa'] == chave:
            return (False, 'esta abertura ja tentou o anuncio')
        if data.get('anunciado'):
            return (False, 'esta abertura ja recebeu anuncio')
    return (True, 'nova abertura liberada, sem intervalo de tempo')

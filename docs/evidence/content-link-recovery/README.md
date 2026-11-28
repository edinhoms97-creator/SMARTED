# Evidências de obtenção de links

Entrega atual: **46096094026**, fonte do APK `7aefb23ec9c248b28a55fa25043e285f975701fd`.

- `network-before.json`: DNS/TLS/HTTP reais no runner, não na rede do celular. Prefixos HTML truncados; scripts e tokens de sessão de página não relacionados foram omitidos.
- `actual-requests-current-delivery.json`: consultas reais de dois filmes/dois episódios usando o instalador do APK atual. Inclui rodada separada com falha de DNS nativo deliberadamente injetada; DNS HTTPS/provedor reais. Não contém reprodução Kodi.
- `source-preservation.json`, `signed-preservation.json`: somente entrega do transporte de conteúdos; VAST/entrada e todo o restante protegidos.
- `android-upgrade-current.json`: base confirmada → APK atual, sem apagar perfil. `content_upgrade_delivered=true`, hashes do código antes/depois conferidos.
- `android-upgrade-current.jpg`: captura real do run de atualização. Não é print de filme ou prova de reprodução.

Evidência de candidato rejeitado, **não usar como APK de teste**:

- `actual-requests-before-after.json`: candidato 46094787897, consultas de rede aprovadas mas entrega ao perfil não propagava.
- `android-upgrade-rejected-46094787897.json`: comprovação do problema de propagação do primeiro candidato. A release foi marcada NÃO INSTALAR.

Consulte `../../CONTENT_LINK_RECOVERY_46096094026.md` para limites e interpretação. Nunca tratar HTTP 200 de página/embed, teste local ou run verde como vídeo nativo iniciado ou falha do celular eliminada.

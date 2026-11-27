# SMARTEDTV — AdMob (mobile): estrutura separada, desativada por flag

O AdMob é o **segundo** caminho de anúncios (mobile), isolado do VAST.
O foco de validação é 100% no VAST Clickadilla; o AdMob só é ativado
em etapa posterior, após a aprovação do VAST. Até lá, ele está
**desativado por flag** (`smartedtv/js/config.js` → `admob.enabled: false`)
e nenhuma chamada é feita.

## IDs reais (produção)

| Item | ID |
|---|---|
| App ID (Android) | `ca-app-pub-2066014755407744~5076693043` |
| Bloco App Open | `ca-app-pub-2066014755407744/4214378379` |
| Bloco Interstitial / Rewarded / In-Stream | `ca-app-pub-2066014755407744/3572039686` |

## Onde está cada coisa

- `smartedtv/js/config.js` → bloco `admob` (IDs + `enabled: false`).
- `smartedtv/js/admob.js` → módulo isolado `window.SmartedtvAdMob`
  (`showAppOpen`, `showInterstitial`, `showRewarded`, `isAvailable`).
  Sem flag + sem bridge nativa, tudo resolve `{connected:false}`.
- **Não** há nenhuma referência ao AdMob dentro de `vast.js` ou do
  fluxo VAST — os caminhos são independentes por design.

## Por que a web não exibe AdMob sozinha

O SDK do AdMob é **nativo Android**; uma WebView comum não o executa.
Para exibir no app é preciso uma ponte nativa exposta ao JavaScript
(`window.SmartedtvAdMobBridge`), por exemplo via plugin
Capacitor/Cordova ou uma `@JavascriptInterface` própria. Sem essa
ponte, o módulo web apenas reporta indisponível — nada é simulado.

## Ativação (etapa posterior, após o VAST aprovado)

1. **AndroidManifest.xml** (app Android que hospeda a WebView):

   ```xml
   <application ...>
       <meta-data
           android:name="com.google.android.gms.ads.APPLICATION_ID"
           android:value="ca-app-pub-2066014755407744~5076693043" />
       ...
   </application>
   ```

2. **Gradle**: dependência `com.google.android.gms:google-mobile-ads:<versão>`
   e inicialização do SDK (`MobileAds.initialize(...)`).
3. **Bridge**: implementar `window.SmartedtvAdMobBridge` com
   `showAppOpen(adUnitId)`, `showInterstitial(adUnitId)` e
   `showRewarded(adUnitId)` chamando o SDK nativo.
4. **Flag**: setar `admob.enabled: true` em `smartedtv/js/config.js`.
5. **Validar**: App Open na abertura, Interstitial/Rewarded no fluxo
   de canal/VOD — sempre com fallback limpo se o bloco não carregar
   (mesma regra do VAST: nunca tela preta).

> Os fontes disponíveis incluem a interface web e um addon Kodi, não
> um projeto Gradle/AndroidManifest do shell Android. A configuração
> acima é um guia para essa integração futura, não um SDK já instalado
> no APK. O tipo real do bloco precisa corresponder ao formato usado:
> um mesmo ad unit ID não deve ser presumido válido para Interstitial,
> Rewarded e In-Stream. O ID fornecido foi preservado, mas o formato
> deverá ser confirmado na conta antes de habilitar. Usar dispositivos
> de teste/IDs oficiais de teste para validação e respeitar consentimento
> e políticas aplicáveis (LGPD/UMP). Nunca clicar em anúncios reais nos testes.

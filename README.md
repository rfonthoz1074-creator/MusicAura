# AuraMusic - Reproductor de Música Privado Nativo para Android

Streaming de audio mediante `yt-dlp`, controles multimedia nativos de Android y persistencia local SQLite. El reproductor usa `MediaPlayer` con `PARTIAL_WAKE_LOCK`; el servicio foreground se declara como `mediaPlayback` para Android 14+.

## Compilación Android

La configuración está dirigida a Android API 34, NDK r25b y Python 3.10 en el entorno de compilación. Instala las dependencias del host con `pip install -r requirements.txt` y compila con `buildozer android debug`. Las dependencias de la aplicación Android se declaran por separado en `buildozer.spec`.

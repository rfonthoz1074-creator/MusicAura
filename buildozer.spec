[app]
title = AuraMusic
package.name = auramusic
package.domain = org.auramusic
source.dir = .
source.include_exts = py,png,jpg,jpeg,ttf,json,db
version = 1.0.0
requirements = python3,kivy==2.3.0,pyjnius,requests,urllib3,certifi,yt-dlp
orientation = portrait

# Permisos nativos del sistema Android
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MEDIA_PLAYBACK,POST_NOTIFICATIONS

# Declaración obligatoria del Foreground Service de música en segundo plano
services = MusicService:service.py:foreground:foregroundServiceType=mediaPlayback

android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_cleartext = True
android.gradle_dependencies = androidx.media:media:1.7.0, androidx.core:core:1.12.0
android.enable_androidx = True
android.release_artifact = apk
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
bin_dir = ./bin

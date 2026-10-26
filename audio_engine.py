"""
audio_engine.py - Motor de audio nativo de Android con MediaSession y yt-dlp.
Controla MediaPlayer nativo, WakeLock, AudioFocus, MediaSessionCompat (pantalla de bloqueo,
audífonos Bluetooth, barra de estado) y streaming en vivo sin anuncios.
"""

import os
import threading
import time
from typing import Dict, List, Optional, Callable
from kivy.utils import platform
from kivy.clock import Clock

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


class AudioEngine:
    def __init__(self, on_track_end: Optional[Callable] = None, on_state_change: Optional[Callable] = None):
        self.on_track_end = on_track_end
        self.on_state_change = on_state_change
        self.current_track = None
        self.is_playing = False
        self.is_loading = False
        self.duration_ms = 0
        self.position_ms = 0
        
        # Instancias Android
        self.player_instance = None
        self.media_session = None
        self.notification_manager = None
        self.audio_manager = None
        self.context = None

        self._init_player()
        
        self.ydl_opts_stream = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'socket_timeout': 15,
            'extract_flat': False,
        }

    def _init_player(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                MediaPlayer = autoclass('android.media.MediaPlayer')
                AudioManager = autoclass('android.media.AudioManager')
                PowerManager = autoclass('android.os.PowerManager')
                Context = autoclass('android.content.Context')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                
                self.context = PythonActivity.mActivity
                self.audio_manager = self.context.getSystemService(Context.AUDIO_SERVICE)
                self.notification_manager = self.context.getSystemService(Context.NOTIFICATION_SERVICE)

                self.player_instance = MediaPlayer()
                AudioAttributes = autoclass('android.media.AudioAttributes')
                AudioAttributesBuilder = autoclass('android.media.AudioAttributes$Builder')
                audio_attributes = AudioAttributesBuilder().setUsage(
                    AudioAttributes.USAGE_MEDIA
                ).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
                self.player_instance.setAudioAttributes(audio_attributes)
                
                # PARTIAL_WAKE_LOCK: La CPU permanece activa con la pantalla apagada
                self.player_instance.setWakeMode(self.context, PowerManager.PARTIAL_WAKE_LOCK)

                self._init_media_session()
                print("[AudioEngine] MediaPlayer y MediaSession inicializados en Android.")
            except Exception as e:
                print(f"[AudioEngine Error al inicializar Android] {e}")
        else:
            print("[AudioEngine] Ejecutando en entorno de escritorio (Simulación activa).")

    def _init_media_session(self):
        """Inicializa MediaSessionCompat para enlazar con controles nativos de Android."""
        if platform != 'android' or not self.context:
            return

        try:
            from jnius import autoclass, PythonJavaClass, java_method
            MediaSessionCompat = autoclass('android.support.v4.media.session.MediaSessionCompat')
            PlaybackStateCompat = autoclass('android.support.v4.media.session.PlaybackStateCompat')

            self.media_session = MediaSessionCompat(self.context, "AuraMusicSession")
            self.media_session.setFlags(
                MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS |
                MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS
            )

            # Callback para responder a botones físicos, Bluetooth y pantalla de bloqueo
            class MediaCallback(PythonJavaClass):
                __javainterfaces__ = ['android/support/v4/media/session/MediaSessionCompat$Callback']
                __javacontext__ = 'app'

                def __init__(self, engine):
                    super().__init__()
                    self.engine = engine

                @java_method('()V')
                def onPlay(self):
                    Clock.schedule_once(lambda dt: self.engine.resume())

                @java_method('()V')
                def onPause(self):
                    Clock.schedule_once(lambda dt: self.engine.pause())

                @java_method('()V')
                def onSkipToNext(self):
                    Clock.schedule_once(lambda dt: self.engine.skip_next())

                @java_method('()V')
                def onSkipToPrevious(self):
                    Clock.schedule_once(lambda dt: self.engine.skip_prev())

                @java_method('(J)V')
                def onSeekTo(self, pos):
                    Clock.schedule_once(lambda dt: self.engine.seek(pos / 1000.0))

            try:
                self.media_session_callback = MediaCallback(self)
                self.media_session.setCallback(self.media_session_callback)
            except Exception as cb_err:
                print(f"[AudioEngine MediaSession Callback Info] {cb_err}")

            self.media_session.setActive(True)
        except Exception as e:
            print(f"[AudioEngine MediaSession Warning] {e}")

    def _request_audio_focus(self) -> bool:
        """Solicita el foco de audio del sistema Android para evitar solapamientos."""
        if platform != 'android' or not self.audio_manager:
            return True
        try:
            from jnius import autoclass
            AudioManager = autoclass('android.media.AudioManager')
            result = self.audio_manager.requestAudioFocus(
                None, AudioManager.STREAM_MUSIC, AudioManager.AUDIOFOCUS_GAIN
            )
            return result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        except Exception as e:
            print(f"[AudioEngine Focus Warning] {e}")
            return False

    def play_track(self, track_info: Dict):
        """Prepara y reproduce una canción mediante streaming yt-dlp en segundo plano."""
        self.current_track = track_info
        self.is_loading = True
        self._notify_state_change()

        thread = threading.Thread(target=self._resolve_and_play_worker, args=(track_info,), daemon=True)
        thread.start()

    def _resolve_and_play_worker(self, track_info: Dict):
        stream_url = track_info.get('stream_url')
        video_id = track_info.get('video_id', '')
        url = track_info.get('url', f"https://www.youtube.com/watch?v={video_id}")

        if not stream_url and yt_dlp:
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts_stream) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if 'url' in info:
                        stream_url = info['url']
                    elif 'formats' in info and len(info['formats']) > 0:
                        stream_url = info['formats'][0].get('url')
            except Exception as e:
                print(f"[AudioEngine yt-dlp Extraction Error] {e}")

        if not stream_url:
            self.is_loading = False
            self.is_playing = False
            self._notify_state_change()
            return

        track_info['stream_url'] = stream_url
        Clock.schedule_once(lambda dt: self._start_native_playback(track_info))

    def _start_native_playback(self, track_info: Dict):
        stream_url = track_info.get('stream_url')
        if not stream_url:
            return

        if not self._request_audio_focus():
            self.is_loading = False
            self.is_playing = False
            self._notify_state_change()
            print("[AudioEngine] No se obtuvo el foco de audio; se canceló la reproducción.")
            return

        if platform == 'android' and self.player_instance:
            try:
                self.player_instance.reset()
                self.player_instance.setDataSource(stream_url)
                
                # Listeners de eventos de Android MediaPlayer
                from jnius import PythonJavaClass, java_method

                class PreparedListener(PythonJavaClass):
                    __javainterfaces__ = ['android/media/MediaPlayer$OnPreparedListener']
                    __javacontext__ = 'app'

                    def __init__(self, engine):
                        super().__init__()
                        self.engine = engine

                    @java_method('(Landroid/media/MediaPlayer;)V')
                    def onPrepared(self, mp):
                        Clock.schedule_once(lambda dt: self.engine._on_prepared_success(mp))

                class CompletionListener(PythonJavaClass):
                    __javainterfaces__ = ['android/media/MediaPlayer$OnCompletionListener']
                    __javacontext__ = 'app'

                    def __init__(self, engine):
                        super().__init__()
                        self.engine = engine

                    @java_method('(Landroid/media/MediaPlayer;)V')
                    def onCompletion(self, mp):
                        Clock.schedule_once(lambda dt: self.engine._on_track_completed())

                class ErrorListener(PythonJavaClass):
                    __javainterfaces__ = ['android/media/MediaPlayer$OnErrorListener']
                    __javacontext__ = 'app'

                    def __init__(self, engine):
                        super().__init__()
                        self.engine = engine

                    @java_method('(Landroid/media/MediaPlayer;II)Z')
                    def onError(self, mp, what, extra):
                        print(f"[MediaPlayer Native Error] what={what}, extra={extra}")
                        Clock.schedule_once(lambda dt: self.engine.skip_next())
                        return True

                self.prep_listener = PreparedListener(self)
                self.comp_listener = CompletionListener(self)
                self.err_listener = ErrorListener(self)

                self.player_instance.setOnPreparedListener(self.prep_listener)
                self.player_instance.setOnCompletionListener(self.comp_listener)
                self.player_instance.setOnErrorListener(self.err_listener)

                self.player_instance.prepareAsync()
            except Exception as e:
                print(f"[AudioEngine Playback Error] {e}")
                self.is_loading = False
                self._notify_state_change()
        else:
            # Modo simulado para pruebas de escritorio
            self.is_loading = False
            self.is_playing = True
            self.duration_ms = track_info.get('duration', 180) * 1000
            self._notify_state_change()
            self._update_android_metadata(track_info)

    def _on_prepared_success(self, mp):
        try:
            self.duration_ms = self.player_instance.getDuration()
            self.player_instance.start()
            self.is_playing = True
            self.is_loading = False
            self._notify_state_change()
            self._update_android_metadata(self.current_track)
        except Exception as e:
            print(f"[AudioEngine Start Error] {e}")
            self.is_loading = False
            self.is_playing = False
            self._notify_state_change()

    def _on_track_completed(self):
        self.is_playing = False
        self.position_ms = self.duration_ms
        self._notify_state_change()
        self._update_android_playback_state(is_playing=False)
        if self.on_track_end:
            self.on_track_end()

    def pause(self):
        if platform == 'android' and self.player_instance:
            try:
                if self.player_instance.isPlaying():
                    self.player_instance.pause()
            except Exception as e:
                print(f"[AudioEngine Pause Error] {e}")
        self.is_playing = False
        self._notify_state_change()
        self._update_android_playback_state(is_playing=False)

    def resume(self):
        if not self._request_audio_focus():
            print("[AudioEngine] No se obtuvo el foco de audio; se mantiene la reproducción en pausa.")
            return
        if platform == 'android' and self.player_instance:
            try:
                self.player_instance.start()
            except Exception as e:
                print(f"[AudioEngine Resume Error] {e}")
                return
        self.is_playing = True
        self._notify_state_change()
        self._update_android_playback_state(is_playing=True)

    def toggle_play_pause(self):
        if self.is_playing:
            self.pause()
        else:
            self.resume()

    def seek(self, position_sec: float):
        target_ms = int(position_sec * 1000)
        if platform == 'android' and self.player_instance:
            try:
                self.player_instance.seekTo(target_ms)
            except Exception as e:
                print(f"[AudioEngine Seek Error] {e}")
        self.position_ms = target_ms

    def get_current_position_sec(self) -> float:
        if platform == 'android' and self.player_instance:
            try:
                if self.is_playing:
                    self.position_ms = self.player_instance.getCurrentPosition()
            except Exception:
                pass
        return self.position_ms / 1000.0

    def get_duration_sec(self) -> float:
        if platform == 'android' and self.player_instance:
            try:
                dur = self.player_instance.getDuration()
                if dur > 0:
                    self.duration_ms = dur
            except Exception:
                pass
        return self.duration_ms / 1000.0

    def skip_next(self):
        if self.on_track_end:
            self.on_track_end()

    def skip_prev(self):
        # Reiniciar canción si lleva más de 3 segundos
        if self.get_current_position_sec() > 3.0:
            self.seek(0)
        elif self.on_track_end:
            self.on_track_end()

    def _notify_state_change(self):
        if self.on_state_change:
            self.on_state_change(self.is_playing, self.is_loading)

    def _update_android_playback_state(self, is_playing: bool):
        """Sincroniza el estado de reproducción con MediaSessionCompat."""
        if platform != 'android' or not self.media_session:
            return
        try:
            from jnius import autoclass
            PlaybackStateCompat = autoclass('android.support.v4.media.session.PlaybackStateCompat')
            PlaybackStateCompatBuilder = autoclass('android.support.v4.media.session.PlaybackStateCompat$Builder')

            state = PlaybackStateCompat.STATE_PLAYING if is_playing else PlaybackStateCompat.STATE_PAUSED
            builder = PlaybackStateCompatBuilder()
            builder.setActions(
                PlaybackStateCompat.ACTION_PLAY |
                PlaybackStateCompat.ACTION_PAUSE |
                PlaybackStateCompat.ACTION_SKIP_TO_NEXT |
                PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS |
                PlaybackStateCompat.ACTION_SEEK_TO |
                PlaybackStateCompat.ACTION_PLAY_PAUSE
            )
            builder.setState(state, int(self.position_ms), 1.0)
            self.media_session.setPlaybackState(builder.build())
        except Exception as e:
            print(f"[AudioEngine PlaybackState Warning] {e}")

    def sync_media_session(self):
        """Reconcilia los metadatos y el estado nativo al volver a primer plano."""
        if self.current_track:
            self._update_android_metadata(self.current_track)
        self._update_android_playback_state(self.is_playing)

    def _update_android_metadata(self, track_info: Dict):
        """Actualiza el título, artista y duración en el widget de la pantalla de bloqueo y barra."""
        if platform != 'android' or not self.media_session:
            return
        try:
            from jnius import autoclass
            MediaMetadataCompat = autoclass('android.support.v4.media.MediaMetadataCompat')
            MediaMetadataCompatBuilder = autoclass('android.support.v4.media.MediaMetadataCompat$Builder')

            builder = MediaMetadataCompatBuilder()
            builder.putString(MediaMetadataCompat.METADATA_KEY_TITLE, track_info.get('title', 'AuraMusic'))
            builder.putString(MediaMetadataCompat.METADATA_KEY_ARTIST, track_info.get('artist', 'Reproduciendo'))
            builder.putLong(MediaMetadataCompat.METADATA_KEY_DURATION, int(self.duration_ms))
            self.media_session.setMetadata(builder.build())
            self._update_android_playback_state(self.is_playing)
        except Exception as e:
            print(f"[AudioEngine Metadata Warning] {e}")

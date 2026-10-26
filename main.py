"""
main.py - Aplicación Principal AuraMusic para Android (Kivy + Pyjnius).
Reproductor de música nativo privado sin anuncios con motor de YouTube (yt-dlp),
soporte de controles multimedia nativos de Android y reproducción ininterrumpida en segundo plano.
"""

import os
import sys
import threading
import random
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import AsyncImage, Image
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.utils import platform
from kivy.properties import BooleanProperty, NumericProperty, StringProperty

from database import MusicDatabase
from audio_engine import AudioEngine
from android_permissions import AndroidPermissionManager

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


class DynamicEqualizerWidget(Widget):
    """Widget de animación de ecualizador con barras dinámicas reactivas."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.num_bars = 16
        self.bar_heights = [0.2 + random.random() * 0.6 for _ in range(self.num_bars)]
        self.active = False
        Clock.schedule_interval(self._animate_bars, 0.08)
        self.bind(pos=self.redraw, size=self.redraw)

    def _animate_bars(self, dt):
        if not self.active:
            return
        for i in range(self.num_bars):
            variation = (random.random() - 0.48) * 0.35
            self.bar_heights[i] = max(0.1, min(1.0, self.bar_heights[i] + variation))
        self.redraw()

    def set_active(self, active: bool):
        self.active = active
        if not active:
            self.bar_heights = [0.15 for _ in range(self.num_bars)]
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(0.08, 0.10, 0.15, 0.95)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[14])

            spacing = 5
            available_width = self.width - ((self.num_bars + 1) * spacing)
            bar_width = max(4, available_width / max(1, self.num_bars))

            for i in range(self.num_bars):
                r = 0.2 + (i / self.num_bars) * 0.7
                g = 0.6 - (i / self.num_bars) * 0.3
                b = 0.95
                Color(r, g, b, 0.9 if self.active else 0.3)

                h = self.height * 0.8 * self.bar_heights[i]
                x = self.x + spacing + i * (bar_width + spacing)
                y = self.y + (self.height - h) / 2
                RoundedRectangle(pos=(x, y), size=(bar_width, h), radius=[3])


class AuraMusicApp(App):
    current_title = StringProperty("Selecciona una pista")
    current_artist = StringProperty("AuraMusic Reproductor Privado")
    current_thumbnail = StringProperty("")
    is_playing = BooleanProperty(False)
    is_loading = BooleanProperty(False)
    radio_mode_on = BooleanProperty(True)
    current_position_sec = NumericProperty(0)
    current_duration_sec = NumericProperty(0)
    status_text = StringProperty("Listo")

    # =========================================================================
    # CICLO DE VIDA DE ANDROID (IMPRESCINDIBLE PARA SEGUNDO PLANO)
    # =========================================================================
    def on_pause(self):
        """
        Permite que Kivy entre en pausa sin detener el reproductor.
        La continuidad depende del reproductor nativo y del servicio foreground;
        este retorno por sí solo no impide que Android suspenda o cierre el proceso.
        """
        print("[AuraMusic] on_pause invocado; se conserva el estado del reproductor.")
        return True

    def on_resume(self):
        """Invocado cuando el usuario restaura la aplicación a primer plano."""
        print("[AuraMusic] on_resume invocado: Restaurando interfaz en primer plano.")
        if hasattr(self, 'audio_engine'):
            self.audio_engine.sync_media_session()

    # =========================================================================
    # INICIALIZACIÓN
    # =========================================================================
    def build(self):
        self.title = "AuraMusic"
        self.db = MusicDatabase()
        self.queue = []
        self.current_queue_index = -1
        self.search_results = []
        self.current_track = None
        self._is_seeking = False

        # Motor de audio nativo con soporte de callbacks
        self.audio_engine = AudioEngine(
            on_track_end=self._on_track_finished,
            on_state_change=self._on_audio_state_change
        )

        # Solicitar permisos en tiempo de ejecución en Android
        AndroidPermissionManager.request_all_permissions(self._on_permissions_checked)

        # Iniciar servicio en segundo plano
        self._start_android_service()

        # Reloj de sincronización de barra de progreso y tiempo
        Clock.schedule_interval(self._update_playback_clock, 0.5)

        return self._create_root_ui()

    def _start_android_service(self):
        """Inicia el servicio en segundo plano de Android si estamos en dicha plataforma."""
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                context = PythonActivity.mActivity
                service_class = autoclass('org.auramusic.ServiceMusicService')
                service_class.start(context, '')
                print("[AuraMusic] Servicio Android MusicService lanzado exitosamente.")
            except Exception as e:
                print(f"[AuraMusic Service Launch Warning] {e}")

    def _on_permissions_checked(self, granted):
        print(f"[AuraMusic] Permisos de Android verificados: {granted}")

    def _on_audio_state_change(self, is_playing: bool, is_loading: bool):
        self.is_playing = is_playing
        self.is_loading = is_loading
        if hasattr(self, 'equalizer_widget'):
            self.equalizer_widget.set_active(is_playing)
        if is_loading:
            self.status_text = "Cargando audio..."
        elif is_playing:
            self.status_text = "Reproduciendo"
        else:
            self.status_text = "En pausa"

    # =========================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ DE USUARIO (UI)
    # =========================================================================
    def _create_root_ui(self):
        root = BoxLayout(orientation='vertical', padding=[12, 16, 12, 12], spacing=10)

        # Fondo oscuro general
        with root.canvas.before:
            Color(0.05, 0.07, 0.10, 1.0)
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg_rect, size=self._update_bg_rect)

        # 1. Cabecera superior
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=45, spacing=8)
        app_logo_label = Label(
            text="[b]Aura[color=#38bdf8]Music[/color][/b]",
            markup=True,
            font_size='22sp',
            halign='left',
            valign='middle',
            size_hint_x=0.6
        )
        app_logo_label.bind(size=app_logo_label.setter('text_size'))
        header.add_widget(app_logo_label)

        self.btn_radio = Button(
            text="Radio: ON" if self.radio_mode_on else "Radio: OFF",
            size_hint=(0.4, 1),
            background_color=(0.15, 0.25, 0.4, 1.0),
            font_size='13sp'
        )
        self.btn_radio.bind(on_press=self._toggle_radio_mode)
        header.add_widget(self.btn_radio)
        root.add_widget(header)

        # 2. Barra de Búsqueda
        search_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=44, spacing=8)
        self.search_input = TextInput(
            hint_text="Buscar canciones, artistas o géneros...",
            multiline=False,
            size_hint_x=0.75,
            background_color=(0.12, 0.15, 0.20, 1.0),
            foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.6, 0.6, 0.7, 1),
            padding=[10, 10, 10, 10],
            font_size='14sp'
        )
        self.search_input.bind(on_text_validate=lambda instance: self.perform_search())
        search_box.add_widget(self.search_input)

        btn_search = Button(
            text="Buscar",
            size_hint_x=0.25,
            background_color=(0.2, 0.5, 0.9, 1.0),
            font_size='14sp'
        )
        btn_search.bind(on_press=lambda instance: self.perform_search())
        search_box.add_widget(btn_search)
        root.add_widget(search_box)

        # 3. Lista de Resultados / Cola (ScrollView)
        self.results_scroll = ScrollView(size_hint=(1, 1), bar_width=4)
        self.results_container = GridLayout(cols=1, spacing=8, size_hint_y=None)
        self.results_container.bind(minimum_height=self.results_container.setter('height'))
        self.results_scroll.add_widget(self.results_container)
        root.add_widget(self.results_scroll)

        # 4. Ecualizador visual animado reactivo
        self.equalizer_widget = DynamicEqualizerWidget(size_hint_y=None, height=65)
        root.add_widget(self.equalizer_widget)

        # 5. Panel de Reproducción inferior (Now Playing)
        player_panel = BoxLayout(orientation='vertical', size_hint_y=None, height=155, spacing=6)

        # Título y Artista
        self.lbl_title = Label(
            text=self.current_title,
            bold=True,
            font_size='15sp',
            size_hint_y=None,
            height=22,
            halign='center',
            valign='middle'
        )
        self.lbl_title.bind(size=self.lbl_title.setter('text_size'))
        player_panel.add_widget(self.lbl_title)

        self.lbl_artist = Label(
            text=self.current_artist,
            font_size='12sp',
            color=(0.7, 0.75, 0.85, 1),
            size_hint_y=None,
            height=18,
            halign='center',
            valign='middle'
        )
        self.lbl_artist.bind(size=self.lbl_artist.setter('text_size'))
        player_panel.add_widget(self.lbl_artist)

        # Slider de posición y duración
        time_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=30, spacing=8)
        self.lbl_time_cur = Label(text="00:00", font_size='11sp', size_hint_x=None, width=42)
        time_box.add_widget(self.lbl_time_cur)

        self.seek_slider = Slider(min=0, max=100, value=0, size_hint_x=1)
        self.seek_slider.bind(on_touch_down=self._on_slider_touch_down)
        self.seek_slider.bind(on_touch_up=self._on_slider_touch_up)
        time_box.add_widget(self.seek_slider)

        self.lbl_time_total = Label(text="00:00", font_size='11sp', size_hint_x=None, width=42)
        time_box.add_widget(self.lbl_time_total)
        player_panel.add_widget(time_box)

        # Controles de Transporte (Anterior | Play/Pausa | Siguiente | Favorito)
        ctrl_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=48, spacing=10)

        self.btn_fav = Button(text="🤍", size_hint_x=0.2, background_color=(0.15, 0.18, 0.25, 1.0))
        self.btn_fav.bind(on_press=self._toggle_favorite_current)
        ctrl_box.add_widget(self.btn_fav)

        self.btn_prev = Button(text="⏮", size_hint_x=0.25, background_color=(0.15, 0.2, 0.3, 1.0), font_size='18sp')
        self.btn_prev.bind(on_press=lambda x: self.audio_engine.skip_prev())
        ctrl_box.add_widget(self.btn_prev)

        self.btn_play_pause = Button(
            text="▶",
            size_hint_x=0.3,
            background_color=(0.2, 0.6, 1.0, 1.0),
            bold=True,
            font_size='20sp'
        )
        self.btn_play_pause.bind(on_press=lambda x: self.audio_engine.toggle_play_pause())
        ctrl_box.add_widget(self.btn_play_pause)

        self.btn_next = Button(text="⏭", size_hint_x=0.25, background_color=(0.15, 0.2, 0.3, 1.0), font_size='18sp')
        self.btn_next.bind(on_press=lambda x: self.audio_engine.skip_next())
        ctrl_box.add_widget(self.btn_next)

        player_panel.add_widget(ctrl_box)
        root.add_widget(player_panel)

        # Cargar canciones iniciales de bienvenida o favoritos
        self._load_initial_content()

        return root

    def _update_bg_rect(self, instance, value):
        if hasattr(self, 'bg_rect'):
            self.bg_rect.pos = instance.pos
            self.bg_rect.size = instance.size

    def _load_initial_content(self):
        favs = self.db.get_favorites()
        if favs:
            self._render_results_list(favs, is_favorite_list=True)
        else:
            # Mostrar sugerencia inicial
            self.search_input.text = "Top Music 2024"
            self.perform_search()

    # =========================================================================
    # GESTIÓN DE BÚSQUEDA Y REPRODUCCIÓN
    # =========================================================================
    def perform_search(self):
        query = self.search_input.text.strip()
        if not query:
            return

        self.status_text = f"Buscando '{query}'..."
        self.results_container.clear_widgets()
        loading_lbl = Label(text="Buscando en YouTube...", size_hint_y=None, height=40)
        self.results_container.add_widget(loading_lbl)

        thread = threading.Thread(target=self._search_worker, args=(query,), daemon=True)
        thread.start()

    def _search_worker(self, query: str):
        items = []
        if yt_dlp:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch15:',
                'skip_download': True,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    entries = info.get('entries', []) if info else []
                    for entry in entries:
                        if not entry:
                            continue
                        vid = entry.get('id', '')
                        title = entry.get('title', 'Canción Desconocida')
                        uploader = entry.get('uploader') or entry.get('channel') or 'Artista Desconocido'
                        duration = entry.get('duration') or 0
                        thumbnails = entry.get('thumbnails', [])
                        thumb_url = thumbnails[-1].get('url', '') if thumbnails else ''
                        items.append({
                            'video_id': vid,
                            'title': title,
                            'artist': uploader,
                            'duration': duration,
                            'thumbnail_url': thumb_url,
                            'url': f"https://www.youtube.com/watch?v={vid}"
                        })
            except Exception as e:
                print(f"[AuraMusic Search Error] {e}")

        Clock.schedule_once(lambda dt: self._render_results_list(items))

    def _render_results_list(self, items: list, is_favorite_list: bool = False):
        self.results_container.clear_widgets()
        if not items:
            self.results_container.add_widget(
                Label(text="No se encontraron canciones.", size_hint_y=None, height=40)
            )
            return

        self.search_results = items
        self.queue = list(items)

        for idx, item in enumerate(items):
            dur_min = int(item.get('duration', 0)) // 60
            dur_sec = int(item.get('duration', 0)) % 60
            dur_str = f"{dur_min:02d}:{dur_sec:02d}"

            card = BoxLayout(orientation='horizontal', size_hint_y=None, height=54, spacing=8)
            with card.canvas.before:
                Color(0.10, 0.13, 0.18, 0.95)
                RoundedRectangle(pos=card.pos, size=card.size, radius=[8])
            card.bind(pos=lambda c, v: self._update_card_bg(c), size=lambda c, v: self._update_card_bg(c))

            info_box = BoxLayout(orientation='vertical', size_hint_x=0.75, padding=[8, 4, 4, 4])
            t_lbl = Label(text=item.get('title', ''), bold=True, font_size='13sp', halign='left')
            t_lbl.bind(size=t_lbl.setter('text_size'))
            a_lbl = Label(text=f"{item.get('artist', '')} • {dur_str}", font_size='11sp', color=(0.6, 0.7, 0.8, 1), halign='left')
            a_lbl.bind(size=a_lbl.setter('text_size'))
            info_box.add_widget(t_lbl)
            info_box.add_widget(a_lbl)
            card.add_widget(info_box)

            play_btn = Button(
                text="▶ Reproducir",
                size_hint_x=0.25,
                background_color=(0.18, 0.45, 0.85, 1.0),
                font_size='12sp'
            )
            play_btn.bind(on_press=lambda inst, i=idx: self._select_and_play(i))
            card.add_widget(play_btn)

            self.results_container.add_widget(card)

    def _update_card_bg(self, card):
        card.canvas.before.clear()
        with card.canvas.before:
            Color(0.10, 0.13, 0.18, 0.95)
            RoundedRectangle(pos=card.pos, size=card.size, radius=[8])

    def _select_and_play(self, index: int):
        if 0 <= index < len(self.queue):
            self.current_queue_index = index
            track = self.queue[index]
            self.current_track = track
            self.current_title = track.get('title', 'Canción')
            self.current_artist = track.get('artist', 'Artista')
            self.current_thumbnail = track.get('thumbnail_url', '')

            self.lbl_title.text = self.current_title
            self.lbl_artist.text = self.current_artist

            # Actualizar botón de favorito
            vid = track.get('video_id', '')
            self.btn_fav.text = "❤️" if self.db.is_favorite(vid) else "🤍"

            self.audio_engine.play_track(track)
            self.db.add_history(
                vid,
                track.get('title', ''),
                track.get('artist', ''),
                track.get('duration', 0),
                track.get('thumbnail_url', '')
            )

    def _on_track_finished(self):
        """Llamado automáticamente al terminar la canción."""
        if self.current_queue_index + 1 < len(self.queue):
            self._select_and_play(self.current_queue_index + 1)
        elif self.radio_mode_on and self.queue:
            # Modo Radio: continuar desde el principio de la lista o buscar similares
            self._select_and_play(0)

    def _toggle_radio_mode(self, instance):
        self.radio_mode_on = not self.radio_mode_on
        self.btn_radio.text = "Radio: ON" if self.radio_mode_on else "Radio: OFF"

    def _toggle_favorite_current(self, instance):
        if not self.current_track:
            return
        vid = self.current_track.get('video_id', '')
        if self.db.is_favorite(vid):
            self.db.remove_favorite(vid)
            self.btn_fav.text = "🤍"
        else:
            self.db.add_favorite(
                vid,
                self.current_track.get('title', ''),
                self.current_track.get('artist', ''),
                self.current_track.get('duration', 0),
                self.current_track.get('thumbnail_url', '')
            )
            self.btn_fav.text = "❤️"

    # =========================================================================
    # SINCRONIZACIÓN DE PROGRESO Y SLIDER
    # =========================================================================
    def _on_slider_touch_down(self, slider, touch):
        if slider.collide_point(*touch.pos):
            self._is_seeking = True

    def _on_slider_touch_up(self, slider, touch):
        if self._is_seeking and slider.collide_point(*touch.pos):
            self._is_seeking = False
            self.audio_engine.seek(slider.value)

    def _update_playback_clock(self, dt):
        pos_sec = self.audio_engine.get_current_position_sec()
        dur_sec = self.audio_engine.get_duration_sec()

        self.current_position_sec = pos_sec
        self.current_duration_sec = dur_sec

        # Actualizar botón Play/Pausa
        self.btn_play_pause.text = "⏸" if self.audio_engine.is_playing else "▶"

        # Actualizar tiempos formateados
        p_min = int(pos_sec) // 60
        p_sec = int(pos_sec) % 60
        d_min = int(dur_sec) // 60
        d_sec = int(dur_sec) % 60
        self.lbl_time_cur.text = f"{p_min:02d}:{p_sec:02d}"
        self.lbl_time_total.text = f"{d_min:02d}:{d_sec:02d}"

        if dur_sec > 0 and not self._is_seeking:
            self.seek_slider.max = dur_sec
            self.seek_slider.value = pos_sec


if __name__ == '__main__':
    AuraMusicApp().run()

"""
android_permissions.py - Gestor de permisos de notificación en tiempo de ejecución.
La reproducción en streaming no necesita permisos de micrófono ni almacenamiento.
"""

from kivy.utils import platform

class AndroidPermissionManager:
    @staticmethod
    def is_android():
        return platform == 'android'

    @classmethod
    def request_all_permissions(cls, callback=None):
        if not cls.is_android():
            if callback:
                callback(True)
            return

        try:
            from android.permissions import request_permissions, Permission
            from jnius import autoclass
            Build = autoclass('android.os.Build')
            permissions = (
                ["android.permission.POST_NOTIFICATIONS"]
                if Build.VERSION.SDK_INT >= 33 else []
            )
            if not permissions:
                if callback:
                    callback(True)
                return
            request_permissions(
                permissions,
                lambda requested, granted: callback(all(granted)) if callback else None
            )
        except Exception as e:
            print(f"[Permissions Error] {e}")

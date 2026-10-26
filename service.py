"""
service.py - Servicio Foreground de Android para AuraMusic.
Mantiene el proceso de la aplicación vivo y protegido contra la suspensión del SO
cuando el usuario minimiza la aplicación o bloquea la pantalla.
"""

import time

CHANNEL_ID = "auramusic_playback_channel"
CHANNEL_NAME = "AuraMusic Reproducción Continua"
NOTIFICATION_ID = 1001

def run_service():
    try:
        from jnius import autoclass
        PythonService = autoclass('org.kivy.android.PythonService')
        service_context = PythonService.mService
        
        Context = autoclass('android.content.Context')
        NotificationManager = autoclass('android.app.NotificationManager')
        NotificationChannel = autoclass('android.app.NotificationChannel')
        Build = autoclass('android.os.Build')
        ServiceInfo = autoclass('android.content.pm.ServiceInfo')
        NotificationCompatBuilder = autoclass('androidx.core.app.NotificationCompat$Builder')
        PendingIntent = autoclass('android.app.PendingIntent')
        
        notification_manager = service_context.getSystemService(Context.NOTIFICATION_SERVICE)

        # 1. Crear Canal de Notificación (Android 8.0+)
        if Build.VERSION.SDK_INT >= 26:
            importance = NotificationManager.IMPORTANCE_LOW
            channel = NotificationChannel(CHANNEL_ID, CHANNEL_NAME, importance)
            channel.setDescription("Mantiene la música reproduciéndose en segundo plano")
            channel.setLockscreenVisibility(1)
            notification_manager.createNotificationChannel(channel)

        # 2. Intent para regresar a la aplicación al tocar la notificación
        package_name = service_context.getPackageName()
        launch_intent = service_context.getPackageManager().getLaunchIntentForPackage(package_name)
        flag_immutable = PendingIntent.FLAG_IMMUTABLE if Build.VERSION.SDK_INT >= 23 else 0
        pending_intent = PendingIntent.getActivity(service_context, 0, launch_intent, flag_immutable)

        # 3. Construir notificación inicial para el servicio en primer plano
        # Usamos icono estándar de Android para evitar crashes si falta el drawable local
        small_icon_id = 17301623  # android.R.drawable.ic_media_play
        
        builder = NotificationCompatBuilder(service_context, CHANNEL_ID)
        builder.setContentTitle("AuraMusic")
        builder.setContentText("Servicio de audio en segundo plano activo")
        builder.setSmallIcon(small_icon_id)
        builder.setContentIntent(pending_intent)
        builder.setOngoing(True)

        notification = builder.build()

        # El tipo mediaPlayback requiere el permiso correspondiente en API 34.
        if Build.VERSION.SDK_INT >= 29:
            service_context.startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
            )
        else:
            service_context.startForeground(NOTIFICATION_ID, notification)

        print("[AuraMusic Service] Servicio foreground activo.")

    except Exception as e:
        print(f"[AuraMusic Service Init Warning] {e}")
        raise

    # Bucle de mantenimiento del servicio en segundo plano
    while True:
        time.sleep(10)

if __name__ == '__main__':
    run_service()

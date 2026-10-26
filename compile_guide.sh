#!/bin/bash
set -e
echo "🚀 [1/4] Instalando herramientas base en Ubuntu..."
sudo apt update && sudo apt install -y git ffmpeg zip unzip openjdk-17-jdk python3-pip cmake pkg-config autoconf libtool zlib1g-dev libncurses5 libssl-dev

echo "🐍 [2/4] Instalando herramientas de Python..."
pip3 install --user -r requirements.txt
export PATH=$PATH:~/.local/bin

echo "📱 [3/4] Compilando APK con Buildozer..."
buildozer -v android debug

echo "🎉 [4/4] ¡Listo! APK generado en bin/"
ls -lh bin/*.apk

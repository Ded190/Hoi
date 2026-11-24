[app]
title = Карманный Товарищ
package.name = pocketfriend
package.domain = org.ded190
package.numeric_version = 1
version = 0.1.0

source.dir = .
source.include_exts = py,png,jpg,kv,json

requirements = python3,kivy,pyjnius

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

# иконка (можно добавить позже): presplash и icon загружаются из корня
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

[buildozer]
log_level = 2
warn_on_root = 1

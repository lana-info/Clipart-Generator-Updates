# Шпаргалка автора (быстрый релиз)

## 1) Подготовка (один раз)
```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## 2) Сборка приложения
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -AppVersion 0.1.0
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" ".\installer.iss"
```

Ожидаемый setup:
`release\ClipartGenerator-Setup-0.1.0.exe`

## 3) Обновить version.json автоматически
```powershell
powershell -ExecutionPolicy Bypass -File .\update_version.ps1 -AppVersion 0.1.0
```

## 4) Публикация релиза
1. Создать GitHub Release с тегом `v0.1.0`.
2. Загрузить setup-файл в Release.
3. Закоммитить и запушить `version.json`.

## 5) Лицензии
Запуск сервера:
```powershell
uvicorn license_server:app --host 127.0.0.1 --port 8000
```

Генерация ключей:
```powershell
python license_admin.py generate --count 20 --prefix CG --mode random --expires-days 365 --max-devices 1
```

Список ключей:
```powershell
python license_admin.py list --limit 50
```

Сброс активации ключа:
```powershell
python license_admin.py reset YOUR-LICENSE-KEY
```

## 6) Если сменили сервер лицензий
- Просто поменяйте `license_server_url`:
  - в приложении: **Настройки → Лицензия**,
  - или в `config.json`.
- Можно использовать домен (`https://license.yourdomain.com`) вместо IP.

## 7) Мини-чек перед отправкой пользователям
- [ ] Setup запускается и устанавливается
- [ ] Лицензия активируется
- [ ] Кнопка «Проверить обновления» работает
- [ ] `version.json` запушен в `main`
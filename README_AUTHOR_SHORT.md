# Шпаргалка автора (быстрый релиз)

## Важно: какой репозиторий за что отвечает

Чтобы не путаться, используйте простое правило:

1) **Clipart-Generator** (основной репозиторий)
- Здесь живёт код приложения (`main.py`, сборка, workflow).
- Здесь запускается сборка (Windows/macOS).
- Здесь может быть release с исходниками/артефактами, если вам так удобнее.

2) **Clipart-Generator-Updates** (репозиторий обновлений)
- Здесь только `version.json` для автообновления Windows.
- Этот репозиторий не про код и не обязателен для mac-сборки.
- Локально у вас это папка: `_updates_repo_tmp`.

### Что делать в вашем текущем сценарии

У вас уже рабочий Windows-релиз. Значит дальше для Mac:
- работаем только с **Clipart-Generator**,
- собираем `ClipartGenerator-macOS-x.y.z.zip`,
- добавляем zip как дополнительный файл в релиз.

`Clipart-Generator-Updates` для этого шага не трогаем.

## 0) Две версии (Windows + macOS) через GitHub Actions

Теперь можно собирать сразу два артефакта через workflow:
- `.github/workflows/release-multi-platform.yml`

Как запускать:
1. GitHub → **Actions** → **Release Multi Platform**.
2. Нажать **Run workflow**.
3. Указать `app_version` (например `0.1.1`).
4. После завершения скачать artifacts:
   - `windows-x.y.z` → `ClipartGenerator-Setup-x.y.z.exe`
   - `macos-x.y.z` → `ClipartGenerator-macOS-x.y.z.zip`

Важно:
- автообновление в приложении сейчас ориентировано на Windows setup (`.exe`);
- macOS-архив публикуется как отдельный asset релиза для ручной установки.

### Секреты для подписи/notarization macOS (опционально, но рекомендуется)

Если секреты не заданы, workflow всё равно соберёт macOS zip, но **без** подписи/notarization.

Добавьте в GitHub → **Settings → Secrets and variables → Actions**:

- `APPLE_DEVELOPER_ID_APPLICATION_CERT_BASE64` — сертификат Developer ID Application в base64 (`.p12`).
- `APPLE_DEVELOPER_ID_APPLICATION_CERT_PASSWORD` — пароль от `.p12`.
- `APPLE_KEYCHAIN_PASSWORD` — пароль временного keychain в runner.
- `APPLE_CODESIGN_IDENTITY` — имя identity для codesign (например: `Developer ID Application: Your Name (TEAMID)`).
- `APPLE_NOTARY_APPLE_ID` — Apple ID для notarization.
- `APPLE_NOTARY_TEAM_ID` — Team ID из Apple Developer.
- `APPLE_NOTARY_APP_PASSWORD` — app-specific password для notarytool.

После добавления секретов workflow автоматически:
1) подпишет `.app`,
2) отправит zip на notarization,
3) сделает staple,
4) переупакует итоговый zip.

### Где взять значения секретов (если у вас нет Mac)

Коротко: реальные значения нельзя «взять готовыми» — их нужно создать в вашем Apple-аккаунте.

Обязательное условие:
- активная подписка **Apple Developer Program**.

Что откуда берётся:
- `APPLE_NOTARY_APPLE_ID` — ваш Apple ID (email).
- `APPLE_NOTARY_TEAM_ID` — Team ID из Apple Developer account.
- `APPLE_NOTARY_APP_PASSWORD` — app-specific password с `appleid.apple.com`.
- `APPLE_KEYCHAIN_PASSWORD` — любое случайное значение (вы придумываете сами).
- `APPLE_DEVELOPER_ID_APPLICATION_CERT_PASSWORD` — пароль, который вы зададите при создании `.p12`.
- `APPLE_CODESIGN_IDENTITY` — CN сертификата, обычно вида `Developer ID Application: Your Name (TEAMID)`.
- `APPLE_DEVELOPER_ID_APPLICATION_CERT_BASE64` — base64 от вашего файла `.p12`.

Как получить `.p12` без Mac (на Windows):
1. Сгенерируйте ключ и CSR (через OpenSSL).
2. В Apple Developer создайте сертификат **Developer ID Application** по этому CSR.
3. Скачайте сертификат и соберите `.p12` (ключ + сертификат) через OpenSSL.
4. Закодируйте `.p12` в base64 и вставьте в `APPLE_DEVELOPER_ID_APPLICATION_CERT_BASE64`.

Пример base64 на Windows (PowerShell):
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes(".\developer_id_application.p12"))
```

Если Apple Developer аккаунта нет:
- workflow всё равно соберёт macOS zip без этих секретов;
- приложение запустится на Mac через обход предупреждения Gatekeeper ("Открыть" через контекстное меню).

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
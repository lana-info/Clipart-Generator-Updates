# Релиз и установка (Windows)

## Быстрый чеклист релиза (обязательный)

> Для этого проекта релиз состоит из **двух репозиториев**:
> - основной: `Clipart-Generator`
> - обновления: `Clipart-Generator-Updates` (локально: `_updates_repo_tmp`)

### 0) Подготовка версии
- [ ] Выбрать новую версию `x.y.z` (например `0.1.1`).
- [ ] Обновить версию в `main.py` (`APP_VERSION`).
- [ ] Обновить версию в `installer.iss` (`#define AppVersion`).
- [ ] Обновить дефолт версии в `build.ps1` (`$AppVersion`).

### 1) Проверки перед сборкой
- [ ] Проверить синтаксис: `python -m py_compile main.py`.
- [ ] Smoke-тест окна (offscreen):
  `python -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; import main; app=main.QApplication([]); w=main.MainWindow(); print('SMOKE_OK')"`

### 2) Публикация кода (основной репозиторий)
- [ ] Закоммитить изменения в `Clipart-Generator`.
- [ ] Запушить в `origin/main`.

### 3) Сборка инсталлятора
- [ ] Собрать приложение: `powershell -ExecutionPolicy Bypass -File .\build.ps1 -AppVersion x.y.z`.
- [ ] Собрать setup: `ISCC .\installer.iss`.
- [ ] Проверить наличие файла `release\ClipartGenerator-Setup-x.y.z.exe`.
- [ ] Посчитать SHA256:
  `Get-FileHash ".\release\ClipartGenerator-Setup-x.y.z.exe" -Algorithm SHA256`.

### 4) Обновить репозиторий обновлений
- [ ] Открыть `_updates_repo_tmp\version.json`.
- [ ] Обновить поля:
  - [ ] `latest_version = x.y.z`
  - [ ] `download_url = https://github.com/lana-info/Clipart-Generator-Updates/releases/download/vx.y.z/ClipartGenerator-Setup-x.y.z.exe`
  - [ ] `sha256 = <новый хеш setup>`
- [ ] Закоммитить изменения в `_updates_repo_tmp`.
- [ ] Запушить в `Clipart-Generator-Updates` (`origin/main`).

### 5) Публикация GitHub Release
- [ ] В репозитории `Clipart-Generator-Updates` создать/обновить Release `vx.y.z`.
- [ ] Загрузить asset `ClipartGenerator-Setup-x.y.z.exe`.
- [ ] Проверить, что имя файла в release совпадает с `download_url` из `version.json`.

### 6) Проверка автообновления
- [ ] На установленной предыдущей версии запустить приложение.
- [ ] Убедиться, что найдено обновление до `x.y.z`.
- [ ] Установить обновление и перезапустить приложение.
- [ ] Проверить, что повторного запроса обновления по кругу нет.

### 7) Финальная проверка релиза
- [ ] Generation/processing smoke (1-2 промпта) проходит без падений.
- [ ] Файлы сохраняются в `raw` и `output`.

## Быстрый чеклист релиза (macOS)

> Важно: сборка macOS делается **только на macOS** (на Windows собрать корректный `.app` нельзя).

### 0) Подготовка окружения (Mac)
- [ ] Установить Python 3.12+.
- [ ] Установить зависимости: `pip install -r requirements.txt -r requirements-dev.txt`.
- [ ] Установить PyInstaller (если не установлен): `pip install pyinstaller`.

### 1) Подготовка версии
- [ ] Убедиться, что `APP_VERSION` в `main.py` соответствует релизу.
- [ ] Для кроссплатформенного релиза использовать одну и ту же версию, что и для Windows.

### 2) Сборка `.app`
- [ ] Выполнить сборку:

```bash
cd "/path/to/Clipart Generator"
python -m PyInstaller --noconfirm --clean --windowed --name "Clipart Generator" --add-data ".env.example:." main.py
```

- [ ] Проверить результат: `dist/Clipart Generator.app`.

### 3) Локальный smoke-тест на Mac
- [ ] Открыть приложение двойным кликом.
- [ ] Проверить запуск окна, вкладки и кнопку Start.
- [ ] Проверить, что создаются папки `raw` и `output` в рабочей директории.

### 4) Упаковка для дистрибуции
- [ ] Базовый вариант: zip архив:

```bash
cd dist
zip -r "Clipart-Generator-mac-x.y.z.zip" "Clipart Generator.app"
```

- [ ] (Опционально) сделать `.dmg` через отдельный инструмент (`create-dmg` и т.п.).

### 5) Подпись и Gatekeeper (рекомендуется)
- [ ] (Опционально) подписать `.app` сертификатом Apple Developer ID (`codesign`).
- [ ] (Опционально) пройти notarization (`xcrun notarytool`).
- [ ] Проверить запуск на «чистом» Mac без ручного обхода безопасности.

### 6) Публикация
- [ ] Загрузить mac-артефакт в GitHub Release (обычно отдельный asset рядом с Windows setup).
- [ ] В описании релиза указать, что файл для macOS: `Clipart-Generator-mac-x.y.z.zip`.

### 7) Важно про автообновление
- [ ] Текущая логика автообновления в приложении ориентирована на Windows installer (`.exe`).
- [ ] Для полноценного автообновления macOS нужен отдельный поток обновления (URL/формат артефакта и установка под macOS).
- [ ] Статус репозиториев чистый (`git status`).

## 1) Подготовка окружения
1. Установить Python 3.12+.
2. Установить Inno Setup 6.
3. Открыть PowerShell в папке проекта.

## 2) Сборка приложения (.exe)
```powershell
Set-Location "d:\Projects\Clipart Generator"
powershell -ExecutionPolicy Bypass -File .\build.ps1 -AppVersion 0.1.0
```

Результат:
- `dist\Clipart Generator\Clipart Generator.exe`
- `release\VERSION.txt`

## 3) Сборка установщика (Inno Setup)
Вариант A (через GUI):
1. Открыть `installer.iss` в Inno Setup.
2. Нажать Compile.

Вариант B (через CLI):
```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" ".\installer.iss"
```

Результат:
- `release\ClipartGenerator-Setup-0.1.0.exe`

## 4) Структура релизного пакета
- `ClipartGenerator-Setup-x.y.z.exe`
- `VERSION.txt`
- `CHANGELOG.md` (рекомендуется)
- `README_install.md` или этот `RELEASE.md`

## 4.1) Обновления приложения (version.json)
Файл `version.json` публикуется в репозитории и читается приложением при старте.

Пример:
```json
{
  "latest_version": "0.1.0",
  "download_url": "https://github.com/lana-info/Clipart-Generator/releases/download/v0.1.0/ClipartGenerator-Setup-0.1.0.exe",
  "sha256": ""
}
```

Порядок на каждый релиз:
1. Собрать новый `ClipartGenerator-Setup-x.y.z.exe`.
2. Вычислить SHA256 файла.
3. Обновить `version.json` (`latest_version`, `download_url`, `sha256`).
4. Загрузить setup в GitHub Release.
5. Закоммитить и запушить `version.json`.

Команда для SHA256 в PowerShell:
```powershell
Get-FileHash ".\release\ClipartGenerator-Setup-0.1.0.exe" -Algorithm SHA256
```

### Автообновление version.json (рекомендуется)
Теперь можно не заполнять `version.json` вручную.

После сборки setup выполните:
```powershell
powershell -ExecutionPolicy Bypass -File .\update_version.ps1 -AppVersion 0.1.0
```

Что делает скрипт:
1. Берёт setup из `release\ClipartGenerator-Setup-<version>.exe`.
2. Считает SHA256.
3. Автоматически формирует `download_url` для GitHub Releases.
4. Обновляет `version.json`.

После этого:
1. Загрузите setup в GitHub Release с тегом `v<version>`.
2. Закоммитьте и запушьте `version.json`.

Пример для другого репозитория/тега:
```powershell
powershell -ExecutionPolicy Bypass -File .\update_version.ps1 `
  -AppVersion 0.2.0 `
  -RepoOwner lana-info `
  -RepoName Clipart-Generator `
  -ReleaseTag v0.2.0 `
  -SetupFileName ClipartGenerator-Setup-0.2.0.exe
```

## 5) Чек-лист на «чистом» ПК
1. Установка проходит без ошибок.
2. Приложение запускается из ярлыка.
3. Создаются папки `raw` и `output`.
4. Открываются вкладки и работает кнопка Start.
5. Удаление через «Приложения и возможности» работает корректно.
6. Кнопка «Проверить обновления» в «Настройки» отрабатывает без падения.

## 6) Лицензирование (локальный сервер)

### Установка зависимостей
```powershell
pip install -r requirements-dev.txt
```

### Запуск сервера лицензий
```powershell
uvicorn license_server:app --host 127.0.0.1 --port 8000
```

### Где должен работать сервер лицензий
- GitHub хранит только код, сервер там не запускается.
- Для продакшна используйте площадку с запуском Python-процесса:
  - Railway — подходит,
  - VPS/Cloud (в т.ч. Hostinger VPS) — подходит,
  - обычный shared-хостинг сайтов (без фоновых процессов) — обычно не подходит.

### Можно ли использовать домен вместо IP
Да, это лучший вариант.

Пример:
- было: `http://123.45.67.89:8000`
- стало: `https://license.yourdomain.com`

В приложении адрес меняется в `Настройки → Лицензия → URL сервера лицензий`
или в `config.json` через поле `license_server_url`.
Это можно менять в любой момент, без переделки логики приложения.

### Админ-утилита ключей
Создать (или подтвердить) ключ:
```powershell
python license_admin.py create YOUR-LICENSE-KEY
```

Автогенерация ключей (случайные):
```powershell
python license_admin.py generate --count 20 --prefix CG --mode random --expires-days 365 --max-devices 2
```

Автогенерация ключей (серийные):
```powershell
python license_admin.py generate --count 10 --prefix CG --mode serial --serial-start 1000 --expires-days 180 --max-devices 1
```

Показать список ключей:
```powershell
python license_admin.py list --limit 50
```

Сбросить привязку устройства:
```powershell
python license_admin.py reset YOUR-LICENSE-KEY
```

### API эндпойнты сервера лицензий
- `POST /activate`
- `POST /validate`
- `POST /deactivate`
- `POST /admin/generate`
- `GET /admin/list`

SQLite база создаётся автоматически в файле `licenses.db` в директории запуска сервера.

### В приложении
1. Откройте вкладку **Настройки → Лицензия**.
2. Укажите URL сервера и лицензионный ключ.
3. Нажмите **Активировать** и затем **Проверить**.
4. При необходимости включите «Требовать лицензию перед запуском».

## 7) Понятный рабочий процесс (для автора)

### Первый запуск (один раз)
1. Установите зависимости:
```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```
2. Поднимите сервер лицензий (локально или на хостинге).
3. Сгенерируйте ключи:
```powershell
python license_admin.py generate --count 20 --prefix CG --mode random --expires-days 365 --max-devices 1
```
4. В приложении укажите `license_server_url` и тестовый ключ.

### Как выпускать обновление
1. Повышаете версию в проекте.
2. Собираете приложение и setup.
3. Обновляете `version.json` скриптом `update_version.ps1`.
4. Публикуете setup в GitHub Release с нужным тегом.
5. Коммит/пуш изменений (`version.json` и код при необходимости).

### Что делает пользователь
1. Устанавливает setup.
2. Запускает приложение.
3. Вводит лицензионный ключ (если включено лицензирование).
4. Работает в обычном режиме.
5. При наличии новой версии нажимает «Проверить обновления» или получает проверку при старте.

# План релиза 0.2.4

## Цель
Собрать артефакты `0.2.4` (Windows + macOS) через GitHub Actions в репозитории с кодом и затем опубликовать релиз в отдельном репозитории обновлений.

## Где что делается
- Сборка (автоматическая): `Clipart-Generator`
  - Workflow: `Release Multi Platform`
  - Ссылка: `https://github.com/lana-info/Clipart-Generator/actions/workflows/release-multi-platform.yml`
- Публикация релиза (ручная после скачивания артефактов): `Clipart-Generator-Updates`
  - Releases: `https://github.com/lana-info/Clipart-Generator-Updates/releases`

## Шаги и статус
- [x] Проверить релизные инструкции в проекте (`RELEASE.md`, `README_AUTHOR_SHORT.md`, `AUTHOR_STEP_BY_STEP.md`)
- [x] Зафиксировать версию `0.2.4` в исходниках и скриптах:
  - [x] `main.py` (`APP_VERSION`)
  - [x] `installer.iss` (`AppVersion`)
  - [x] `build.ps1` (дефолт `AppVersion`)
  - [x] `release/VERSION.txt`
- [x] Проверить синтаксис (`python -m py_compile main.py`)
- [x] Закоммитить и запушить изменения в `main` (триггер GitHub Actions)
- [ ] Дождаться завершения workflow `Release Multi Platform` в `Clipart-Generator`
- [ ] Скачать artifacts из workflow:
  - [ ] `windows-0.2.4` → `ClipartGenerator-Setup-0.2.4.exe`
  - [ ] `macos-0.2.4` → `ClipartGenerator-macOS-0.2.4.zip`
- [ ] Получить `SHA256` для `ClipartGenerator-Setup-0.2.4.exe`
- [ ] Обновить `_updates_repo_tmp/version.json`:
  - [ ] `latest_version = 0.2.4`
  - [ ] `download_url` на asset релиза `Clipart-Generator-Updates`
  - [ ] `sha256` от финального setup
- [ ] Закоммитить/запушить `_updates_repo_tmp`
- [ ] Создать/обновить GitHub Release `v0.2.4` в `Clipart-Generator-Updates`
  - [ ] Загрузить `ClipartGenerator-Setup-0.2.4.exe`
  - [ ] (опционально) загрузить `ClipartGenerator-macOS-0.2.4.zip`
- [ ] Проверить автообновление в приложении

## Что уже сделано в этой сессии
- Выполнен commit: `61b9e13` (`chore(release): bump version to 0.2.4`)
- Выполнен push: `main -> origin/main`

## Ограничение на текущем окружении
В этой сессии GitHub API/веб для репозиториев отвечает `404`, а `gh auth status` показывает отсутствие входа. Поэтому я не могу автоматически проверить статус workflow и скачать artifacts отсюда, но триггер сборки уже выполнен push-ом в `main`.
# Релиз и установка (Windows)

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

## 5) Чек-лист на «чистом» ПК
1. Установка проходит без ошибок.
2. Приложение запускается из ярлыка.
3. Создаются папки `raw` и `output`.
4. Открываются вкладки и работает кнопка Start.
5. Удаление через «Приложения и возможности» работает корректно.
6. Кнопка «Проверить обновления» в «Настройки» отрабатывает без падения.

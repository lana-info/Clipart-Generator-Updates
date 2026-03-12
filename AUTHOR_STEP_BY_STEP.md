# Подробная инструкция для автора (просто и по шагам)

Этот файл — «что делать дальше» без лишней теории.

---

## 0) Что у вас уже готово

В проекте уже есть:
- сборка приложения (`build.ps1`, `installer.iss`),
- автообновления (`version.json`, `update_version.ps1`),
- лицензирование (`license_server.py`, `license_admin.py`, `license_client.py`).

Значит дальше вам нужно только правильно запускать процесс релиза.

---

## 1) Подготовка на вашем ПК (делается один раз)

1. Установите Python 3.12+.
2. Установите Inno Setup 6.
3. В папке проекта выполните:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## 2) Где запускать сервер лицензий

Важно:
- GitHub = хранение кода, **не** запуск сервера.
- Обычный shared-хостинг часто не подходит для FastAPI.
- Подходит: Railway / VPS / Cloud.

Если пока тестируете локально:

```powershell
uvicorn license_server:app --host 127.0.0.1 --port 8000
```

Для боевого режима лучше использовать домен (например `https://license.yourdomain.com`).

### Важно: защита админки сервера лицензий

Теперь админ-эндпойнты сервера защищены секретным токеном:
- `POST /admin/generate`
- `GET /admin/list`

На Railway нужно добавить переменную окружения:

```text
LICENSE_ADMIN_TOKEN=придумайте_сюда_длинный_секретный_токен
```

Пример хорошего токена:

```text
CG_ADMIN_9fK2xP7mQ4vL8sR1zN6tW3yH5uB0aD
```

Если токен не задан, админ-эндпойнты не будут работать.

Передавать токен можно двумя способами:

### Вариант A — через HTTP-заголовок

Заголовок:

```text
X-Admin-Token: ваш_секретный_токен
```

### Вариант B — через query-параметр

Пример:

```text
https://your-domain/admin/list?admin_token=ваш_секретный_токен
```

Но безопаснее использовать именно заголовок.

---

## 3) Как создать ключи для клиентов

### Вариант A — случайные ключи

Если сервер запущен на Railway, для создания ключей через API не забудьте передать админ-токен.

Пример `curl`:

```powershell
curl -X POST "https://your-domain/admin/generate" ^
  -H "Content-Type: application/json" ^
  -H "X-Admin-Token: ваш_секретный_токен" ^
  -d "{\"count\":5,\"prefix\":\"CG\",\"mode\":\"random\",\"expires_days\":365,\"updates_days\":365,\"max_devices\":1,\"serial_start\":1}"
```

```powershell
python license_admin.py generate --count 50 --prefix CG --mode random --expires-days 365 --max-devices 1
```

Что это значит:
- `count 50` — создаст 50 ключей,
- `expires-days 365` — срок 1 год,
- `max-devices 1` — один ключ на одно устройство.

### Вариант B — серийные ключи

```powershell
python license_admin.py generate --count 20 --prefix CG --mode serial --serial-start 1000 --expires-days 180 --max-devices 1
```

### Посмотреть ключи

```powershell
python license_admin.py list --limit 100
```

Если смотрите список через Railway API:

```text
GET https://your-domain/admin/list?admin_token=ваш_секретный_токен
```

### Сбросить активацию ключа (если клиент сменил ПК)

```powershell
python license_admin.py reset YOUR-LICENSE-KEY
```

---

## 4) Как собрать приложение перед релизом

1. Соберите exe:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -AppVersion 0.1.0
```

2. Соберите установщик:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" ".\installer.iss"
```

Ожидаемый файл:
- `release\ClipartGenerator-Setup-0.1.0.exe`

---

## 5) Как сделать обновление (без ручного JSON)

После сборки setup запустите:

```powershell
powershell -ExecutionPolicy Bypass -File .\update_version.ps1 -AppVersion 0.1.0
```

Скрипт сам:
- обновит `latest_version`,
- соберёт `download_url`,
- посчитает `sha256` (если setup-файл найден).

---

## 6) Публикация релиза в GitHub

1. Откройте GitHub → Releases.
2. Создайте релиз с тегом `v0.1.0`.
3. Прикрепите файл `ClipartGenerator-Setup-0.1.0.exe`.
4. Проверьте, что `version.json` уже обновлён скриптом.
5. Закоммитьте и запушьте изменения в `main`.

---

## 7) Что отправлять пользователю

Минимум:
1. Ссылка на setup (или сам setup).
2. Лицензионный ключ.
3. Короткая инструкция:
   - установить приложение,
   - открыть Настройки → Лицензия,
   - ввести ключ,
   - нажать «Активировать».

---

## 8) Если вы меняете сервер/домен

Да, это можно делать в любой момент.

Где меняется адрес:
- в приложении: Настройки → Лицензия → URL сервера,
- или в `config.json`: поле `license_server_url`.

Если используете домен, а не IP — это даже лучше.

---

## 9) Мини-чек перед запуском продаж

- [ ] Установщик ставится без ошибок
- [ ] Лицензия активируется
- [ ] Start работает
- [ ] Проверка обновлений работает
- [ ] В `version.json` актуальная версия/ссылка/sha256
- [ ] Релиз с setup опубликован в GitHub

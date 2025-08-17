# Warehouse (Storm Universal) — Prototype v1.1

## Что это
Веб-приложение для заявок на склад с ролями: заявитель, складчик, менеджер, администратор.
Функции: логин, создание заявок, комментарии с фото, статусы (меняет только складчик), просмотр менеджерами.

## Новое в версии 1.1
- Добавлен статус **«Материал забран»**. При выборе этого статуса складчиком заявка **автоматически закрывается**, в карточке фиксируются дата и время забора (**pickup_at**) и закрытия (**closed_at**).

## Быстрый старт (macOS)
1) Установите Python 3.11+.
2) Распакуйте архив.
3) В терминале:
```
cd warehouse_app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```
4) Откройте в браузере: http://localhost:5000

Тестовые логины:
- admin / admin123 (админ)
- applicant1 / test123 (заявитель)
- stockman1 / test123 (складчик)
- manager1 / test123 (менеджер)

## На iPhone
Подключите iPhone и Mac в одну сеть Wi‑Fi.
Определите IP Mac: `ipconfig getifaddr en0` (или en1).
Запустите сервер, затем откройте в Safari на iPhone: `http://IP_МАКа:5000`

## Примечания
- Файлы изображений сохраняются в папку `uploads/` рядом с приложением.
- Встроена лёгкая миграция БД: при запуске добавит новые поля `pickup_at`, `closed_at`, если их нет.
- Иконка использует цвета чёрный/красный (SU — Storm Universal). Лого можно заменить в `static/styles.css` и `templates/base.html`.


## Новое в версии 1.2
- **Журнал истории статусов**: кто и когда менял статус, старый → новый, примечание. Для события «Материал забран» добавляется отметка и автозакрытие.


## Новое в версии 1.3
- При выборе статуса **«Материал забран»** появляется форма: **ФИО получателя** и **фото-подтверждение** (можно указать одно из двух, но лучше оба). Данные сохраняются в заявку и отображаются в карточке.


## Deploying to Render (One Link for Everyone)
1) Push this folder to a GitHub repo.
2) In Render: New → Web Service → Connect repo.
3) Ensure build command is `pip install -r requirements.txt` and start command is `gunicorn app:app`.
4) Add env vars: `PYTHON_VERSION=3.11`, `DATA_DIR=/data`, and set `SECRET_KEY`.
5) Add a persistent disk mounted to `/data` (2GB+). That will persist the SQLite DB and uploads.
6) Deploy. You'll get an HTTPS URL to share with your team.

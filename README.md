# Realty Landing — Лендинг для Instagram/TikTok

## Структура
```
realty-landing/
├── app.py              # Flask бэкенд
├── requirements.txt
├── templates/
│   ├── index.html      # Публичный лендинг
│   ├── admin.html      # Админ-панель (квартиры)
│   ├── leads.html      # Просмотр заявок
│   └── login.html      # Вход в админку
└── data/               # Создаётся автоматически
    ├── apartments.json  # База квартир
    └── leads.json       # Все заявки
```

## Запуск локально

```bash
pip install -r requirements.txt
python app.py
```

Лендинг: http://localhost:5050  
Админка: http://localhost:5050/admin  
Пароль по умолчанию: `admin123`

## Настройка AmoCRM

В файле `app.py` или через переменные окружения:

```bash
export AMO_DOMAIN="yourcompany.amocrm.ru"
export AMO_TOKEN="ваш_долгоживущий_токен"
export ADMIN_PASSWORD="ваш_пароль"
```

## Деплой на Railway

1. Загрузи код на GitHub
2. Railway → New Project → Deploy from GitHub
3. Добавь переменные окружения:
   - `AMO_DOMAIN`
   - `AMO_TOKEN`  
   - `ADMIN_PASSWORD`
   - `SECRET_KEY` (любая случайная строка)
4. Добавь `Procfile`:
   ```
   web: python app.py
   ```
   И в `app.py` измени последнюю строку:
   ```python
   app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5050)))
   ```

## Как использовать

1. Зайди в `/admin` → добавь квартиры (название, адрес, цена, фото по ссылкам)
2. Ссылку на лендинг поставь в профиль Instagram/TikTok
3. В описании поста пиши "Ссылка в профиле"
4. Пользователь открывает лендинг → видит все квартиры → нажимает на понравившуюся → оставляет имя и телефон
5. Лид падает в AmoCRM с тегом квартиры + дублируется в `/admin/leads`

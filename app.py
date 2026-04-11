from flask import Flask, request, jsonify, render_template, redirect, session, send_from_directory
import json
import os
import requests
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'realty-secret-2024')

DATA_FILE = 'data/apartments.json'
UPLOAD_FOLDER = 'static/uploads'
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
AMO_DOMAIN = os.environ.get('AMO_DOMAIN', 'laresgroup.amocrm.ru')
AMO_TOKEN = os.environ.get('AMO_TOKEN', 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjQ2N2VjY2ViZTAzZmQzY2RiMDBjNmQxMTY4MGNhNmVkNWQ4NjI2MTBjNDgxZmFhM2QyZjdiYzMzYzlhNTRmYjgyZGUyMzQ1NzJlMzA5YTQxIn0.eyJhdWQiOiI0ZjBhMjNhYy01NzI0LTQ0Y2ItOGQ0ZC0xNmQ4ZmQxNjc3MzkiLCJqdGkiOiI0NjdlY2NlYmUwM2ZkM2NkYjAwYzZkMTE2ODBjYTZlZDVkODYyNjEwYzQ4MWZhYTNkMmY3YmMzM2M5YTU0ZmI4MmRlMjM0NTcyZTMwOWE0MSIsImlhdCI6MTc3NTgyNDkxNCwibmJmIjoxNzc1ODI0OTE0LCJleHAiOjE3NzgzNzEyMDAsInN1YiI6IjkwOTgyMzAiLCJncmFudF90eXBlIjoiIiwiYWNjb3VudF9pZCI6MzA3Nzk2MzAsImJhc2VfZG9tYWluIjoiYW1vY3JtLnJ1IiwidmVyc2lvbiI6Miwic2NvcGVzIjpbInB1c2hfbm90aWZpY2F0aW9ucyIsImZpbGVzIiwiY3JtIiwiZmlsZXNfZGVsZXRlIiwibm90aWZpY2F0aW9ucyJdLCJoYXNoX3V1aWQiOiJjZTM4Yjc1Ny0yODBjLTRkMDItYjIzOC0xZmY4ZWE4NTBhY2YiLCJhcGlfZG9tYWluIjoiYXBpLWIuYW1vY3JtLnJ1In0.Vd8R5c5usJ2sOoEqmS8qQgyJfNs3B2gFQ3o4IWym5gmUCKXiEqEDvodBEwlj4-y1xMlaVB4vuz3Bkaj2Gpsf-WKQy9OTbzRVU8lir9gKfj_eJ52ZIokpySiL0pKEy6bFeJXOjkhg2We6ZIy3voYCSvuTzDqD2pyKmhFX06O1PkJepvfUX4la2NN0385Ebh9T686gv54t1QIsRhgaOvKg1UXaiDCQMMLi70AdoPP4p_56HNZbbCiUWUG0fMyB87dyCX3NCurzlRUFGwP_sFncZDQxko3ueNUXpeI2t4-o6qaSDkPErqtZ3yEz4AUX9Vkg2_9ht2n6O5uSGsF6aNrIGQ')
AMO_PIPELINE_ID = 6314686   # ОТДЕЛ ПРОДАЖ
AMO_STATUS_ID = 54235682    # 1. Новая заявка

os.makedirs('data', exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import random

VIEWS_FILE = 'data/views.json'

def load_views():
    if not os.path.exists(VIEWS_FILE):
        return {}
    with open(VIEWS_FILE, 'r') as f:
        return json.load(f)

def save_views(views):
    with open(VIEWS_FILE, 'w') as f:
        json.dump(views, f)

def get_views(apt_id):
    views = load_views()
    if apt_id not in views:
        # Стартовое число — случайное от 50 до 200
        views[apt_id] = random.randint(50, 200)
        save_views(views)
    return views[apt_id]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_apartments():
    if not os.path.exists(DATA_FILE):
        save_apartments([])
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_apartments(apartments):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(apartments, f, ensure_ascii=False, indent=2)

def amo_headers():
    return {
        'Authorization': f'Bearer {AMO_TOKEN}',
        'Content-Type': 'application/json'
    }

def create_amo_lead(name, phone, apartment_title):
    if not AMO_TOKEN or not AMO_DOMAIN:
        print("AmoCRM не настроен")
        return None

    base = f'https://{AMO_DOMAIN}'
    headers = amo_headers()

    try:
        # 1. Создаём контакт
        contact_payload = [{
            'name': name,
            'custom_fields_values': [{
                'field_code': 'PHONE',
                'values': [{'value': phone, 'enum_code': 'MOB'}]
            }]
        }]
        r = requests.post(f'{base}/api/v4/contacts', headers=headers, json=contact_payload, timeout=10)
        contact_data = r.json()
        contact_id = contact_data['_embedded']['contacts'][0]['id']
        print(f'Контакт создан: {contact_id}')

        # 2. Создаём сделку и привязываем контакт
        lead_payload = [{
            'name': f'Заявка с лендинга: {apartment_title}',
            'pipeline_id': AMO_PIPELINE_ID,
            'status_id': AMO_STATUS_ID,
            '_embedded': {
                'contacts': [{'id': contact_id}],
                'tags': [{'name': 'tenet'}]
            }
        }]
        r = requests.post(f'{base}/api/v4/leads', headers=headers, json=lead_payload, timeout=10)
        lead_data = r.json()
        lead_id = lead_data['_embedded']['leads'][0]['id']
        print(f'Сделка создана: {lead_id}')

        # 3. Добавляем тег отдельным запросом (надёжнее)
        requests.patch(f'{base}/api/v4/leads', headers=headers,
            json=[{'id': lead_id, 'tags': [{'name': 'tenet'}]}], timeout=10)
        print('Тег добавлен')

        # 4. Добавляем примечание с квартирой
        note_payload = [{
            'entity_id': lead_id,
            'note_type': 'common',
            'params': {
                'text': f'Клиент заинтересован в объекте: {apartment_title}'
            }
        }]
        requests.post(f'{base}/api/v4/leads/notes', headers=headers, json=note_payload, timeout=10)
        print('Примечание добавлено')

        return {'contact_id': contact_id, 'lead_id': lead_id}

    except Exception as e:
        print(f'Ошибка AmoCRM: {e}')
        return None

# ── Публичные ──────────────────────────────────────────

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/quiz')
def quiz():
    return render_template('quiz.html')

@app.route('/submit-quiz', methods=['POST'])
def submit_quiz():
    data = request.json
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    note = data.get('note', '')
    if not name or not phone:
        return jsonify({'success': False, 'error': 'Заполните все поля'})

    # Создаём лид в AmoCRM
    if AMO_TOKEN and AMO_DOMAIN:
        base = f'https://{AMO_DOMAIN}'
        headers = amo_headers()
        try:
            contact_payload = [{'name': name, 'custom_fields_values': [{'field_code': 'PHONE', 'values': [{'value': phone, 'enum_code': 'MOB'}]}]}]
            r = requests.post(f'{base}/api/v4/contacts', headers=headers, json=contact_payload, timeout=10)
            contact_id = r.json()['_embedded']['contacts'][0]['id']

            lead_payload = [{'name': f'Квиз: подбор квартиры', 'pipeline_id': AMO_PIPELINE_ID, 'status_id': AMO_STATUS_ID, '_embedded': {'contacts': [{'id': contact_id}], 'tags': [{'name': 'tenet'}, {'name': 'квиз'}]}}]
            r = requests.post(f'{base}/api/v4/leads', headers=headers, json=lead_payload, timeout=10)
            lead_id = r.json()['_embedded']['leads'][0]['id']

            requests.patch(f'{base}/api/v4/leads', headers=headers, json=[{'id': lead_id, 'tags': [{'name': 'tenet'}, {'name': 'квиз'}]}], timeout=10)

            note_payload = [{'entity_id': lead_id, 'note_type': 'common', 'params': {'text': note}}]
            requests.post(f'{base}/api/v4/leads/notes', headers=headers, json=note_payload, timeout=10)
        except Exception as e:
            print(f'Ошибка AmoCRM квиз: {e}')

    # Логируем локально
    log_file = 'data/leads.json'
    logs = json.load(open(log_file)) if os.path.exists(log_file) else []
    logs.append({'time': datetime.now().isoformat(), 'name': name, 'phone': phone, 'apartment': 'Квиз', 'note': note})
    json.dump(logs, open(log_file, 'w'), ensure_ascii=False, indent=2)
    return jsonify({'success': True})

@app.route('/view/<apt_id>', methods=['POST'])
def track_view(apt_id):
    views = load_views()
    if apt_id not in views:
        views[apt_id] = random.randint(50, 200)
    views[apt_id] += 1
    save_views(views)
    return jsonify({'views': views[apt_id]})

@app.route('/')
def index():
    apartments = [a for a in load_apartments() if a.get('active', True)]
    views = load_views()
    # Инициализируем просмотры для новых квартир
    for apt in apartments:
        if apt['id'] not in views:
            views[apt['id']] = random.randint(50, 200)
    save_views(views)
    return render_template('index.html', apartments=apartments, views=views)

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    apt_id = data.get('apartment_id', '')
    apt_title = data.get('apartment_title', '')
    if not name or not phone:
        return jsonify({'success': False, 'error': 'Заполните все поля'})

    result = create_amo_lead(name, phone, apt_title)

    log_file = 'data/leads.json'
    logs = json.load(open(log_file)) if os.path.exists(log_file) else []
    logs.append({
        'time': datetime.now().isoformat(),
        'name': name, 'phone': phone,
        'apartment': apt_title, 'apartment_id': apt_id,
        'amo': result
    })
    json.dump(logs, open(log_file, 'w'), ensure_ascii=False, indent=2)
    return jsonify({'success': True})

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ── Загрузка фото ──────────────────────────────────────

@app.route('/admin/upload', methods=['POST'])
def upload_photo():
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    f = request.files.get('file')
    if not f or not allowed_file(f.filename):
        return jsonify({'success': False, 'error': 'Неверный формат'})
    ext = f.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({'success': True, 'url': f"/static/uploads/{filename}"})

# ── Админка ────────────────────────────────────────────

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/admin/login')
    return render_template('admin.html', apartments=load_apartments())

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin')
        return render_template('login.html', error='Неверный пароль')
    return render_template('login.html', error=None)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/')

@app.route('/admin/add', methods=['POST'])
def admin_add():
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    data = request.json
    apartments = load_apartments()
    apt = {
        'id': str(uuid.uuid4())[:8],
        'title': data.get('title', ''),
        'address': data.get('address', ''),
        'price': data.get('price', ''),
        'rooms': data.get('rooms', ''),
        'area': data.get('area', ''),
        'floor': data.get('floor', ''),
        'description': data.get('description', ''),
        'images': data.get('images', []),
        'active': True,
        'created_at': datetime.now().isoformat()
    }
    apartments.append(apt)
    save_apartments(apartments)
    return jsonify({'success': True, 'apt': apt})

@app.route('/admin/update/<apt_id>', methods=['POST'])
def admin_update(apt_id):
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    data = request.json
    apartments = load_apartments()
    for apt in apartments:
        if apt['id'] == apt_id:
            apt.update({k: v for k, v in data.items() if k != 'id'})
    save_apartments(apartments)
    return jsonify({'success': True})

@app.route('/admin/delete/<apt_id>', methods=['POST'])
def admin_delete(apt_id):
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    apartments = [a for a in load_apartments() if a['id'] != apt_id]
    save_apartments(apartments)
    return jsonify({'success': True})

@app.route('/admin/leads')
def admin_leads():
    if not session.get('admin'):
        return redirect('/admin/login')
    log_file = 'data/leads.json'
    leads = list(reversed(json.load(open(log_file)))) if os.path.exists(log_file) else []
    return render_template('leads.html', leads=leads)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(debug=True, host='0.0.0.0', port=port)

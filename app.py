from flask import Flask, request, jsonify, render_template, redirect, session, send_from_directory
import json
import os
import requests
from datetime import datetime
import uuid
import random

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

try:
    from google import genai as google_genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'realty-secret-2024')

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
AMO_DOMAIN = os.environ.get('AMO_DOMAIN', 'laresgroup.amocrm.ru')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
AMO_TOKEN = os.environ.get('AMO_TOKEN', 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjQ2N2VjY2ViZTAzZmQzY2RiMDBjNmQxMTY4MGNhNmVkNWQ4NjI2MTBjNDgxZmFhM2QyZjdiYzMzYzlhNTRmYjgyZGUyMzQ1NzJlMzA5YTQxIn0.eyJhdWQiOiI0ZjBhMjNhYy01NzI0LTQ0Y2ItOGQ0ZC0xNmQ4ZmQxNjc3MzkiLCJqdGkiOiI0NjdlY2NlYmUwM2ZkM2NkYjAwYzZkMTE2ODBjYTZlZDVkODYyNjEwYzQ4MWZhYTNkMmY3YmMzM2M5YTU0ZmI4MmRlMjM0NTcyZTMwOWE0MSIsImlhdCI6MTc3NTgyNDkxNCwibmJmIjoxNzc1ODI0OTE0LCJleHAiOjE3NzgzNzEyMDAsInN1YiI6IjkwOTgyMzAiLCJncmFudF90eXBlIjoiIiwiYWNjb3VudF9pZCI6MzA3Nzk2MzAsImJhc2VfZG9tYWluIjoiYW1vY3JtLnJ1IiwidmVyc2lvbiI6Miwic2NvcGVzIjpbInB1c2hfbm90aWZpY2F0aW9ucyIsImZpbGVzIiwiY3JtIiwiZmlsZXNfZGVsZXRlIiwibm90aWZpY2F0aW9ucyJdLCJoYXNoX3V1aWQiOiJjZTM4Yjc1Ny0yODBjLTRkMDItYjIzOC0xZmY4ZWE4NTBhY2YiLCJhcGlfZG9tYWluIjoiYXBpLWIuYW1vY3JtLnJ1In0.Vd8R5c5usJ2sOoEqmS8qQgyJfNs3B2gFQ3o4IWym5gmUCKXiEqEDvodBEwlj4-y1xMlaVB4vuz3Bkaj2Gpsf-WKQy9OTbzRVU8lir9gKfj_eJ52ZIokpySiL0pKEy6bFeJXOjkhg2We6ZIy3voYCSvuTzDqD2pyKmhFX06O1PkJepvfUX4la2NN0385Ebh9T686gv54t1QIsRhgaOvKg1UXaiDCQMMLi70AdoPP4p_56HNZbbCiUWUG0fMyB87dyCX3NCurzlRUFGwP_sFncZDQxko3ueNUXpeI2t4-o6qaSDkPErqtZ3yEz4AUX9Vkg2_9ht2n6O5uSGsF6aNrIGQ')
AMO_PIPELINE_ID = 6314686
AMO_STATUS_ID = 54235682

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

USE_DB = bool(DATABASE_URL) and PSYCOPG2_AVAILABLE

DATA_FILE = 'data/apartments.json'
VIEWS_FILE = 'data/views.json'

os.makedirs('data', exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── БД ─────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS apartments (
            id VARCHAR(16) PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            price TEXT NOT NULL DEFAULT '',
            rooms TEXT NOT NULL DEFAULT '',
            area TEXT NOT NULL DEFAULT '',
            floor TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            images JSONB NOT NULL DEFAULT '[]',
            covered_image TEXT NOT NULL DEFAULT '',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            metro_name TEXT NOT NULL DEFAULT '',
            metro_color TEXT NOT NULL DEFAULT '',
            metro_walk TEXT NOT NULL DEFAULT ''
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS apt_views (
            apt_id VARCHAR(16) PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def apt_from_row(row):
    d = dict(row)
    if isinstance(d.get('created_at'), datetime):
        d['created_at'] = d['created_at'].isoformat()
    if d.get('images') is None:
        d['images'] = []
    return d

def migrate_from_json():
    json_file = 'data/apartments.json'
    if not os.path.exists(json_file):
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM apartments')
    if cur.fetchone()[0] > 0:
        cur.close()
        conn.close()
        return
    with open(json_file, 'r', encoding='utf-8') as f:
        apts = json.load(f)
    for apt in apts:
        cur.execute('''
            INSERT INTO apartments (id, title, address, price, rooms, area, floor, description,
                images, covered_image, active, created_at, metro_name, metro_color, metro_walk)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        ''', (
            apt.get('id'), apt.get('title',''), apt.get('address',''),
            apt.get('price',''), apt.get('rooms',''), apt.get('area',''),
            apt.get('floor',''), apt.get('description',''),
            json.dumps(apt.get('images',[])), apt.get('covered_image',''),
            apt.get('active', True), apt.get('created_at', datetime.now().isoformat()),
            apt.get('metro_name',''), apt.get('metro_color',''), apt.get('metro_walk',''),
        ))
    conn.commit()
    cur.close()
    conn.close()
    print(f'Migrated {len(apts)} apartments from JSON')

def load_apartments():
    if USE_DB:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT * FROM apartments ORDER BY created_at DESC')
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [apt_from_row(r) for r in rows]
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_apartments_json(apartments):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(apartments, f, ensure_ascii=False, indent=2)

def get_apartment(apt_id):
    if USE_DB:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT * FROM apartments WHERE id = %s', (apt_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return apt_from_row(row) if row else None
    return next((a for a in load_apartments() if a['id'] == apt_id), None)

def _json_views():
    if not os.path.exists(VIEWS_FILE):
        return {}
    with open(VIEWS_FILE, 'r') as f:
        return json.load(f)

def _save_json_views(views):
    with open(VIEWS_FILE, 'w') as f:
        json.dump(views, f)

def get_views(apt_id):
    if USE_DB:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT count FROM apt_views WHERE apt_id = %s', (apt_id,))
        row = cur.fetchone()
        if row is None:
            count = random.randint(50, 200)
            cur.execute('INSERT INTO apt_views (apt_id, count) VALUES (%s, %s) ON CONFLICT DO NOTHING', (apt_id, count))
            conn.commit()
        else:
            count = row[0]
        cur.close()
        conn.close()
        return count
    views = _json_views()
    if apt_id not in views:
        views[apt_id] = random.randint(50, 200)
        _save_json_views(views)
    return views[apt_id]

def get_all_views(apt_ids):
    if not apt_ids:
        return {}
    if USE_DB:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT apt_id, count FROM apt_views WHERE apt_id = ANY(%s)', (apt_ids,))
        existing = {r[0]: r[1] for r in cur.fetchall()}
        result = {}
        for apt_id in apt_ids:
            if apt_id not in existing:
                count = random.randint(50, 200)
                cur.execute('INSERT INTO apt_views (apt_id, count) VALUES (%s, %s) ON CONFLICT DO NOTHING', (apt_id, count))
                result[apt_id] = count
            else:
                result[apt_id] = existing[apt_id]
        conn.commit()
        cur.close()
        conn.close()
        return result
    views = _json_views()
    for apt_id in apt_ids:
        if apt_id not in views:
            views[apt_id] = random.randint(50, 200)
    _save_json_views(views)
    return {apt_id: views[apt_id] for apt_id in apt_ids}

# Инициализация БД при старте
if DATABASE_URL and PSYCOPG2_AVAILABLE:
    try:
        init_db()
        migrate_from_json()
    except Exception as e:
        print(f'DB init error: {e}')

# ── Утилиты ────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        contact_payload = [{
            'name': name,
            'custom_fields_values': [{
                'field_code': 'PHONE',
                'values': [{'value': phone, 'enum_code': 'MOB'}]
            }]
        }]
        r = requests.post(f'{base}/api/v4/contacts', headers=headers, json=contact_payload, timeout=10)
        contact_id = r.json()['_embedded']['contacts'][0]['id']

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
        lead_id = r.json()['_embedded']['leads'][0]['id']

        requests.patch(f'{base}/api/v4/leads', headers=headers,
            json=[{'id': lead_id, 'tags': [{'name': 'tenet'}]}], timeout=10)

        note_payload = [{
            'entity_id': lead_id,
            'note_type': 'common',
            'params': {'text': f'Клиент заинтересован в объекте: {apartment_title}'}
        }]
        requests.post(f'{base}/api/v4/leads/notes', headers=headers, json=note_payload, timeout=10)
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

    if AMO_TOKEN and AMO_DOMAIN:
        base = f'https://{AMO_DOMAIN}'
        headers = amo_headers()
        try:
            contact_payload = [{'name': name, 'custom_fields_values': [{'field_code': 'PHONE', 'values': [{'value': phone, 'enum_code': 'MOB'}]}]}]
            r = requests.post(f'{base}/api/v4/contacts', headers=headers, json=contact_payload, timeout=10)
            contact_id = r.json()['_embedded']['contacts'][0]['id']
            lead_payload = [{'name': 'Квиз: подбор квартиры', 'pipeline_id': AMO_PIPELINE_ID, 'status_id': AMO_STATUS_ID, '_embedded': {'contacts': [{'id': contact_id}], 'tags': [{'name': 'tenet'}, {'name': 'квиз'}]}}]
            r = requests.post(f'{base}/api/v4/leads', headers=headers, json=lead_payload, timeout=10)
            lead_id = r.json()['_embedded']['leads'][0]['id']
            requests.patch(f'{base}/api/v4/leads', headers=headers, json=[{'id': lead_id, 'tags': [{'name': 'tenet'}, {'name': 'квиз'}]}], timeout=10)
            note_payload = [{'entity_id': lead_id, 'note_type': 'common', 'params': {'text': note}}]
            requests.post(f'{base}/api/v4/leads/notes', headers=headers, json=note_payload, timeout=10)
        except Exception as e:
            print(f'Ошибка AmoCRM квиз: {e}')

    log_file = 'data/leads.json'
    logs = json.load(open(log_file)) if os.path.exists(log_file) else []
    logs.append({'time': datetime.now().isoformat(), 'name': name, 'phone': phone, 'apartment': 'Квиз', 'note': note})
    json.dump(logs, open(log_file, 'w'), ensure_ascii=False, indent=2)
    return jsonify({'success': True})

@app.route('/view/<apt_id>', methods=['POST'])
def track_view(apt_id):
    if USE_DB:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO apt_views (apt_id, count) VALUES (%s, 1)
            ON CONFLICT (apt_id) DO UPDATE SET count = apt_views.count + 1
            RETURNING count
        ''', (apt_id,))
        count = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'views': count})
    views = _json_views()
    views[apt_id] = views.get(apt_id, 0) + 1
    _save_json_views(views)
    return jsonify({'views': views[apt_id]})

@app.route('/')
def index():
    apartments = [a for a in load_apartments() if a.get('active', True)]
    apt_ids = [a['id'] for a in apartments]
    views = get_all_views(apt_ids)
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
    apt_id = str(uuid.uuid4())[:8]
    if USE_DB:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO apartments (id, title, address, price, rooms, area, floor, description,
                images, covered_image, active, created_at, metro_name, metro_color, metro_walk)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,NOW(),%s,%s,%s)
        ''', (
            apt_id,
            data.get('title', ''), data.get('address', ''), data.get('price', ''),
            data.get('rooms', ''), data.get('area', ''), data.get('floor', ''),
            data.get('description', ''), json.dumps(data.get('images', [])),
            data.get('covered_image', ''),
            data.get('metro_name', ''), data.get('metro_color', ''), data.get('metro_walk', ''),
        ))
        conn.commit()
        cur.close()
        conn.close()
    else:
        apt = {
            'id': apt_id, 'title': data.get('title', ''), 'address': data.get('address', ''),
            'price': data.get('price', ''), 'rooms': data.get('rooms', ''),
            'area': data.get('area', ''), 'floor': data.get('floor', ''),
            'description': data.get('description', ''), 'images': data.get('images', []),
            'covered_image': data.get('covered_image', ''), 'active': True,
            'created_at': datetime.now().isoformat(),
            'metro_name': data.get('metro_name', ''), 'metro_color': data.get('metro_color', ''),
            'metro_walk': data.get('metro_walk', ''),
        }
        apts = load_apartments()
        apts.append(apt)
        save_apartments_json(apts)
    apt = get_apartment(apt_id)
    return jsonify({'success': True, 'apt': apt})

@app.route('/admin/update/<apt_id>', methods=['POST'])
def admin_update(apt_id):
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    data = request.json
    if USE_DB:
        allowed = ['title', 'address', 'price', 'rooms', 'area', 'floor',
                   'description', 'covered_image', 'active', 'metro_name', 'metro_color', 'metro_walk']
        updates = {k: data[k] for k in allowed if k in data}
        if 'images' in data:
            updates['images'] = json.dumps(data['images'])
        if not updates:
            return jsonify({'success': True})
        set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
        values = list(updates.values()) + [apt_id]
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f'UPDATE apartments SET {set_clause} WHERE id = %s', values)
        conn.commit()
        cur.close()
        conn.close()
    else:
        apts = load_apartments()
        for apt in apts:
            if apt['id'] == apt_id:
                apt.update({k: v for k, v in data.items() if k != 'id'})
        save_apartments_json(apts)
    return jsonify({'success': True})

@app.route('/admin/delete/<apt_id>', methods=['POST'])
def admin_delete(apt_id):
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    if USE_DB:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('DELETE FROM apartments WHERE id = %s', (apt_id,))
        cur.execute('DELETE FROM apt_views WHERE apt_id = %s', (apt_id,))
        conn.commit()
        cur.close()
        conn.close()
    else:
        apts = [a for a in load_apartments() if a['id'] != apt_id]
        save_apartments_json(apts)
    return jsonify({'success': True})

@app.route('/admin/generate-covered/<apt_id>', methods=['POST'])
def generate_covered_text(apt_id):
    if not session.get('admin'):
        return jsonify({'success': False}), 403
    if not GEMINI_AVAILABLE:
        return jsonify({'success': False, 'error': 'google-genai не установлен'})
    if not GEMINI_API_KEY:
        return jsonify({'success': False, 'error': 'GEMINI_API_KEY не задан'})

    apt = get_apartment(apt_id)
    if not apt:
        return jsonify({'success': False, 'error': 'Квартира не найдена'})

    metro = apt.get('metro_name', '')
    rooms = apt.get('rooms', '')
    area = apt.get('area', '')
    floor = apt.get('floor', '')
    desc = apt.get('description', '')

    prompt = f"""Ты маркетолог элитной недвижимости в Москве.
Создай текст для обложки поста в Instagram/TikTok о продаже квартиры.

Данные квартиры:
- Метро: {metro}
- Комнат: {rooms}
- Площадь: {area} м²
- Этаж: {floor}
- Описание: {desc}

Формат ответа — строго два блока:

ЗАГОЛОВОК: (одна строка — название станции метро, коротко и цепко, например «м. Сокольники»)

ОПИСАНИЕ:
• (маркер 1 — самое сильное преимущество, 5-8 слов)
• (маркер 2 — площадь/планировка/этаж, 5-8 слов)
• (маркер 3 — локация/инфраструктура/вид, 5-8 слов)

Требования:
- Только про продажу, никакой аренды
- Текст маркетинговый, живой, без канцелярита
- Каждый маркер — законченная мысль
- Не более 3 маркеров
- Если есть вид на Москва-Сити, Кремль — обязательно упомяни"""

    try:
        client = google_genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return jsonify({'success': True, 'text': response.text.strip()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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

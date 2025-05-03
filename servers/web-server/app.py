from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime
from DBMS_worker import DBMS_worker

app = Flask(__name__)
app.secret_key = "super secret key"

# Инициализация DBMS_worker
db = DBMS_worker(
    "localhost",
    "root",
    "123",
    "GreenHouseLocal"
)
if not db.created:
    raise RuntimeError(f"Ошибка подключения к БД: {db.error}")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('datetime_format')
def datetime_format(value, format='%d.%m.%Y %H:%M'):
    """Фильтр для форматирования даты"""
    if value is None:
        return ""
    return value.strftime(format)

@app.route('/', methods=['GET'])
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Заглушка проверки подписки (реализуйте свою логику)
        has_subscription = check_subscription(email)
        
        if has_subscription:
            session['logged_in'] = True
            session['user_email'] = email
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error="Неактивная подписка")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        # Статистика устройств
        db.cursor.execute("SELECT COUNT(*) FROM devices")
        devices_total = db.cursor.fetchone()[0]

        # Статистика правил
        db.cursor.execute("SELECT COUNT(*) FROM rules WHERE is_active = TRUE")
        active_rules = db.cursor.fetchone()[0]

        # Получаем секторы с показателями
        sectors = []
        db.cursor.execute("SELECT * FROM sectors")
        for sector_row in db.cursor.fetchall():
            sector = {
                'sector_id': sector_row[0],
                'name': sector_row[1],
                'description': sector_row[2],
                'metrics': {}
            }

            # Получаем устройства в секторе
            db.cursor.execute("""
                SELECT d.device_id 
                FROM devices d 
                WHERE d.sector_id = %s
            """, (sector['sector_id'],))
            device_ids = [row[0] for row in db.cursor.fetchall()]

            if device_ids:
                # Получаем последние показания для каждого параметра
                db.cursor.execute(f"""
                    SELECT a.data_name, a.data_value 
                    FROM actual_data a
                    WHERE a.data_device_id IN ({','.join(['%s']*len(device_ids))})
                    GROUP BY a.data_name
                    ORDER BY a.data_timestamp DESC
                """, device_ids)
                metrics = {row[0]: row[1] for row in db.cursor.fetchall()}
                sector['metrics'] = dict(sorted(metrics.items(), key=lambda item: item[0]))

            sectors.append(sector)

        return render_template('dashboard.html',
                             sectors=sectors,
                             devices_total=devices_total,
                             active_rules=active_rules)
    
    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500

def get_sectors_with_stats():
    """Возвращает секторы с дополнительной статистикой"""
    try:
        db.cursor.execute("""
            SELECT s.sector_id, s.name, s.description, 
                   COUNT(d.device_id) as device_count,
                   MAX(a.data_timestamp) as last_activity
            FROM sectors s
            LEFT JOIN devices d ON s.sector_id = d.sector_id
            LEFT JOIN actual_data a ON d.device_id = a.data_device_id
            GROUP BY s.sector_id
        """)
        columns = [col[0] for col in db.cursor.description]
        return [dict(zip(columns, row)) for row in db.cursor.fetchall()]
    except Exception as e:
        return []

@app.route('/sectors', methods=['GET', 'POST'])
@login_required
def manage_sectors():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('Название сектора не может быть пустым', 'error')
            return redirect(url_for('manage_sectors'))
            
        try:
            # Проверка на существующее имя
            db.cursor.execute(
                "SELECT sector_id FROM sectors WHERE LOWER(name) = LOWER(%s)",
                (name,)
            )
            if db.cursor.fetchone():
                flash('Сектор с таким названием уже существует', 'error')
                return redirect(url_for('manage_sectors'))

            # Создание нового сектора
            db.cursor.execute(
                "INSERT INTO sectors (name, description) VALUES (%s, %s)",
                (name, description)
            )
            db.cnx.commit()
            flash('Сектор успешно создан', 'success')
            
        except mysql.connector.Error as err:
            db.cnx.rollback()
            flash(f'Ошибка базы данных: {err.msg}', 'error')
        
        return redirect(url_for('manage_sectors'))

    # Получение списка секторов
    try:
        db.cursor.execute("""
            SELECT s.sector_id, 
                   s.name, 
                   s.description,
                   COUNT(d.device_id) AS device_count
            FROM sectors s
            LEFT JOIN devices d ON s.sector_id = d.sector_id
            GROUP BY s.sector_id
            ORDER BY s.sector_id
        """)
        columns = [col[0] for col in db.cursor.description]
        sectors = [dict(zip(columns, row)) for row in db.cursor.fetchall()]
        
    except mysql.connector.Error as err:
        flash(f'Ошибка загрузки секторов: {err.msg}', 'error')
        sectors = []

    return render_template('sectors.html', sectors=sectors)

@app.route('/sectors/update/<int:sector_id>', methods=['POST'])
@login_required
def update_sector(sector_id):
    new_name = request.form.get('name').strip()
    new_description = request.form.get('description').strip()
    
    if not new_name:
        flash('Название сектора не может быть пустым', 'error')
        return redirect(url_for('manage_sectors'))

    try:
        db.cursor.execute(
            "SELECT sector_id FROM sectors WHERE LOWER(name) = LOWER(%s) AND sector_id != %s",
            (new_name, sector_id)
        )
        if db.cursor.fetchone():
            flash('Сектор с таким названием уже существует', 'error')
            return redirect(url_for('manage_sectors'))

        db.cursor.execute(
            "UPDATE sectors SET name = %s, description = %s WHERE sector_id = %s",
            (new_name, new_description, sector_id)
        )
        flash('Сектор успешно обновлен', 'success')
        
    except mysql.connector.Error as err:
        flash(f'Ошибка базы данных: {err.msg}', 'error')
    
    return redirect(url_for('manage_sectors'))

@app.route('/update-device-sector', methods=['POST'])
@login_required
def update_device_sector():
    try:
        data = request.get_json()
        device_id = int(data['device_id'])
        sector_id = data['sector_id']

        # Обработка отвязки
        if sector_id in ["", None]:
            success = db.unassign_device_from_sector(device_id)
        else:
            # Проверка и назначение сектора
            sector_id = int(sector_id)
            success = db.assign_device_to_sector(device_id, sector_id)

        return jsonify({'success': success})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/sectors/delete/<int:sector_id>', methods=['POST'])
@login_required
def delete_sector(sector_id):
    db.remove_sector(sector_id)
    return redirect(url_for('manage_sectors'))

@app.route('/devices', methods=['GET', 'POST'])
@login_required
def manage_devices():
    if request.method == 'POST':
        # Обработка изменения сектора устройства
        device_id = request.form.get('device_id')
        new_sector_id = request.form.get('sector_id')
        if device_id and new_sector_id:
            db.assign_device_to_sector(int(device_id), int(new_sector_id))
    
    # Получение устройств и секторов
    db.cursor.execute("SELECT * FROM devices")
    devices = [dict(zip(['device_id', 'device_uuid', 'device_name', 'sector_id', 'device_last_communication'], row)) 
              for row in db.cursor.fetchall()]
    
    db.cursor.execute("SELECT * FROM sectors")
    sectors = [dict(zip(['sector_id', 'name', 'description'], row)) 
              for row in db.cursor.fetchall()]
    
    return render_template('devices.html', devices=devices, sectors=sectors)

@app.route('/rules', methods=['GET', 'POST'])
@login_required
def manage_rules():
    if request.method == 'POST':
        data_id = request.form.get('data_id')
        condition = request.form.get('condition')
        value = request.form.get('value')
        device_id = request.form.get('device_id')
        command = request.form.get('command')
        delay = request.form.get('delay', '10')  # Значение по умолчанию
        
        if all([data_id, condition, value, device_id, command, delay]):
            # Формируем сообщение в формате "команда~задержка"
            rule_message = f"{command}~{delay}"
            
            db.cursor.execute("""
                INSERT INTO rules (
                    rule_data_id, 
                    rule_condition, 
                    rule_value, 
                    rule_device_id, 
                    rule_message
                ) VALUES (%s, %s, %s, %s, %s)
            """, (data_id, condition, value, device_id, rule_message))
    
    db.cursor.execute("""
        SELECT 
            a.data_id, 
            a.data_name, 
            s.name AS sector_name 
        FROM actual_data a
        JOIN devices d ON a.data_device_id = d.device_id
        JOIN sectors s ON d.sector_id = s.sector_id
    """)
    available_data = [dict(zip(['data_id', 'data_name', 'sector_name'], row)) 
                     for row in db.cursor.fetchall()]
    
    db.cursor.execute("""
        SELECT 
            d.device_id, 
            d.device_name,
            s.name AS sector_name
        FROM devices d
        LEFT JOIN sectors s ON d.sector_id = s.sector_id
    """)
    actuators = [dict(zip(['device_id', 'device_name', 'sector_name'], row)) 
                for row in db.cursor.fetchall()]
    
    # Получение правил с названиями секторов
    db.cursor.execute("""
        SELECT 
            r.rule_id,
            r.rule_condition,
            r.rule_value,
            r.rule_device_id,
            r.rule_message,
            r.is_active,
            a.data_name,
            d.device_name,
            s.name AS sector_name
        FROM rules r
        JOIN actual_data a ON r.rule_data_id = a.data_id
        JOIN devices d ON r.rule_device_id = d.device_id
        JOIN sectors s ON d.sector_id = s.sector_id
    """)
    columns = [col[0] for col in db.cursor.description]
    rules = [dict(zip(columns, row)) for row in db.cursor.fetchall()]
    
    return render_template('rules.html', 
                         rules=rules,
                         available_data=available_data,
                         actuators=actuators)

@app.route('/rules/toggle/<int:rule_id>', methods=['POST'])
@login_required
def toggle_rule(rule_id):
    db.cursor.execute("""
        UPDATE rules 
        SET is_active = NOT is_active 
        WHERE rule_id = %s
    """, (rule_id,))
    return redirect(url_for('manage_rules'))

@app.route('/rules/delete/<int:rule_id>', methods=['POST'])
@login_required
def delete_rule(rule_id):
    db.remove_rule(rule_id)
    return redirect(url_for('manage_rules'))

def check_subscription(email):
    """Заглушка проверки подписки (реализуйте свою логику)"""
    return True

@app.template_filter('get_condition_symbol')
def get_condition_symbol(condition: int) -> str:
    """Преобразует числовой код условия в символ"""
    symbols = {
        1: '>',
        2: '<', 
        3: '==',
        4: '!='
    }
    return symbols.get(condition, 'UNKNOWN')

@app.route('/history')
@login_required
def history():
    try:
        # Получаем список доступных параметров
        db.cursor.execute("""
            SELECT DISTINCT data_name 
            FROM data_history
            ORDER BY data_name
        """)
        available_params = [row[0] for row in db.cursor.fetchall()]

        # Получаем список секторов
        db.cursor.execute("SELECT sector_id, name FROM sectors")
        sectors = [dict(zip(['id', 'name'], row)) for row in db.cursor.fetchall()]

        # Фильтры из GET-параметров
        selected_param = request.args.get('param', available_params[0] if available_params else '')
        selected_sector = request.args.get('sector', 'all')
        time_range = request.args.get('range', '24h')

        # Формируем запрос данных
        query = """
            SELECT dh.data_timestamp, dh.data_value, d.device_name, s.name
            FROM data_history dh
            JOIN devices d ON dh.data_device_id = d.device_id
            LEFT JOIN sectors s ON d.sector_id = s.sector_id
            WHERE dh.data_name = %s
        """
        params = [selected_param]

        if selected_sector != 'all':
            query += " AND s.sector_id = %s"
            params.append(selected_sector)

        # Добавляем временной фильтр
        if time_range == '24h':
            query += " AND dh.data_timestamp >= NOW() - INTERVAL 1 DAY"
        elif time_range == '7d':
            query += " AND dh.data_timestamp >= NOW() - INTERVAL 7 DAY"

        query += " ORDER BY dh.data_timestamp ASC"

        db.cursor.execute(query, params)
        history_data = [
            {
                'timestamp': row[0],
                'value': row[1],
                'device': row[2],
                'sector': row[3]
            }
            for row in db.cursor.fetchall()
        ]

        return render_template(
            'history.html',
            params=available_params,
            sectors=sectors,
            selected_param=selected_param,
            selected_sector=selected_sector,
            time_range=time_range,
            history_data=history_data
        )

    except Exception as e:
        return f"Ошибка загрузки истории: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
    make_response,
)
import json
import socket
import struct
from threading import Lock
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from DBMS_worker import DBMS_worker
from encryption import encrypt, decrypt
from config import REMOTE_SERV_ADDR, REMOTE_SERV_PORT

app = Flask(__name__)
app.secret_key = "super secret key"
app.config["SUBSCRIPTION_SERVER"] = (REMOTE_SERV_ADDR, REMOTE_SERV_PORT)
app.config["SOCKET_TIMEOUT"] = 5
socket_lock = Lock()

db = DBMS_worker("localhost", "root", "123", "GreenHouseLocal")
if not db.created:
    raise RuntimeError(f"Ошибка подключения к БД: {db.error}")


def login_required(f):
    """
    Декоратор для проверки аутентификации и активной подписки
    
    Args:
        f (function): Оборачиваемая функция
        
    Returns:
        function: Декорированная функция с проверкой доступа
        
    Raises:
        Redirect: Перенаправление на login при отсутствии доступа
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))

        email = session.get("user_email")
        if not email or not check_subscription(email).get("active", False):
            session.clear()
            flash("Доступ запрещен: неактивная подписка или ошибка проверки", "error")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function


@app.template_filter("datetime_format")
def datetime_format(value, format="%d.%m.%Y %H:%M"):
    """
    Фильтр для форматирования даты в шаблонах Jinja2
    
    Args:
        value (int/datetime): Временная метка или объект datetime
        format (str): Строка формата даты
        
    Returns:
        str: Отформатированная дата или пустая строка при ошибке
    """
    if value is None:
        return ""

    if isinstance(value, int):
        dt = datetime.fromtimestamp(value)
    elif isinstance(value, datetime):
        dt = value
    else:
        return ""

    return dt.strftime(format)


@app.route("/", methods=["GET"])
@login_required
def index():
    """Главная страница с перенаправлением на dashboard"""
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Обработка входа пользователя
    
    Methods:
        POST: Проверка учетных данных и подписки
        GET: Отображение формы входа
        
    Returns:
        render_template: Страница входа с ошибкой при необходимости
        redirect: Перенаправление на dashboard при успешной аутентификации
    """
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = db.get_user_by_email(email)
        if not user:
            return render_template("login.html", error="Пользователь не найден")

        if not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Неверный пароль")
        
        subscription = check_subscription(email)

        if not subscription.get("active", False):
            return render_template("login.html", error="Подписка не активна")

        session["logged_in"] = True
        session["user_email"] = email
        session["sub_until"] = subscription.get("until").split("T")[0].replace("-", ".")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """
    Завершение сессии пользователя
    
    Returns:
        redirect: Перенаправление на страницу входа
    """
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """
    Главная информационная панель с метриками
    
    Returns:
        render_template: Страница dashboard с данными секторов
        str: Сообщение об ошибке при проблемах с БД
        
    Raises:
        500: При внутренних ошибках сервера
    """
    try:
        db.cursor.execute("SELECT COUNT(*) FROM devices")
        devices_total = db.cursor.fetchone()[0]

        db.cursor.execute("SELECT COUNT(*) FROM rules WHERE is_active = TRUE")
        active_rules = db.cursor.fetchone()[0]

        sectors = []
        db.cursor.execute("SELECT * FROM sectors")
        for sector_row in db.cursor.fetchall():
            sector = {
                "sector_id": sector_row[0],
                "name": sector_row[1],
                "description": sector_row[2],
                "metrics": {},
            }

            db.cursor.execute(
                """
                SELECT d.device_id 
                FROM devices d 
                WHERE d.sector_id = %s
            """,
                (sector["sector_id"],),
            )
            device_ids = [row[0] for row in db.cursor.fetchall()]

            if device_ids:
                db.cursor.execute(
                    f"""
                    SELECT a.data_name, a.data_value 
                    FROM actual_data a
                    WHERE a.data_device_id IN ({','.join(['%s']*len(device_ids))})
                    GROUP BY a.data_name
                    ORDER BY a.data_timestamp DESC
                """,
                    device_ids,
                )
                metrics = {row[0]: row[1] for row in db.cursor.fetchall()}
                sector["metrics"] = dict(
                    sorted(metrics.items(), key=lambda item: item[0])
                )

            sectors.append(sector)

        response = make_response(
            render_template(
                "dashboard.html",
                sectors=sectors,
                devices_total=devices_total,
                active_rules=active_rules,
            )
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    except Exception as e:
        return f"Ошибка базы данных: {str(e)}", 500


def get_sectors_with_stats():
    """
    Получение списка секторов с расширенной статистикой
    
    Returns:
        list[dict]: Список секторов с полями:
            - sector_id (int)
            - name (str)
            - description (str)
            - device_count (int)
            - last_activity (datetime)
    """
    try:
        db.cursor.execute(
            """
            SELECT s.sector_id, s.name, s.description, 
                   COUNT(d.device_id) as device_count,
                   MAX(a.data_timestamp) as last_activity
            FROM sectors s
            LEFT JOIN devices d ON s.sector_id = d.sector_id
            LEFT JOIN actual_data a ON d.device_id = a.data_device_id
            GROUP BY s.sector_id
        """
        )
        columns = [col[0] for col in db.cursor.description]
        return [dict(zip(columns, row)) for row in db.cursor.fetchall()]
    except Exception as e:
        return []


@app.route("/sectors", methods=["GET", "POST"])
@login_required
def manage_sectors():
    """
    Управление секторами теплицы
    
    Methods:
        POST: Создание нового сектора
        GET: Отображение списка секторов
        
    Returns:
        render_template: Страница управления секторами
        redirect: Обновление страницы после создания сектора
        
    Raises:
        DatabaseError: При ошибках работы с БД
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Название сектора не может быть пустым", "error")
            return redirect(url_for("manage_sectors"))

        try:
            db.cursor.execute(
                "SELECT sector_id FROM sectors WHERE LOWER(name) = LOWER(%s)", (name,)
            )
            if db.cursor.fetchone():
                flash("Сектор с таким названием уже существует", "error")
                return redirect(url_for("manage_sectors"))

            db.cursor.execute(
                "INSERT INTO sectors (name, description) VALUES (%s, %s)",
                (name, description),
            )
            db.cnx.commit()
            flash("Сектор успешно создан", "success")

        except mysql.connector.Error as err:
            db.cnx.rollback()
            flash(f"Ошибка базы данных: {err.msg}", "error")

        return redirect(url_for("manage_sectors"))

    try:
        db.cursor.execute(
            """
            SELECT s.sector_id, 
                   s.name, 
                   s.description,
                   COUNT(d.device_id) AS device_count
            FROM sectors s
            LEFT JOIN devices d ON s.sector_id = d.sector_id
            GROUP BY s.sector_id
            ORDER BY s.sector_id
        """
        )
        columns = [col[0] for col in db.cursor.description]
        sectors = [dict(zip(columns, row)) for row in db.cursor.fetchall()]

    except mysql.connector.Error as err:
        flash(f"Ошибка загрузки секторов: {err.msg}", "error")
        sectors = []

    return render_template("sectors.html", sectors=sectors)


@app.route("/sectors/update/<int:sector_id>", methods=["POST"])
@login_required
def update_sector(sector_id):
    """
    Обновление информации о секторе
    
    Args:
        sector_id (int): Идентификатор обновляемого сектора
        
    Returns:
        redirect: Перенаправление на страницу управления секторами
        
    Raises:
        DatabaseError: При ошибках валидации или работы с БД
    """
    new_name = request.form.get("name").strip()
    new_description = request.form.get("description").strip()

    if not new_name:
        flash("Название сектора не может быть пустым", "error")
        return redirect(url_for("manage_sectors"))

    try:
        db.cursor.execute(
            "SELECT sector_id FROM sectors WHERE LOWER(name) = LOWER(%s) AND sector_id != %s",
            (new_name, sector_id),
        )
        if db.cursor.fetchone():
            flash("Сектор с таким названием уже существует", "error")
            return redirect(url_for("manage_sectors"))

        db.cursor.execute(
            "UPDATE sectors SET name = %s, description = %s WHERE sector_id = %s",
            (new_name, new_description, sector_id),
        )
        flash("Сектор успешно обновлен", "success")

    except mysql.connector.Error as err:
        flash(f"Ошибка базы данных: {err.msg}", "error")

    return redirect(url_for("manage_sectors"))


@app.route("/update-device-sector", methods=["POST"])
@login_required
def update_device_sector():
    """
    Обновление привязки устройства к сектору (AJAX)
    
    Returns:
        jsonify: Результат операции в формате JSON:
            {'success': bool, 'error': str (опционально)}
    """
    try:
        data = request.get_json()
        device_id = int(data["device_id"])
        sector_id = data["sector_id"]

        if sector_id in ["", None]:
            success = db.unassign_device_from_sector(device_id)
        else:
            sector_id = int(sector_id)
            success = db.assign_device_to_sector(device_id, sector_id)

        return jsonify({"success": success})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/sectors/delete/<int:sector_id>", methods=["POST"])
@login_required
def delete_sector(sector_id):
    """
    Удаление сектора
    
    Args:
        sector_id (int): Идентификатор удаляемого сектора
        
    Returns:
        redirect: Перенаправление на страницу управления секторами
    """
    db.remove_sector(sector_id)
    return redirect(url_for("manage_sectors"))


@app.route("/devices", methods=["GET", "POST"])
@login_required
def manage_devices():
    """
    Управление устройствами теплицы
    
    Returns:
        render_template: Страница со списком устройств
    """
    if request.method == "POST":
        device_id = request.form.get("device_id")
        new_sector_id = request.form.get("sector_id")
        if device_id and new_sector_id:
            db.assign_device_to_sector(int(device_id), int(new_sector_id))

    db.cursor.execute("SELECT * FROM devices")
    devices = [
        dict(
            zip(
                [
                    "device_id",
                    "device_uuid",
                    "device_name",
                    "sector_id",
                    "device_last_communication",
                ],
                row,
            )
        )
        for row in db.cursor.fetchall()
    ]

    db.cursor.execute("SELECT * FROM sectors")
    sectors = [
        dict(zip(["sector_id", "name", "description"], row))
        for row in db.cursor.fetchall()
    ]

    response = make_response(
        render_template(
            "devices.html",
            devices=devices,
            sectors=sectors,
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/devices/delete/<int:device_id>", methods=["POST"])
@login_required
def delete_device(device_id):
    """
    Удаление устройства
    
    Args:
        device_id (int): Идентификатор удаляемого устройства
        
    Returns:
        redirect: Перенаправление на страницу управления устройствами
    """
    try:
        success = db.remove_device(device_id)
        if success:
            flash("Устройство успешно удалено", "success")
        else:
            flash("Устройство не найдено", "error")
    except Exception as e:
        flash(f"Ошибка удаления: {str(e)}", "error")
    return redirect(url_for("manage_devices"))


@app.route("/rules", methods=["GET", "POST"])
@login_required
def manage_rules():
    """
    Управление правилами автоматизации
    
    Returns:
        render_template: Страница с таблицей правил и формами управления
    """
    if request.method == "POST":
        data_id = request.form.get("data_id")
        condition = request.form.get("condition")
        value = request.form.get("value")
        device_id = request.form.get("device_id")
        command = request.form.get("command")  # "start"
        load = request.form.get("load")        # число от пользователя
        delay = request.form.get("delay", "10")

        if all([data_id, condition, value, device_id, command, load, delay]):
            rule_message = f"{command}:{load}~{delay}"

            db.cursor.execute(
                """
                INSERT INTO rules (
                    rule_data_id, 
                    rule_condition, 
                    rule_value, 
                    rule_device_id, 
                    rule_message
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (data_id, condition, value, device_id, rule_message),
            )

    db.cursor.execute(
        """
        SELECT 
            a.data_id, 
            a.data_name, 
            s.name AS sector_name 
        FROM actual_data a
        JOIN devices d ON a.data_device_id = d.device_id
        JOIN sectors s ON d.sector_id = s.sector_id
    """
    )
    available_data = [
        dict(zip(["data_id", "data_name", "sector_name"], row))
        for row in db.cursor.fetchall()
    ]

    db.cursor.execute(
        """
        SELECT 
            d.device_id, 
            d.device_name,
            s.name AS sector_name
        FROM devices d
        LEFT JOIN sectors s ON d.sector_id = s.sector_id
    """
    )
    actuators = [
        dict(zip(["device_id", "device_name", "sector_name"], row))
        for row in db.cursor.fetchall()
    ]

    db.cursor.execute(
        """
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
    """
    )
    columns = [col[0] for col in db.cursor.description]
    rules = [dict(zip(columns, row)) for row in db.cursor.fetchall()]

    return render_template(
        "rules.html", rules=rules, available_data=available_data, actuators=actuators
    )


@app.route("/rules/toggle/<int:rule_id>", methods=["POST"])
@login_required
def toggle_rule(rule_id):
    """
    Активация/деактивация правила
    
    Args:
        rule_id (int): Идентификатор правила
        
    Returns:
        redirect: Перенаправление на страницу управления правилами
    """
    db.cursor.execute(
        """
        UPDATE rules 
        SET is_active = NOT is_active 
        WHERE rule_id = %s
    """,
        (rule_id,),
    )
    return redirect(url_for("manage_rules"))


@app.route("/rules/delete/<int:rule_id>", methods=["POST"])
@login_required
def delete_rule(rule_id):
    """
    Удаление правила автоматизации
    
    Args:
        rule_id (int): Идентификатор удаляемого правила
        
    Returns:
        redirect: Перенаправление на страницу управления правилами
    """
    db.remove_rule(rule_id)
    return redirect(url_for("manage_rules"))


def check_subscription(email: str) -> bool:
    """
    Проверка статуса подписки через удаленный сервер
    
    Args:
        email (str): Email пользователя для проверки
        
    Returns:
        dict: Результат проверки:
            {'active': bool, 'until': datetime (опционально)}
    """
    encrypted_data = encrypt(json.dumps({"email": email}))

    try:
        with socket_lock:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(app.config["SOCKET_TIMEOUT"])
                sock.connect(app.config["SUBSCRIPTION_SERVER"])

                sock.sendall(struct.pack("!I", len(encrypted_data)))
                sock.sendall(encrypted_data)

                length_data = sock.recv(4)
                if len(length_data) != 4:
                    return False

                response_length = struct.unpack("!I", length_data)[0]
                response = sock.recv(response_length)

                decrypted = decrypt(response)
                return json.loads(decrypted)

    except (socket.timeout, ConnectionRefusedError, Exception) as e:
        app.logger.error(f"Ошибка проверки подписки: {str(e)}")
        return {"active": False, "sub_until": None}


@app.template_filter("get_condition_symbol")
def get_condition_symbol(condition: int) -> str:
    """
    Преобразование кода условия в символ
    
    Args:
        condition (int): Числовой код условия
        
    Returns:
        str: Символьное представление условия
    """
    symbols = {1: ">", 2: "<", 3: "==", 4: "!="}
    return symbols.get(condition, "UNKNOWN")


@app.route("/history")
@login_required
def history():
    """
    Отображение исторических данных
    
    Returns:
        render_template: Страница с графиками и фильтрами
    """
    try:
        db.cursor.execute(
            """
            SELECT DISTINCT data_name 
            FROM data_history
            ORDER BY data_name
        """
        )
        available_params = [row[0] for row in db.cursor.fetchall()]

        db.cursor.execute("SELECT sector_id, name FROM sectors")
        sectors = [dict(zip(["id", "name"], row)) for row in db.cursor.fetchall()]

        selected_param = request.args.get(
            "param", available_params[0] if available_params else ""
        )
        selected_sector = request.args.get("sector", "all")
        time_range = request.args.get("range", "24h")

        query = """
            SELECT 
                s.sector_id,
                s.name as sector_name,
                UNIX_TIMESTAMP(dh.data_timestamp) as timestamp,
                dh.data_value,
                d.device_name
            FROM data_history dh
            JOIN devices d ON dh.data_device_id = d.device_id
            LEFT JOIN sectors s ON d.sector_id = s.sector_id
            WHERE dh.data_name = %s
        """
        params = [selected_param]

        if selected_sector != "all":
            query += " AND s.sector_id = %s"
            params.append(selected_sector)

        if time_range == "24h":
            query += " AND dh.data_timestamp >= NOW() - INTERVAL 1 DAY"
        elif time_range == "7d":
            query += " AND dh.data_timestamp >= NOW() - INTERVAL 7 DAY"

        query += " ORDER BY dh.data_timestamp ASC"

        db.cursor.execute(query, params)
        results = db.cursor.fetchall()

        history_data = []
        sector_data = defaultdict(list)

        for row in results:
            history_data.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        row[2]
                    ),
                    "value": row[3],
                    "device": row[4],
                    "sector": row[1],
                }
            )

            sector_id = row[0] or "unassigned"
            sector_data[sector_id].append(
                {
                    "sector_id": sector_id,
                    "sector_name": row[1] or "Не назначено",
                    "timestamp": datetime.fromtimestamp(row[2]),
                    "value": row[3],
                    "device": row[4],
                }
            )

        history_json = {}
        for sector_id, entries in sector_data.items():
            history_json[str(sector_id)] = [
                {
                    "timestamp": entry["timestamp"].isoformat(),
                    "value": entry["value"],
                    "device": entry["device"],
                }
                for entry in entries
            ]

        if not history_data:
            flash("Нет данных для выбранных параметров", "info")

        return render_template(
            "history.html",
            params=available_params,
            sectors=sectors,
            selected_param=selected_param,
            selected_sector=selected_sector,
            time_range=time_range,
            sector_data=sector_data,
            history_json=json.dumps(history_json),
            history_data=history_data,
        )

    except Exception as e:
        return f"Ошибка загрузки истории: {str(e)}", 500


def validate_credentials(email: str, password: str) -> bool:
    """
    Валидация учетных данных пользователя
    
    Args:
        email (str): Email пользователя
        password (str): Пароль в открытом виде
        
    Returns:
        bool: Результат проверки
    """
    try:
        db.cursor.execute("SELECT password_hash FROM users WHERE email = %s", (email,))
        result = db.cursor.fetchone()
        if result and check_password_hash(result[0], password):
            return True
        return False
    except Exception as e:
        app.logger.error(f"Auth error: {str(e)}")
        return False


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Регистрация нового пользователя
    
    Returns:
        render_template: Форма регистрации с сообщениями об ошибках
        redirect: Перенаправление на вход после успешной регистрации
    """
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not all([email, password, confirm_password]):
            return render_template("register.html", error="Все поля обязательны")

        if password != confirm_password:
            return render_template("register.html", error="Пароли не совпадают")

        if db.get_user_by_email(email):
            return render_template("register.html", error="Пользователь уже существует")

        password_hash = generate_password_hash(password)

        if db.add_user(email, password_hash):
            return redirect(url_for("login"))

        return render_template("register.html", error="Ошибка регистрации")

    return render_template("register.html")


if __name__ == "__main__":
    app.run(debug=True)

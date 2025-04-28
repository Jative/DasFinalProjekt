import sqlite3
from flask import Flask, render_template, session, redirect, url_for, request
from datetime import datetime


def main() -> None:
    app = Flask(__name__, static_folder='./static/')

    @app.route("/")
    def index():
        if "logined" in session:
            iot_data = {
                'temperature': {
                    'value': 23.4,
                    'unit': '°C',
                    'icon': 'fa-thermometer-half',
                    'display_name': 'Temperatur',
                    'timestamp': datetime.now()
                },
                'humidity': {
                    'value': 45.6,
                    'unit': '%',
                    'icon': 'fa-tint',
                    'display_name': 'Luftfeuchtigkeit',
                    'timestamp': datetime.now()
                },
                'pressure': {
                    'value': 1013.2,
                    'unit': 'hPa',
                    'icon': 'fa-tachometer-alt',
                    'display_name': 'Luftdruck',
                    'timestamp': datetime.now()
                }
            }
            
            return render_template(
                'index.html',
                title='Главная',
                iot_data=iot_data,
                last_update=datetime.now()
            )
        else:
            return redirect(url_for("login"))

    @app.route("/config")
    def config():
        if "logined" in session:
            return render_template("config.html", title='Конфигурация')
        else:
            return redirect(url_for("login"))

    @app.route("/about")
    def about():
        if "logined" in session:
            return render_template("about.html", title='О нас')
        else:
            return redirect(url_for("login"))
    
    @app.route("/login", methods=['GET', 'POST'])
    def login():
        if "logined" in session:
            return redirect(url_for("index"))
        else:
            if request.method == 'POST':
                session["logined"] = True
                return redirect(url_for("index"))
            return render_template('login.html', title='Вход')

    app.secret_key = 'super secret key'
    app.debug = True
    
    app.run()


if __name__ == "__main__":
    main()
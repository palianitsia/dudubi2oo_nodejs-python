import sys
import time
import re
import os
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPlainTextEdit
from bs4 import BeautifulSoup
import requests
from qt_material import apply_stylesheet
import random
from threading import Event, Lock
import socket
import subprocess
import threading

class SocketServer:
    def __init__(self, host='127.0.0.1', port=65432):
        self.host = host
        self.port = port
        self.timer_nodejs = None
        self.server_socket = None
        self.running = True

    def start(self):
        """Avvia il server socket"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"Socket server in ascolto su {self.host}:{self.port}")
        threading.Thread(target=self.accept_connections, daemon=True).start()

    def accept_connections(self):
        """Accetta connessioni dai client"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                print(f"Connessione accettata da {client_address}")
                threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
            except Exception as e:
                print(f"Errore durante l'accettazione della connessione: {str(e)}")

    def handle_client(self, client_socket):
        """Gestisce il client socket"""
        try:
            while self.running:
                data = client_socket.recv(1024).decode().strip()
                if not data:
                    break
                print(f"Timer ricevuto da Node.js: {data}")
                self.timer_nodejs = int(data)  # Salva il timer ricevuto da Node.js
        except Exception as e:
            print(f"Errore durante la gestione del client: {str(e)}")
        finally:
            client_socket.close()

    def stop(self):
        """Ferma il server socket"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()

socket_server = SocketServer()
socket_server.start()

def check_and_bid(timer_python, slider_value):
    global socket_server
    timer_nodejs = socket_server.timer_nodejs

    timer_minore = min(timer_python, timer_nodejs) if timer_nodejs is not None else timer_python

    print(f"Timer Python: {timer_python}, Timer Node.js: {timer_nodejs}, Timer minore: {timer_minore}")

    if timer_minore <= slider_value:
        print("Invia puntata manuale!")

def send_parameters_to_nodejs(self):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect(('127.0.0.1', 65432))
            message = f"{self.domain}|{self.id_asta}"
            client_socket.sendall(message.encode())
            self.log_signal.emit(f"{self.TIME()} Parametri inviati a Node.js: domain={self.domain}, id_asta={self.id_asta}")
    except Exception as e:
        self.log_signal.emit(f"{self.TIME()} Errore durante l'invio dei parametri: {str(e)}")

class IdleCheckBypass(QThread):
    def __init__(self, session, domain, stop_event):
        super().__init__()
        self.session = session
        self.domain = domain
        self.stop_event = stop_event
        self.url = f"https://{domain}.bidoo.com/closed_auctions.php"

    def run(self):
        while not self.stop_event.is_set():
            try:
                delay = random.randint(240, 540)
                self.stop_event.wait(delay)
                
                if not self.stop_event.is_set():
                    response = self.session.get(self.url)
                    if response.status_code != 200:
                        print(f"Idle check bypass failed with status {response.status_code}")
            except Exception as e:
                print(f"Error in idle check bypass: {str(e)}")

class BidooBot(QThread):
    update_signal = pyqtSignal(str, str, str, str, str, str)
    log_signal = pyqtSignal(str)
    reset_signal = pyqtSignal()
    update_timer_signal = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False
        self.session = requests.Session()  # Sessione HTTP globale
        self.domain = "it"
        self.id_asta = ""
        self.username = ""
        self.saldo = 0
        self.current_slider_value = 0
        self.slider_timer = 0
        self.min_price = 0
        self.max_price = 0
        self.use_range = False
        self.puntate_usate = 0
        self.update_timer_signal.connect(self.set_slider_value)
        self.accounts_list = []
        self.current_account_index = 0
        self.idle_check_stop_event = Event()
        self.idle_check_thread = None
        node_process = subprocess.Popen(["node", "bot0.js"])

    def initialize_session(self):
        """Inizializza la sessione HTTP globale"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'accept-language': "es" if self.domain == "es" else "it",
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Connection': 'keep-alive'
        }
        self.session.headers.update(headers)
 
    def make_request(self, method, url, **kwargs):
        """Wrapper per effettuare richieste HTTP thread-safe"""
        with self.session_lock:
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                self.log_signal.emit(f"{self.TIME()} Errore nella richiesta HTTP: {str(e)}")
                return None
 
    def start_idle_check_bypass(self):
        """Start the idle check bypass thread"""
        if not self.idle_check_thread or not self.idle_check_thread.isRunning():
            self.idle_check_stop_event.clear()
            self.idle_check_thread = IdleCheckBypass(
                self.session, 
                self.domain, 
                self.idle_check_stop_event
            )
            self.idle_check_thread.start()
            
    def stop_idle_check_bypass(self):
        """Stop the idle check bypass thread"""
        if self.idle_check_thread and self.idle_check_thread.isRunning():
            self.idle_check_stop_event.set()
            self.idle_check_thread.quit()
            self.idle_check_thread.wait()

    def close_session(self):
        """Chiude la sessione HTTP globale"""
        self.session.close()

    def shutdown(self):
        """Properly close all resources"""
        self.stop_idle_check_bypass()
        self.session.close()
        self.session = None

    def run(self):
        self.running = True
        try:
            self.initialize_session()
            self.start_idle_check_bypass()
            success = self.get_auction_info()
            if not success:
                self.log_signal.emit(f"{self.TIME()}")
        except Exception as e:
            self.log_signal.emit(f"{self.TIME()} Error in bot thread: {str(e)}")
        finally:
            self.stop_idle_check_bypass()
            self.running = False

    def stop(self):
        """Stop the bot safely"""
        self.running = False

    def TIME(self):
        return datetime.now().strftime("[%H:%M:%S]")

    def get_domain(self):
        return self.domain

    def login_via_api(self, username, password, use_es):
        self.domain = "es" if use_es else "it"
        login_url = f"https://{self.domain}.bidoo.com/userlogin.php"
        logged_user_url = f"https://{self.domain}.bidoo.com/ajax/get_logged_user.php"
        payload = {
            'email': username,
            'pswd': password,
            'recaptcha_response': '',
            'ctype': '10'
        }
        try:
            self.initialize_session()
            login_response = self.session.post(login_url, data=payload)
            if login_response.status_code != 200:
                self.log_signal.emit(f"{self.TIME()} Errore durante il login: Codice di stato {login_response.status_code}")
                return False
            
            logged_user_response = self.session.get(logged_user_url)
            if logged_user_response.status_code == 200:
                logged_user_data = logged_user_response.json()
                if logged_user_data.get("is_valid"):
                    self.username = logged_user_data.get("username", "UNKNOWN")
                    self.get_saldo()
                    return True
        except Exception as e:
            self.log_signal.emit(f"{self.TIME()} Errore durante il login o la verifica dello stato: {str(e)}")
        return False

    def login_via_dess(self, dess_cookie, use_es):
        self.domain = "es" if use_es else "it"
        domain_url = f"https://{self.domain}.bidoo.com"
        user_url = f"{domain_url}/ajax/get_logged_user.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'accept-language': "es" if self.domain == "es" else "it",
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Connection': 'keep-alive'
        }
        retry_delay = 2 
        timeout = 3 

        try:
            self.session = requests.Session()
            self.session.headers.update(headers)

            while True:
                try:
                    response = self.session.get(user_url, timeout=timeout)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("is_valid"):
                            self.username = data.get("username", "UNKNOWN")
                            self.get_saldo()
                            return True
                    else:
                        self.log_signal.emit(f"{self.TIME()} ❌ HTTP {response.status_code} durante il login DESS")
                except requests.Timeout:
                    self.log_signal.emit(f"{self.TIME()} ⏱ Timeout durante il login DESS")
                except requests.ConnectionError:
                    self.log_signal.emit(f"{self.TIME()} ⚡ Errore di connessione durante il login DESS")
                except Exception as e:
                    self.log_signal.emit(f"{self.TIME()} ‼ Errore durante il login DESS: {str(e)}")

                time.sleep(retry_delay)

        except Exception as e:
            self.log_signal.emit(f"{self.TIME()} Errore durante il login DESS: {str(e)}")
            if self.session:
                self.session.close()
        return False

    def login_via_accounts_txt(self, use_es=False):
        accounts_file = "accounts.txt"
        if not os.path.exists(accounts_file):
            self.log_signal.emit(f"{self.TIME()} File 'accounts.txt' non trovato.")
            return False

        retry_delay = 2 
        timeout = 5 

        try:
            with open(accounts_file, "r", encoding="utf-8") as file:
                all_lines = file.readlines()
                self.accounts_list = [
                    line.strip() for line in all_lines[3:] 
                    if line.strip() and not line.startswith("#")
                ]

            if not self.accounts_list:
                self.log_signal.emit(f"{self.TIME()} Nessun account valido trovato in accounts.txt")
                return False

            for i in range(self.current_account_index, len(self.accounts_list)):
                account = self.accounts_list[i]
                try:
                    domain, dess_cookie = account.split(":")
                    self.domain = domain 
                    self.log_signal.emit(f"{self.TIME()} Tentativo login con {domain.upper()}: {dess_cookie[:5]}...")

                    while True:
                        try:
                            success = self.login_via_dess(dess_cookie, domain == "es")
                            if success:
                                self.current_account_index = i  
                                return True  
                            else:
                                self.log_signal.emit(f"{self.TIME()} Login fallito, riprovo...")
                        except requests.Timeout:
                            self.log_signal.emit(f"{self.TIME()} ⏱ Timeout durante il login DESS")
                        except requests.ConnectionError:
                            self.log_signal.emit(f"{self.TIME()} ⚡ Errore di connessione durante il login DESS")
                        except Exception as e:
                            self.log_signal.emit(f"{self.TIME()} ‼ Errore durante il login DESS: {str(e)}")

                        time.sleep(retry_delay)

                except ValueError:
                    self.log_signal.emit(f"{self.TIME()} Account malformato: {account}")
                    continue

            self.log_signal.emit(f"{self.TIME()} Tutti gli account provati senza successo")
            return False

        except Exception as e:
            self.log_signal.emit(f"{self.TIME()} Errore durante il login: {str(e)}")
            return False
            
    def get_saldo(self):
        saldo_url = f"https://{self.get_domain()}.bidoo.com/user_settings.php"
        try:
            response = self.session.get(saldo_url)
            if response.status_code == 200:
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                saldo_element = soup.find(id="divSaldoBidBottom")
                self.saldo = int(saldo_element.text.strip()) if saldo_element else 0
        except Exception as e:
            self.log_signal.emit(f"{self.TIME()} Errore durante il recupero del saldo: {str(e)}")

    def open_auction(self, id_asta):
        url = f"https://{self.get_domain()}.bidoo.com/auction.php?a={id_asta}"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate",
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                self.id_asta = id_asta
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                prodotto = str(soup.title).replace('<title>', '').replace(' - Bidoo</title>', '').replace('&amp;plus;', '').replace('&dash;', '').replace('&amp;dash;', '-')
                self.update_signal.emit(self.username, str(self.saldo), "", "", "", prodotto)
                self.send_parameters_to_nodejs()                
                return True
        except Exception as e:
            self.log_signal.emit(f"{self.TIME()} Errore durante l'apertura dell'asta: {str(e)}")
        
        return False

    def set_slider_value(self, value):
        """Aggiorna il valore dello slider in modo thread-safe"""
        self.current_slider_value = value
        self.log_signal.emit(f"[DEBUG] Timer impostato a {value} secondi")

    def get_auction_info(self):
        info_asta = f"https://{self.get_domain()}.bidoo.com/data.php?ALL={self.id_asta}&LISTID=0"
        retry_delay = 2  
        timeout = 0.5  

        while self.running:
            try:
                if self.saldo <= 0:
                    self.log_signal.emit(f"{self.TIME()} Saldo esaurito, cambio account...")
                    self.current_account_index += 1
                    if not self.login_via_accounts_txt():
                        self.log_signal.emit(f"{self.TIME()} Nessun altro account disponibile")
                        self.running = False
                        return False
                    if not self.open_auction(self.id_asta):
                        self.log_signal.emit(f"{self.TIME()} Errore riaprendo l'asta")
                        return False
                    self.get_saldo()

                slider_value = self.current_slider_value
                while True:
                    try:
                        response = self.session.get(info_asta, timeout=timeout)
                        if response.status_code == 200:
                            data = response.text
                            if ';OFF;' in data:
                                vincitore = data.split(';')[4]
                                messaggio = f"{self.TIME()} Asta Terminata | Vincitore: {vincitore}"
                                self.log_signal.emit(messaggio)
                                self.update_signal.emit(self.username, str(self.saldo), "", "", "", "")
                                return False
                            if ';STOP;' in data:
                                self.log_signal.emit(f"{self.TIME()} Asta in pausa. Ricontrollo tra 1min")
                                time.sleep(60)
                                continue
                            raw_data_bid = re.findall('\\(|\\)|\\d{10}', data)
                            if len(raw_data_bid) >= 2:
                                differenza_secondi = int(raw_data_bid[1]) - int(raw_data_bid[0])
                                prezzo = str(int(data.split(';')[3]) / 100) + '€'
                                vincitore = data.split(';')[4]
                                current_price = float(data.split(';')[3]) / 100
                                if self.use_range and (current_price < self.min_price or current_price > self.max_price):
                                    self.log_signal.emit(f"{self.TIME()} Prezzo {current_price}€ fuori range, fermo.")
                                    self.reset_signal.emit()
                                    return False
                                if slider_value == 0:
                                    if differenza_secondi == 0 and vincitore != self.username:
                                        self.punta_in_manuale()
                                else:
                                    if (-3) <= differenza_secondi <= slider_value and vincitore != self.username:
                                        self.punta_in_manuale()
                                if vincitore == self.username:
                                    time.sleep(1)
                                self.update_signal.emit(
                                    self.username,
                                    str(self.saldo),
                                    vincitore,
                                    prezzo,
                                    str(differenza_secondi),
                                    ""
                                )
                            break 
                        else:
                            self.log_signal.emit(f"{self.TIME()} ❌ HTTP {response.status_code}")
                    except requests.Timeout:
                        self.log_signal.emit(f"{self.TIME()} ⏱ Timeout durante il recupero delle informazioni")
                    except requests.ConnectionError:
                        self.log_signal.emit(f"{self.TIME()} ⚡ Errore di connessione durante il recupero delle informazioni")
                    except Exception as e:
                        self.log_signal.emit(f"{self.TIME()} ‼ Errore durante il recupero delle informazioni: {str(e)}")

                    time.sleep(retry_delay) 

                time.sleep(1)
            except Exception as e:
                self.log_signal.emit(f"{self.TIME()} Errore in get_auction_info: {str(e)}")
                time.sleep(retry_delay)

        return False

    def punta_in_manuale(self):
        bid_url = f"https://{self.get_domain()}.bidoo.com/bid.php?AID={self.id_asta}&sup=0&shock=0"
        retry_delay = 2  
        timeout = 0.5    

        while True:
            try:
                response = self.session.get(bid_url, timeout=timeout)
                if response.status_code == 200:
                    response_text = response.text
                    if response_text.startswith('ok|'):
                        parts = response_text.split('|')
                        remaining_bids = parts[1]
                        bids_used = parts[4]
                        self.saldo = int(remaining_bids)
                        self.puntate_usate += int(bids_used)
                        self.log_signal.emit(f"{self.TIME()} ✅ Puntata accettata! Saldo: {remaining_bids}")
                        return True
                    elif "Sessione scaduta" in response_text:
                        self.log_signal.emit(f"{self.TIME()} ❌ Sessione scaduta. Riprova login.")
                        self.shutdown()
                        return False
                    else:
                        self.log_signal.emit(f"{self.TIME()} ❌ Server refused: {response_text}")
                else:
                    self.log_signal.emit(f"{self.TIME()} ❌ HTTP {response.status_code}")
            except requests.Timeout:
                self.log_signal.emit(f"{self.TIME()} ⏱ Timeout durante la puntata manuale")
            except requests.ConnectionError:
                self.log_signal.emit(f"{self.TIME()} ⚡ Errore di connessione durante la puntata manuale")
            except Exception as e:
                self.log_signal.emit(f"{self.TIME()} ‼ Error: {str(e)}")

            time.sleep(retry_delay) 


class Ui_MainWindow(object):
    def __init__(self):
        super().__init__()
        self.bot = BidooBot()
        self.bot.update_signal.connect(self.update_ui)
        self.bot.log_signal.connect(self.log_message)
        self.bot.reset_signal.connect(self.reset_all)
        self.accounts_file()
        self.loop = None

    def accounts_file(self):
        """Crea il file accounts.txt se non esiste e scrive un formato predefinito"""
        accounts_file = "accounts.txt"
        if not os.path.exists(accounts_file):
            try:
                with open(accounts_file, "w", encoding="utf-8") as file:
                    file.write("# Inserisci i tuoi account uno per riga digitando domain:dess\n")
                    file.write("# Esempio:\n")
                    file.write("# es:43ut3409fh3209023uy09hf0f43f304\n")
                self.log_message(f"{self.bot.TIME()} File 'accounts.txt' creato con successo.")
            except Exception as e:
                self.log_message(f"{self.bot.TIME()} Errore durante la creazione di 'accounts.txt': {str(e)}")

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(365, 258)
        MainWindow.setFixedSize(365, 258)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.tabWidget = QtWidgets.QTabWidget(self.centralwidget)
        self.tabWidget.setGeometry(QtCore.QRect(6, 9, 351, 241))
        self.tabWidget.setObjectName("tabWidget")
        self.Home = QtWidgets.QWidget()
        self.Home.setObjectName("Home")
        self.username = QtWidgets.QLabel(self.Home)
        self.username.setGeometry(QtCore.QRect(10, 10, 161, 21))
        self.username.setObjectName("username")
        self.saldo = QtWidgets.QLabel(self.Home)
        self.saldo.setGeometry(QtCore.QRect(210, 10, 121, 21))
        self.saldo.setObjectName("saldo")
        self.vincitore = QtWidgets.QLabel(self.Home)
        self.vincitore.setGeometry(QtCore.QRect(210, 40, 121, 21))
        self.vincitore.setObjectName("vincitore")
        self.prodotto = QtWidgets.QLabel(self.Home)
        self.prodotto.setGeometry(QtCore.QRect(10, 40, 161, 21))
        self.prodotto.setObjectName("prodotto")
        self.prezzo = QtWidgets.QLabel(self.Home)
        self.prezzo.setGeometry(QtCore.QRect(10, 70, 161, 21))
        self.prezzo.setObjectName("prezzo")
        self.timerasta = QtWidgets.QLabel(self.Home)
        self.timerasta.setGeometry(QtCore.QRect(210, 70, 121, 21))
        self.timerasta.setObjectName("timerasta")
        self.plainTextEdit = QtWidgets.QPlainTextEdit(self.Home)
        self.plainTextEdit.setGeometry(QtCore.QRect(13, 100, 321, 101))
        self.plainTextEdit.setObjectName("plainTextEdit")
        self.plainTextEdit.setReadOnly(True)
        self.tabWidget.addTab(self.Home, "")
        self.Details = QtWidgets.QWidget()
        self.Details.setObjectName("Details")
        self.api = QtWidgets.QRadioButton(self.Details)
        self.api.setGeometry(QtCore.QRect(10, 10, 51, 21))
        self.api.setObjectName("api")
        self.username_api = QtWidgets.QLineEdit(self.Details)
        self.username_api.setGeometry(QtCore.QRect(70, 10, 101, 20))
        self.username_api.setObjectName("username_api")
        self.password_api = QtWidgets.QLineEdit(self.Details)
        self.password_api.setGeometry(QtCore.QRect(190, 10, 111, 20))
        self.password_api.setObjectName("password_api")
        self.password_api.setEchoMode(QtWidgets.QLineEdit.Password)
        self.cookie = QtWidgets.QLineEdit(self.Details)
        self.cookie.setGeometry(QtCore.QRect(70, 50, 231, 20))
        self.cookie.setObjectName("cookie")
        self.dess = QtWidgets.QRadioButton(self.Details)
        self.dess.setGeometry(QtCore.QRect(10, 50, 51, 21))
        self.dess.setObjectName("dess")
        self.es = QtWidgets.QCheckBox(self.Details)
        self.es.setGeometry(QtCore.QRect(310, 30, 21, 21))
        self.es.setText("")
        self.es.setObjectName("es")
        self.accounts_txt = QtWidgets.QRadioButton(self.Details)
        self.accounts_txt.setGeometry(QtCore.QRect(10, 90, 101, 21))
        self.accounts_txt.setObjectName("accounts_txt")
        self.id_asta = QtWidgets.QLineEdit(self.Details)
        self.id_asta.setGeometry(QtCore.QRect(10, 120, 141, 20))
        self.id_asta.setObjectName("id_asta")
        self.avvia = QtWidgets.QPushButton(self.Details)
        self.avvia.setGeometry(QtCore.QRect(10, 150, 91, 31))
        self.avvia.setObjectName("avvia")
        self.stop = QtWidgets.QPushButton(self.Details)
        self.stop.setGeometry(QtCore.QRect(110, 150, 91, 31))
        self.stop.setObjectName("stop")
        self.stop.setEnabled(False)
        self.verticalSlider_timersecondi = QtWidgets.QSlider(self.Details)
        self.verticalSlider_timersecondi.setGeometry(QtCore.QRect(310, 100, 21, 111))
        self.verticalSlider_timersecondi.setMaximum(12)
        self.verticalSlider_timersecondi.setOrientation(QtCore.Qt.Vertical)
        self.verticalSlider_timersecondi.setTickPosition(QtWidgets.QSlider.TicksBothSides)
        self.verticalSlider_timersecondi.setObjectName("verticalSlider_timersecondi")
        self.slider_value_label = QtWidgets.QLabel(self.Details)
        self.slider_value_label.setGeometry(QtCore.QRect(320, 145, 30, 20))
        self.slider_value_label.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_value_label.setText("0")
        self.verticalSlider_timersecondi.valueChanged.connect(self.update_slider_display)
        self.verticalSlider_timersecondi.valueChanged.connect(lambda value: self.bot.update_timer_signal.emit(value))
        self.reset = QtWidgets.QPushButton(self.Details)
        self.reset.setGeometry(QtCore.QRect(210, 150, 91, 31))
        self.reset.setObjectName("reset")
        self.prezzo_min = QtWidgets.QSpinBox(self.Details)
        self.prezzo_min.setGeometry(QtCore.QRect(171, 100, 61, 22))
        self.prezzo_min.setObjectName("prezzo_min")
        self.prezzo_min.setMinimum(0)
        self.prezzo_min.setMaximum(9999)
        self.prezzo_max = QtWidgets.QSpinBox(self.Details)
        self.prezzo_max.setGeometry(QtCore.QRect(240, 100, 61, 22))
        self.prezzo_max.setObjectName("prezzo_max")
        self.prezzo_max.setMinimum(0)
        self.prezzo_max.setMaximum(9999)
        self.tabWidget.addTab(self.Details, "")
        MainWindow.setCentralWidget(self.centralwidget)
        self.retranslateUi(MainWindow)
        self.tabWidget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        # Bot instance
        self.bot = BidooBot()
        self.bot.update_signal.connect(self.update_ui)
        self.bot.log_signal.connect(self.log_message)
        self.bot.reset_signal.connect(self.reset_all)

        # Connect buttons
        self.avvia.clicked.connect(self.on_avvia_clicked)
        self.stop.clicked.connect(self.stop_bot)
        self.reset.clicked.connect(self.reset_all)

    def on_avvia_clicked(self):
        """Wrapper for the start_bot method"""
        self.start_bot()

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "dudubi2oo"))
        self.username.setText(_translate("MainWindow", "Username:"))
        self.saldo.setText(_translate("MainWindow", "Puntate:"))
        self.vincitore.setText(_translate("MainWindow", "Vincitore:"))
        self.prodotto.setText(_translate("MainWindow", "Prodotto:"))
        self.prezzo.setText(_translate("MainWindow", "Prezzo:"))
        self.timerasta.setText(_translate("MainWindow", "Timer:"))
        self.plainTextEdit.setToolTip(_translate("MainWindow", "<html><head/><body><p>info</p></body></html>"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Home), _translate("MainWindow", "Home"))
        self.api.setText(_translate("MainWindow", "HTTP"))
        self.username_api.setToolTip(_translate("MainWindow", "<html><head/><body><p>username</p></body></html>"))
        self.password_api.setToolTip(_translate("MainWindow", "<html><head/><body><p>password</p></body></html>"))
        self.dess.setText(_translate("MainWindow", "DESS"))
        self.es.setToolTip(_translate("MainWindow", "<html><head/><body><p>ES</p></body></html>"))
        self.accounts_txt.setText(_translate("MainWindow", "accounts.txt"))
        self.id_asta.setToolTip(_translate("MainWindow", "<html><head/><body><p>id asta</p></body></html>"))
        self.avvia.setText(_translate("MainWindow", "Avvia"))
        self.stop.setText(_translate("MainWindow", "Stop"))
        self.verticalSlider_timersecondi.setToolTip(_translate("MainWindow", "Imposta il timer (0=disattivato)"))
        self.reset.setText(_translate("MainWindow", "Reset"))
        self.prezzo_min.setToolTip(_translate("MainWindow", "<html><head/><body><p>prezzo min</p></body></html>"))
        self.prezzo_max.setToolTip(_translate("MainWindow", "<html><head/><body><p>prezzo max</p></body></html>"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Details), _translate("MainWindow", "Details"))
    
    def update_ui(self, username, saldo, vincitore, prezzo, timer, prodotto):
        self.username.setText(f"Username: {username}")
        self.saldo.setText(f"Puntate: {saldo}")
        
        if vincitore == "": 
            self.vincitore.setText("Asta Terminata")
        else:
            self.vincitore.setText(f"Vincitore: {vincitore}" if vincitore else "Vincitore:")
        
        self.prezzo.setText(f"Prezzo: {prezzo}" if prezzo else "Prezzo:")
        self.timerasta.setText(f"Timer: {timer}" if timer else "Timer:")
        
        if prodotto:
            self.prodotto.setText(f"Prodotto: {prodotto}")

    def log_message(self, message):
        self.plainTextEdit.appendPlainText(message)

    def reset_all(self):
        self.bot.stop()
        self.username.setText("Username:")
        self.saldo.setText("Puntate:")
        self.vincitore.setText("Vincitore:")
        self.prodotto.setText("Prodotto:")
        self.prezzo.setText("Prezzo:")
        self.timerasta.setText("Timer:")
        self.plainTextEdit.clear()
        self.username_api.clear()
        self.password_api.clear()
        self.cookie.clear()
        self.id_asta.clear()
        self.api.setChecked(False)
        self.dess.setChecked(False)
        self.accounts_txt.setChecked(False)
        self.es.setChecked(False)
        self.verticalSlider_timersecondi.setValue(0)
        self.prezzo_min.setValue(0)
        self.prezzo_max.setValue(0)
        self.avvia.setEnabled(True)
        self.stop.setEnabled(False)
        self.bot.current_account_index = 0

    def update_slider_display(self, value):
        """Aggiorna il label accanto allo slider e mostra un tooltip"""
        self.slider_value_label.setText(str(value))
        
        slider_height = self.verticalSlider_timersecondi.height()
        max_value = self.verticalSlider_timersecondi.maximum()
        y_pos = int(slider_height - (value * slider_height / max_value))
        
        QtWidgets.QToolTip.showText(
            self.verticalSlider_timersecondi.mapToGlobal(
                QtCore.QPoint(40, y_pos) 
            ),
            f"Timer: {value}s",
            self.verticalSlider_timersecondi,
            QtCore.QRect(), 
            1000  
        )

    def start_bot(self):
        id_asta = self.id_asta.text()
        if not id_asta:
            self.log_message("Inserisci un ID asta valido")
            return False
        
        self.bot.slider_timer = self.verticalSlider_timersecondi.value()
        self.bot.min_price = self.prezzo_min.value()
        self.bot.max_price = self.prezzo_max.value()
        self.bot.use_range = self.bot.min_price > 0 or self.bot.max_price > 0
        
        if self.api.isChecked():
            username = self.username_api.text()
            password = self.password_api.text()
            use_es = self.es.isChecked()
            if not username or not password:
                self.log_message("Inserisci username e password")
                return False
            if not self.bot.login_via_api(username, password, use_es):
                self.log_message("Login fallito")
                return False
        elif self.dess.isChecked():
            dess_cookie = self.cookie.text()
            use_es = self.es.isChecked()
            if not dess_cookie:
                self.log_message("Inserisci il cookie DESS")
                return False
            if not self.bot.login_via_dess(dess_cookie, use_es):
                self.log_message("Login DESS fallito")
                return False
        elif self.accounts_txt.isChecked():
            if not self.bot.login_via_accounts_txt():
                self.log_message("Login tramite accounts.txt fallito")
                return False
        else:
            self.log_message("Seleziona un metodo di login")
            return False
        
        if not self.bot.open_auction(id_asta):
            self.log_message("Impossibile aprire l'asta")
            return False
        
        self.avvia.setEnabled(False)
        self.stop.setEnabled(True)
        self.bot.start()
        return True

    def stop_bot(self):
        """Stop the bot safely"""
        self.bot.stop()
        self.avvia.setEnabled(True)
        self.stop.setEnabled(False)
        self.log_message("Bot stopped")
        node_process.terminate()

    def closeEvent(self, event):
        """Handle window close event"""
        self.bot.stop()
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_stylesheet(
    app, 
    theme='dark_cyan.xml',
    invert_secondary=True,
    extra={
        'density_scale': '-2',
        'font_family': 'Arial',
    }
)
    MainWindow = QtWidgets.QMainWindow()
    icon_path = "dudubi2oo.png"
    if os.path.exists(icon_path):
        MainWindow.setWindowIcon(QtGui.QIcon(icon_path))
    else:
        print(f"Attenzione: file {icon_path} non trovato")
    MainWindow.setWindowFlags(MainWindow.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())

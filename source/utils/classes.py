import logging
import os
import json
import sys
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

import statistics
import steam.webauth as wa
import steam.guard as guard
from lxml import html
import urllib

from . import functions

load_dotenv()

STEAM_COMMISION = 0.1304


class Game:
    '''Contiene la informacion de un juego

    Parametros
    ----------
    appid : int
        AppID del juego
    session : requests.Session
        Objeto request.session por el cual se realizan las requests. Normalmente se utiliza la propiedad User.session
    fast_mode : bool
        Determina si se evitan las pausas entre requests

    Atributos
    ---------
    appID : int
        AppID del juego
    name : str
        Nombre del juego
    price : float
        Precio
    min_profit : float
        Retorno minimo
    avg_profit : float
        Retorno medio
    med_profit : float
        Retorno mediano
    card_list : list[float]
        Lista de precios de los cromos
    last_updated : datetime.datetime
        Fecha y hora de ultima actualización
    session : request.Session
        Sesión del usuario
    logger: logging.Logger
        Objeto logger para registrar eventos
    '''

    def __init__(self, appid: int, fast_mode: bool = True, instant_prices: bool = False, session: requests.Session = requests.Session, logger: logging.Logger = None):
        self.appID = appid
        self.name = ''
        self.price = 0
        self.min_profit = 0
        self.avg_profit = 0
        self.med_profit = 0
        self.card_list = []
        self.last_updated = 0
        self.session = session
        self.logger = logger
        self.update(fast_mode, instant_prices=instant_prices)

    def update(self, fast_mode=True, instant_prices=False):
        store_URL = 'https://store.steampowered.com/api/appdetails?cc=ar&appids=' + \
            str(self.appID)
        response = functions.throttle_retry_request(self.session, store_URL, self.logger)

        # Si la cantidad de appIDs ingresadas es mayor a 250, se reducen las requests por segundo para evitar error 503
        if (not fast_mode):
            time.sleep(1)
        game_data = json.loads(response.text)
        # Obtiene el precio de los cromos
        self.card_list = self.get_price_list(
        ) if instant_prices == False else self.get_instant_price_list()
        if (not fast_mode):
            time.sleep(1)

        # Obtiene el nombre del juego
        self.name = game_data[str(self.appID)]['data']['name']
        # Obtiene la cantidad de los cromos que se dropean del juego
        cards_dropped = 3 if len(
            self.card_list) == 5 else len(self.card_list)//2
        # Calcula la media de los precios de los cromos
        average_price = statistics.mean(self.card_list)
        # Calcula la mediana de los precios de los cromos
        median_price = statistics.median(self.card_list)

        # Detecta si el juego es gratis o no
        is_free = game_data[str(self.appID)]['data']['is_free']
        if (not is_free):
            # Obtiene el precio del juego en centavos
            self.price = game_data[str(
                self.appID)]['data']['price_overview']['final'] / 100
            # Calcula el retorno mínimo
            self.min_profit = round((
                (self.card_list[0] * cards_dropped * (1 - STEAM_COMMISION) / (self.price)) - 1), 3)
            # Calcula el retorno medio
            self.avg_profit = round((
                (average_price * cards_dropped * (1 - STEAM_COMMISION) / (self.price)) - 1), 3)
            # Calcula el retorno mediano
            self.med_profit = round(((median_price * cards_dropped *
                                      (1 - STEAM_COMMISION) / (self.price)) - 1), 3)

        # Se actualiza el campo 'Ultima Actualizacion', tiempo en epoch
        self.last_updated = int(time.time())

    def get_price_list(self):
        '''Obtener una lista de los precios mínimos de los cromos del juego'''
        # Link a los cromos de un juego.
        cards_URL = 'https://steamcommunity.com/market/search/render/?l=spanish&currency=34&category_753_cardborder%5B%5D=tag_cardborder_0&category_753_item_class%5B%5D=tag_item_class_2&appid=753&norender=1&category_753_Game%5B%5D=tag_app_' + \
            str(self.appID)
        response = functions.throttle_retry_request(self.session, cards_URL, self.logger)

        cards_data = json.loads(response.text)
        # Si no existen cromos, retorna 0 para evitar un error
        if (cards_data['total_count'] == 0):
            return [0]
        # Obtiene el valor de los cromos, limpia el string para sólo obtener el valor numérico y los ordena de menor a mayor
        cards_prices = [cards_data['results'][i]['sell_price'] /
                        100 for i in range(len(cards_data['results']))]
        cards_prices.sort()
        # Retorna la lista de los cromos en orden ascendente
        return cards_prices

    def get_hash_names(self):
        '''Obtener una lista de los hash_names de los cromos de un juego'''
        # Link a los cromos de un juego.
        cards_URL = 'https://steamcommunity.com/market/search/render/?l=spanish&currency=34&category_753_cardborder%5B%5D=tag_cardborder_0&category_753_item_class%5B%5D=tag_item_class_2&appid=753&norender=1&category_753_Game%5B%5D=tag_app_' + \
            str(self.appID)
        response = self.session.get(cards_URL)
        # Si falla la solicitud, reintenta cada 5 segundos
        while (response.status_code != 200 or json.loads(response.text)['total_count'] == 0):
            self.logger.warn(
                f'Could not get hashes for {self.appID}. Reason: {response.reason if response.status_code != 200 else "total_count = 0"}. Retrying in 5 seconds...')
            time.sleep(5)
            response = self.session.get(cards_URL)

        cards_data = json.loads(response.text)
        # Obtiene el hash name de cada cromo y lo formatea como URL encoded
        hash_names = [urllib.parse.quote(
            cards_data['results'][i]['hash_name']) for i in range(len(cards_data['results']))]
        # Retorna la lista de hash names
        return hash_names

    def get_instant_price_list(self):
        '''Obtener una lista de los precios instantáneos de los cromos del juego'''
        # Obtiene la lista de los hash names de los cromos del juego
        hash_names = self.get_hash_names()
        price_list = [((float)(get_highest_buy_order(
            i, max_retries=3, session=self.session, logger=self.logger))) / 100 for i in hash_names]
        price_list.sort()
        return price_list


class User:
    '''Crear un objeto usuario donde se almacenan los datos del mismo.
    El inicio de sesion es automático

    Parametros
    ----------
    username : str
        Nombre de usuario
    password : str
        Contraseña
    dir : str
        Ruta del archivo de configuracion

    Atributos
    ---------
    username : str
        Nombre de usuario
    password : str
        Contraseña
    steamID64 : str
        SteamID64 del usuario de Steam
    webAPIKey : str
        Clave de web API del usuario de Steam
    session : request.Session
        Sesión del usuario
    logged_on : bool
        Indica si la sesion del usuario esta iniciada
    email_code : str
        Codigo de verificacion de email
    twofactor_code : str
        Codigo de verificacion de 2FA
    logger : logging.Logger
        Logger para el registro de eventos
    '''

    def __init__(self, username: str = '', password: str = '', dir: str = 'user.json', session: requests.Session = None, logger: logging.Logger = None):
        self.username = username
        self.password = password
        self.steamID64 = ''
        self.webAPIKey = ''
        self.session = ''
        self.logged_on = False
        self.email_code = ''
        self.twofactor_code = ''
        self.logger = logger

        if session != None:
            if 'login' not in session.get('https://steamcommunity.com/dev/apikey').url.split('/'):
                self.session = session
                user_account_page = self.session.get(
                    'https://store.steampowered.com/account/').content
                self.steamID64 = html.fromstring(user_account_page).xpath(
                    '//*[@id="responsive_page_template_content"]/div[1]/div/div[2]')[0].text.split(' ')[3]
                # https://steamcommunity.com/dev/apikey
                # //*[@id="responsive_page_template_content"]/div[1]/div/div[2]
                self.username = html.fromstring(user_account_page).xpath(
                    '/html/body/div[1]/div[7]/div[1]/div/div[3]/div/div[3]/div/a[3]/span')[0].text
                key = html.fromstring(self.session.get(
                    'https://steamcommunity.com/dev/apikey').content).xpath('//*[@id="bodyContents_ex"]/p[1]/text()')[0]
                self.webAPIKey = key.split(' ')[1] if key[0] != 'R' else ''
                self.logger.info(
                    'Logged in successfully with user ' + self.username)
                self.logged_on = True
                return

        if (os.path.isfile(dir)):
            if not self.load(dir):
                os.remove('user.json')
                self.create(dir)
        else:
            self.create(dir)

    def load(self, dir='user.json'):
        try:
            with open(dir, 'r', encoding='utf-8') as usercfg:
                data = json.load(usercfg)
                self.username = data['username']
                self.password = data['password']
                if self.username == '' or self.password == '':
                    raise Exception('No username or password specified')
                self.login()
            return True
        except:
            self.logger.warn('Invalid configuration file, recreating...')
            return False

    def create(self, dir='user.json'):
        with open(dir, 'w', encoding='utf-8') as usercfg:
            self.logger.info(
                'A configuration file will be created. To enable skipping already owned games, you must enable the Steam Web API Key')
            if self.username == '' or self.password == '':
                self.username = os.getenv('STEAM_USERNAME')
                self.password = os.getenv('STEAM_PASSWORD')
                if self.username == None or self.password == None:
                    raise Exception('No username or password specified')

            data = {'username': self.username, 'password': self.password}
            usercfg.write(json.dumps(data))
        self.login()

    def login(self):
        user = wa.WebAuth(self.username)
        while user.logged_on == False:
            try:
                user = wa.WebAuth(self.username)
                if os.path.isfile('2FA.maFile'):
                    with open('2FA.maFile', 'r') as f:
                        data = json.load(f)
                        if data['account_name'] == self.username:
                            self.twofactor_code=guard.SteamAuthenticator(secrets=data).get_code()
                        else:
                            self.logger.warn('2FA maFile does not match username')
                self.session = user.login(
                    self.password, email_code=self.email_code, twofactor_code=self.twofactor_code)
            except wa.TwoFactorCodeRequired:
                raise Exception(
                    '2FA required. Haze-core does not support manual 2FA entry')
            except wa.EmailCodeRequired:
                raise Exception(
                    'Email code required. Haze-core does not support email code entry')
            except wa.LoginIncorrect:
                raise Exception(
                    'Incorrect login. Check your username and password')
            except wa.TooManyLoginFailures:
                self.logger.warn(
                    'Too many login failures. Check your username and password or wait a few minutes')
                sys.exit()

        if user.logged_on:
            self.steamID64 = user.steam_id.as_64
            # https://steamcommunity.com/dev/apikey
            key = html.fromstring(self.session.get(
                'https://steamcommunity.com/dev/apikey').content).xpath('//*[@id="bodyContents_ex"]/p[1]/text()')[0]
            self.webAPIKey = key[5:] if key[0] != 'R' else ''
            self.logged_on = True
        else:
            raise Exception('Login failed')
        self.logger.info(
            'Logged in successfully with user ' + self.username)


def get_card_sales_histogram(market_hash_name: str, throttle_sleep_time: float = 0, max_retries: int = 0, only_highest_buy_order: bool = False, session: requests.Session = requests.Session, logger: logging.Logger = None):
    '''Obtener el histograma de oferta/demanda de un cromo

    Parámetros
    ----------
    market_hash_name: str Market hash name del cromo. Se obtiene desde Steam.
    throttling_sleep_time: float Tiempo de espera despues de cada request satisfactoria. Por defecto 0.

    Retorna
    -------
    Si only_highest_buy_order = False, retorna: X_buy, Y_buy, X_sell, Y_sell
    Si only_highest_buy_order = True, retorna: highest_buy_order

    X_buy: list[float] Precio de compra
    Y_buy: list[int] Cantidad de ordenes de compra
    X_sell: list[float] Precio de venta
    Y_sell: list[int] Cantidad de ordenes de venta
    highest_buy_order: int Precio de la orden de compra más alta

    2 REQUESTS
    '''
    listings_URL = f'https://steamcommunity.com/market/listings/753/{market_hash_name}/?currency=34&country=AR'
    response = functions.throttle_retry_request(session, listings_URL, max_retries, logger)
    time.sleep(throttle_sleep_time)
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    last_script = str(soup.find_all('script')[-1])
    last_script_token = last_script.split('(')[-1]
    item_nameid = last_script_token.split(');')[0].strip()

    itemordershistogram_URL = f'https://steamcommunity.com/market/itemordershistogram?country=AR&language=spanish&currency=34&item_nameid={item_nameid}&two_factor=0'

    # Para esta query, Steam no tira codigo de error distinto, sino que no devuelve un json, entonces no alcanza con chequear status code = 200
    sleep_time = 5
    retry_count = 1
    while True:
        response = session.get(itemordershistogram_URL)
        if response.status_code == 200:
            try:
                json = response.json()
                break
            except:
                if max_retries and max_retries == retry_count:
                    logger.error(f'Could not card sales histogram for card {market_hash_name} after {str(max_retries)} retries.')
                    return 0
                logger.warn(f'Error getting card sales histogram. Retrying in {str(sleep_time)} seconds...')
        else:
            if max_retries and max_retries == retry_count:
                logger.error(f'Could not card sales histogram for card {market_hash_name} after {str(max_retries)} retries.')
                return 0
            logger.warn(f'Error getting card sales histogram. Status code {str(response.status_code)} ({response.reason}). Retrying in {str(sleep_time)} seconds...')
        time.sleep(sleep_time)
        sleep_time *= 2
        if max_retries:
            retry_count += 1
    time.sleep(throttle_sleep_time)

    X_buy: list[float]
    Y_buy: list[int]
    X_sell: list[float]
    Y_sell: list[int]

    if (json['success'] == 1):
        if only_highest_buy_order:
            return json['highest_buy_order']
        X_buy = [json['buy_order_graph'][i][0]
                 for i in range(len(json['buy_order_graph']))]
        Y_buy = [json['buy_order_graph'][i][1]
                 for i in range(len(json['buy_order_graph']))]
        X_sell = [json['sell_order_graph'][i][0]
                  for i in range(len(json['sell_order_graph']))]
        Y_sell = [json['sell_order_graph'][i][1]
                  for i in range(len(json['sell_order_graph']))]

        return X_buy, Y_buy, X_sell, Y_sell
    else:
        raise ValueError(
            f'Hubo un error al obtener el histograma de oferta/demanda del cromo {market_hash_name}')


def get_highest_buy_order(market_hash_name: str, max_retries: int = 0, session: requests.Session = requests.Session, logger: logging.Logger = None):
    '''Obtener el precio de la orden de compra más alta de un cromo

    Retorna: highest_buy_order

    highest_buy_order: int Precio de la orden de compra más alta

    2 REQUESTS
    '''
    if max_retries:
        return get_card_sales_histogram(market_hash_name, throttle_sleep_time=1, max_retries=max_retries, session=session, only_highest_buy_order=True, logger=logger)
    else:
        return get_card_sales_histogram(market_hash_name, throttle_sleep_time=1, session=session, only_highest_buy_order=True, logger=logger)

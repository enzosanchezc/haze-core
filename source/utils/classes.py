import datetime
import logging
import os
import json
import sys
import time
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
    appid : int
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

    def __init__(self, appid: int, fast_mode: bool = True, session: requests.Session = requests.Session, logger: logging.Logger = logging.getLogger()):
        self.appid = appid
        self.name = ''
        self.price = 0
        self.min_profit = 0
        self.avg_profit = 0
        self.med_profit = 0
        self.card_list = []
        self.last_updated = 0
        self.has_cards = False
        self.session = session
        self.logger = logger
        self.update(fast_mode)

    def update(self, fast_mode: bool = True):
        '''Actualiza todos los datos del juego'''

        self.last_updated = int(time.time())
        
        store_URL = 'https://store.steampowered.com/api/appdetails?cc=ar&appids=' + \
            str(self.appid)
        response = functions.throttle_retry_request(self.session, store_URL, self.logger)

        # Si la cantidad de appids ingresadas es mayor a 250, se reducen las requests por segundo para evitar error 503
        if not fast_mode:
            time.sleep(1)
        game_data = json.loads(response.text)[str(self.appid)]['data']

        if game_data['is_free']:
            return

        # Obtiene el nombre del juego
        self.name = game_data['name']
        
        self.update_cards(fast_mode)
        if not self.has_cards:
            return
        
        # Obtiene la cantidad de los cromos que se dropean del juego
        cards_dropped = 3 if len(
            self.card_list) == 5 else len(self.card_list)//2
        # Calcula la media de los precios de los cromos
        average_price = statistics.mean(list(map(lambda x: x.price, self.card_list)))
        # Calcula la mediana de los precios de los cromos
        median_price = statistics.median(list(map(lambda x: x.price, self.card_list)))

        # Obtiene el precio del juego en centavos
        self.price = game_data['price_overview']['final'] / 100
        # Calcula el retorno mínimo
        self.min_profit = round((
            (self.card_list[0].price * cards_dropped * (1 - STEAM_COMMISION) / (self.price)) - 1), 3)
        # Calcula el retorno medio
        self.avg_profit = round((
            (average_price * cards_dropped * (1 - STEAM_COMMISION) / (self.price)) - 1), 3)
        # Calcula el retorno mediano
        self.med_profit = round(((median_price * cards_dropped *
                                    (1 - STEAM_COMMISION) / (self.price)) - 1), 3)

    def update_cards(self, fast_mode: bool = True):
        '''Actualiza la lista de los cromos del juego'''
        # Link a los cromos de un juego.
        cards_URL = 'https://steamcommunity.com/market/search/render/?l=spanish&currency=34&category_753_cardborder%5B%5D=tag_cardborder_0&category_753_item_class%5B%5D=tag_item_class_2&appid=753&norender=1&category_753_Game%5B%5D=tag_app_' + \
            str(self.appid)
        response = functions.throttle_retry_request(self.session, cards_URL, self.logger)
        if not fast_mode:
            time.sleep(1)

        cards_data = json.loads(response.text)
        # Si no existen cromos, retorna 0 para evitar un error
        if (cards_data['total_count'] == 0):
            return [0]
        self.has_cards = True
        
        for i in range(len(cards_data['results'])):
            self.card_list.append(Card(self.appid, i, cards_data['results'][i], self.session, self.logger))
        self.card_list.sort(key=lambda x: x.price)
    
    def update_instant_prices(self):
        '''Actualiza el precio de instant sell de los cromos del juego'''
        for card in self.card_list:
            card.update_instant_price()
            time.sleep(1)


class Card:
    '''Cromo de un juego.

    Parametros
    ----------
    appid : int
        AppID del juego
    idx : int
        Indice del cromo en la lista de cromos del juego

    Atributos
    ---------
    appid : int
        AppID del juego
    idx : int
        Indice del cromo en la lista de cromos del juego
    name : str
        Nombre del cromo
    hash_name : str
        Hash name del cromo
    listings : int
        Número de ofertas en el mercado
    price : float
        Precio más bajo del cromo en el mercado
    instant_price : float
        Precio de instant sell del cromo
    '''

    def __init__(self, appid: int, idx: int, card_data: dict, session: requests.Session = requests.Session, logger: logging.Logger = logging.getLogger()):
        self.appid = appid
        self.idx = idx
        self.name = ''
        self.hash_name = ''
        self.listings = 0
        self.price = 0.0
        self.instant_price = 0.0
        self.session = session
        self.logger = logger
        self.update(card_data)
    
    def update(self, card_data):
        '''Actualizar los datos del cromo'''
        self.name = card_data['name']
        self.hash_name = urllib.parse.quote(card_data['hash_name'])
        self.listings = card_data['sell_listings']
        self.price = card_data['sell_price'] / 100

    def update_instant_price(self, max_retries: int = 3):
        '''Actualizar el precio instantáneo del cromo'''
        if max_retries:
            self.instant_price = self.get_sales_histogram(max_retries=max_retries, only_highest_buy_order=True)
        else:
            self.instant_price = self.get_sales_histogram(only_highest_buy_order=True)

    def get_sales_histogram(self, throttle_sleep_time: float = 1, max_retries: int = 0, only_highest_buy_order: bool = False):
        '''Obtener el histograma de oferta/demanda.

        Parámetros
        ----------
        throttling_sleep_time: float 
            Tiempo de espera en segundos despues de cada request satisfactoria.

        Retorna
        -------
        Si only_highest_buy_order = False, retorna: X_buy, Y_buy, X_sell, Y_sell
        Si only_highest_buy_order = True, retorna: highest_buy_order

        X_buy: list[float]
            Precio de compra
        Y_buy: list[int]
            Cantidad de ordenes de compra
        X_sell: list[float]
            Precio de venta
        Y_sell: list[int]
            Cantidad de ordenes de venta
        highest_buy_order: int
            Precio de la orden de compra más alta
        '''
        listings_URL = f'https://steamcommunity.com/market/listings/753/{self.hash_name}/?currency=34&country=AR'
        response = functions.throttle_retry_request(self.session, listings_URL, max_retries, self.logger)
        time.sleep(throttle_sleep_time)
        last_script = html.fromstring(response.content).xpath('(//script)[last()]')[0].text
        last_script_token = last_script.split('(')[-1]
        item_nameid = last_script_token.split(');')[0].strip()

        itemordershistogram_URL = f'https://steamcommunity.com/market/itemordershistogram?country=AR&language=spanish&currency=34&item_nameid={item_nameid}&two_factor=0'

        # Para esta query, Steam no tira codigo de error distinto, sino que no devuelve un json, entonces no alcanza con chequear status code = 200
        sleep_time = 5
        retry_count = 1
        while True:
            response = self.session.get(itemordershistogram_URL)
            if response.status_code == 200:
                try:
                    json = response.json()
                    break
                except:
                    if max_retries and max_retries == retry_count:
                        self.logger.error(f'Could not card sales histogram for card {self.hash_name} after {str(max_retries)} retries.')
                        return 0
                    self.logger.warn(f'Error getting card sales histogram. Retrying in {str(sleep_time)} seconds...')
            else:
                if max_retries and max_retries == retry_count:
                    self.logger.error(f'Could not card sales histogram for card {self.hash_name} after {str(max_retries)} retries.')
                    return 0
                self.logger.warn(f'Error getting card sales histogram. Status code {str(response.status_code)} ({response.reason}). Retrying in {str(sleep_time)} seconds...')
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
                f'Hubo un error al obtener el histograma de oferta/demanda del cromo {self.name}')
        
    def get_price_history(self, since: str = 'general'):
        '''Obtener el historial de precios de un cromo

        since : str
            'general', 'last-week', 'last-month', default:'general'

        Retorna: X, Y, N

        X: list[datetime]
            Fechas
        Y: list[float]
            Precios
        N: list[int]
            Cantidad vendidos

        1 REQUEST
        '''
        price_history_url = f'https://steamcommunity.com/market/pricehistory/?appid=753&market_hash_name={self.hash_name}'
        response = self.session.get(price_history_url)

        # Si falla la solicitud, reintenta cada 5 segundos
        while(response.status_code != 200):
            wait_time = 1
            for i in range(wait_time, 0, -1):
                time.sleep(1)
            wait_time *= 2
            response = self.session.get(price_history_url)
        json = response.json()

        X: list[datetime.datetime]
        Y: list[float]
        N: list[int]

        if(json['success'] == True):
            X = [datetime.datetime.strptime(
                json['prices'][i][0][:-4], '%b %d %Y %H') for i in range(len(json['prices']))]
            Y = [json['prices'][i][1]
                for i in range(len(json['prices']))]
            N = [int(json['prices'][i][2])
                for i in range(len(json['prices']))]
            if(since == 'general'):
                return X, Y, N
            elif(since == 'last-week'):
                X = [i for i in X if i > datetime.datetime.today() -
                    datetime.timedelta(7)]
                Y = Y[-len(X):]
                N = N[-len(X):]
                return X, Y, N
            elif(since == 'last-month'):
                X = [i for i in X if i > datetime.datetime.today() -
                    datetime.timedelta(31)]
                Y = Y[-len(X):]
                N = N[-len(X):]
                return X, Y, N
            else:
                raise ValueError(
                    f'Debe indicar un periodo de tiempo válido')
        else:
            raise ValueError(
                f'Hubo un error al obtener el historial de precios del cromo {self.hash_name}')


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
        self.owned_games = []
        self.logged_on = False
        self.email_code = ''
        self.twofactor_code = ''
        self.session = ''
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

    def update_owned_games(self):
        if self.webAPIKey == '':
            self.logger.warn('Cannot update owned games. User does not have a web API key.')
            return
        
        self.logger.info('Checking owned games...')
        owned_games_URL = 'http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=' + self.webAPIKey + '&steamid=' + str(self.steamID64) + '&format=json'
        games_data = self.session.get(owned_games_URL).json()['response']['games']
        self.owned_games = list(map(lambda x: int(x['appid']), games_data))
        self.logger.info(f'Found {len(self.owned_games)} owned games')
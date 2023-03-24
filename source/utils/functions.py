import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
import requests
import pickle
from dotenv import load_dotenv

from lxml import html
from time import time, sleep
import sqlite3 as sql

from . import classes

load_dotenv()

def update_database(appID: list[int], database : sql.Connection, instant_prices=False, session: requests.Session = requests.Session, logger : logging.Logger = None):
    '''Actualizar la base de datos con la lista de juegos indicada'''

    cursor = database.cursor()
    table = 'instant_prices' if instant_prices else 'games'
    fast_mode = False if os.getenv('HAZE_DISABLE_FAST_MODE') else True

    # Si la cantidad de juegos es mayor a 250, se desactiva el fast mode. Los valores de expected son empíricos
    # Si se usa el modo instant_prices, no se calcula el expected time porque puede variar mucho
    if not instant_prices:
        if len(appID) > 250:
            fast_mode = False
            time_left = datetime.timedelta(seconds=(len(appID) * 3.1))
            logger.info(f'Expected completion time: {time_left.seconds // 3600}hs {time_left.seconds % 3600 // 60}min')
        else:
            time_left = datetime.timedelta(seconds=(len(appID) * 1.35))
            logger.info(f'Expected completion time: {time_left.seconds // 60}min {time_left.seconds % 60}sec')
    
    for i in range(len(appID)):
        logger.debug(f'[{i+1}/{len(appID)}] Updating game {appID[i]}...')
        game = classes.Game(appID[i], fast_mode=fast_mode, session=session, logger=logger)
        if not game.has_cards or game.price == 0:
            logger.debug(f'Game {appID[i]} has no cards or is free, skipping...')
            continue
        if instant_prices:
            game.update_instant_prices()
        # Verificar si el juego ya está en la base de datos
        cursor.execute(f'SELECT * FROM {table} WHERE appid=?', (game.appid,))
        if cursor.fetchone() is None:
            # Si no está, se agrega
            cursor.execute(f'INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (
                game.appid, game.name, game.price, game.min_profit, game.avg_profit, game.med_profit, ', '.join(list(map(lambda x: str(x.price), game.card_list))), game.last_updated))
        else:
            # Si está, se actualiza
            cursor.execute(f'UPDATE {table} SET name=?, price=?, min_return=?, mean_return=?, median_return=?, cards_list=?, last_update=? WHERE appID=?', (
                game.name, game.price, game.min_profit, game.avg_profit, game.med_profit, ', '.join(list(map(lambda x: str(x.price), game.card_list))), game.last_updated, game.appid))
        database.commit()


def delete_database():
    '''Eliminar base de datos'''
    if(os.path.isfile('database/main.db')):
        os.remove('database/main.db')


def get_appid_list(maxprice=16):
    '''Obtener los appids de los juegos con precio inferior a maxprice

    Retorna: appid_list

    appid_list: list[int] Lista de appids

    1 REQUEST
    '''

    appid_list = []
    i = 1
    while(True):
        page = requests.get(
            f'https://store.steampowered.com/search/results/?query&start=0&count=200&dynamic_data=&sort_by=Price_ASC&ignore_preferences=1&maxprice=70&category1=998&category2=29&snr=1_7_7_2300_7&specials=1&infinite=0&page={i}')
        tree = html.fromstring(page.content)
        price_list = tree.xpath(
            '//div[@class="col search_price discounted responsive_secondrow"]/text()')
        price_list = [x[5:].replace(',', '.') for x in [
            y.rstrip() for y in price_list] if x not in ['']]
        price_list = [float(x) if x != '' else 0 for x in price_list]
        if any(float(x) > maxprice for x in price_list):
            try:
                appid_list += tree.xpath('//a[@data-ds-appid]/@data-ds-appid')[
                    :price_list.index(next(filter(lambda x: x > maxprice, price_list), None)) + 1]
            except:
                appid_list += tree.xpath('//a[@data-ds-appid]/@data-ds-appid')[
                    :price_list.index(next(filter(lambda x: x > maxprice, price_list), None))]
            break
        appid_list += tree.xpath('//a[@data-ds-appid]/@data-ds-appid')
        i += 1
    appid_list = [int(x) for x in appid_list if not ',' in x]
    return appid_list


def trusty_sleep(seconds: float):
    start = time()
    while (time() - start < seconds):
        sleep(seconds - (time() - start))


def save_cookies(requests_cookiejar, filename):
    with open(filename, 'wb') as f:
        pickle.dump(requests_cookiejar, f)


def load_cookies(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)


def init_logger(name: str = 'haze-core', level: int = logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s', datefmt='%d/%m/%Y %I:%M:%S %p')

    # Stream handler
    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # File handler
    fh = RotatingFileHandler('haze.log', maxBytes=2*1024*1024, backupCount=1)
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def init_db(db_file: str = 'database/main.db', logger: logging.Logger = None):
    db = sql.connect(db_file)
    cursor = db.cursor()

    # Crear tablas
    # La tabla 'games' contiene los datos de los juegos
    cursor.execute('''CREATE TABLE IF NOT EXISTS games (
        appid INTEGER PRIMARY KEY,
        name TEXT,
        price REAL,
        min_return REAL,
        mean_return REAL,
        median_return REAL,
        cards_list TEXT,
        last_update INTEGER
    )''')
    db.commit()
    # La tabla 'instant_prices' contiene los mismos datos que 'games' pero con los precios de instant sell
    cursor.execute('''CREATE TABLE IF NOT EXISTS instant_prices (
        appid INTEGER PRIMARY KEY,
        name TEXT,
        price REAL,
        min_return REAL,
        mean_return REAL,
        median_return REAL,
        cards_list TEXT,
        last_update INTEGER
    )''')
    db.commit()
    
    logger.info('Database initialized')

    return db, cursor


def throttle_retry_request(session: requests.Session = requests.Session, url: str = '', sleep_time: int = 5, max_retries: int = 0, logger: logging.Logger = logging.getLogger('root')):
    '''Intenta hacer una solicitud a una URL, si falla, espera sleep_time * 2 ^ tries segundos y vuelve a intentar hasta max_retries veces

    Retorna: response

    response: requests.Response Respuesta de la solicitud
    '''
    response = session.get(url)
    retries = 0
    while response.status_code != 200 and (retries < max_retries if max_retries else True):
        logger.info(f'Error {response.status_code} getting {url}, retrying in {sleep_time} seconds')
        trusty_sleep(sleep_time)
        response = session.get(url)
        retries += 1
        sleep_time *= 2
    if response.status_code != 200:
        logger.error(f'Error {response.status_code} getting {url}')
    return response

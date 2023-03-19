# Standard library imports
import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Third party imports
import sqlite3 as sql

# Local application imports
from functions import update_database, get_appid_list, save_cookies, load_cookies, trusty_sleep
from functions import save_cookies, load_cookies
from classes import User

load_dotenv()

VERSION = '0.1.0'

# Se inicializa el logger a stdout para el manejo de errores
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s', datefmt='%d/%m/%Y %I:%M:%S %p')
logger = logging.getLogger("haze-core")
# Si existe la variable de entorno HAZE_DEBUG, se activa el modo debug
if (os.getenv('HAZE_DEBUG')):
    logging.getLogger("haze-core").setLevel(logging.DEBUG)
    logger.debug('Debug mode activated')

# Log version
logger.info('Haze version: ' + VERSION)

# Si no existe la carpeta database, se crea
if (not os.path.exists('database')):
    os.makedirs('database')
    logger.info('Created database folder')

# Se intenta cargar la sesión de usuario desde el archivo de sesión session.pkl
# Si no existe el archivo o la sesión expiró, se crea un objeto usuario
try:
    session = requests.session()
    session.cookies = load_cookies('session.pkl')
    user = User(session=session, logger=logger)
    save_cookies(user.session.cookies, 'session.pkl')
    logger.info('User session loaded')
except:
    user = User(logger=logger)
    save_cookies(user.session.cookies, 'session.pkl')
    logger.info('User session created')

# Se inicializa la base de datos sqlite3
db = sql.connect('database/main.db')
cursor = db.cursor()
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
logger.info('Database initialized')

logo = '''
      ___           ___           ___           ___      
     /\__\         /\  \         /\  \         /\  \     
    /:/  /        /::\  \        \:\  \       /::\  \    
   /:/__/        /:/\:\  \        \:\  \     /:/\:\  \   
  /::\  \ ___   /::\~\:\  \        \:\  \   /::\~\:\  \  
 /:/\:\  /\__\ /:/\:\ \:\__\ _______\:\__\ /:/\:\ \:\__\ 
 \/__\:\/:/  / \/__\:\/:/  / \::::::::/__/ \:\~\:\ \/__/ 
      \::/  /       \::/  /   \:\~~\~~      \:\ \:\__\   
      /:/  /        /:/  /     \:\  \        \:\ \/__/   
     /:/  /        /:/  /       \:\__\        \:\__\     
     \/__/         \/__/         \/__/         \/__/     
'''
logger.info(logo)

try:
    while True:
        logger.info('Getting appid list...')
        appid_list = get_appid_list()
        logger.info('Number of games: ' + str(len(appid_list)))
        # Da la opcion de omitir los juegos que ya estan comprados
        if (user.webAPIKey != ''):
            logger.debug('Web API key found: ' + user.webAPIKey)
            logger.info('Checking owned games...')
            owned_games_URL = 'http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key=' + \
                user.webAPIKey + '&steamid=' + \
                str(user.steamID64) + '&format=json'
            games_data = user.session.get(
                owned_games_URL).json()['response']
            owned_games_list = [int(games_data['games'][x]['appid']) for x in range(
                len(games_data['games']))]
            logger.debug('Owned games: ' + str(owned_games_list))
            appid_list = [x for x in appid_list if int(
                x) not in owned_games_list]
        logger.info('Number of games to check: ' + str(len(appid_list)))
        logger.debug('Appid list: ' + str(appid_list))
        # Se actualiza la base de datos
        logger.info('Updating database...')
        update_database(appid_list, db, session=user.session, logger=logger)
        logger.info('Database updated')
        # Dormir por una hora
        logger.info('Sleeping for 1 hour...')
        trusty_sleep(3600)
# Salvo que el programa se cierre de forma inesperada, se guardan los detalles en el logger antes de cerrarse
except KeyboardInterrupt:
    logger.info('Program closed')
except Exception as e:
    logger.error(e)
    sys.exit()

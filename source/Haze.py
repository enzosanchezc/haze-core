# Standard library imports
import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Local application imports
from utils.functions import update_database, get_appid_list, save_cookies, load_cookies, trusty_sleep, init_logger, init_db, save_cookies, load_cookies
from utils.classes import User

load_dotenv()

VERSION = '0.1.0'

# Se inicializa el logger
if (os.getenv('HAZE_DEBUG')):
    logger = init_logger(level=logging.DEBUG)
    logger.debug('Debug mode activated')
else:
    logger = init_logger()

# Log version
logger.info('Haze version: ' + VERSION)

# Verificar si existe la variable de entorno DB_LOCATION, sino, usar la carpeta database. Crear el directorio si no existe
if (os.getenv('DB_LOCATION')):
    db_location = os.getenv('DB_LOCATION')
else:
    db_location = 'database'
if (not os.path.exists(db_location)):
    os.mkdir(db_location)
    logger.info('Database folder created')

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
db, cursor = init_db(db_location + '/main.db', logger=logger)

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
        logger.info('Updating instant prices for top 10 games...')
        # Se actualizan los precios instantaneos de los 10 juegos con mayor retorno
        cursor.execute('SELECT appid FROM games ORDER BY min_return DESC LIMIT 10')
        appid_list = [x[0] for x in cursor.fetchall()]
        update_database(appid_list, db, session=user.session, logger=logger, instant_prices=True)
        logger.info('Instant prices updated')
        # Dormir por una hora
        logger.info('Sleeping for 1 hour...')
        trusty_sleep(3600)
# Salvo que el programa se cierre de forma inesperada, se guardan los detalles en el logger antes de cerrarse
except KeyboardInterrupt:
    db.close()
    logger.info('Database connection closed')
    logger.info('Program closed')
except Exception as e:
    logger.exception(e)
    if os.getenv('HAZE_DEBUG'): raise e
    db.close()
    logger.info('Database connection closed')
    sys.exit()

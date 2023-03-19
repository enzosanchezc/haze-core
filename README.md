# Haze Core

Una herramienta para monitorear el retorno esperado de la compra de juegos y venta de cromos en la plataforma Steam. La versión Core está pensada para instalarse en un servidor, ya que no tiene GUI y debe desplegarse como contenedor junto a InfluxDB (pendiente) para guardar el historial de precios y Grafana para visualización de las bases de datos.

Como base de datos principal utiliza Sqlite3, por lo que Grafana debe tener instalado un plugin que soporte dicha base de datos.

## Integración con Steam
La lista de juegos es obtenida directamente de **Steam**.
Adicionalmente, si se habilita la *[Clave de Web API de Steam](https://steamcommunity.com/dev/apikey)*, puede utilizar la opción para omitir los juegos que ya se encuentran en la biblioteca.

## Integración con Steam Desktop Authenticator
Se debe colocar el archivo de secretos generado por [SDA](https://github.com/Jessecar96/SteamDesktopAuthenticator) en la carpeta base del repositorio, con el nombre **2FA.maFile**

## Modo de uso

1. Clonar el repositorio

```git clone https://github.com/enzosanchezc/haze-core.git && cd haze-core```

2. Crear un entorno virtual (Python 3.10.10)

```python3.10 -m venv venv && source venv/bin/activate```

3. Instalar dependencias

```pip install -r requirements.txt```

4. Crear archivo de variables de entorno y completar con los datos correspondientes

```cp .env.example .env```

5. Copiar archivo **2FA.maFile** de Steam Desktop Authenticator a la carpeta base del repositorio
6. Instalar [docker](https://www.docker.com/) y [docker-compose](https://docs.docker.com/compose/install/)
7. Iniciar el programa con docker-compose

```docker-compose up -d```
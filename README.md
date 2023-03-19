# Haze Core

Una herramienta para monitorear el retorno esperado de la compra de juegos y venta de cromos en la plataforma Steam. La versión Core está pensada para instalarse en un servidor, ya que no tiene GUI y debe desplegarse como contenedor junto a InfluxDB para guardar el historial de precios y Grafana para visualización de las bases de datos.

Como base de datos principal utiliza Sqlite3, por lo que Grafana debe tener instalado un plugin que soporte dicha base de datos.

## Integración con Steam
La lista de juegos es obtenida directamente de **Steam**.
Adicionalmente, si se habilita la *[Clave de Web API de Steam](https://steamcommunity.com/dev/apikey)*, puede utilizar la opción para omitir los juegos que ya se encuentran en la biblioteca.

## Integración con Steam Desktop Authenticator
La autenticación en 2 factores puede automatizarse si se coloca el archivo de secretos generado por [SDA](https://github.com/Jessecar96/SteamDesktopAuthenticator) en la carpeta donde está el ejecutable, con el nombre **2FA.maFile**

## Modo de uso

WIP

## Compilación de imagen de Docker

WIP
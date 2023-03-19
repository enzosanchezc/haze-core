FROM python:3.10.10-alpine3.17
WORKDIR /haze/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY source/Haze.py .
COPY source/classes.py .
COPY source/functions.py .

ENV DB_LOCATION /database

CMD [ "python", "/haze/Haze.py" ]

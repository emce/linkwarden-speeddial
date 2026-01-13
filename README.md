# Linkwarden Speed Dial
A Speed Dial page for browser based on data from Linkwarden (a bit familiar to speeddial2.com).
Links are created based on selected collections.

## Features

- Collections chooser (based on configuration) - based on specific link one can set different collection on different device as speed dial.
- Theme support (auto/dark/light)
- Background setting (image via url/color)
- Bookmarks sidebar (based on data from Linkwarden)
- Data is stored locally (local storage)

## Configuration

Create `.env` based on `.env.template` to apply your configuration:
```dotenv
FLASK_SECRET_KEY=dev-change-me
FLASK_PORT=9018
FLASK_HOST=127.0.0.1
FLASK_DEBUG=true
LINKWARDEN_URL=https://linkwarden.example
LINKWARDEN_USERNAME=username
LINKWARDEN_TOKEN=
LINKWARDEN_PASSWORD=
### number (or numbers, if you want additional tabs) from link, like https://linkwarden.example/collections/50
LINKWARDEN_COLLECTION=[50,51]
LINKWARDEN_COLLECTION_NAME="Linkwarden SpeedDial"
LINKWARDEN_COLLECTION_COLUMNS=(4-12)
LINKWARDEN_COLLECTION_SPACING=(4-36)
LINKWARDEN_COLLECTION_SORT=(date_desc|date_asc|name_asc|name_desc)
SPEEDDIAL_THEME=(auto|dark|light)
SPEEDDIAL_BACKGROUND=(wallpaper|color)
SPEEDDIAL_WALLPAPER_URL=
SPEEDDIAL_BACKGROUND_COLOR=(black|#FFFFFF)
SPEEDDIAL_TEXT_COLOR=(black|#FFFFFF)
SPEEDDIAL_OPEN_IN_NEW_TAB=(true|false)
SPEEDDIAL_BOOKMARKS=false
SPEEDDIAL_PASSWORD=
SPEEDDIAL_UNLOCK_TTL_MINUTES=(0-525600)
HOSTNAME=speeddial
TZ=Europe/Warsaw
LANG=pl_PL.UTF-8
LANGUAGE=pl_PL:pl
LC_ALL=pl_PL.UTF-8
```


## Security

This is single user application, to make your data secure, use `SPEEDDIAL_PASSWORD` to set password to be checked and `SPEEDDIAL_UNLOCK_TTL_MINUTES` to set lifetime of cookie for this session.

## Screenshots

![Main grid](images/screen_1.png)

![Sidebar](images/screen_2.png)

![Password](images/screen_3.png)

## Deployment

You can build this app as docker or podman image, here's Dockerfile to build image:
```dockerfile
FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY . .

EXPOSE 9018

CMD ["python", "app.py"]
```

And here's example compose file code:
```yaml
services:
    tools:
        container_name: linkwarden-speeddial
        build:
            context: .
            dockerfile: Dockerfile
        env_file:
            - .env
        ports:
            - "9018:9018"
        volumes:
            - ./:/code
```

## Development

App is build with Flask, in Python environment. It uses HTML and CSS, templates are written in Jinja2.
In order to run application, create virtual environment:
```shell
python3 -m venv .venv
```
Then, using `pip` install dependencies:
```shell
python3 -m pip install -r requirements.txt
```
Run application with:
```shell
python3 app.py
```
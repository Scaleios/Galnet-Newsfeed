#  Copyright (c) 2020 Hassan Abouelela
#  Licensed under the MIT License

import datetime
import json
import os
import re
from urllib.parse import unquote

import aiohttp
import asyncpg
from bs4 import BeautifulSoup as Bs4

from python import articlesearch


async def db_builder(host: str, database: str, table: str = "Articles", create_table=True, user: str = "postgres",
                     passfile=None, password: str = None, ssl=False, port: int = None):
    """Builds an article database, with all articles to date."""
    # Establishing DB Connection
    connection = await asyncpg.connect(host=host, port=port, user=user, password=password,
                                       passfile=passfile, database=database, ssl=ssl)

    # Make table if one is not provided
    if create_table:
        table = table.strip()
        await connection.execute(f"""
        CREATE TABLE "{table}" (
        "ID" serial NOT NULL, 
        "Title" text, 
        "UID" text, 
        "dateReleased" date, 
        "dateAdded" date, 
        "Text" text,
        PRIMARY KEY ("ID"));
        ALTER TABLE "{table}" OWNER to "{user}";
        """)

    # Collecting Links and articles
    links = []
    date_now = datetime.datetime.now().strftime("%Y-%m-%d")

    async with aiohttp.ClientSession() as session:
        async with session.get("https://community.elitedangerous.com/#") as response:
            bs4 = Bs4(await response.text(), "html.parser")

    for entry in bs4.find_all(id="block-frontier-galnet-frontier-galnet-block-filter"):
        for link in entry.find_all("a"):
            links.append(link.get("href"))
    links.reverse()

    for result in links:
        date_article = datetime.datetime.strptime(result.replace("#", "")[re.search("^/galnet/", result).end():],
                                                  "%d-%b-%Y")
        if date_article.year >= 3300:
            date_article = date_article.replace(year=(date_article.year - articlesearch.GAME_YEAR_OFFSET))
        date_article = date_article.strftime("%Y-%m-%d")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://community.elitedangerous.com{result}") as response:
                bs4 = Bs4(await response.text(), "html.parser")

        for entry in bs4.find_all("h3", {"class": "hiLite galnetNewsArticleTitle"}):
            entry_title = entry.get_text().strip().replace("'", "''")
            if entry_title == "" or entry_title is None:
                entry_title = "No Title Available"

            entry_uid = entry.find("a").get("href")[re.search("^/galnet/uid/", entry.find("a").get("href")).end():]

            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://community.elitedangerous.com/galnet/uid/{entry_uid}/") as response:
                    bs4 = Bs4(await response.text(), "html.parser")
            text = unquote(bs4.find_all("p")[1].get_text().replace("'", "''"))

            await connection.execute(f"""
            INSERT INTO "{table}"("Title", "UID", "dateReleased", "dateAdded", "Text")
            VALUES($1, $2, $3, $4, $5);""", entry_title, entry_uid, date_article, date_now, text)

    await connection.close()

    # Dumping Settings For Future Use
    if os.path.exists("Settings.json"):
        os.remove("Settings.json")

    settings = await articlesearch.fetch_settings()
    settings["previous version"] = settings["version"]

    settings["host"] = host
    settings["database"] = database
    settings["table"] = table
    settings["user"] = user
    settings["passfile"] = passfile
    settings["password"] = password
    settings["ssl"] = ssl
    settings["port"] = port

    with open("Settings.json", "w+") as settings_file:
        json.dump(settings, settings_file, indent=2)

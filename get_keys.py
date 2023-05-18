import requests
import xmltodict
import json
import base64
from pathlib import Path
import subprocess
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import sqlite3
import os
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

common_headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0',
}

license_headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'es-MX,es;q=0.8,en-US;q=0.5,en;q=0.3',
    # 'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.udemy.com/course/blendertutorial/learn/lecture/32904468',
    'Content-Type': 'application/octet-stream',
    'Origin': 'https://www.udemy.com',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    # Requests doesn't support trailers
    # 'TE': 'trailers',
}

dbconnection = sqlite3.connect("database.db")
dbcursor = dbconnection.cursor()
dbcursor.execute('CREATE TABLE IF NOT EXISTS "udemy" ( cid TEXT, "pssh" TEXT, "keys" TEXT, PRIMARY KEY("pssh") )')
dbconnection.close()

def cache_key(cid: str, cpssh: str, ckeys: str):
    dbconnection = sqlite3.connect("database.db")
    dbcursor = dbconnection.cursor()
    dbcursor.execute("INSERT or REPLACE INTO udemy VALUES (?, ?, ?)", (cid, cpssh, ckeys))
    dbconnection.commit()
    dbconnection.close()

def selectKey(pssh):
    try:
        con = sqlite3.connect("database.db")
        cursor = con.cursor()
        SELECT_SQL = f"SELECT * FROM udemy WHERE pssh = '{pssh}'"
        cursor.execute(SELECT_SQL)
        SELECT_RESULTS = cursor.fetchall()

        return SELECT_RESULTS
    except Exception as E:
        print(E)

def selectKeyByCid(cid):
    try:
        con = sqlite3.connect("database.db")
        cursor = con.cursor()
        SELECT_SQL = f"SELECT * FROM udemy WHERE cid = '{cid}'"
        cursor.execute(SELECT_SQL)
        SELECT_RESULTS = cursor.fetchall()

        return SELECT_RESULTS
    except Exception as E:
        print(E)

def find_wv_pssh_offset(raw: bytes) -> str:
    #print('Searching pssh offset')
    offset = raw.rfind(b'pssh')
    return raw[offset - 4:offset - 4 + raw[offset - 1]]


def to_pssh(content: bytes) -> str:
    wv_offset = find_wv_pssh_offset(content)
    return base64.b64encode(wv_offset).decode()


def from_file(file_path: str) -> str:
    #print('Extracting PSSH from init file:', file_path)
    # esto obtiene todos los pssh si hay varios DRM
    #source: https://forum.videohelp.com/threads/405001-How-to-get-the-widevine-pssh-from-init-mp4-JUST-using-python-script#post2650501
    return to_pssh(Path(file_path).read_bytes())

def getInit(url, local_filename="init.mp4"):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                f.write(chunk)
def getPSSH():
    # source: https://forum.videohelp.com/threads/405001-How-to-get-the-widevine-pssh-from-init-mp4-JUST-using-python-script#post2688839
    mp4dump = subprocess.Popen(['mp4dump', '--verbosity', '3', '--format', 'json', 'init.mp4'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    dump = (mp4dump.stdout.read())
    json_info = json.loads(dump.decode("utf-8"))

def getKeys(cid, pssh, license_url):
    print("Obtaining keys for:")
    print("PSSH: {}".format(pssh))
    print("License URL: {}".format(license_url))
    ipssh = pssh
    pssh = PSSH(pssh)
    device = Device.load("/contnet/wvd.wvd")
    cdm = Cdm.from_device(device)

    session_id = cdm.open()
    challenge = cdm.get_license_challenge(session_id, pssh)

    licence = requests.post(license_url, data=challenge, headers=license_headers)

    licence.raise_for_status()
    cdm.parse_license(session_id, licence.content)
    fkeys = ""
    for key in cdm.get_keys(session_id):
        if key.type != 'SIGNING':
            fkeys += key.kid.hex + ":" + key.key.hex() + "\n"
    cache_key(cid, ipssh, fkeys)
    print("")
    print(fkeys)
    cdm.close(session_id)

def getMPD(url, driver):
   
    #mpd = requests.get(url, headers=common_headers)
    mpd = getPage(url, driver, inJson=False)

    xml = xmltodict.parse(mpd)

    audio = False
    video_pssh = ""

    for adapt in xml["MPD"]["Period"]["AdaptationSet"]:
        mime = adapt["@mimeType"]
        #print(mime)
        for repr in adapt["Representation"]:
            getInit(repr["SegmentTemplate"]["@initialization"])

            if mime == "video/mp4":
                width = repr["@width"]
                height = repr["@height"]
                framerate = repr["@frameRate"]
                codecs = repr["@codecs"]
                bandwidth = repr["@bandwidth"]
                if int(height) >= 1000:
                    # print("""
                    # width: {}
                    # height: {}
                    # framerate: {}
                    # codecs: {}
                    # bandwidth: {}
                    # pssh: {}
                    # """.format(width, height, framerate, codecs, bandwidth, from_file("init.mp4") ))

                    video_pssh = from_file("init.mp4")

            
            if mime == "audio/mp4":
                audioSamplingRate = repr["@audioSamplingRate"]
                codecs = repr["@codecs"]
                bandwidth = repr["@bandwidth"]
                channels = repr["AudioChannelConfiguration"]["@value"]
                # if not audio: 
                #     print("""
                #     sampling: {}
                #     channels: {}
                #     codecs: {}
                #     bandwidth: {}
                #     pssh: {}
                #     """.format(audioSamplingRate, channels, codecs, bandwidth, from_file("init.mp4") ))

                audio = True
    os.remove("init.mp4")

    return video_pssh
            
def getLecture(cid, id, driver):
    # response = requests.get("https://www.udemy.com/api-2.0/users/me/subscribed-courses/{}/lectures/{}/?fields[lecture]=asset,description,download_url,is_free,last_watched_second&fields[asset]=asset_type,length,media_license_token,course_is_drmed,media_sources,captions,thumbnail_sprite,slides,slide_urls,download_urls,external_url".format(cid, id),
    #     cookies=cookies,
    #     headers=headers
    # )
    res = getPage("https://www.udemy.com/api-2.0/users/me/subscribed-courses/{}/lectures/{}/?fields[lecture]=asset,description,download_url,is_free,last_watched_second&fields[asset]=asset_type,length,media_license_token,course_is_drmed,media_sources,captions,thumbnail_sprite,slides,slide_urls,download_urls,external_url".format(cid, id), driver)
    if res["asset"]["media_license_token"]:
        return "https://www.udemy.com/api-2.0/media-license-server/validate-auth-token?drm_type=widevine&auth_token=" + res["asset"]["media_license_token"]

def getPage(url, driver, inJson=True):
    if not driver:
        print("Not driver")
        exit()
    driver.get(url)
    info = driver.find_element(By.CSS_SELECTOR, "body").text
    
    if inJson:
        try:
            WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#rawdata-tab")))
            button = driver.find_element(By.CSS_SELECTOR, "#rawdata-tab")
            driver.execute_script("arguments[0].click();", button)
            info = driver.find_element(By.CSS_SELECTOR, "pre.data").text
            return json.loads(info)
        except:
            info = driver.find_element(By.CSS_SELECTOR, "body").text
            return info
            
        
    else:
        return info

def parse(json_res, cid, driver):
    for res in json_res["results"]:
        if res["_class"] == "lecture":
            #print(res["title"])
            #print(res["id"])
            # this way doesn't get updated
            # if res["asset"]["media_license_token"]:
            #     print("https://www.udemy.com/api-2.0/media-license-server/validate-auth-token?drm_type=widevine&auth_token=" + res["asset"]["media_license_token"])
            for media in res["asset"]["media_sources"]:
                if media["type"] == "application/dash+xml":
                    #print(media["src"])
                    pssh = getMPD(media["src"], driver)
                    key_res = selectKey(pssh)
                    if key_res:
                        print("this pssh is already on the database")
                        keys = key_res[0][2]
                        kid,key = keys.split("\n")[0].split(":")
                        with open("/home/pansutodeus/sync/wv/udemy-downloader-1/keyfile.json", "w") as f:
                            f.write('{{\n"{}":"{}"\n}}'.format(kid, key))
                        print('!echo \'{{"{}":"{}"}}\' > keyfile.json'.format(kid, key))
                        print('key_id={}:key={}'.format(kid,key))

                    else:
                        getKeys( cid, pssh , getLecture(cid, res["id"], driver))

                    return

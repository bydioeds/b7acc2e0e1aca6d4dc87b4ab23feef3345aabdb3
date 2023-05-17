import argparse
import os 
from get_keys import selectKeyByCid, getPage, parse
from pathvalidate import sanitize_filename
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium import webdriver
import m3u8
import json
import yt_dlp
from typing import IO
import subprocess
import time
from utils import extract_kid
from unidecode import unidecode

download_dir = os.path.join(os.getcwd(), "downloads")
course_id = None
driver = None
home_dir = os.getcwd()
keys = {}

class Selenium:
    def __init__(self):
        options = FirefoxOptions()
        options.add_argument("-profile")
        options.add_argument("/home/pansutodeus/.mozilla/firefox/selenium")
        
        self._driver = webdriver.Remote(command_executor="http://104.193.110.16:55555", desired_capabilities=None, options=options)
    
    @property
    def driver(self):
        return self._driver
def decrypt(kid, in_filepath, out_filepath):
    try:
        key = keys[kid.lower()]
    except KeyError:
        raise KeyError("Key not found")

    if os.name == "nt":
        command = f'shaka-packager --enable_raw_key_decryption --keys key_id={kid}:key={key} input="{in_filepath}",stream_selector="0",output="{out_filepath}"'
    else:
        command = f'nice -n 7 shaka-packager --enable_raw_key_decryption --keys key_id={kid}:key={key} input="{in_filepath}",stream_selector="0",output="{out_filepath}"'

    process = subprocess.Popen(command, shell=True)
    log_subprocess_output("SHAKA-STDOUT", process.stdout)
    log_subprocess_output("SHAKA-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Decryption returned a non-zero exit code")

    return ret_code

def get_course_info(cid, driver):
    info_url = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/".format(portal_name="www", course_id=cid)
    
    return getPage(info_url, driver)

def get_course_json_large(url, driver):
    url = url.replace("10000", "50") if url.endswith("10000") else url

    try:
        course_json = getPage(url, driver)

        if not course_json or not isinstance(course_json, dict):
            print("Could not get json")
    except:
        print("Something went wrong extracting course json")
        exit()
    else:
        _next = course_json.get("next")

        while _next:
            try:
                resp = getPage(_next, driver)

                if not course_json or not isinstance(course_json, dict):
                    print("Could not get json")

            except:
                print("Something went wrong extracting course json")
                exit()
            else:
                _next = resp.get("next")

                results = resp.get("results")

                if results and isinstance(results, list):
                    for d in resp["results"]:
                        course_json["results"].append(d)
        return course_json

def get_course_json(cid, driver):
    course_url = "https://{portal_name}.udemy.com/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items?fields[asset]=results,title,external_url,time_estimation,download_urls,slide_urls,filename,asset_type,captions,media_license_token,course_is_drmed,media_sources,stream_urls,body&fields[chapter]=object_index,title,sort_order&fields[lecture]=id,title,object_index,asset,supplementary_assets,view_html&page_size=10000".format(portal_name="www", course_id=cid)

    info = getPage(course_url, driver)

    if isinstance(info, dict):
        return info
    else:
        if "502 Bad Gateway" in info or "We are having trouble reaching our servers" in info:
            print("The course is throwing a 502...")
            return get_course_json_large(course_url, driver)

def pre_run():
    global course_id, driver

    # if it doesn't exists we will make it
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    parser = argparse.ArgumentParser(description="Udemy Downloader")

    parser.add_argument(
        "-cid",
        "--course-id",
        dest="course_id",
        type=str,
        help="Course Id in numeral format. eg: 299209",
    )

    args = parser.parse_args()

    if args.course_id:
        course_id = args.course_id
    else:
        print("You need to specify a course id.")
        exit(1)
    
    driver = Selenium().driver
def durationtoseconds(period):
    """
    @author Jayapraveen
    """

    # Duration format in PTxDxHxMxS
    if period[:2] == "PT":
        period = period[2:]
        day = int(period.split("D")[0] if "D" in period else 0)
        hour = int(period.split("H")[0].split("D")[-1] if "H" in period else 0)
        minute = int(period.split("M")[0].split("H")[-1] if "M" in period else 0)
        second = period.split("S")[0].split("M")[-1]
        # print("Total time: " + str(day) + " days " + str(hour) + " hours " +
        #       str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) + (int(second.split(".")[0]))) + "." + str(int(second.split(".")[-1])))
        return total_time

    else:
        print("Duration Format Error")
        return None


def cleanup(path):
    """
    @author Jayapraveen
    """
    leftover_files = glob.glob(path + "/*.mp4", recursive=True)
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            print(f"Error deleting file: {file_list}")
    os.removedirs(path)


def mux_process(video_title, video_filepath, audio_filepath, output_path):
    """
    @author Jayapraveen
    """
    codec = "hevc_nvenc" if False else "libx265"
    transcode = "-hwaccel cuda -hwaccel_output_format cuda" if False else []
    if os.name == "nt":
        if False: #use_h265
            command = 'ffmpeg {} -y -i "{}" -i "{}" -c:v {} -crf {} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                transcode, video_filepath, audio_filepath, codec, h265_crf, h265_preset, video_title, output_path
            )
        else:
            command = 'ffmpeg -y -i "{}" -i "{}" -c:v copy  -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                video_filepath, audio_filepath, video_title, output_path
            )
    else:
        if False: #use_h265
            command = 'nice -n 7 ffmpeg {} -y -i "{}" -i "{}" -c:v libx265 -crf {} -preset {} -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                transcode, video_filepath, audio_filepath, codec, h265_crf, h265_preset, video_title, output_path
            )
        else:
            command = 'nice -n 7 ffmpeg -y -i "{}" -i "{}" -c:v copy -c:a copy -fflags +bitexact -map_metadata -1 -metadata title="{}" "{}"'.format(
                video_filepath, audio_filepath, video_title, output_path
            )
    print(command)
    process = subprocess.Popen(command, shell=True)
    log_subprocess_output("FFMPEG-STDOUT", process.stdout)
    log_subprocess_output("FFMPEG-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Muxing returned a non-zero exit code")

    return ret_code
def _extract_m3u8( url, title):
    global driver
    """extracts m3u8 streams"""
    _temp = []
    try:
        resp = getPage(url, driver, inJson=False)
        mpd_filename = "downloads/streams/{}.m3u8".format(sanitize_filename(title)).replace("#", "")
        try:
            os.remove(mpd_filename)
        except:
            pass

        with open(mpd_filename, "w") as f:
            f.write(resp)
        raw_data = resp
        m3u8_object = m3u8.loads(raw_data)
        playlists = m3u8_object.playlists
        seen = set()
        for pl in playlists:
            resolution = pl.stream_info.resolution
            codecs = pl.stream_info.codecs
            if not resolution:
                continue
            if not codecs:
                continue
            width, height = resolution
            download_url = pl.uri
            if height not in seen:
                seen.add(height)
                _temp.append(
                    {
                        "type": "hls",
                        "height": height,
                        "width": width,
                        "extension": "mp4",
                        "download_url": download_url,
                    }
                )
                
                res = getPage(download_url, driver, inJson=False)
                mpd_filename = "downloads/streams/{}.m3u8".format(sanitize_filename(title + "-" + str(height)))
                try:
                    os.remove(mpd_filename)
                except:
                    pass

                with open(mpd_filename, "w") as f:
                    f.write(res)
    except Exception as error:
        print(f"[-] Udemy Says : '{error}' while fetching hls streams..")
    return _temp

def _extract_mpd( url, title):
    """extracts mpd streams"""
    _temp = []
    try:
        
        mpd = getPage(url, driver, inJson=False)
        mpd_filename = "downloads/streams/{}.mpd".format(sanitize_filename(title)).replace("#", "")
        try:
            os.remove(mpd_filename)
        except:
            pass

        with open(mpd_filename, "w") as f:
            f.write(mpd)
        ytdl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "allow_unplayable_formats": True, "enable_file_urls": True})
        results = ytdl.extract_info("file://" + os.getcwd() + "/" + mpd_filename, download=False, force_generic_extractor=True)
        seen = set()
        formats = results.get("formats")

        format_id = results.get("format_id")
        best_audio_format_id = format_id.split("+")[1]
        # I forget what this was for
        # best_audio = next((x for x in formats
        #                    if x.get("format_id") == best_audio_format_id),
        #                   None)
        for f in formats:
            if "video" in f.get("format_note"):
                # is a video stream
                format_id = f.get("format_id")
                extension = f.get("ext")
                height = f.get("height")
                width = f.get("width")

                if height and height not in seen:
                    seen.add(height)
                    _temp.append(
                        {
                            "type": "dash",
                            "height": str(height),
                            "width": str(width),
                            "format_id": f"{format_id},{best_audio_format_id}",
                            "extension": extension,
                            "download_url": f.get("manifest_url"),
                        }
                    )
            # ignore audio tracks
            else:
                continue
    except Exception as e:
        print(e)
        print(f"[-] Error fetching MPD streams")
    return _temp

def _extract_media_sources(sources, title):
        _temp = []
        if sources and isinstance(sources, list):
            for source in sources:
                _type = source.get("type")
                src = source.get("src")

                if _type == "application/dash+xml":
                    out = _extract_mpd(src, title)
                    if out:
                        _temp.extend(out)
        return _temp

def _extract_subtitles(tracks):
        _temp = []
        if tracks and isinstance(tracks, list):
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                if track.get("_class") != "caption":
                    continue
                download_url = track.get("url")
                if not download_url or not isinstance(download_url, str):
                    continue
                lang = track.get("language") or track.get("srclang") or track.get("label") or track["locale_id"].split("_")[0]
                ext = "vtt" if "vtt" in download_url.rsplit(".", 1)[-1] else "srt"
                _temp.append(
                    {
                        "type": "subtitle",
                        "language": lang,
                        "extension": ext,
                        "download_url": download_url,
                    }
                )
        return _temp

def _extract_sources(sources, skip_hls, title):
        _temp = []
        if sources and isinstance(sources, list):
            for source in sources:
                label = source.get("label")
                download_url = source.get("file")
                if not download_url:
                    continue
                if label.lower() == "audio":
                    continue
                height = label if label else None
                if height == "2160":
                    width = "3840"
                elif height == "1440":
                    width = "2560"
                elif height == "1080":
                    width = "1920"
                elif height == "720":
                    width = "1280"
                elif height == "480":
                    width = "854"
                elif height == "360":
                    width = "640"
                elif height == "240":
                    width = "426"
                else:
                    width = "256"
                if source.get("type") == "application/x-mpegURL" or "m3u8" in download_url:
                    if not skip_hls:
                        out = _extract_m3u8(download_url, title)
                        if out:
                            _temp.extend(out)
                else:
                    _type = source.get("type")
                    _temp.append(
                        {
                            "type": "video",
                            "height": height,
                            "width": width,
                            "extension": _type.replace("video/", ""),
                            "download_url": download_url,
                        }
                    )
        return _temp

def _extract_ppt(asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Presentation", [])[0].get("file")
            _temp.append({"type": "presentation", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

def _extract_file(asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("File", [])[0].get("file")
            _temp.append({"type": "file", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

def _extract_ebook(asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("E-Book", [])[0].get("file")
            _temp.append({"type": "ebook", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp

def _extract_audio(asset, lecture_counter):
        _temp = []
        download_urls = asset.get("download_urls")
        filename = asset.get("filename")
        id = asset.get("id")
        if download_urls and isinstance(download_urls, dict):
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            download_url = download_urls.get("Audio", [])[0].get("file")
            _temp.append({"type": "audio", "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
        return _temp
def handle_segments(url, format_id, video_title, output_path, lecture_file_name, chapter_dir, localmpd):
    global home_dir
    print(url)
    os.chdir(os.path.join(chapter_dir))
    file_name = lecture_file_name.replace("%", "")
    
    # for french language among others, this characters cause problems with shaka-packager resulting in decryption failure
    # https://github.com/Puyodead1/udemy-downloader/issues/137
    # Thank to cutecat !
    file_name = (
        file_name.replace("é", "e")
        .replace("è", "e")
        .replace("à", "a")
        .replace("À", "A")
        .replace("à", "a")
        .replace("Á", "A")
        .replace("á", "a")
        .replace("Â", "a")
        .replace("â", "a")
        .replace("Ã", "A")
        .replace("ã", "a")
        .replace("Ä", "A")
        .replace("ä", "a")
        .replace("Å", "A")
        .replace("å", "a")
        .replace("Æ", "AE")
        .replace("æ", "ae")
        .replace("Ç", "C")
        .replace("ç", "c")
        .replace("Ð", "D")
        .replace("ð", "o")
        .replace("È", "E")
        .replace("è", "e")
        .replace("É", "e")
        .replace("Ê", "e")
        .replace("ê", "e")
        .replace("Ë", "E")
        .replace("ë", "e")
        .replace("Ì", "I")
        .replace("ì", "i")
        .replace("Í", "I")
        .replace("í", "I")
        .replace("Î", "I")
        .replace("î", "i")
        .replace("Ï", "I")
        .replace("ï", "i")
        .replace("Ñ", "N")
        .replace("ñ", "n")
        .replace("Ò", "O")
        .replace("ò", "o")
        .replace("Ó", "O")
        .replace("ó", "o")
        .replace("Ô", "O")
        .replace("ô", "o")
        .replace("Õ", "O")
        .replace("õ", "o")
        .replace("Ö", "o")
        .replace("ö", "o")
        .replace("œ", "oe")
        .replace("Œ", "OE")
        .replace("Ø", "O")
        .replace("ø", "o")
        .replace("ß", "B")
        .replace("Ù", "U")
        .replace("ù", "u")
        .replace("Ú", "U")
        .replace("ú", "u")
        .replace("Û", "U")
        .replace("û", "u")
        .replace("Ü", "U")
        .replace("ü", "u")
        .replace("Ý", "Y")
        .replace("ý", "y")
        .replace("Þ", "P")
        .replace("þ", "P")
        .replace("Ÿ", "Y")
        .replace("ÿ", "y")
        .replace("%", "")
    )
    # commas cause problems with shaka-packager resulting in decryption failure
    file_name = file_name.replace(",", "")
    file_name = unidecode(file_name)
    file_name = file_name.replace('"', "")
    file_name = file_name.replace(".mp4", "")

    video_filepath_enc = file_name + ".encrypted.mp4"
    audio_filepath_enc = file_name + ".encrypted.m4a"
    video_filepath_dec = file_name + ".decrypted.mp4"
    audio_filepath_dec = file_name + ".decrypted.m4a"
    print("> Downloading Lecture Tracks...")
    args = [
        "yt-dlp",
        "--enable-file-urls",
        "--force-generic-extractor",
        "--allow-unplayable-formats",
        "--concurrent-fragments",
        "10",
        "--downloader",
        "aria2c",
        "--fixup",
        "never",
        "-k",
        "-o",
        f"{file_name}.encrypted.%(ext)s",
        "-f",
        format_id,
        f"{localmpd}",
    ]
    if True: #disable_ipv6
        args.append("--downloader-args")
        args.append('aria2c:"--disable-ipv6"')
    process = subprocess.Popen(args)
    log_subprocess_output("YTDLP-STDOUT", process.stdout)
    log_subprocess_output("YTDLP-STDERR", process.stderr)
    ret_code = process.wait()
    print("> Lecture Tracks Downloaded")

    if ret_code != 0:
        print("Return code from the downloader was non-0 (error), skipping!")
        return

    try:
        video_kid = extract_kid(video_filepath_enc)
        print("KID for video file is: " + video_kid)
    except Exception:
        print(f"Error extracting video kid")
        return

    try:
        audio_kid = extract_kid(audio_filepath_enc)
        print("KID for audio file is: " + audio_kid)
    except Exception:
        print(f"Error extracting audio kid")
        return

    try:
        print("> Decrypting video, this might take a minute...")
        ret_code = decrypt(video_kid, video_filepath_enc, video_filepath_dec)
        if ret_code != 0:
            print("> Return code from the decrypter was non-0 (error), skipping!")
            return
        print("> Decryption complete")
        print("> Decrypting audio, this might take a minute...")
        decrypt(audio_kid, audio_filepath_enc, audio_filepath_dec)
        if ret_code != 0:
            print("> Return code from the decrypter was non-0 (error), skipping!")
            return
        print("> Decryption complete")
        print("> Merging video and audio, this might take a minute...")
        mux_process(video_title, video_filepath_dec, audio_filepath_dec, output_path)
        if ret_code != 0:
            print("> Return code from ffmpeg was non-0 (error), skipping!")
            return
        print("> Merging complete, removing temporary files...")
        os.remove(video_filepath_enc)
        os.remove(audio_filepath_enc)
        os.remove(video_filepath_dec)
        os.remove(audio_filepath_dec)
    except Exception as e:
        print(f"Error: ")
        print(e)
    finally:
        os.chdir(home_dir)

def process_lecture(lecture, lecture_path, lecture_file_name, chapter_dir, course_name):
    lecture_title = lecture.get("lecture_title")
    is_encrypted = lecture.get("is_encrypted")
    lecture_sources = lecture.get("video_sources")
    quality = 1080

    if is_encrypted:
        if len(lecture_sources) > 0:
            source = lecture_sources[-1]  # last index is the best quality
            if isinstance(quality, int):
                source = min(lecture_sources, key=lambda x: abs(int(x.get("height")) - quality))
            print(f"      > Lecture '%s' has DRM, attempting to download" % lecture_title)
            localmpd = "file://" + os.getcwd() + "/downloads/streams/" + course_name + " - " + lecture_title+".mpd"
            handle_segments(source.get("download_url"), source.get("format_id"), lecture_title, lecture_path, lecture_file_name, chapter_dir, localmpd.replace("#", ""))
        else:
            print(f"      > Lecture '%s' is missing media links" % lecture_title)
            print(f"Lecture source count: {len(lecture_sources)}")
    else:
        sources = lecture.get("sources")
        sources = sorted(sources, key=lambda x: int(x.get("height")), reverse=True)
        if sources:
            if not os.path.isfile(lecture_path):
                print("      > Lecture doesn't have DRM, attempting to download...")
                source = sources[0]  # first index is the best quality
                if isinstance(quality, int):
                    source = min(sources, key=lambda x: abs(int(x.get("height")) - quality))
                try:
                    print("      ====== Selected quality: %s %s", source.get("type"), source.get("height"))
                    url = source.get("download_url")
                    source_type = source.get("type")
                    print(url)
                    print(source_type)
                    
                    localm3u8 = "file://" + os.getcwd() + "/downloads/streams/" + course_name + " - " + lecture_title+"-{}.m3u8".format(quality)

                    print(localm3u8)
                    if source_type == "hls":
                        temp_filepath = lecture_path.replace(".mp4", ".%(ext)s")
                        cmd = [ "yt-dlp", 
                                "--force-generic-extractor", 
                                "--concurrent-fragments", "10", 
                                "--downloader", "aria2c", 
                                "--enable-file-urls",
                                "-o", f"{temp_filepath}", f"{localm3u8}"]
                        print(cmd)
                        if True:
                            cmd.append("--downloader-args")
                            cmd.append('aria2c:"--disable-ipv6"')
                        process = subprocess.Popen(cmd)
                        log_subprocess_output("YTDLP-STDOUT", process.stdout)
                        log_subprocess_output("YTDLP-STDERR", process.stderr)
                        ret_code = process.wait()
                        print(ret_code)
                        if ret_code == 0:
                            tmp_file_path = lecture_path + ".tmp"
                            print("      > HLS Download success")
                            if False: #use_h265
                                codec = "hevc_nvenc" if False else "libx265"
                                transcode = "-hwaccel cuda -hwaccel_output_format cuda".split(" ") if False else []
                                cmd = ["ffmpeg", *transcode, "-y", "-i", lecture_path, "-c:v", codec, "-c:a", "copy", "-f", "mp4", tmp_file_path]
                                process = subprocess.Popen(cmd)
                                log_subprocess_output("FFMPEG-STDOUT", process.stdout)
                                log_subprocess_output("FFMPEG-STDERR", process.stderr)
                                ret_code = process.wait()
                                if ret_code == 0:
                                    os.unlink(lecture_path)
                                    os.rename(tmp_file_path, lecture_path)
                                    print("      > Encoding complete")
                                else:
                                    print("      > Encoding returned non-zero return code")
                    else:
                        ret_code = download_aria(url, chapter_dir, lecture_title + ".mp4")
                        print(f"      > Download return code: {ret_code}")
                except Exception as e:
                    print(e)
                    print(f">        Error downloading lecture")
                    exit(1)
            else:
                print(f"      > Lecture '{lecture_title}' is already downloaded, skipping...")
        else:
            print("      > Missing sources for lecture", lecture)
def process_caption(caption, lecture_title, lecture_dir, tries=0):
    filename = f"%s_%s.%s" % (sanitize_filename(lecture_title), caption.get("language"), caption.get("extension"))
    filename_no_ext = f"%s_%s" % (sanitize_filename(lecture_title), caption.get("language"))
    filepath = os.path.join(lecture_dir, filename)

    if os.path.isfile(filepath):
        print("    > Caption '%s' already downloaded." % filename)
    else:
        print(f"    >  Downloading caption: '%s'" % filename)
        try:
            ret_code = download_aria(caption.get("download_url"), lecture_dir, filename)
            print(f"      > Download return code: {ret_code}")
        except Exception as e:
            if tries >= 3:
                print(f"    > Error downloading caption: {e}. Exceeded retries, skipping.")
                return
            else:
                print(f"    > Error downloading caption: {e}. Will retry {3-tries} more times.")
                process_caption(caption, lecture_title, lecture_dir, tries + 1)
        if caption.get("extension") == "vtt":
            try:
                print("    > Converting caption to SRT format...")
                convert(lecture_dir, filename_no_ext)
                print("    > Caption conversion complete.")
                if not keep_vtt:
                    os.remove(filepath)
            except Exception:
                print(f"    > Error converting caption")
def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(lambda: pipe.read(1), ""):
            print("[%s]: %r", prefix, line.decode("utf8").strip())
        pipe.flush()

def download_aria(url, file_dir, filename):
    """
    @author Puyodead1
    """
    args = ["aria2c", url, "-o", filename, "-d", file_dir, "-j16", "-s20", "-x16", "-c", "--auto-file-renaming=false", "--summary-interval=0"]
    if True:
        args.append("--disable-ipv6")
    process = subprocess.Popen(args)
    log_subprocess_output("ARIA2-STDOUT", process.stdout)
    log_subprocess_output("ARIA2-STDERR", process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception("Return code from the downloader was non-0 (error)")
    return ret_code

def parse_new(_udemy):
    total_chapters = _udemy.get("total_chapters")
    total_lectures = _udemy.get("total_lectures")
    dl_captions = True
    caption_locale = "all"
    dl_assets = True
    print(f"Chapter(s) ({total_chapters})")
    print(f"Lecture(s) ({total_lectures})")

    course_name = _udemy.get("course_title")
    course_dir = os.path.join(download_dir, course_name)
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)

    for chapter in _udemy.get("chapters"):
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_dir = os.path.join(course_dir, chapter_title)
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)
        print(f"======= Processing chapter {chapter_index} of {total_chapters} =======")

        for lecture in chapter.get("lectures"):
            lecture_title = lecture.get("lecture_title")
            lecture_index = lecture.get("lecture_index")
            lecture_extension = lecture.get("extension")
            extension = "mp4"  # video lectures dont have an extension property, so we assume its mp4
            if lecture_extension != None:
                # if the lecture extension property isnt none, set the extension to the lecture extension
                extension = lecture_extension
            lecture_file_name = sanitize_filename(lecture_title + "." + extension)
            lecture_path = os.path.join(chapter_dir, lecture_file_name)

            print(f"  > Processing lecture {lecture_index} of {total_lectures}")
            
            # Check if the lecture is already downloaded
            if os.path.isfile(lecture_path):
                print("      > Lecture '%s' is already downloaded, skipping..." % lecture_title)
            else:
                # Check if the file is an html file
                if extension == "html":
                    # if the html content is None or an empty string, skip it so we dont save empty html files
                    if lecture.get("html_content") != None and lecture.get("html_content") != "":
                        html_content = lecture.get("html_content").encode("ascii", "ignore").decode("utf8")
                        lecture_path = os.path.join(chapter_dir, "{}.html".format(sanitize_filename(lecture_title)))
                        try:
                            with open(lecture_path, encoding="utf8", mode="w") as f:
                                f.write(html_content)
                                f.close()
                        except Exception:
                            print("    > Failed to write html file")
                else:
                    process_lecture(lecture, lecture_path, lecture_file_name, chapter_dir, course_name)

            # download subtitles for this lecture
            subtitles = lecture.get("subtitles")
            if dl_captions and subtitles != None and lecture_extension == None:
                print("Processing {} caption(s)...".format(len(subtitles)))
                for subtitle in subtitles:
                    lang = subtitle.get("language")
                    if lang == caption_locale or caption_locale == "all":
                        process_caption(subtitle, lecture_title, chapter_dir)

            if dl_assets:
                assets = lecture.get("assets")
                print("    > Processing {} asset(s) for lecture...".format(len(assets)))

                for asset in assets:
                    asset_type = asset.get("type")
                    filename = asset.get("filename")
                    download_url = asset.get("download_url")

                    if asset_type == "article":
                        print(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        print("AssetType: Article; AssetData: ", asset)
                        # html_content = lecture.get("html_content")
                        # lecture_path = os.path.join(
                        #     chapter_dir, "{}.html".format(sanitize(lecture_title)))
                        # try:
                        #     with open(lecture_path, 'w') as f:
                        #         f.write(html_content)
                        #         f.close()
                        # except Exception as e:
                        #     print("Failed to write html file: ", e)
                        #     continue
                    elif asset_type == "video":
                        print(
                            "If you're seeing this message, that means that you reached a secret area that I haven't finished! jk I haven't implemented handling for this asset type, please report this at https://github.com/Puyodead1/udemy-downloader/issues so I can add it. When reporting, please provide the following information: "
                        )
                        print("AssetType: Video; AssetData: ", asset)
                    elif asset_type == "audio" or asset_type == "e-book" or asset_type == "file" or asset_type == "presentation" or asset_type == "ebook":
                        try:
                            ret_code = download_aria(download_url, chapter_dir, filename)
                            print(f"      > Download return code: {ret_code}")
                        except Exception:
                            print("> Error downloading asset")
                    elif asset_type == "external_link":
                        # write the external link to a shortcut file
                        file_path = os.path.join(chapter_dir, f"{filename}.url")
                        file = open(file_path, "w")
                        file.write("[InternetShortcut]\n")
                        file.write(f"URL={download_url}")
                        file.close()

                        # save all the external links to a single file
                        savedirs, name = os.path.split(os.path.join(chapter_dir, filename))
                        filename = "external-links.txt"
                        filename = os.path.join(savedirs, filename)
                        file_data = []
                        if os.path.isfile(filename):
                            file_data = [i.strip().lower() for i in open(filename, encoding="utf-8", errors="ignore") if i]

                        content = "\n{}\n{}\n".format(name, download_url)
                        if name.lower() not in file_data:
                            with open(filename, "a", encoding="utf-8", errors="ignore") as f:
                                f.write(content)
                                f.close()


def _extract_supplementary_assets(supp_assets, lecture_counter):
        _temp = []
        for entry in supp_assets:
            title = sanitize_filename(entry.get("title"))
            filename = entry.get("filename")
            download_urls = entry.get("download_urls")
            external_url = entry.get("external_url")
            asset_type = entry.get("asset_type").lower()
            id = entry.get("id")
            if asset_type == "file":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("File", [])[0].get("file")
                    _temp.append({"type": "file", "title": title, "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
            elif asset_type == "sourcecode":
                if download_urls and isinstance(download_urls, dict):
                    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
                    download_url = download_urls.get("SourceCode", [])[0].get("file")
                    _temp.append({"type": "source_code", "title": title, "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": extension, "download_url": download_url, "id": id})
            elif asset_type == "externallink":
                _temp.append({"type": "external_link", "title": title, "filename": "{0:03d} ".format(lecture_counter) + filename, "extension": "txt", "download_url": external_url, "id": id})
        return _temp
def _print_course_info(course_data):
    print("\n\n\n\n")
    course_title = course_data.get("title")
    chapter_count = course_data.get("total_chapters")
    lecture_count = course_data.get("total_lectures")

    print("> Course: {}".format(course_title))
    print("> Total Chapters: {}".format(chapter_count))
    print("> Total Lectures: {}".format(lecture_count))
    print("\n")

    chapters = course_data.get("chapters")
    for chapter in chapters:
        chapter_title = chapter.get("chapter_title")
        chapter_index = chapter.get("chapter_index")
        chapter_lecture_count = chapter.get("lecture_count")
        chapter_lectures = chapter.get("lectures")

        print("> Chapter: {} ({} of {})".format(chapter_title, chapter_index, chapter_count))

        for lecture in chapter_lectures:
            lecture_title = lecture.get("lecture_title")
            lecture_index = lecture.get("index")
            lecture_asset_count = lecture.get("assets_count")
            lecture_is_encrypted = lecture.get("is_encrypted")
            lecture_subtitles = lecture.get("subtitles")
            lecture_extension = lecture.get("extension")
            lecture_sources = lecture.get("sources")
            lecture_video_sources = lecture.get("video_sources")

            if lecture_sources:
                lecture_sources = sorted(lecture.get("sources"), key=lambda x: int(x.get("height")), reverse=True)
            if lecture_video_sources:
                lecture_video_sources = sorted(lecture.get("video_sources"), key=lambda x: int(x.get("height")), reverse=True)

            if lecture_is_encrypted:
                lecture_qualities = ["{}@{}x{}".format(x.get("type"), x.get("width"), x.get("height")) for x in lecture_video_sources]
            elif not lecture_is_encrypted and lecture_sources:
                lecture_qualities = ["{}@{}x{}".format(x.get("type"), x.get("height"), x.get("width")) for x in lecture_sources]

            if lecture_extension:
                continue

            print("  > Lecture: {} ({} of {})".format(lecture_title, lecture_index, chapter_lecture_count))
            print("    > DRM: {}".format(lecture_is_encrypted))
            print("    > Asset Count: {}".format(lecture_asset_count))
            print("    > Captions: {}".format([x.get("language") for x in lecture_subtitles]))
            print("    > Qualities: {}".format(lecture_qualities))

        if chapter_index != chapter_count:
            print("==========================================")

def check_for_aria():
    try:
        subprocess.Popen(["aria2c", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        return True
    except FileNotFoundError:
        return False
    except Exception:
        print("> Unexpected exception while checking for Aria2c, please tell the program author about this! ")
        return True
def getkid(cid):
    global keys
    database_results = selectKeyByCid(cid)
    
    if database_results:
        print("This course is in the database")
        keyss = database_results[0][2]
        kid,key = keyss.split("\n")[0].split(":")
        
        keys[kid] = key
    else:
        info = getPage("https://www.udemy.com/api-2.0/courses/{}/subscriber-curriculum-items/?page_size=100&fields[lecture]=title,asset,description,download_url,is_free,last_watched_second&fields[asset]=asset_type,length,media_license_token,course_is_drmed,media_sources,captions,thumbnail_sprite,slides,slide_urls,download_urls,external_url&caching_intent=True".format(cid))
        parse(info, cid)
        getkid(cid)
def main():
    global keys
    
    skip_hls = False
    if course_id:
        getkid(course_id)
        print(keys)
        course_info = get_course_info(course_id, driver)
        title = sanitize_filename(course_info.get("title"))
        course_title = course_info.get("published_title")

        print(title, course_title)

        course_json = get_course_json(course_id, driver)

        course = course_json.get("results")
        resource = course_json.get("detail")
        course_dir = os.path.join(download_dir, course_title)
        streams_dir = os.path.join(download_dir, "streams")
        if not os.path.exists(course_dir):
            os.mkdir(course_dir)

        if not os.path.exists(streams_dir):
            os.mkdir(streams_dir)
        udemy = {}
        udemy["chapters"] = []
        udemy["course_id"] = course_id
        udemy["title"] = title
        udemy["course_title"] = course_title
        counter = -1
        if course:
            print("> Processing course data, this may take a minute. ")

            lecture_counter = 0

            for entry in course:
                clazz = entry.get("_class")
                asset = entry.get("asset")
                supp_assets = entry.get("supplementary_assets")

                if clazz == "chapter":
                    lecture_counter = 0
                    lectures = []
                    chapter_index = entry.get("object_index")
                    chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                    
                    if chapter_title not in udemy["chapters"]:
                        udemy["chapters"].append({"chapter_title": chapter_title, "chapter_id": entry.get("id"), "chapter_index": chapter_index, "lectures": []})
                        counter += 1
                elif clazz == "lecture":
                    lecture_counter += 1
                    lecture_id = entry.get("id")

                    if len(udemy["chapters"]) == 0:
                        lectures = []
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))

                        if chapter_title not in udemy["chapters"]:
                            udemy["chapters"].append({"chapter_title": chapter_title, "chapter_id": lecture_id, "chapter_index": chapter_index, "lectures": []})
                            counter += 1
                    
                    if lecture_id:
                        print(f"Processing {course.index(entry)} of {len(course)}")
                        retVal = []

                        if isinstance(asset, dict):
                            asset_type = asset.get("asset_type").lower() or asset.get("assetType").lower
                            if asset_type == "article":
                                if isinstance(supp_assets, list) and len(supp_assets) > 0:
                                    retVal = _extract_supplementary_assets(supp_assets, lecture_counter)
                            elif asset_type == "video":
                                if isinstance(supp_assets, list) and len(supp_assets) > 0:
                                    retVal = _extract_supplementary_assets(supp_assets, lecture_counter)
                            elif asset_type == "e-book":
                                retVal = _extract_ebook(asset, lecture_counter)
                            elif asset_type == "file":
                                retVal = _extract_file(asset, lecture_counter)
                            elif asset_type == "presentation":
                                retVal = _extract_ppt(asset, lecture_counter)
                            elif asset_type == "audio":
                                retVal = _extract_audio(asset, lecture_counter)

                        lecture_index = entry.get("object_index")
                        lecture_title = "{0:03d} ".format(lecture_counter) + sanitize_filename(entry.get("title"))

                        if asset.get("stream_urls") != None:
                            # not encrypted
                            data = asset.get("stream_urls")
                            if data and isinstance(data, dict):
                                sources = data.get("Video")
                                tracks = asset.get("captions")
                                # duration = asset.get("time_estimation")
                                sources = _extract_sources(sources, skip_hls, course_title + " - " + lecture_title)
                                subtitles = _extract_subtitles(tracks)
                                sources_count = len(sources)
                                subtitle_count = len(subtitles)
                                lectures.append(
                                    {
                                        "index": lecture_counter,
                                        "lecture_index": lecture_index,
                                        "lecture_id": lecture_id,
                                        "lecture_title": lecture_title,
                                        # "duration": duration,
                                        "assets": retVal,
                                        "assets_count": len(retVal),
                                        "sources": sources,
                                        "subtitles": subtitles,
                                        "subtitle_count": subtitle_count,
                                        "sources_count": sources_count,
                                        "is_encrypted": False,
                                        "asset_id": asset.get("id"),
                                    }
                                )
                            else:
                                lectures.append(
                                    {
                                        "index": lecture_counter,
                                        "lecture_index": lecture_index,
                                        "lectures_id": lecture_id,
                                        "lecture_title": lecture_title,
                                        "html_content": asset.get("body"),
                                        "extension": "html",
                                        "assets": retVal,
                                        "assets_count": len(retVal),
                                        "subtitle_count": 0,
                                        "sources_count": 0,
                                        "is_encrypted": False,
                                        "asset_id": asset.get("id"),
                                    }
                                )
                        else:
                            # encrypted
                            data = asset.get("media_sources")
                            if data and isinstance(data, list):
                                sources = _extract_media_sources(data, course_title + " - " + lecture_title)
                                tracks = asset.get("captions")
                                # duration = asset.get("time_estimation")
                                subtitles = _extract_subtitles(tracks)
                                sources_count = len(sources)
                                subtitle_count = len(subtitles)
                                lectures.append(
                                    {
                                        "index": lecture_counter,
                                        "lecture_index": lecture_index,
                                        "lectures_id": lecture_id,
                                        "lecture_title": lecture_title,
                                        # "duration": duration,
                                        "assets": retVal,
                                        "assets_count": len(retVal),
                                        "video_sources": sources,
                                        "subtitles": subtitles,
                                        "subtitle_count": subtitle_count,
                                        "sources_count": sources_count,
                                        "is_encrypted": True,
                                        "asset_id": asset.get("id"),
                                    }
                                )
                            else:
                                lectures.append(
                                    {
                                        "index": lecture_counter,
                                        "lecture_index": lecture_index,
                                        "lectures_id": lecture_id,
                                        "lecture_title": lecture_title,
                                        "html_content": asset.get("body"),
                                        "extension": "html",
                                        "assets": retVal,
                                        "assets_count": len(retVal),
                                        "subtitle_count": 0,
                                        "sources_count": 0,
                                        "is_encrypted": False,
                                        "asset_id": asset.get("id"),
                                    }
                                )
                    udemy["chapters"][counter]["lectures"] = lectures
                    udemy["chapters"][counter]["lecture_count"] = len(lectures)

                elif clazz == "quiz":
                    lecture_id = entry.get("id")
                    if len(udemy["chapters"]) == 0:
                        lectures = []
                        chapter_index = entry.get("object_index")
                        chapter_title = "{0:02d} - ".format(chapter_index) + sanitize_filename(entry.get("title"))
                        if chapter_title not in _udemy["chapters"]:
                            lecture_counter = 0
                            udemy["chapters"].append(
                                {
                                    "chapter_title": chapter_title,
                                    "chapter_id": lecture_id,
                                    "chapter_index": chapter_index,
                                    "lectures": [],
                                }
                            )
                            counter += 1

                    udemy["chapters"][counter]["lectures"] = lectures
                    udemy["chapters"][counter]["lectures_count"] = len(lectures)
            udemy["total_chapters"] = len(udemy["chapters"])
            udemy["total_lectures"] = sum([entry.get("lecture_count", 0) for entry in udemy["chapters"] if entry])

        with open(os.path.join(os.getcwd(), "downloads", "{}.json".format(course_title)), encoding="utf8", mode="w") as f:
            f.write(json.dumps(udemy))
            f.close()
            print("> Saved parsed data to json")
        
        _print_course_info(udemy)
        parse_new(udemy)
        driver.quit()
        

if __name__ == "__main__":
    # parse arguments and make directories
    pre_run()

    main()
import bs4 as bs
import argparse
import browser_cookie3 as cookies
import os
import requests
import time
import sys
import webbrowser
import json
import re
import urllib.parse
import cgi

BASE_URL = "https://jigsaw.chegg.com"
API_URL = BASE_URL + "/api/v0"
HTML_HEADERS = {
    'upgrade-insecure-requests': "1",
    'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_1) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
    'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    'dnt': "1",
    'referer': "https://ereader.chegg.com/",
    'accept-encoding': "gzip, deflate, br",
    'accept-language': "en",
    'cache-control': "no-cache",
    'X-Requested-With': 'XMLHttpRequest'
}
IMAGE_HEADERS = {
    'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_1) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
    'accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    'dnt': "1",
    'accept-encoding': "gzip, deflate, br",
    'accept-language': "en",
    'cache-control': "no-cache",
}

JAR = {c.name: c.value for c in cookies.chrome(domain_name='jigsaw.chegg.com')}


def prompt_login() -> None:
    choice = input(
        "It seems that you have not logged into the Chegg eReader yet.\n"
        "You can also log in by copying a pasting the following URL into "
        "Google Chrome:\nhttps://ereader.chegg.com\n"
        "Would you like to open Google Chrome and log in? (Y/N) ")
    if choice.lower() == 'y':
        webbrowser.get('chrome').open('https://ereader.chegg.com')


def get_response(url, querystring, max_retries, retry_delay) -> str:
    resp = None
    for i in range(0, max_retries):
        resp = requests.get(url, params=querystring, headers=HTML_HEADERS, cookies=JAR)
        if resp.status_code in [200, 401, 406]: # don't retry
            break
        print("[status={:d} attempt={:d}] Unable to download page {:s}: {:s}"
              .format(resp.status_code, i, url, str(resp.text)))
        time.sleep(retry_delay / 1000)
    if resp:
        return resp.text
    return ""

def get_json_data(isbn: str, path: str, max_retries: int, retry_delay: int):
    url = API_URL + "/books/{:s}/{:s}".format(isbn, path)
    resp = get_response(url, {}, max_retries, retry_delay)
    if resp:
        return json.loads(resp)
    return None

def get_pages(isbn: str, max_retries: int, retry_delay: int):
    return get_json_data(isbn, "pages", max_retries, retry_delay)

def get_pagebreaks(isbn: str, max_retries: int, retry_delay: int):
    return get_json_data(isbn, "pagebreaks", max_retries, retry_delay)

def get_toc(isbn: str, max_retries: int, retry_delay: int):
    return get_json_data(isbn, "toc", max_retries, retry_delay)

def get_figures(isbn: str, max_retries: int, retry_delay: int):
    return get_json_data(isbn, "figures", max_retries, retry_delay)

def get_ancillaries(isbn: str, max_retries: int, retry_delay: int):
    return get_json_data(isbn, "ancillaries", max_retries, retry_delay)

def save_json_data(out_dir, name, data):
    with open(os.path.join(out_dir, "{:s}.json".format(name)), "w") as f:
        json.dump(data, f)

def get_html(isbn: str, start: str, end: str, max_retries: int, retry_delay: int) -> str:
    url = API_URL + "/books/{:s}/print".format(isbn)
    querystring = {'from': start, 'to': end}
    return get_response(url, querystring, max_retries, retry_delay)

def mark_renamed(source, target, out_dir):
    with open(os.path.join(out_dir, 'renames.json'), 'rb') as f:
        renames = json.load(f)

    prefixlen = len(os.path.abspath(out_dir))
    abssource = os.path.abspath(source)
    renames[abssource[prefixlen+1:]] = os.path.abspath(target)[prefixlen+1:]
    save_json_data(out_dir, "renames", renames)

def download_image(url: str, path: str, out_dir: str, max_retries: int, retry_delay: int, rename: bool) -> bool:
    new_filename = None
    success = False
    with open(path, 'wb') as f:
        resp = None
        for i in range(0, max_retries):
            resp = requests.get(url, headers=IMAGE_HEADERS, cookies=JAR, stream=True)
            if resp.status_code == 200:
                if 'Content-Disposition' in resp.headers:
                    value, params = cgi.parse_header(resp.headers['Content-Disposition'])
                    if params['filename'] != os.path.basename(path):
                        new_filename = os.path.join(os.path.dirname(path), params['filename'])
                        if os.path.isfile(new_filename):
                            print("File '{:s}' already exists, skipping download!".format(new_filename))
                            mark_renamed(path, new_filename, out_dir)
                            f.close()
                            os.remove(path)
                            return True
                break
            print("[status={:d} attempt={:d}] Unable to download {:s}: {:s}"
                  .format(resp.status_code, i, url, str(resp.text)))
            time.sleep(retry_delay / 1000)
        if resp:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)
            success = True

    if success:
        if new_filename:
            mark_renamed(path, new_filename, out_dir)
            if rename:
                os.rename(path, new_filename)
    else:
        os.remove(path)

    return success

def get_image(src: str, out_file: str, out_dir: str, max_retries: int, retry_delay: int) -> bool:
    url = API_URL + src
    return download_image(url, out_file, out_dir, max_retries, retry_delay, False)

def get_filename(book_name: str, page_num: str, out_dir: str) -> str:
    filename = '{:s}_{:s}.png'.format(book_name, page_num)
    return os.path.join(out_dir, filename)

def get_path(url: str):
    urlpath = urllib.parse.urlparse(url).path
    match = re.search(r"^(/books/\d+)?/(.+?)(/content|/encrypted/\d+)?$", urlpath)
    path = match.group(2)
    if path[-8:].find(".") == -1:
        if str(match.group(3)).find("encrypted") >= 0:
            path += ".jpg"
        else:
            path += ".html"
    return path

def save_file(url: str, out_dir: str, cache: bool, callback) -> bool:
    if url[0:2] == "//":
        url = "https:" + url
    elif url[0] == "/":
        url = BASE_URL + url

    base_path = get_path(url)
    path = os.path.join(out_dir, base_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if cache and os.path.isfile(path):
        print("File '{:s}' already exists, skipping download!".format(base_path))
        return True

    return callback(url, path)

def download_files(html: str, baseurl: str, out_dir: str,
                   max_retries: int, retry_delay: int) -> bool:
    soup = bs.BeautifulSoup(html, 'html.parser')
    files  = [t['href'] for t in soup.find_all('link', href=True)]
    files += [t['src']  for t in soup.find_all('img', src=True)]
    files += [t['src']  for t in soup.find_all('script', src=True)]
    # we should process 'style' too for CSS urls

    result = True
    for offset, src in enumerate(files):
        if src[0:4] != 'http' and src[0:1] != "/":
            src = baseurl + '/' + src
        print("Downloading file '{:s}' ({:d}/{:d})".format(src, offset + 1, len(files)))
        # if it's a CSS file we actually should process it too for urls
        if not save_file(src, out_dir, True, lambda url, path: download_image(url, path, out_dir, max_retries, retry_delay, True)):
            result = False
    return result

def download_images(html: str, page: str,
                   book_name: str, out_dir: str,
                   max_retries: int, retry_delay: int) -> bool:
    soup = bs.BeautifulSoup(html, 'html.parser')
    images = [t['src'] for t in soup.find_all('img')]
    result = True
    for offset, src in enumerate(images):
       name = page
       if offset != 0:
           name = name + "_" + str(offset)
       if not get_image(src, get_filename(book_name, name, out_dir), out_dir, max_retries, retry_delay):
           result = False
    return result


def download_single(isbn: str, page: str,
                    book_name: str, out_dir: str,
                    max_retries: int, retry_delay: int) -> bool:
    html = get_html(isbn, page, page, max_retries, retry_delay)
    soup = bs.BeautifulSoup(html, 'html.parser')
    images = [t['src'] for t in soup.find_all('img')]
    if images:
        if not get_image(images[0], get_filename(book_name, page, out_dir), out_dir, max_retries, retry_delay):
            return False
        return True
    return False


def download_list(isbn: str, pages: list,
                   book_name: str, out_dir: str,
                   max_retries: int, retry_delay: int,
                   quiet: bool=False) -> None:
    save_json_data(out_dir, "renames", {})
    failed_pages = []
    start_time = time.time()
    for page in pages:
        if not quiet:
            print("downloading page {:s}".format(page))
        if not download_single(isbn, str(page), book_name, out_dir, max_retries, retry_delay):
            failed_pages.append(page)
    end_time = time.time()
    print("downloaded {:d} pages in {:6.3f} seconds"
          .format(len(pages) - len(failed_pages) + 1, end_time - start_time))
    if failed_pages:
        print("failed pages: {:s}".format(str(failed_pages)))


def download_range(isbn: str, start: int, end: int, interval: int,
                   book_name: str, out_dir: str,
                   max_retries: int, retry_delay: int,
                   quiet: bool=False) -> None:
    save_json_data(out_dir, "renames", {})
    failed_pages = []
    start_time = time.time()
    for page in range(start, end, interval):
        html = get_html(isbn, str(page), str(page + interval - 1), max_retries, retry_delay)
        if not quiet:
            print("downloading page {:d}/{:d}".format(page, end))
        result = download_images(html, str(page), book_name, out_dir, max_retries, retry_delay)
        if not result:
            failed_pages.append(page + offset)
    end_time = time.time()
    print("downloaded {:d} pages in {:6.3f} seconds"
          .format((end - start) - len(failed_pages) + 1, end_time - start_time))
    if failed_pages:
        print("failed pages: {:s}".format(str(failed_pages)))

def download_figures(figures, out_dir, max_retries, retry_delay):
    for i, figure in enumerate(figures):
        print("Downloading figure '{:s}' ({:d}/{:d})".format(str(figure["title"]), i + 1, len(figures)))
        if not save_file(figure["imageURL"], out_dir, True, lambda url, path: download_image(url, path, out_dir, max_retries, retry_delay, True)):
            break


def download_all(isbn: str, quality: int, book_name: str, out_dir: str,
                 max_retries: int, retry_delay: int,
                 quiet: bool=False) -> None:
    failed_pages = []
    start_time = time.time()

    pages = get_pages(isbn, max_retries, retry_delay)
    if not pages:
        print('You need to login!')
        return False

    save_json_data(out_dir, "renames", {})

    save_json_data(out_dir, book_name + "_pages", pages)

    pagebreaks = get_pagebreaks(isbn, max_retries, retry_delay)
    save_json_data(out_dir, book_name + "_pagebreaks", pagebreaks)

    toc = get_toc(isbn, max_retries, retry_delay)
    save_json_data(out_dir, book_name + "_toc", toc)

    figures = get_figures(isbn, max_retries, retry_delay)
    save_json_data(out_dir, book_name + "_figures", figures)

    ancillaries = get_ancillaries(isbn, max_retries, retry_delay)
    save_json_data(out_dir, book_name + "_ancillaries", ancillaries)

    downloaded_urls = []

    download_figures(figures, out_dir, max_retries, retry_delay)

    for i, page in enumerate(pages):
        label = ""
        if "page" in page:
            label = page["page"]
        elif "number" in page:
            label = str(page["number"])
        elif "chapterTitle" in page:
            label = page["chapterTitle"]

        if not quiet:
            print("downloading page {:s} ({:d}/{:d})".format(label, i + 1, len(pages)))

        def page_saver(url, path):
            if url in downloaded_urls:
                return True

            html = get_response(url, {}, max_retries, retry_delay)
            if html.find('popup-signin') != -1:
                print('You need to login!')
                return False

            downloaded_urls.append(url)
            with open(path, "wb") as f:
                f.write(html.encode("utf-8"))

            urlparts = list(urllib.parse.urlsplit(url))
            urlparts[2] = os.path.dirname(urlparts[2])
            urlparts[3] = ''
            urlparts[4] = ''
            if not download_files(html, urllib.parse.urlunsplit(urlparts), out_dir, max_retries, retry_delay):
                failed_pages.append(url)
            return True

        if not save_file("{:s}?width={:d}".format(page["absoluteURL"], quality), out_dir, False, lambda url, path: page_saver(url, path)):
            break

    end_time = time.time()
    print("downloaded {:d} pages in {:6.3f} seconds"
          .format(len(pages) - len(failed_pages) + 1, end_time - start_time))
    if failed_pages:
        print("failed pages: {:s}".format(str(failed_pages)))


def verify_args(args):
    if not args.start and not args.end and not args.pages:
        print("Fatal: you must either specify a range or a list of pages")
        sys.exit(-1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('isbn', type=str,
                        help='the e-ISBN of the book to download')

    page_group = parser.add_argument_group('pages')
    page_group.add_argument('start', type=int, nargs='?',
                        help='starting page to download')
    page_group.add_argument('end', type=int, nargs='?',
                        help='ending page to download')
    page_group.add_argument('-i', '--interval', type=int, default=2,
                        help='maximum pages to query and download at once')
    page_group.add_argument('-p', '--pages', type=str, nargs='*',
                            help='a list of pages to download, separated by space')

    error_group = parser.add_argument_group("error handling")
    error_group.add_argument('--max-retries', type=int, default=3,
                        help='maximum number to retry downloading a page if it fails. Default=[%(default)d]')
    error_group.add_argument('--retry-delay', type=int, default=500,
                        help='delay in milliseconds between retries. Default=[%(default)d]')

    parser.add_argument('--quality', type=int, default=2000,
                        help='quality of the book to download. Default=[%(default)s]')
    parser.add_argument('--book-name', type=str, default='Book',
                        help='name of the book to download. Default=[%(default)s]')
    parser.add_argument('--out-dir', type=str, default='.',
                        help='specify a directory to save all images. Default=[Current Directory]')

    args = parser.parse_args()

    verify_args(args)

    if len(JAR) == 0:
        prompt_login()
        sys.exit(0)
    try:
        os.makedirs(args.out_dir, exist_ok=True)
    except OSError as e:
        print("Unable to create output directory {:s}: {:s}"
              .format(args.out_dir, e))

    if args.pages:
        if 'all' in args.pages:
            download_all(
                args.isbn,
                args.quality,
                args.book_name,
                args.out_dir,
                args.max_retries,
                args.retry_delay,
            )
        else:
            download_list(
                args.isbn,
                args.pages,
                args.book_name,
                args.out_dir,
                args.max_retries,
                args.retry_delay,
            )
    else:
        download_range(
            args.isbn,
            args.start,
            args.end,
            args.interval,
            args.book_name,
            args.out_dir,
            args.max_retries,
            args.retry_delay,
        )


if __name__ == '__main__':
    main()

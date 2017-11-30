import bs4 as bs
import argparse
import browser_cookie3 as cookies
import os
import requests
import time
import sys
import webbrowser

API_URL = "https://jigsaw.chegg.com/api/v0"
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


def get_html(isbn: str, start: str, end: str, max_retries: int, retry_delay: int) -> str:
    url = API_URL + "/books/{:s}/print".format(isbn)
    querystring = {'from': start, 'to': end}
    resp = None
    for i in range(0, max_retries):
        resp = requests.get(url, params=querystring, headers=HTML_HEADERS, cookies=JAR)
        if resp.status_code == 200:
            break
        print("[status={:d} attempt={:d}] Unable to download pages {:s} to {:s}: {:s}"
              .format(resp.status_code, i, start, end, str(resp.text)))
        time.sleep(retry_delay / 1000)
    if resp:
        return resp.text
    return ""


def get_image(src: str, out_file: str, max_retries: int, retry_delay: int) -> bool:
    url = API_URL + src
    with open(out_file, 'wb') as f:
        resp = None
        for i in range(0, max_retries):
            resp = requests.get(url, headers=IMAGE_HEADERS, cookies=JAR, stream=True)
            if resp.status_code == 200:
                break
            print("[status={:d} attempt={:d}] Unable to download {:s}: {:s}"
                  .format(resp.status_code, i, src, str(resp.text)))
            time.sleep(retry_delay / 1000)
        if resp:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)
            return True
        return False


def get_filename(book_name: str, page_num: str, out_dir: str) -> str:
    filename = '{:s}_{:s}.png'.format(book_name, page_num)
    return os.path.join(out_dir, filename)


def download_single(isbn: str, page: str,
                    book_name: str, out_dir: str,
                    max_retries: int, retry_delay: int) -> bool:
    html = get_html(isbn, page, page, max_retries, retry_delay)
    soup = bs.BeautifulSoup(html, 'html.parser')
    images = [t['src'] for t in soup.find_all('img')]
    if images:
        if not get_image(images[0], get_filename(book_name, page, out_dir), max_retries, retry_delay):
            return False
        return True
    return False


def download_list(isbn: str, pages: list,
                   book_name: str, out_dir: str,
                   max_retries: int, retry_delay: int,
                   quiet: bool=False) -> None:
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
    failed_pages = []
    start_time = time.time()
    for page in range(start, end, interval):
        html = get_html(isbn, str(page), str(page + interval - 1), max_retries, retry_delay)
        soup = bs.BeautifulSoup(html, 'html.parser')
        images = [t['src'] for t in soup.find_all('img')]
        for offset, src in enumerate(images):
            if not quiet:
                print("downloading page {:d}/{:d}".format(page + offset, end))
            if not get_image(src, get_filename(book_name, str(page + offset), out_dir), max_retries, retry_delay):
                failed_pages.append(page + offset)
    end_time = time.time()
    print("downloaded {:d} pages in {:6.3f} seconds"
          .format((end - start) - len(failed_pages) + 1, end_time - start_time))
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

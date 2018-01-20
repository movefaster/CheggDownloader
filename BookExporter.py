#!/bin/python

import argparse
import os
import glob
import json
import shutil
import urllib.parse
import re
import bs4 as bs
import subprocess

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

def export(dir, book_name, tmp_dir, out_dir):
    pages = []

    pages_files = glob.glob(os.path.join(dir, '*_pages.json'))[0]
    with open(pages_files) as f:
        pages = json.load(f)

    if len(pages) == 0:
        return

    print("Copying files")
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir)
    shutil.copytree(dir, tmp_dir)

    filelist = []
    pageimages = []
    with open(os.path.join(tmp_dir, 'renames.json')) as f:
        renames = json.load(f)

    print("Fixing files")
    for page in pages:
        path = get_path(page["absoluteURL"])
        changed = False
        file = os.path.join(tmp_dir, path)
        with open(file) as f:
            soup = bs.BeautifulSoup(f.read(), 'html.parser')
            for style in soup.head.find_all("style"):
                # some xhtml files contain "body{visibility:hidden}" making content invisible
                if style.string.find("visibility:hidden") != -1:
                    style.decompose()
                    changed = True

            for link in soup.find_all("link", href=True):
                if link["href"][0] == "/":
                    new_path = get_path(link["href"])
                    link["href"] = os.path.relpath(os.path.join(tmp_dir, new_path), os.path.dirname(file))
                    changed = True

            for source in soup.find_all(["img", "script"], src=True):
                if source["src"][0] == "/":
                    new_path = get_path(source["src"])
                    if new_path in renames:
                        new_path = renames[new_path]
                    source["src"] = os.path.relpath(os.path.join(tmp_dir, new_path), os.path.dirname(file))
                    changed = True
                if source.has_attr("id") and source["id"] == "pbk-page":
                    pageimages.append(os.path.join(os.path.dirname(file), source["src"]));

        if changed:
            with open(file, "wb") as f:
                f.write(str(soup).encode("utf-8"))

        filelist.append(file)

    if len(pageimages) > 0:
        filelist = pageimages

    create_pdf(out_dir, book_name, filelist)

def create_pdf(out_dir, book_name, filelist):
    print("Generating PDF, Please Wait! This will take a while.")

    outfile = os.path.join(out_dir, book_name + ".pdf")

    if filelist[0][-4:] == 'html':
        params = ["--no-pdf-compression", "--disable-javascript"]
        args = ["wkhtmltopdf"]
    else:
        params = []
        args = ["magick"]

    args = args + params + filelist + [outfile]

    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Created {:s}".format(outfile))
    if result.returncode != 0:
        print(result.stderr)
        print("Warning! There was some error while creating PDF!")



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dir', type=str,
                        help='path to a location of book')

    parser.add_argument('--book-name', type=str, default='Book',
                        help='name of the book. Default=[%(default)s]')
    parser.add_argument('--tmp-dir', type=str, default='tmp',
                        help='specify a directory to keep temporally files. Default=[%(default)s]')
    parser.add_argument('--out-dir', type=str, default='.',
                        help='specify a directory where to save exported book. Default=[Current Directory]')

    args = parser.parse_args()

    try:
        os.makedirs(args.out_dir, exist_ok=True)
    except OSError as e:
        print("Unable to create output directory {:s}: {:s}"
              .format(args.out_dir, e))

    if not os.path.isdir(args.dir):
        print("Wrong location to book!")
        return

    export(args.dir, args.book_name, args.tmp_dir, args.out_dir)

if __name__ == '__main__':
    main()

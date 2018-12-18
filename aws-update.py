#!/usr/local/bin/python3
import argparse
import configparser
import datetime
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import time
from time import gmtime, strftime
from loguru import logger

import boto3.session

# Paths
this_file = os.path.abspath(os.path.dirname(__file__))

# Config
CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(this_file, 'super_secrets.ini'))
POPSKI = CONFIG['pop.ski']

# Folder paths
built_website = POPSKI["static_website"]  # Absolute path to the output of jekyll build
temp_folder = POPSKI["temp_folder"]  # Absolute path to the temporary directory

# File related constants
excluded = [".DS_Store", "function.ts", "feed.xml", ".sass-cache", ".scssc", ".scss"]
excluded_ext = [".scssc", ".md"]

mime_type = {
    "html": "text/html",
    "css": "text/css",
    "js": "application/javascript",
    "svg": "image/svg+xml",
    "xml": "text/xml",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "txt": "text/plain",
    "ico": "image/x-icon",
    "webp": "image/webp"
}

# AWS
AWS = boto3.session.Session(profile_name='popski')

# S3
S3_CLIENT = AWS.client("s3")
S3 = AWS.resource('s3')
MAIN_BUCKET_NAME = POPSKI["main_bucket_name"]
MAIN_BUCKET = S3.Bucket(MAIN_BUCKET_NAME)
BACKUP_BUCKET_NAME = POPSKI["backup_bucket_name"]

# Cloudfront
CLOUDFRONT_ID = POPSKI["CLOUDFRONT_ID"]
CLOUDFRONT = AWS.client("cloudfront")

# Yes/no cmd line options
yes = {'yes', 'y', 'ye', ''}
no = {'no', 'n'}


def backup_website():
    backup_path = strftime("%Y-%m-%d/%H:%M:%S/", gmtime())

    for item in MAIN_BUCKET.objects.all():
        logger.debug("Backing up file: {}".format(item.key))
        S3.meta.client.copy_object(
            ACL='public-read',
            Bucket=BACKUP_BUCKET_NAME,
            CopySource={'Bucket': MAIN_BUCKET_NAME, 'Key': item.key},
            Key=backup_path + item.key
        )


def find_content_type(path):
    ext = path.split(".")[1]
    return mime_type[ext]


def gzip_files():
    os.makedirs(temp_folder, exist_ok=True)

    for root, _, files in os.walk(built_website):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)

                tmp_path = "{temp_folder}{filepath}.gz".format(temp_folder=temp_folder,
                                                               filepath=file_path.replace(built_website, ""))
                os.makedirs(temp_folder + root.replace(built_website, ""), exist_ok=True)
                with open(file_path, 'rb') as f_in:
                    with gzip.open(tmp_path, 'wb+') as f_out:
                        logger.debug("G-zipping file {} to {}".format(file_path, tmp_path))
                        shutil.copyfileobj(f_in, f_out)


def load_to_s3():
    logger.debug("Deleting contents of the bucket {}".format(MAIN_BUCKET_NAME))
    MAIN_BUCKET.objects.all().delete()

    for root, _, files in os.walk(temp_folder):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)

                if "tmp/index.html.gz" in file_path:
                    key = index_html
                else:
                    key = file_path.replace(temp_folder, "").replace(".gz", "")

                logger.debug("Uploading file {} to s3 with the path {:10s}".format(file_path.replace(temp_folder, ""), key))
                data = open(file_path, "rb")

                MAIN_BUCKET.put_object(Bucket=MAIN_BUCKET_NAME, Key=key, Body=data,
                                       ContentType=find_content_type(file_path), ContentEncoding="gzip",
                                       ACL="public-read", CacheControl="max-age=3600")


def update_cloudfront():
    logger.debug("Updating Cloudfront distribution with new index path: {}", index_html)
    dist_config = CLOUDFRONT.get_distribution_config(Id=CLOUDFRONT_ID)

    dist_config["DistributionConfig"]["DefaultRootObject"] = index_html

    dis_config = dist_config["DistributionConfig"]
    etag = dist_config["ETag"]
    CLOUDFRONT.update_distribution(DistributionConfig=dis_config, Id=CLOUDFRONT_ID, IfMatch=etag)


def files_to_invalidate():
    invalidation = []
    git_command_1 = "git diff --name-only HEAD _site"
    git_command_2 = "grep \"$(git diff --name-only HEAD)\""
    p1 = subprocess.Popen(git_command_1, stdout=subprocess.PIPE, shell=True)
    p2 = subprocess.Popen(git_command_2, stdin=p1.stdout, stdout=subprocess.PIPE, shell=True)
    p1.stdout.close()
    process, _ = p2.communicate()

    process = process.decode("utf-8").strip()

    for file in process.split("\n"):
        ext = file.split(".")[1]
        if "_site" in file and ext not in excluded_ext:
            file = file.replace("_site/", "")

            if ".scss" in file:
                file = file.replace(".scss", ".css")

            invalidation.append(file)

    return invalidation


def yes_or_no():
    choice = input().lower()
    if choice in yes:
        return True
    elif choice in no:
        return False
    else:
        sys.stdout.write("Please respond with 'yes' or 'no'")


def invalidate_cloudfront(l):
    if len(l) > 0:
        logger.info("Invalidation available for the following paths: {}".format(l))
        sys.stdout.write("Continue with invalidation? y(es)/n(o)\n")

        if yes_or_no():
            CLOUDFRONT.create_invalidation(
                DistributionId=CLOUDFRONT_ID,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': len(l),
                        'Items': ['/{}'.format(f) for f in l]
                    },
                    'CallerReference': 'website-updated-{}'.format(datetime.datetime.now())
                }
            )
        else:
            logger.error("Not invalidating paths")
    else:
        logger.error("No files have updated - not invalidating Cloudfront")


def make_a_hash():
    hash_string = hashlib.md5()

    with open(built_website + "index.html") as opened_file:
        data = opened_file.read()
        hash_string.update(data.encode("utf-8"))

    hash_string.update(str(time.time()).encode("utf-8"))
    hash_string = hash_string.hexdigest()[0:10]

    global index_html
    index_html = "index-{}.html".format(hash_string)
    logger.info("Setting index filename to {}".format(index_html))


def build_website():
    logger.info("Building the website from scratch 🌐")
    git_command = "jekyll clean && jekyll build"
    p1, _ = subprocess.Popen(git_command, stdout=subprocess.PIPE, shell=True).communicate()


def main(a):
    build_website()
    backup_website()
    make_a_hash()
    gzip_files()
    load_to_s3()
    update_cloudfront()

    shutil.rmtree(temp_folder)

    if a.invalid:
        if a.force:
            i_list = ["*"]
        else:
            i_list = files_to_invalidate()

        invalidate_cloudfront(i_list)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', help='Force invalidation of all paths', dest="force", required=False, action='store_true')
    parser.add_argument('-i', help='Invalidate all updated objects', dest="invalid", required=False, action='store_true')
    parser.set_defaults(force=False, invalid=False)
    args = parser.parse_args()

    main(args)

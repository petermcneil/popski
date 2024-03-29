#!/usr/bin/env python
import argparse
import boto3.session
import configparser
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from loguru import logger
from time import gmtime, strftime

# Paths
this_file = os.path.abspath(os.path.dirname(__file__))

# Config
CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(this_file, 'popski.ini'))
POPSKI = CONFIG['pop.ski']

# Folder paths
built_website = POPSKI["static_website"]  # Absolute path to the output of jekyll build
temp_folder = "/tmp/popski/"  # Absolute path to the temporary directory

# File related constants
excluded = [".DS_Store", ".ts", "feed.xml", ".sass-cache", ".scssc", ".scss", ".md"]
excluded_ext = [".scssc", ".md"]
dont_remove = POPSKI["dont_remove"].split("|")

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
    "webp": "image/webp",
    "png": "image/png",
    "mp3": "audio/mpeg",
    "pdf": "application/pdf"
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

# Headers
expires = datetime.utcnow() + timedelta(days=(25 * 365))
expires = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
cache_control = "max-age=86400"


def backup_website():
    backup_path = strftime("%Y-%m-%d/%H:%M:%S/", gmtime())
    logger.info("🗄  Archiving old website to path: {}".format(backup_path))

    global previous_index
    for key in MAIN_BUCKET.objects.filter(Prefix="index-"):
        previous_index = key.key
        logger.debug("Storing the old root index - {}".format(previous_index))
        break

    for item in MAIN_BUCKET.objects.all():
        logger.debug("Backing up file: {} to bucket {} at {}".format(item.key, BACKUP_BUCKET_NAME, backup_path + item.key))
        S3.meta.client.copy_object(
            ACL='private',
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
                        logger.debug("🗜  🗂  G-zipping file {} to {} ".format(file_path, tmp_path))
                        shutil.copyfileobj(f_in, f_out)


def load_to_s3():
    logger.info("💥 Deleting contents of the bucket {}".format(MAIN_BUCKET_NAME))
    MAIN_BUCKET.objects.all().delete()
    logger.info("⬆️  Uploading website to S3")
    for root, _, files in os.walk(temp_folder):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)
                if temp_folder + "index.html.gz" in file_path:
                    key = hashed_index_html
                else:
                    key = file_path.replace(temp_folder, "").replace(".gz", "")

                logger.debug(
                    "✈️  Uploading file {} to S3 with the path {:10s}️".format(file_path.replace(temp_folder, ""), key))
                data = open(file_path, "rb")

                MAIN_BUCKET.put_object(Bucket=MAIN_BUCKET_NAME, Key=key, Body=data,
                                       ContentType=find_content_type(file_path), ContentEncoding="gzip",
                                       ACL="public-read", CacheControl=cache_control, Expires=expires)
                data.close()


def update_cloudfront():
    logger.info("Updating Cloudfront distribution with new index path: {}", hashed_index_html)
    dist_config = CLOUDFRONT.get_distribution_config(Id=CLOUDFRONT_ID)

    dist_config["DistributionConfig"]["DefaultRootObject"] = hashed_index_html

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

            if file == "index.html":
                file = previous_index

            if ".scss" in file:
                file = file.replace(".scss", ".css")

            invalidation.append(file)

    return invalidation


def yes_or_no():
    choice = input().lower().strip()
    if choice in yes:
        return True
    elif choice in no:
        return False
    else:
        sys.stdout.write("Please respond with 'y(es)' or 'n(o)'")


def invalidate_cloudfront(l):
    if len(l) > 0:
        logger.info("✅ Invalidation available for the following paths:")
        for path in l:
            logger.info(path)

        sys.stdout.write("Continue with invalidation? y(es)/n(o)\n")

        if yes_or_no():
            logger.info("Invalidating cloudfront")
            CLOUDFRONT.create_invalidation(
                DistributionId=CLOUDFRONT_ID,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': len(l),
                        'Items': ['/{}'.format(f) for f in l]
                    },
                    'CallerReference': 'website-updated-{}'.format(datetime.now())
                }
            )
        else:
            logger.info("🚫 Not invalidating paths")
    else:
        logger.info("🚫 No files have updated - not invalidating Cloudfront")


def make_a_hash():
    hash_string = hashlib.md5()

    with open(built_website + "index.html") as opened_file:
        data = opened_file.read()
        hash_string.update(data.encode("utf-8"))

    hash_string.update(str(time.time()).encode("utf-8"))
    hash_string = hash_string.hexdigest()[0:10]

    global hashed_index_html
    hashed_index_html = "index-{}.html".format(hash_string)
    logger.debug("Setting index filename to {}".format(hashed_index_html))


def build_website():
    logger.info("🏗  Building the website from scratch")
    git_command = "JEKYLL_ENV=\"production\" jekyll clean && jekyll build"
    p1, _ = subprocess.Popen(git_command, stdout=subprocess.PIPE, shell=True).communicate()


def main(a):
    build_website()
    backup_website()
    make_a_hash()
    gzip_files()
    load_to_s3()
    update_cloudfront()

    if a.invalid:
        if a.force:
            i_list = ["*"]
        else:
            i_list = files_to_invalidate()

        invalidate_cloudfront(i_list)
    else:
        logger.info("🚫 No invalidation of Cloudfront")

    logger.info("🎉 Website has been updated - https://pop.ski")
    shutil.rmtree(temp_folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--force', help='Force invalidation of all paths.', dest="force", required=False,
                        action='store_true')
    parser.add_argument('-i', '--invalidate',
                        help='Invalidate all objects of the website that have updated since the last git commit.',
                        dest="invalid", required=False, action='store_true')
    parser.add_argument('-d', '--debug', help="Debug output.", dest="debug", required=False, action='store_true')
    parser.set_defaults(force=False, invalid=False)
    args = parser.parse_args()

    logger.remove()
    if args.debug:
        logger.add(sys.stdout, level="DEBUG")
    else:
        logger.add(sys.stdout, level="INFO")

    main(args)

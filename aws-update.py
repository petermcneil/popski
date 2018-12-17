#!/usr/local/bin/python3
import argparse
import configparser
import datetime
import gzip
import hashlib
import os
import shutil
import subprocess
import time
from time import gmtime, strftime

import boto3.session

this_file = os.path.abspath(os.path.dirname(__file__))
config = configparser.ConfigParser()
config.read(os.path.join(this_file, 'super_secrets.ini'))
popski = config['pop.ski']

CLOUDFRONT_ID = popski["CLOUDFRONT_ID"]
main_bucket_name = popski["main_bucket_name"]
backup_bucket_name = popski["backup_bucket_name"]

built_website = popski["static_website"]
temp_folder = popski["temp_folder"]

excluded = [".DS_Store", "function.ts", "feed.xml", ".sass-cache", ".scssc", ".scss"]

excluded_ext = [".scssc", ".md"]
pattern = '%d.%m.%Y %H:%M:%S'

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

AWS = boto3.session.Session(profile_name='popski')
S3_CLIENT = AWS.client("s3")
S3 = AWS.resource('s3')
CLOUDFRONT = AWS.client("cloudfront")
main_bucket = S3.Bucket(main_bucket_name)


def backup_website():
    backup_path = strftime("%Y-%m-%d/%H:%M:%S/", gmtime())

    for item in main_bucket.objects.all():
        print("Backing up file: {}".format(item.key))
        S3.meta.client.copy_object(
            ACL='public-read',
            Bucket=backup_bucket_name,
            CopySource={'Bucket': main_bucket_name, 'Key': item.key},
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
                        print("G-zipping file {} saving to with the path {}".format(file_path, tmp_path))
                        shutil.copyfileobj(f_in, f_out)


def load_to_s3():
    print("Deleting contents of the bucket {}".format(main_bucket_name))
    main_bucket.objects.all().delete()

    for root, _, files in os.walk(temp_folder):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)

                if "tmp/index.html.gz" in file_path:
                    key = index_html
                else:
                    key = file_path.replace(temp_folder, "").replace(".gz", "")

                print("Uploading file {} to s3 with the path {:10s}".format(file_path.replace(temp_folder, ""), key))
                data = open(file_path, "rb")
                content_type = find_content_type(file_path)

                if "text/html" not in content_type:
                    main_bucket.put_object(Bucket=main_bucket_name, Key=key, Body=data,
                                           ContentType=content_type, ContentEncoding="gzip", ACL="public-read")
                else:
                    main_bucket.put_object(Bucket=main_bucket_name, Key=key, Body=data,
                                           ContentType=content_type, ContentEncoding="gzip", ACL="public-read", CacheControl="max-age=3600")


def update_cloudfront():
    print("Updating Cloudfront distribution with new index path")
    dist_config = CLOUDFRONT.get_distribution_config(Id=CLOUDFRONT_ID)

    dist_config["DistributionConfig"]["DefaultRootObject"] = index_html

    dis_config = dist_config["DistributionConfig"]
    etag = dist_config["ETag"]
    CLOUDFRONT.update_distribution(DistributionConfig=dis_config, Id=CLOUDFRONT_ID, IfMatch=etag)


def files_to_invalidate():
    invalidation = []
    git_command_1 = "git ls-files --full-name _site"
    git_command_2 = "grep \"$(git diff --name-only HEAD)\""
    p1 = subprocess.Popen(git_command_1, stdout=subprocess.PIPE, shell=True)
    p2 = subprocess.Popen(git_command_2, stdin=p1.stdout, stdout=subprocess.PIPE, shell=True)
    p1.stdout.close()
    process, _ = p2.communicate()

    process = process.decode("utf-8").strip()

    for file in process.split("\n"):
        ext = file.split(".")[1]
        if "website" in file and ext not in excluded_ext and file != "website/index.html":
            file = file.replace("website/", "")

            if ".scss" in file:
                file = file.replace(".scss", ".css")

            invalidation.append(file)

    return invalidation


def invalidate_cloudfront(l):
    if len(l) > 0:
        print("Invalidating the following paths: {}".format(l))
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


def md5(files):
    hash_string = hashlib.md5()

    for f in files:
        with open(built_website + f) as opened_file:
            data = opened_file.read()
            hash_string.update(data.encode("utf-8"))

    hash_string.update(str(time.time()).encode("utf-8"))
    hash_string = hash_string.hexdigest()[0:10]

    global index_html
    index_html = "index-{}.html".format(hash_string)
    print("Setting index filename to {}".format(index_html))


def build_website():
    git_command = "jekyll clean && jekyll build"
    p1, _ = subprocess.Popen(git_command, stdout=subprocess.PIPE, shell=True).communicate()


def main(argsv):
    build_website()
    backup_website()
    md5(["index.html"])
    gzip_files()
    load_to_s3()
    update_cloudfront()

    shutil.rmtree(temp_folder)

    if argsv.i:
        i_list = files_to_invalidate()

        if argsv.f:
            i_list = ["*"]
        invalidate_cloudfront(i_list)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', help='Force invalidation of all paths', required=False)
    parser.add_argument('-i', help='Invalidate all updated objects', required=False, action='store_true')
    args = parser.parse_args()

    main(args)

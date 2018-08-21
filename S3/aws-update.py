import boto3.session
import hashlib
import os
import time
import configparser
from time import gmtime, strftime

aws = boto3.session.Session(profile_name='popski')
s3 = aws.resource('s3')

config = configparser.ConfigParser()
config.read('super_secrets.ini')

popski = config['pop.ski']

CLOUDFRONT_ID = popski["CLOUDFRONT_ID"]
main_bucket_name = popski["main_bucket_name"]
backup_bucket_name = popski["backup_bucket_name"]

hash_string = "HASH_STRING"
excluded = [".DS_Store", "function.ts"]

mime_type = {
    "html": "text/html",
    "css": "text/css",
    "js": "application/javascript",
    "svg": "image/svg+xml",
    "xml": "text/xml"
}

website = os.path.abspath('../static-website/_site/')


def backup_website():
    main_bucket = s3.Bucket(main_bucket_name)
    backup_path = strftime("%Y-%m-%d/%H:%M:%S/", gmtime())

    for item in main_bucket.objects.all():
        print("Backing up file: {}".format( item.key))
        s3.meta.client.copy_object(
            ACL='public-read',
            Bucket=backup_bucket_name,
            CopySource={'Bucket': main_bucket_name, 'Key': item.key},
            Key=backup_path + item.key
        )


def find_content_type(path):
    ext = path.split(".")[1]
    return mime_type[ext]


def load_to_s3():
    main_bucket = s3.Bucket(main_bucket_name)

    print("Deleting contents of the bucket {}".format(main_bucket_name))
    main_bucket.objects.all().delete()

    for root, subdirs, files in os.walk(website):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)

                if "_site/index.html" in file_path:
                    key = "index-{}.html".format(hash_string)
                else:
                    key = file_path.replace(website, "").replace("/", "", 1)

                print("Uploading file {}\t to s3 with the path {}".format(file_path, key))
                data = open(file_path, "rb")
                content_type = find_content_type(file_path)
                main_bucket.put_object(Bucket=main_bucket_name, Key=key, Body=data, ContentType=content_type, ACL="public-read")


def invalidate_cloudfront():
    print("Updating Cloudfront distribution with new index path")
    client = aws.client("cloudfront")
    config = client.get_distribution_config(Id=CLOUDFRONT_ID)

    config["DistributionConfig"]["DefaultRootObject"] = "index-{}.html".format(hash_string)

    dis_config = config["DistributionConfig"]
    etag = config["ETag"]
    client.update_distribution(DistributionConfig=dis_config, Id=CLOUDFRONT_ID, IfMatch=etag)


def md5(files):
    global hash_string
    hash_string = hashlib.md5()

    for f in files:
        with open(website + "/" + f) as opened_file:
            data = opened_file.read()
            hash_string.update(data.encode("utf-8"))

    hash_string.update(str(time.time()).encode("utf-8"))
    hash_string = hash_string.hexdigest()[0:10]


def main():
    backup_website()
    md5(["index.html"])
    load_to_s3()
    invalidate_cloudfront()


if __name__ == "__main__":
    main()

import boto3.session
import hashlib
import os
import time
import configparser
import gzip
import shutil
from time import gmtime, strftime

aws = boto3.session.Session(profile_name='popski')
s3 = aws.resource('s3')

this_file = os.path.abspath(os.path.dirname(__file__))
config = configparser.ConfigParser()
config.read(os.path.join(this_file, 'super_secrets.ini'))
popski = config['pop.ski']

CLOUDFRONT_ID = popski["CLOUDFRONT_ID"]
main_bucket_name = popski["main_bucket_name"]
backup_bucket_name = popski["backup_bucket_name"]

built_website = popski["static_website"]
temp_folder = popski["temp_folder"]

excluded = [".DS_Store", "function.ts", "feed.xml"]

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


def backup_website():
    main_bucket = s3.Bucket(main_bucket_name)
    backup_path = strftime("%Y-%m-%d/%H:%M:%S/", gmtime())

    for item in main_bucket.objects.all():
        print("Backing up file: {}\n".format(item.key))
        s3.meta.client.copy_object(
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

    for root, subdirs, files in os.walk(built_website):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)

                tmp_path = "{temp_folder}{filepath}.gz".format(temp_folder=temp_folder,
                                                               filepath=file_path.replace(built_website, ""))
                os.makedirs(temp_folder + root.replace(built_website, ""), exist_ok=True)
                with open(file_path, 'rb') as f_in:
                    with gzip.open(tmp_path, 'wb+') as f_out:
                        print("G-zipping file {} saving to with the path {}\n".format(file_path, tmp_path))
                        shutil.copyfileobj(f_in, f_out)


def load_to_s3():
    main_bucket = s3.Bucket(main_bucket_name)

    print("Deleting contents of the bucket {}\n".format(main_bucket_name))
    main_bucket.objects.all().delete()

    for root, subdirs, files in os.walk(temp_folder):
        for filename in files:
            if filename not in excluded:
                file_path = os.path.join(root, filename)

                if "tmp/index.html.gz" in file_path:
                    key = index_html
                else:
                    key = file_path.replace(temp_folder, "").replace(".gz", "")

                print("Uploading file {} to s3 with the path {:10s}\n".format(file_path.replace(temp_folder, ""), key))
                data = open(file_path, "rb")
                content_type = find_content_type(file_path)

                if "text/html" not in content_type: 
                    main_bucket.put_object(Bucket=main_bucket_name, Key=key, Body=data, 
                        ContentType=content_type, ContentEncoding="gzip", ACL="public-read")
                else:
                    main_bucket.put_object(Bucket=main_bucket_name, Key=key, Body=data, 
                        ContentType=content_type, ContentEncoding="gzip", ACL="public-read", CacheControl="max-age=3600")


def invalidate_cloudfront():
    print("Updating Cloudfront distribution with new index path\n")
    client = aws.client("cloudfront")
    dist_config = client.get_distribution_config(Id=CLOUDFRONT_ID)

    dist_config["DistributionConfig"]["DefaultRootObject"] = index_html

    dis_config = dist_config["DistributionConfig"]
    etag = dist_config["ETag"]
    client.update_distribution(DistributionConfig=dis_config, Id=CLOUDFRONT_ID, IfMatch=etag)


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
    print("Setting index filename to {}\n".format(index_html))


def main():
    backup_website()
    md5(["index.html"])
    gzip_files()
    load_to_s3()
    invalidate_cloudfront()

    shutil.rmtree(temp_folder)


if __name__ == "__main__":
    main()

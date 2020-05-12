import json
import logging
import os
import shutil
import uuid
import tempfile
import zipfile
import mimetypes
import datetime
import time
import threading

import config

from flask import Response, redirect, abort

from google.cloud import storage, datastore
from settings import get_batch_registrations, create_csv_file, create_zip_file

logger = logging.getLogger(__name__)


class Registration:
    """
    A class based func that intends to capsule functionality to get
    all photos of a specific registration
    """

    def __init__(self, bucket=None, survey_id=None, serial_number=None):
        self.survey_id = survey_id
        self.serial_number = serial_number
        self.request_id = uuid.uuid4()

        self.bucket = bucket

    def get_registrations(self, prefix):
        """
        Get all registrations
        :return:
        """
        registrations = {}
        batch = get_batch_registrations(self.bucket, prefix)
        if batch and batch['elements']:
            for registration in batch['elements']:
                registrations[registration["meta"]["serialNumber"]] = registration
            # self.registrations = registrations
            return registrations
        else:
            abort(Response(status=404, response=f"No registrations found using: {prefix}"))

    def get_csv(self, survey_id):
        """
        Return a csv file of all registrations
        :return:
        """
        registrations = self.get_registrations(prefix=survey_id)
        return create_csv_file(registrations)

    def get_zip(self, survey_id):
        """
        Return a zip file of all registrations

        :return:
        """
        registrations = self.get_registrations(prefix=survey_id)
        return create_zip_file(registrations, self.request_id)

    def get_list(self, survey_id):
        """
        Get a list of all registrations meta information
        :return:
        """
        registrations = self.get_registrations(prefix=survey_id)
        registration_list = {}
        for key in registrations:
            registration_list[registrations[key]['info']['formId']] = \
                [dict(serial_number=k,
                      date_of_registration=int(v['meta']['registrationDate']),
                      site_location=v['data']['tMNLLocationID']['CITY'] if 'tMNLLocationID' in v[
                          'data'].keys() else '',
                      site_id=v['data']['siteID'] if 'siteID' in v['data'].keys() else
                      ''.join(n for n in v['info']['formName'] if n.isdigit())
                      ) for k, v in registrations.items()]

        # self.registration_list = registration_list
        return json.dumps(registration_list)

    def get_attachment_list(self, survey_id, registration_id):
        """
        Return a list of objects belonging to a specific registration
        :param survey_id: An int value to represent the form e.g 7
        :param registration_id: An int value to represent which registration is in qtn e.g e213424jfsdkfh234
        :return:
        """
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket)
        blobs = bucket.list_blobs(prefix=f'attachments/{survey_id}/{registration_id if registration_id else ""}')
        images = {}
        for blob in blobs:
            images[blob.name] = blob.content_type  # Future: Other detail neccessary for front end i.v.m type

        if images:
            # self.images = images
            return images
        else:
            abort(Response(status=404, response=f"No registrations found using: {survey_id} and {registration_id}"))

    def get_images(self, survey_id, registration_id):
        """
        Retrieves a list single image of a file to a temporary directory
        """
        images = self.get_attachment_list(survey_id, registration_id)
        logger.warning(f'Images collection: {images}')
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket)

        location = f"{tempfile.gettempdir()}/images/{self.request_id}/{registration_id if registration_id else survey_id}/"
        logger.warning(location)
        try:
            os.makedirs(location)
        except FileExistsError:
            pass

        for key in images:
            mime_type = images[key]
            blob = bucket.blob(key)
            logger.warning(f'Downloading {blob.name} to {location}')
            blob.download_to_filename(
                f'{location}/{survey_id}-{registration_id if registration_id else ""}-{blob.name.split("/")[-1]}'
                f'{mimetypes.guess_extension(mime_type)}'
            )

        return location

    @staticmethod
    def clean_images(location):
        logger.warning(f'Cleanup {location}')
        try:
            shutil.rmtree(location)
        except OSError as e:
            logger.error(f'Error: {e.filename} - {e.strerror}')

    @staticmethod
    def zip_image_dir(directory, zip_file_name):
        """
        Compress a directory (ZIP file).
        """
        if os.path.exists(directory):
            batch_images_file_archive = zipfile.ZipFile(zip_file_name, 'w', zipfile.ZIP_DEFLATED)

            rootdir = os.path.basename(directory)

            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    parentpath = os.path.relpath(filepath, directory)
                    arcname = os.path.join(rootdir, parentpath)
                    batch_images_file_archive.write(filepath, arcname)
            batch_images_file_archive.close()

    def get_registrations_images_archive(self, survey_id):
        """
        Returns all registration images in an archief
        :param survey_id: A form or survey ID
        :return:
        """
        location = self.get_images(survey_id, registration_id=False)
        images_file = f"{tempfile.gettempdir()}/img-{self.request_id}.zip"

        self.zip_image_dir(location, images_file)
        self.clean_images(location)
        return images_file

    def get_single_registration_images_archive(self, survey_id, registration_id):
        """
        Download a Zip file archive for a single registration
        :return:
        """
        location = self.get_images(survey_id, registration_id)
        images_file = f"{tempfile.gettempdir()}/{self.request_id}/img-{registration_id}.zip"
        os.makedirs(os.path.dirname(images_file))

        self.zip_image_dir(location, images_file)
        self.clean_images(location)
        return images_file

    def has_registration_images(self, view_id):
        """
        Get a list of Registrations with an image saved in the storage
        :return:
        """
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket)
        list_blobs = list(bucket.list_blobs(prefix=f'attachments/{view_id}', max_results=1))
        return True if list_blobs else False

    def get_survey_forms_list(self):
        """
        Return all forms available
        :return:
        """
        forms_list = get_batch_registrations(self.bucket, 'surveys')
        forms = {}

        if not forms_list:
            abort(Response(status=404, response="No registrations found"))

        for key, value in forms_list.items():
            forms[key] = []
            for form in value:
                forms[key].append(dict(survey_id=form['properties']['view_id'], name=form['properties']['label_text'],
                                       has_images=self.has_registration_images(form['properties']['view_id']),
                                       description_text=form['properties']['description_text']
                                       if 'description_text' in form['properties'].keys() else ''))
        return json.dumps(forms)


def get_registrations_as_csv(survey_id):
    """
    This aims to create a csv file from all
    the registrations that have been downloaded
    """
    store_client = storage.Client()
    nonce_bucket = store_client.get_bucket(config.NONCE_BUCKET)
    nonce = str(uuid.uuid4())
    nonce_blob = nonce_bucket.blob(f'{nonce}.csv')
    registration_instance = Registration(bucket=config.BUCKET)
    nonce_blob.upload_from_string(registration_instance.get_csv(survey_id), content_type="text/csv")
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = datastore.Entity(key=downloads_key)
    downloads.update({
        'created': datetime.datetime.now(),
        'blob_name': f'{nonce}.csv',
        'headers': {
            "Content-Type": "text/csv",
            "Content-Disposition": 'attachment; filename="~/blobs.csv"'
        }
    })
    db_client.put(downloads)
    return Response(json.dumps({'nonce': downloads.key.id_or_name, "mime_type": "text/csv"}),
                    headers={
                        'Content-Type': 'application/json'
                    })


def get_registrations_as_zip(survey_id):
    """
    This aims to create a csv zip file from all
    the registrations that have been downloaded
    """
    store_client = storage.Client()
    nonce_bucket = store_client.get_bucket(config.NONCE_BUCKET)
    nonce = str(uuid.uuid4())
    nonce_blob = nonce_bucket.blob(f'{nonce}.zip')
    registration_instance = Registration(bucket=config.BUCKET)
    zip_file_name = registration_instance.get_zip(survey_id)
    nonce_blob.upload_from_filename(zip_file_name, content_type="application/zip")
    os.remove(zip_file_name)
    os.removedirs(os.path.dirname(zip_file_name))
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = datastore.Entity(key=downloads_key)
    downloads.update({
        'created': datetime.datetime.utcnow(),
        'blob_name': f'{nonce}.zip',
        'headers': {
            "Content-Type": "application/zip",
            "Content-Disposition": 'attachment; filename="~/surveys.zip"'
        }
    })
    db_client.put(downloads)
    return Response(json.dumps({'nonce': downloads.key.id_or_name, "mime_type": "application/zip"}),
                    headers={
                        'Content-Type': 'application/json'
                    })


def get_registrations_list(survey_id):
    """
    Return a list of registrations
    :return:
    """
    registration_instance = Registration(bucket=config.BUCKET)
    return Response(
        registration_instance.get_list(survey_id),
        headers={
            "Content-Type": "application/json",
        }
    )


def get_forms_list():
    """
    Return a list of registrations
    :return:
    """
    registration_instance = Registration(bucket=config.BUCKET)
    return Response(
        registration_instance.get_survey_forms_list(),
        headers={
            "Content-Type": "application/json",
        }
    )


def get_registrations_attachments(survey_id, registration_id):
    """
    Get a list of attachments per registration
    :param survey_id: An integer that represents a form or a survey eg e34njedjsfh4jk5
    :param registration_id: An integer that represents a Registration e.g => 7
    :return:
    """
    registration_instance = Registration(bucket=config.BUCKET)
    return registration_instance.get_attachment_list(survey_id, registration_id)


def get_single_images_archive(survey_id, registration_id):
    """
    Download a zip archive of a single registration
    :param survey_id: An integer that represents a form or a survey eg e34njedjsfh4jk5
    :param registration_id: An integer that represents a Registration e.g => 7
    :return:
    """
    store_client = storage.Client()
    nonce_bucket = store_client.get_bucket(config.NONCE_BUCKET)
    nonce = str(uuid.uuid4())
    nonce_blob = nonce_bucket.blob(f'{nonce}.zip')
    logger.warning('Single image archive before generation')
    registration_instance = Registration(bucket=config.BUCKET)
    zip_filename = registration_instance.get_single_registration_images_archive(survey_id, registration_id)
    nonce_blob.upload_from_filename(zip_filename, content_type="application/zip")
    os.remove(zip_filename)
    os.removedirs(os.path.dirname(zip_filename))
    logger.warning('Single image archive generated')
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = datastore.Entity(key=downloads_key)
    downloads.update({
        'created': datetime.datetime.utcnow(),
        'blob_name': f'{nonce}.zip',
        'headers': {
            "Content-Type": "application/zip",
            "Content-Disposition":
                f'attachment; filename="image-{survey_id}-{registration_id}.zip"'
        }
    })
    db_client.put(downloads)
    logger.warning('Single image archive nonce stored')
    return Response(json.dumps({'nonce': downloads.key.id_or_name, "mime_type": "application/json"}),
                    headers={
                        'Content-Type': 'application/json'
                    })


def get_surveys_nonce(nonce):
    """
    Perform actual download operation of already prepared data
    :param nonce:
    :return:
    """
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = db_client.get(downloads_key)
    if downloads:
        try:
            return redirect(f'https://storage.googleapis.com/{config.NONCE_BUCKET}/{downloads["blob_name"]}')
        finally:
            db_client.delete(downloads_key)

            def cleanup():
                time.sleep(15)
                store_client = storage.Client()
                nonce_bucket = store_client.get_bucket(config.NONCE_BUCKET)
                nonce_bucket.delete_blob(downloads['blob_name'])

            threading.Thread(target=cleanup).start()

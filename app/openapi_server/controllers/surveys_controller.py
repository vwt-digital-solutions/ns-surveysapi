import json
import logging
import os
import uuid
import tempfile
import zipfile
import mimetypes
import datetime
import time

import config

from flask import jsonify
from flask import Response, send_file, redirect

from google.cloud import storage, datastore
from settings import get_batch_registrations, create_csv_file, create_zip_file
from exceptions import AttachmentsNotFound, RegistrationsNotFound

logger = logging.getLogger(__name__)

if hasattr(config, 'NONCE_BUCKET'):
    NONCE_BUCKET = config.NONCE_BUCKET
else:
    NONCE_BUCKET = 'vwt-d-gew1-ns-surveys-nonce-stg'

class Registration:
    """
    A class based func that intends to capsule functionality to get
    all photos of a specific registration
    """

    def __init__(self, bucket=None, survey_id=None, serial_number=None):
        self.survey_id = survey_id
        self.serial_number = serial_number

        self.registration_list = dict()
        self.registrations = dict()

        self.bucket = bucket
        self.photos = []

        self.storage_client = storage.Client()
        self.storage = self.storage_client.get_bucket(self.bucket)
        self.images = dict()
        self.registrations_with_images = self.get_registration_with_image()

    def get_registrations(self, prefix):
        """
        Get all registrations
        :return:
        """
        batch = get_batch_registrations(self.bucket, prefix)
        registrations = {}
        try:
            if batch['elements']:
                for registration in batch['elements']:
                    registrations[registration["meta"]["serialNumber"]] = registration
                self.registrations = registrations
                return self.registrations
            else:
                raise RegistrationsNotFound('Empty Folder', f'There are no registrations for this folder: {prefix}')
        except Exception as error:
            raise RegistrationsNotFound('Processing error', error)

    def get_csv(self, survey_id):
        """
        Return a csv file of all registrations
        :return:
        """
        self.get_registrations(prefix=survey_id)
        return create_csv_file(self.registrations)

    def get_zip(self, survey_id):
        """
        Return a zip file of all registrations

        :return:
        """
        self.get_registrations(prefix=survey_id)
        return create_zip_file(self.registrations)

    def get_list(self, survey_id):
        """
        Get a list of all registrations meta information
        :return:
        """
        self.get_registrations(prefix=survey_id)
        registration_list = {}
        for key in self.registrations:
            registration_list[self.registrations[key]['info']['formId']] = \
                [dict(serial_number=k,
                      date_of_registration=int(v['meta']['registrationDate']),
                      site_location=v['data']['tMNLLocationID']['CITY'] if 'tMNLLocationID' in v[
                          'data'].keys() else '',
                      site_id=v['data']['siteID'] if 'siteID' in v['data'].keys() else
                      ''.join(n for n in v['info']['formName'] if n.isdigit())
                      ) for k, v in self.registrations.items()]

        self.registration_list = registration_list
        return json.dumps(registration_list)

    def get_attachment_list(self, survey_id, registration_id):
        """
        Return a list of objects belonging to a specific registration
        :param survey_id: An int value to represent the form e.g 7
        :param registration_id: An int value to represent which registration is in qtn e.g e213424jfsdkfh234
        :return:
        """
        storage_client = self.storage_client
        bucket = storage_client.get_bucket(self.bucket)
        blobs = bucket.list_blobs(prefix=f'attachments/{survey_id}/{registration_id if registration_id else ""}')
        images = {}
        for blob in blobs:
            images[blob.name] = blob.content_type  # Future: Other detail neccessary for front end i.v.m type

        try:
            if images:
                self.images = images
                return jsonify(images)
            else:
                raise AttachmentsNotFound(
                    'Not Found', f'There were no Registration images found matching the '
                    f'following id: {survey_id} and registration id: {registration_id}')
        except Exception as error:
            return jsonify({error.message: error.error})

    def get_images(self, survey_id, registration_id):
        """
        Retrieves a list single image of a file to a temporary directory
        """
        self.get_attachment_list(survey_id, registration_id)
        storage_client = self.storage_client
        bucket = storage_client.get_bucket(self.bucket)

        for key, value in self.images.items():
            blob = bucket.blob(key)
            location = f"{tempfile.gettempdir()}/images/{registration_id if registration_id else survey_id}/"
            try:
                os.makedirs(location)
            except FileExistsError:
                pass
            blob.download_to_filename(
                f'{location}/{survey_id}-{registration_id if registration_id else ""}-{blob.name.split("/")[-1]}'
                f'{mimetypes.guess_extension(value)}'
            )

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
        self.get_images(survey_id, registration_id=False)
        location = f"{tempfile.gettempdir()}/images/{survey_id}"
        images_file = f"{tempfile.gettempdir()}/img-{survey_id}.zip"

        self.zip_image_dir(location, images_file)
        return images_file

    def get_single_registration_images_archive(self, survey_id, registration_id):
        """
        Download a Zip file archive for a single registration
        :return:
        """
        self.get_images(survey_id, registration_id)
        location = f"{tempfile.gettempdir()}/images/{registration_id}/"
        images_file = f"{tempfile.gettempdir()}/img-{registration_id}.zip"

        self.zip_image_dir(location, images_file)
        return images_file

    def get_registration_with_image(self):
        """
        Get a list of Registrations with an image saved in the storage
        :return:
        """
        lst_blobs = self.storage.list_blobs(prefix='attachments/')
        return list(set([blob.name.split('/')[1] for blob in lst_blobs]))

    def get_survey_forms_list(self):
        """
        Return all forms available
        :return:
        """
        forms_list = get_batch_registrations(self.bucket, 'surveys')
        forms = {}

        for key, value in forms_list.items():
            forms[key] = []
            for form in value:
                forms[key].append(dict(survey_id=form['properties']['view_id'], name=form['properties']['label_text'],
                                       has_images=form['properties']['view_id'] in self.registrations_with_images,
                                       description_text=
                                       form['properties']['description_text']
                                       if 'description_text' in form['properties'].keys() else ''))
        return json.dumps(forms)


registration_instance = Registration(bucket=config.BUCKET)


def get_registrations_as_csv(survey_id):
    """
    This aims to create a csv file from all
    the registrations that have been downloaded
    """
    store_client = storage.Client()
    nonce_bucket = store_client.get_bucket(NONCE_BUCKET)
    nonce = str(uuid.uuid4())
    nonce_blob = nonce_bucket.blob(nonce)
    nonce_blob.upload_from_string(registration_instance.get_csv(survey_id), content_type="text/csv")
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = datastore.Entity(key=downloads_key)
    downloads.update({
        'created': datetime.datetime.now(),
        'headers': {
            "Content-Type": "text/csv",
            "Content-Disposition": 'attachment; filename="~/blobs.csv"'
            # "Authorization": ''
        }
    })
    db_client.put(downloads)
    return Response(downloads.key.id_or_name,
                    headers={
                        'Content-Type': 'text/plain'
                    })
    # return Response(
    #     registration_instance.get_csv(survey_id),
    #     headers={
    #         "Content-Type": "text/csv",
    #         "Content-Disposition": 'attachment; filename="~/blobs.csv"',
    #         "Authorization": ''
    #     },
    # )


def get_registrations_as_zip(survey_id):
    """
    This aims to create a csv zip file from all
    the registrations that have been downloaded
    """
    store_client = storage.Client()
    nonce_bucket = store_client.get_bucket(NONCE_BUCKET)
    nonce = str(uuid.uuid4())
    nonce_blob = nonce_bucket.blob(nonce)
    nonce_blob.upload_from_filename(registration_instance.get_zip(survey_id), content_type="application/zip")
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = datastore.Entity(key=downloads_key)
    downloads.update({
        'created': datetime.datetime.utcnow(),
        'headers': {
            "Content-Type": "application/zip",
            "Content-Disposition": 'attachment; filename="~/surveys.zip"'
            # "Authorization": ''
        }
    })
    db_client.put(downloads)
    return Response(downloads.key.id_or_name,
                    headers={
                        'Content-Type': 'text/plain'
                    })
    # try:
    #     return send_file(
    #         registration_instance.get_zip(survey_id),
    #         mimetype='application/zip',
    #         as_attachment=True,
    #         attachment_filename='surveys.zip'
    #     )
    # except Exception as e:
    #     return jsonify({'Important': f'{e}'})


def get_registrations_list(survey_id):
    """
    Return a list of registrations
    :return:
    """
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
    return registration_instance.get_attachment_list(survey_id, registration_id)


def get_single_images_archive(survey_id, registration_id):
    """
    Download a zip archive of a single registration
    :param survey_id: An integer that represents a form or a survey eg e34njedjsfh4jk5
    :param registration_id: An integer that represents a Registration e.g => 7
    :return:
    """
    store_client = storage.Client()
    nonce_bucket = store_client.get_bucket(NONCE_BUCKET)
    nonce = str(uuid.uuid4())
    nonce_blob = nonce_bucket.blob(nonce)
    nonce_blob.upload_from_filename(
        registration_instance.get_single_registration_images_archive(survey_id, registration_id), content_type="application/zip")
    db_client = datastore.Client()
    downloads_key = db_client.key('Downloads', nonce)
    downloads = datastore.Entity(key=downloads_key)
    downloads.update({
        'created': datetime.datetime.utcnow(),
        'headers': {
            "Content-Type": "application/zip",
            "Content-Disposition":
                f'attachment; filename="image-{survey_id}-{registration_id}.zip"'
            # "Authorization": ''
        }
    })
    db_client.put(downloads)
    return Response(downloads.key.id_or_name,
                    headers={
                        'Content-Type': 'text/plain'
                    })
    # return Response(
    #     open(registration_instance.get_single_registration_images_archive(survey_id, registration_id), 'rb').read(),
    #     headers={
    #         'Content-Type': "application/zip",
    #         'Transfer-Encoding': 'chunked',
    #         'Content-Disposition': f'attachment;filename=image-{survey_id}-{registration_id}.zip',
    #     }
    # )


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
        # delta = datetime.datetime.now() - downloads['created']
        # nonce_blob = nonce_bucket.blob(nonce)
        try:
            return redirect(f'https://storage.cloud.google.com/vwt-d-gew1-ns-surveys-nonce-stg/{nonce}')
            # if delta.seconds < 10:
            #     payload = nonce_blob.download_as_string()
            #     headers = downloads['headers']
                # nonce_bucket.delete_blob(nonce_blob)
                # db_client.delete(downloads_key)
                # rsp = Response(payload, headers)
                # return rsp
            # else:
            #     logger.error(f'Nonce too old {nonce}')
        finally:
            db_client.delete(downloads_key)
            # time.sleep(5)
            # store_client = storage.Client()
            # nonce_bucket = store_client.get_bucket(NONCE_BUCKET)
            # nonce_bucket.delete_blob(nonce)



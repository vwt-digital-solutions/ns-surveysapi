import os
import logging
import re
import zipfile
import csv
from collections import OrderedDict
from tempfile import gettempdir

import pandas as pd
import json

from google.cloud import storage

logger = logging.getLogger(__name__)

CSV_DELIMITER = ';'


def get_label(key, value):
    """
    A long camelCased label to a readable sentence
    :param key:
    :return:
    """
    label = re.split('(?=[A-Z])', key)
    return ''.join(word + ' ' for word in label).capitalize()


def flatten_dict(value):
    """
    Flattens a dictionary object with (nested) list values. For example:
    a_registration:  another_list_registration: {
                    _tt667dsfs: [ x: { y: fs56df64sd3} ]
                    }

    => { a_registration.another_list_registration._tt667dsfs.x.y: 'fs56df64sd3' }
    :param value:
    :return:
    """
    flat = dict()
    for key, value in value.items():
        if isinstance(value, list):
            torn = dict()
            for index, x in enumerate(value):
                torn[f"items__{index}"] = pd.io.json.json_normalize(
                    x, sep="."
                ).to_dict(orient="records")[0]
                flat[key] = torn
        else:
            flat[key] = value
    return flat


def create_csv_file(surveys):
    """
    Creates the csv file that gets downloaded exclusively data on request.
    And flatten sub question to a 2 dimensional data representation
    ** for example:
    locationSearch: {
        mast: 'x3srrR'
        typea: 'A type'
        another: [ anotherList: {
                    _tt667dsfs: fs56df64sd3}
                    ]
        }
    => locationSearch.mast: 'x3srrR' ...
    => locationSearch.another.anotherList._tt667dsfs: 'fs56df64sd3' ...
    :param surveys:
    :return:
    """
    list_of_registrations = []
    for k, v in surveys.items():
        data = dict()
        for key, value in v["data"].items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        data[key] = pd.DataFrame(value).to_dict(orient="records")
                    else:
                        data[key] = ' | '.join(value)
            elif isinstance(value, dict):
                data[key] = flatten_dict(value)
            else:
                data[key] = value
        list_of_registrations.append(data)

    df = pd.io.json.json_normalize(list_of_registrations, sep=".")
    return df.to_csv(sep=CSV_DELIMITER)


def create_subforms(value, reference, survey, list_of_subforms):
    """
    Flattens a dictionary object OR creates a subform with (nested) list values. For example:
    a_registration:  another_list_registration: {
                    _tt667dsfs: [ x: { y: fs56df64sd3} ]
                    }

    => This in a separate CSV { a_registration.another_list_registration._tt667dsfs.x.y: 'fs56df64sd3' }
    :param list_of_subforms:
    :param survey:
    :param reference:
    :param value:
    :return:
    """

    toadd_data = OrderedDict()
    for key, value in value.items():
        if isinstance(value, list):
            if value.__len__() > 0:
                for index, item in enumerate(value):
                    if isinstance(item, str):
                        toadd_data[key] = item
                    else:
                        toadd_data[f"{index}_{key}"] = pd.io.json.json_normalize(item, sep=".").to_dict(
                            orient="records")[0]
            else:
                toadd_data[key] = ''

        else:
            toadd_data.update({key: value})

    if toadd_data:
        toadd_data = pd.io.json.json_normalize(toadd_data).to_dict(orient='records')[0]
        toadd_field_names = list(toadd_data.keys())

        # Serial number on first column
        toadd_field_names = ['serialNumber', *toadd_field_names]
        toadd_data = {'serialNumber': survey, **toadd_data}

        should_write_header = False

        if reference in list_of_subforms:
            # Read header to check headers are the same
            previous_reader = csv.DictReader(open(f'{gettempdir()}/{reference}.header.csv', "r"), delimiter=CSV_DELIMITER)
            combined_field_names = [*previous_reader.fieldnames]

            for toadd_field_name in toadd_field_names:
                if toadd_field_name not in combined_field_names:
                    combined_field_names.append(toadd_field_name)
                    should_write_header = True
            sub_forms_data_file = open(f"{gettempdir()}/{reference}.data.csv", "a")
        else:
            combined_field_names = toadd_field_names
            sub_forms_data_file = open(f"{gettempdir()}/{reference}.data.csv", "w")
            list_of_subforms.append(reference)
            should_write_header = True

        if should_write_header:
            # (Re)write header
            header_writer = csv.DictWriter(open(f'{gettempdir()}/{reference}.header.csv', "w"),
                                           fieldnames=combined_field_names, delimiter=CSV_DELIMITER)
            header_writer.writeheader()

        # Add content to CSV and file to list of sub forms
        writer = csv.DictWriter(sub_forms_data_file, fieldnames=combined_field_names, delimiter=CSV_DELIMITER)
        writer.writerow(toadd_data)
        sub_forms_data_file.close()


def create_zip_file(surveys, request_id):
    """
    Creates the zip file that gets downloaded exclusively data on request.
    And flatten sub question to a 2 dimensional data representation
    ** for example:
    locationSearch: {
        mast: 'x3srrR'
        typea: 'A type'
        another: [ anotherList: {
                    _tt667dsfs: fs56df64sd3}
                    ]
        }
    => locationSearch.mast: 'x3srrR' ...
    => locationSearch.another.anotherList._tt667dsfs: 'fs56df64sd3' ...
    :param surveys:
    :param: request_id
    :return:
    """
    surveys_zip_directory = f'{gettempdir()}/{request_id}'
    try:
        os.mkdir(surveys_zip_directory)
    except OSError:
        pass
    surveys_zip_location = f"{surveys_zip_directory}/surveys.zip"
    surveys_zip = zipfile.ZipFile(surveys_zip_location, "w")
    list_of_registrations = []
    list_of_subforms = []
    for k, v in surveys.items():
        data = {'serialNumber': k}
        for key, value in v["data"].items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        create_subforms(item, key, k, list_of_subforms)
            elif isinstance(value, dict):
                # Checks if all values have a uniform data type. These should not
                # be made sub forms e.g 'tMNLLocationID'
                if set(list(map(type, value.values()))).__len__() == 1:
                    data[key] = value
                else:
                    create_subforms(value, key, k, list_of_subforms)
            else:
                data[key] = value
        list_of_registrations.append(data)

    df = pd.io.json.json_normalize(list_of_registrations, sep=".")
    df.to_csv(f"{gettempdir()}/surveys_main.csv", index=None, sep=CSV_DELIMITER)

    surveys_zip.write(f"{gettempdir()}/surveys_main.csv", 'surveys_main.csv')
    for subform_name in list_of_subforms:
        combined_subform_csv = open(f"{gettempdir()}/{subform_name}.csv", "w")
        combined_subform_csv.write(open(f"{gettempdir()}/{subform_name}.header.csv", "r").read())
        combined_subform_csv.write(open(f"{gettempdir()}/{subform_name}.data.csv", "r").read())
        combined_subform_csv.close()
        surveys_zip.write(f"{gettempdir()}/{subform_name}.csv", f"{subform_name}.csv")
    surveys_zip.close()

    return surveys_zip_location


def get_batch_registrations(bucket_name, prefix=None):
    """
        lists all the surveys in the bucket
        - Using the a stringgetter() - batch them into a single dict file
    """
    storage_client = storage.Client(
        os.environ.get("PROJECT", "Specified environment variable is not set.")
    )

    bucket = storage_client.get_bucket(bucket_name)

    if prefix == 'surveys':
        latest = list(bucket.list_blobs(prefix=f'source/{prefix}/folders'))[-1].download_as_string()
    else:
        latest = list(bucket.list_blobs(prefix=f'source/registrations/{prefix}'))[-1].download_as_string()

    return json.loads(latest)

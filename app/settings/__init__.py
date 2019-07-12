import itertools
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
    return df.to_csv(sep = ";")


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

    file_rw_ready = OrderedDict()
    header_rows_catalogue = {}
    for key, value in value.items():
        if isinstance(value, list):
            if value.__len__() > 0:
                for index, item in enumerate(value):
                    if isinstance(item, str):
                        file_rw_ready[key] = item
                    else:
                        file_rw_ready[f"{index}_{key}"] = pd.io.json.json_normalize(item, sep=".").to_dict(
                            orient="records")[0]
            else:
                file_rw_ready[key] = ''

        else:
            file_rw_ready.update({key: value})

    file_rw_ready = pd.io.json.json_normalize(file_rw_ready).to_dict(orient='records')[0]
    field_names = list(file_rw_ready.keys())

    # Serial number on first column
    fields = ['serialNumber', *field_names]
    file_rw_ready = {'serialNumber': survey, **file_rw_ready}

    # Add to csv or write a new file
    sub_forms_file = open(f"{gettempdir()}/{reference}.csv", "a") if reference in list_of_subforms else \
        open(f"{gettempdir()}/{reference}.csv", "w")

    # Add content to CSV and file to list of sub forms
    writer = csv.DictWriter(sub_forms_file, fieldnames=fields)
    if reference not in list_of_subforms:
        writer.writeheader()
        list_of_subforms.append(reference)

    # Read header to check headers are the same
    reader = csv.DictReader(open(f'{gettempdir()}/{reference}.csv'))
    file_length = [x for x in reader].__len__()
    if not reader.fieldnames == fields and file_length > 0:
        # Fields missing in original csv file
        missing_fields = list(itertools.filterfalse(set(reader.fieldnames).__contains__, writer.fieldnames))

        # Overwrite and BackUp fields
        back_up = [*writer.fieldnames]
        writer.fieldnames.clear()
        writer.fieldnames = [*reader.fieldnames]

        # Fields missing after overwrite
        lost_initial_fields = list(itertools.filterfalse(set(writer.fieldnames).__contains__, back_up))
        vals = ('0', '1', '2', '3', '5', '6', '7', '8', '9', '10')

        missing = []
        missing_after_overwrite = []
        for fld in missing_fields:
            if not fld.__str__().startswith(vals):
                missing.append(fld)

        for fld in lost_initial_fields:
            missing_after_overwrite.append(fld)

        def write_field_names(missed, after_overwrite=None):
            """
            Write fields to the file that are missing
            :param after_overwrite:
            :param missed:
            """
            if missed:
                for field in missed:
                    # Get the index of the missing field
                    if field not in reader.fieldnames or after_overwrite:
                        idx = back_up.index(field)
                        writer.fieldnames.insert(idx, field)
                    else:
                        idx = reader.fieldnames.index(field)
                        writer.fieldnames.insert(idx, field)

        write_field_names(missing)
        write_field_names(missing_after_overwrite, after_overwrite=True)

    writer.writerow(file_rw_ready)
    sub_forms_file.close()


def create_zip_file(surveys):
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
    :return:
    """
    surveys_zip_location = f"{gettempdir()}/surveys.zip"
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
    df.to_csv(f"{gettempdir()}/surveys_main.csv", index=None, sep=";")

    surveys_zip.write(f"{gettempdir()}/surveys_main.csv", 'surveys_main.csv')
    for subform_name in list_of_subforms:
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

    latest = list(bucket.list_blobs(prefix=f'source/{prefix}/folders'))[
        -1].download_as_string() if prefix == 'surveys' else \
        list(bucket.list_blobs(prefix=f'source/registrations/{prefix}'))[-1].download_as_string()
    logger.info("Downloaded Survey String", latest)
    return json.loads(latest)
